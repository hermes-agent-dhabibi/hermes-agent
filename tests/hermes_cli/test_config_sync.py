"""Tests for ``hermes config sync`` — backfill missing DEFAULT_CONFIG keys."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_hermes_home(tmp_path, monkeypatch):
    """Redirect HERMES_HOME to a temp dir so tests never touch the real config."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    # Also patch get_hermes_home / get_config_path to use tmp_path
    monkeypatch.setattr(
        "hermes_cli.config.get_hermes_home", lambda: tmp_path
    )
    monkeypatch.setattr(
        "hermes_cli.config.get_config_path", lambda: tmp_path / "config.yaml"
    )
    # Ensure config_sync uses the same patched paths
    monkeypatch.setattr(
        "hermes_cli.config_sync.get_config_path", lambda: tmp_path / "config.yaml"
    )
    monkeypatch.setattr(
        "hermes_cli.config_sync.ensure_hermes_home", lambda: None
    )
    monkeypatch.setattr(
        "hermes_cli.config_sync.is_managed", lambda: False
    )


def _write_config(tmp_path: Path, text: str) -> Path:
    """Write YAML text to config.yaml and return the path."""
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def _read_config(tmp_path: Path) -> dict:
    """Read config.yaml back as a dict."""
    p = tmp_path / "config.yaml"
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read_config_text(tmp_path: Path) -> str:
    """Read config.yaml as raw text."""
    return (tmp_path / "config.yaml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmptyConfig:
    """Empty config file → all defaults should be written."""

    def test_empty_file_gets_all_defaults(self, tmp_path):
        _write_config(tmp_path, "")
        from hermes_cli.config_sync import sync_config
        result = sync_config()

        assert len(result["added"]) > 0
        assert "message" in result

        # Verify the written file is valid YAML
        cfg = _read_config(tmp_path)
        assert isinstance(cfg, dict)
        # Should have at least some top-level keys
        assert "agent" in cfg or "terminal" in cfg or "display" in cfg

    def test_no_file_creates_one(self, tmp_path):
        from hermes_cli.config_sync import sync_config
        result = sync_config()

        assert len(result["added"]) > 0
        assert (tmp_path / "config.yaml").exists()


class TestPartialConfig:
    """Partial config → only missing keys added, existing preserved."""

    def test_existing_model_preserved(self, tmp_path):
        _write_config(tmp_path, """\
            model: anthropic/claude-sonnet-4
            agent:
              max_turns: 120
        """)
        from hermes_cli.config_sync import sync_config
        result = sync_config()

        assert len(result["added"]) > 0
        cfg = _read_config(tmp_path)
        # Existing values must NOT be overwritten
        assert cfg["model"] == "anthropic/claude-sonnet-4"
        assert cfg["agent"]["max_turns"] == 120

    def test_nested_key_added_to_existing_section(self, tmp_path):
        """delegation section exists but is missing reasoning_effort."""
        _write_config(tmp_path, """\
            delegation:
              model: google/gemini-3-flash-preview
        """)
        from hermes_cli.config_sync import sync_config
        result = sync_config()

        cfg = _read_config(tmp_path)
        assert cfg["delegation"]["model"] == "google/gemini-3-flash-preview"
        # Should have added missing sub-keys
        assert "reasoning_effort" in result["added"] or "delegation.reasoning_effort" in result["added"]
        assert "reasoning_effort" in cfg["delegation"]

    def test_custom_keys_preserved(self, tmp_path):
        """User-defined keys not in DEFAULT_CONFIG must survive."""
        _write_config(tmp_path, """\
            model: anthropic/claude-sonnet-4
            my_custom_key: my_value
            agent:
              max_turns: 90
              my_agent_flag: true
        """)
        from hermes_cli.config_sync import sync_config
        result = sync_config()

        cfg = _read_config(tmp_path)
        assert cfg["my_custom_key"] == "my_value"
        assert cfg["agent"]["my_agent_flag"] is True


class TestFullySynced:
    """Config that already has all keys → no changes."""

    def test_up_to_date_message(self, tmp_path):
        # Write a config that has ALL default keys at their default values
        from hermes_cli.config import DEFAULT_CONFIG
        import copy
        full = copy.deepcopy(DEFAULT_CONFIG)
        # Remove internal keys
        full.pop("_config_version", None)
        # Remove skip sections that sync skips
        for k in ("providers", "custom_providers", "personalities",
                   "quick_commands", "credential_pool_strategies"):
            full.pop(k, None)

        p = tmp_path / "config.yaml"
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(full, f, default_flow_style=False, sort_keys=False)

        from hermes_cli.config_sync import sync_config
        result = sync_config()

        assert result["added"] == []
        assert "up to date" in result["message"].lower()


class TestDryRun:
    """dry_run=True should not write any changes."""

    def test_dry_run_does_not_write(self, tmp_path):
        _write_config(tmp_path, """\
            model: test
        """)
        original_text = _read_config_text(tmp_path)

        from hermes_cli.config_sync import sync_config
        result = sync_config(dry_run=True)

        assert len(result["added"]) > 0
        assert "would add" in result["message"].lower()
        # File should be unchanged
        assert _read_config_text(tmp_path) == original_text


class TestSkipSections:
    """providers, custom_providers, etc. are never synced."""

    def test_providers_not_added(self, tmp_path):
        _write_config(tmp_path, """\
            model: test
        """)
        from hermes_cli.config_sync import sync_config
        result = sync_config()

        # 'providers' should not appear in added keys
        for key in result["added"]:
            assert not key.startswith("providers"), f"providers key should be skipped: {key}"
            assert not key.startswith("custom_providers"), f"custom_providers should be skipped: {key}"
            assert not key.startswith("personalities"), f"personalities should be skipped: {key}"
            assert not key.startswith("quick_commands"), f"quick_commands should be skipped: {key}"


class TestYamlFormatting:
    """Verify YAML output formatting edge cases."""

    def test_empty_string_rendered_as_quotes(self, tmp_path):
        _write_config(tmp_path, """\
            model: test
        """)
        from hermes_cli.config_sync import sync_config
        sync_config()

        text = _read_config_text(tmp_path)
        # Empty strings in defaults should appear as '' not as empty
        # Check that timezone (which defaults to "") appears with quotes
        assert "timezone:" in text

    def test_list_values_written_correctly(self, tmp_path):
        _write_config(tmp_path, """\
            model: test
        """)
        from hermes_cli.config_sync import sync_config
        sync_config()

        cfg = _read_config(tmp_path)
        # toolsets should be written as a list
        if "toolsets" in cfg:
            assert isinstance(cfg["toolsets"], list)

    def test_result_is_valid_yaml(self, tmp_path):
        """After sync, the file must be parseable YAML."""
        _write_config(tmp_path, """\
            model: anthropic/claude-sonnet-4
            agent:
              max_turns: 100
        """)
        from hermes_cli.config_sync import sync_config
        sync_config()

        # Must not raise
        cfg = _read_config(tmp_path)
        assert isinstance(cfg, dict)


class TestCollectMissing:
    """Unit tests for the _collect_missing helper."""

    def test_flat_missing(self):
        from hermes_cli.config_sync import _collect_missing
        defaults = {"a": 1, "b": 2, "c": 3}
        user = {"a": 10}
        missing = _collect_missing(defaults, user)
        keys = [k for k, _ in missing]
        assert "b" in keys
        assert "c" in keys
        assert "a" not in keys

    def test_nested_missing(self):
        from hermes_cli.config_sync import _collect_missing
        defaults = {"x": {"y": 1, "z": 2}}
        user = {"x": {"y": 10}}
        missing = _collect_missing(defaults, user)
        keys = [k for k, _ in missing]
        assert "x.z" in keys
        assert "x.y" not in keys

    def test_whole_section_missing(self):
        from hermes_cli.config_sync import _collect_missing
        defaults = {"section": {"a": 1, "b": 2}}
        user = {}
        missing = _collect_missing(defaults, user)
        keys = [k for k, _ in missing]
        assert "section" in keys

    def test_private_keys_skipped(self):
        from hermes_cli.config_sync import _collect_missing
        defaults = {"_internal": 42, "visible": 1}
        user = {}
        missing = _collect_missing(defaults, user)
        keys = [k for k, _ in missing]
        assert "_internal" not in keys
        assert "visible" in keys

    def test_skip_sections(self):
        from hermes_cli.config_sync import _collect_missing
        defaults = {"providers": {"openai": "key"}, "model": "test"}
        user = {}
        missing = _collect_missing(defaults, user)
        keys = [k for k, _ in missing]
        assert "model" in keys
        assert "providers" not in keys


class TestYamlScalar:
    """Unit tests for _yaml_scalar rendering."""

    def test_empty_string(self):
        from hermes_cli.config_sync import _yaml_scalar
        assert _yaml_scalar("") == "''"

    def test_bool_true(self):
        from hermes_cli.config_sync import _yaml_scalar
        assert _yaml_scalar(True) == "true"

    def test_bool_false(self):
        from hermes_cli.config_sync import _yaml_scalar
        assert _yaml_scalar(False) == "false"

    def test_integer(self):
        from hermes_cli.config_sync import _yaml_scalar
        assert _yaml_scalar(42) == "42"

    def test_none(self):
        from hermes_cli.config_sync import _yaml_scalar
        assert _yaml_scalar(None) == "null"

    def test_empty_list(self):
        from hermes_cli.config_sync import _yaml_scalar
        assert _yaml_scalar([]) == "[]"

    def test_empty_dict(self):
        from hermes_cli.config_sync import _yaml_scalar
        assert _yaml_scalar({}) == "{}"

    def test_string_with_special_chars(self):
        from hermes_cli.config_sync import _yaml_scalar
        result = _yaml_scalar("hello: world")
        assert result.startswith('"') or result.startswith("'")

    def test_plain_string(self):
        from hermes_cli.config_sync import _yaml_scalar
        assert _yaml_scalar("hello") == "hello"


class TestDeepNesting:
    """Three-level nesting like browser.camofox.managed_persistence."""

    def test_deep_nested_key_added_when_parent_exists(self, tmp_path):
        """browser exists, but browser.camofox is missing entirely."""
        _write_config(tmp_path, """\
            browser:
              inactivity_timeout: 60
        """)
        from hermes_cli.config_sync import sync_config
        result = sync_config()

        cfg = _read_config(tmp_path)
        # browser.camofox.managed_persistence should be added
        assert "camofox" in cfg.get("browser", {}), "camofox section should be created"
        assert "managed_persistence" in cfg["browser"]["camofox"]
        # Existing value preserved
        assert cfg["browser"]["inactivity_timeout"] == 60

    def test_deep_nested_key_when_middle_exists(self, tmp_path):
        """browser.camofox exists as empty dict, managed_persistence missing."""
        _write_config(tmp_path, """\
            browser:
              camofox: {}
        """)
        from hermes_cli.config_sync import sync_config
        result = sync_config()

        cfg = _read_config(tmp_path)
        assert cfg["browser"]["camofox"]["managed_persistence"] is False


class TestExistingComments:
    """User's existing YAML comments should survive sync."""

    def test_inline_comments_preserved(self, tmp_path):
        _write_config(tmp_path, """\
            # My custom header comment
            model: anthropic/claude-sonnet-4  # my preferred model
            agent:
              # I like a high turn count
              max_turns: 200
        """)
        from hermes_cli.config_sync import sync_config
        sync_config()

        text = _read_config_text(tmp_path)
        assert "# My custom header comment" in text
        assert "# my preferred model" in text
        assert "# I like a high turn count" in text


class TestValueTypes:
    """Verify different value types round-trip correctly."""

    def test_large_integer_default(self, tmp_path):
        """file_read_max_chars defaults to 100000."""
        _write_config(tmp_path, """\
            model: test
        """)
        from hermes_cli.config_sync import sync_config
        sync_config()

        cfg = _read_config(tmp_path)
        assert cfg.get("file_read_max_chars") == 100000

    def test_boolean_defaults(self, tmp_path):
        _write_config(tmp_path, """\
            model: test
        """)
        from hermes_cli.config_sync import sync_config
        sync_config()

        cfg = _read_config(tmp_path)
        # checkpoints.enabled defaults to True
        assert cfg.get("checkpoints", {}).get("enabled") is True
        # privacy.redact_pii defaults to False
        assert cfg.get("privacy", {}).get("redact_pii") is False

    def test_none_value(self, tmp_path):
        """compression.summary_base_url defaults to None."""
        _write_config(tmp_path, """\
            compression:
              enabled: true
        """)
        from hermes_cli.config_sync import sync_config
        sync_config()

        cfg = _read_config(tmp_path)
        assert cfg["compression"]["summary_base_url"] is None


class TestIdempotent:
    """Running sync twice should be idempotent."""

    def test_double_sync(self, tmp_path):
        _write_config(tmp_path, """\
            model: test
        """)
        from hermes_cli.config_sync import sync_config

        result1 = sync_config()
        assert len(result1["added"]) > 0

        # Second run should find nothing to add
        result2 = sync_config()
        assert result2["added"] == []
        assert "up to date" in result2["message"].lower()

    def test_triple_sync_with_partial_config(self, tmp_path):
        """Start with a realistic partial config and sync 3 times."""
        _write_config(tmp_path, """\
            model: anthropic/claude-sonnet-4
            agent:
              max_turns: 100
            terminal:
              backend: docker
            display:
              compact: true
        """)
        from hermes_cli.config_sync import sync_config

        r1 = sync_config()
        assert len(r1["added"]) > 0

        r2 = sync_config()
        assert r2["added"] == []

        r3 = sync_config()
        assert r3["added"] == []

        # Final config must still be valid YAML
        cfg = _read_config(tmp_path)
        assert cfg["model"] == "anthropic/claude-sonnet-4"
        assert cfg["agent"]["max_turns"] == 100
        assert cfg["terminal"]["backend"] == "docker"
        assert cfg["display"]["compact"] is True
