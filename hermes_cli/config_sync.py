"""``hermes config sync`` — backfill missing DEFAULT_CONFIG keys into config.yaml.

Reads the user's config.yaml, computes missing keys relative to DEFAULT_CONFIG,
and surgically inserts them into the YAML file without reformatting existing
content.  Existing values are never overwritten, and user-defined keys (like
custom provider entries) are never removed.

Since ruamel.yaml is not available we do line-level text insertion instead of
a full round-trip through a YAML library.  The algorithm:

1. Walk DEFAULT_CONFIG vs the user dict to find missing key-paths.
2. For each missing key, locate the parent section in the YAML text by its
   indentation and header line, then append the new key (with optional
   comment) at the end of that section.
3. If the parent section itself is missing, create it.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from hermes_cli.config import (
    DEFAULT_CONFIG,
    get_config_path,
    read_raw_config,
    ensure_hermes_home,
    is_managed,
    managed_error,
    _secure_file,
)


# ---------------------------------------------------------------------------
# Comment catalog — maps dotted key paths to inline/block comments.
# Extracted once from the Python-source comments adjacent to each key in
# DEFAULT_CONFIG.  We maintain a hand-curated subset for the keys that
# benefit most from a comment in the user's YAML.  Keys not listed here
# are inserted without a comment — the value itself is usually self-
# explanatory (e.g. ``tts.openai.voice: alloy``).
# ---------------------------------------------------------------------------

_KEY_COMMENTS: Dict[str, str] = {
    # agent
    "agent.gateway_timeout": "Inactivity timeout for gateway sessions (seconds). 0 = unlimited.",
    "agent.tool_use_enforcement": 'Tool-use enforcement: "auto", true/false, or list of model substrings',
    "agent.gateway_timeout_warning": "Warn user at this threshold before full timeout. 0 = disable.",
    # terminal
    "terminal.env_passthrough": "Env vars to pass through to sandboxed execution (non-skill)",
    "terminal.docker_env": "Explicit env vars for Docker containers: {KEY: VALUE}",
    "terminal.docker_volumes": 'Docker volume mounts: ["host:container", ...]',
    "terminal.docker_mount_cwd_to_workspace": "Mount host cwd into /workspace in Docker",
    "terminal.persistent_shell": "Keep a long-lived shell across execute() calls",
    # browser
    "browser.inactivity_timeout": "Browser inactivity timeout (seconds)",
    "browser.command_timeout": "Timeout for browser commands (seconds)",
    "browser.record_sessions": "Auto-record browser sessions as WebM videos",
    "browser.allow_private_urls": "Allow navigating to private/internal IPs",
    "browser.camofox.managed_persistence": "Stable profile-scoped userId for Camofox",
    # checkpoints
    "checkpoints.enabled": "Filesystem checkpoints before destructive file ops",
    "checkpoints.max_snapshots": "Max checkpoints to keep per directory",
    # file_read_max_chars
    "file_read_max_chars": "Max chars per read_file call (100K ~ 25-35K tokens)",
    # compression
    "compression.threshold": "Compress when context usage exceeds this ratio",
    "compression.target_ratio": "Fraction of threshold to preserve as recent tail",
    "compression.protect_last_n": "Minimum recent messages to keep uncompressed",
    "compression.summary_model": "Model for compression summaries (empty = main model)",
    # smart_model_routing
    "smart_model_routing.enabled": "Route simple messages to a cheaper model",
    # display
    "display.compact": "Compact display mode",
    "display.resume_display": 'Resume display mode: "full" or "compact"',
    "display.busy_input_mode": '"interrupt" or "queue" — behavior when agent is busy',
    "display.bell_on_complete": "Ring terminal bell when agent finishes",
    "display.show_reasoning": "Show model reasoning traces",
    "display.streaming": "Enable streaming output",
    "display.inline_diffs": "Show inline diff previews for write actions",
    "display.show_cost": "Show $ cost in the status bar",
    "display.skin": "Display skin/theme name",
    "display.tool_progress_command": "Enable /verbose command in messaging gateway",
    "display.tool_progress_overrides": 'Per-platform overrides: {"signal": "off", ...}',
    "display.tool_preview_length": "Max chars for tool call previews (0 = no limit)",
    # privacy
    "privacy.redact_pii": "Hash user IDs and strip phone numbers from LLM context",
    # memory
    "memory.memory_enabled": "Enable persistent memory",
    "memory.user_profile_enabled": "Enable user profile memory",
    "memory.memory_char_limit": "Max chars for memory store (~800 tokens)",
    "memory.user_char_limit": "Max chars for user profile (~500 tokens)",
    "memory.provider": 'External memory provider: "" (built-in), "mem0", etc.',
    # delegation
    "delegation.model": 'Subagent model (empty = inherit parent). e.g. "google/gemini-3-flash-preview"',
    "delegation.provider": 'Subagent provider (empty = inherit parent). e.g. "openrouter"',
    "delegation.base_url": "Direct OpenAI-compatible endpoint for subagents",
    "delegation.api_key": "API key for delegation.base_url",
    "delegation.max_iterations": "Per-subagent iteration cap",
    "delegation.reasoning_effort": 'Subagent reasoning: "xhigh", "high", "medium", "low", "minimal", "none"',
    # prefill
    "prefill_messages_file": "Ephemeral prefill messages file for few-shot priming",
    # skills
    "skills.external_dirs": "Extra skill directories for cross-tool sharing",
    # discord
    "discord.require_mention": "Require @mention to respond in server channels",
    "discord.free_response_channels": "Channel IDs where bot responds without mention",
    "discord.auto_thread": "Auto-create threads on @mention in channels",
    "discord.reactions": "Add 👀/✅/❌ reactions during processing",
    # approvals
    "approvals.mode": '"manual", "smart" (LLM auto-approve), or "off" (skip all)',
    "approvals.timeout": "Approval prompt timeout (seconds)",
    # security
    "security.redact_secrets": "Redact secrets from tool output",
    "security.tirith_enabled": "Pre-exec security scanning",
    # cron
    "cron.wrap_response": "Wrap cron responses with header/footer",
    # logging
    "logging.level": "Minimum log level: DEBUG, INFO, WARNING",
    "logging.max_size_mb": "Max size per log file before rotation",
    "logging.backup_count": "Number of rotated backup files to keep",
    # timezone
    "timezone": 'IANA timezone (e.g. "America/New_York"). Empty = server local.',
}

# Keys whose sub-tree should never be synced (user-defined, no defaults)
_SKIP_SECTIONS = frozenset({"providers", "custom_providers", "personalities",
                            "quick_commands", "credential_pool_strategies"})


# ---------------------------------------------------------------------------
# Core diff logic
# ---------------------------------------------------------------------------

def _collect_missing(
    defaults: dict,
    user_cfg: dict,
    prefix: str = "",
) -> List[Tuple[str, Any]]:
    """Return list of ``(dotted_key, default_value)`` for missing keys.

    Recurses into nested dicts.  Skips private keys (``_``-prefixed) and
    user-defined sections listed in ``_SKIP_SECTIONS``.
    """
    missing: List[Tuple[str, Any]] = []
    for key, default_value in defaults.items():
        if key.startswith("_"):
            continue
        full_key = f"{prefix}.{key}" if prefix else key
        top_level = full_key.split(".")[0]
        if top_level in _SKIP_SECTIONS:
            continue

        if key not in user_cfg:
            missing.append((full_key, default_value))
        elif isinstance(default_value, dict) and isinstance(user_cfg.get(key), dict):
            missing.extend(_collect_missing(default_value, user_cfg[key], full_key))
    return missing


# ---------------------------------------------------------------------------
# YAML text surgery helpers
# ---------------------------------------------------------------------------

def _yaml_scalar(value: Any) -> str:
    """Render a Python value as an inline YAML scalar."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if value == "":
            return "''"
        # Quote if it contains special YAML chars or looks like a bool/number
        needs_quote = any(c in value for c in ":#{}[]|>!&*?,") or value.lower() in (
            "true", "false", "yes", "no", "on", "off", "null", "~",
        )
        if needs_quote:
            # Use double quotes, escaping internal double quotes
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return value
    if isinstance(value, list):
        if not value:
            return "[]"
        # Short lists inline, long lists block
        items = [_yaml_scalar(v) for v in value]
        inline = "[" + ", ".join(items) + "]"
        if len(inline) < 80:
            return inline
        # Fall back to yaml.dump for long lists
        return yaml.dump(value, default_flow_style=True).strip()
    if isinstance(value, dict):
        if not value:
            return "{}"
        return yaml.dump(value, default_flow_style=True).strip()
    return str(value)


def _yaml_block(key: str, value: Any, indent: int, comment: str | None = None) -> str:
    """Render a key-value pair (possibly a nested dict) as YAML text lines.

    Args:
        key: The bare key name (no dots).
        value: The value to render.
        indent: Number of spaces for indentation.
        comment: Optional inline comment.

    Returns a string ending with ``\\n``, ready to be spliced into the file.
    """
    pad = " " * indent

    # Nested dict → render recursively as a block
    if isinstance(value, dict) and value:
        lines = [f"{pad}{key}:"]
        if comment:
            lines[0] += f"  # {comment}"
        lines[0] += "\n"
        for sub_key, sub_val in value.items():
            if sub_key.startswith("_"):
                continue
            sub_comment = _KEY_COMMENTS.get(f"{key}.{sub_key}" if not "." in key else None)
            # Build the full dotted key for comment lookup — handled below
            lines.append(_yaml_block(sub_key, sub_val, indent + 2))
        return "".join(lines)

    # Scalar / list / empty dict
    rendered = _yaml_scalar(value)
    line = f"{pad}{key}: {rendered}"
    if comment:
        line += f"  # {comment}"
    return line + "\n"


def _find_section_end(lines: List[str], section_key: str, parent_indent: int) -> int:
    """Find the line index where a YAML section ends.

    Given a section header like ``agent:`` at *parent_indent* spaces,
    returns the index of the first line that is **not** part of that
    section (i.e. the next line at the same or lesser indentation, or EOF).
    """
    # First find the header line
    header_pattern = re.compile(
        r"^" + " " * parent_indent + re.escape(section_key) + r"\s*:"
    )
    header_idx = None
    for i, line in enumerate(lines):
        if header_pattern.match(line):
            header_idx = i
            break

    if header_idx is None:
        return -1

    # Walk forward past all lines that belong to this section
    child_indent = parent_indent + 1  # anything indented more
    for i in range(header_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue  # blank lines and comments don't end a section
        line_indent = len(lines[i]) - len(lines[i].lstrip())
        if line_indent <= parent_indent:
            return i
    return len(lines)


def _expand_inline_empty(lines: List[str], idx: int) -> List[str]:
    """If ``lines[idx]`` has an inline ``{}`` or ``[]``, strip it to block style.

    Converts e.g. ``  camofox: {}`` → ``  camofox:\\n`` so that child keys
    can be inserted below without producing invalid YAML.  Returns a
    (possibly modified) copy of *lines*.
    """
    line = lines[idx]
    # Match pattern: <key>: {} or <key>: []  (with optional trailing comment)
    m = re.match(r"^(\s*\S+\s*:)\s*(\{\}|\[\])\s*(#.*)?$", line)
    if m:
        lines = list(lines)  # shallow copy
        prefix = m.group(1)
        comment = m.group(3) or ""
        if comment:
            lines[idx] = prefix + "  " + comment + "\n"
        else:
            lines[idx] = prefix + "\n"
    return lines


def _insert_into_section(
    lines: List[str],
    section_path: List[str],
    new_text: str,
) -> List[str]:
    """Insert *new_text* at the end of the section identified by *section_path*.

    *section_path* is a list of YAML keys like ``["agent"]`` or
    ``["browser", "camofox"]``.  The text is inserted just before the
    next sibling (or EOF).
    """
    current_indent = 0
    search_start = 0

    for depth, key in enumerate(section_path):
        # Find the header for this key at current_indent
        header_pattern = re.compile(
            r"^" + " " * current_indent + re.escape(key) + r"\s*:"
        )
        found = False
        for i in range(search_start, len(lines)):
            if header_pattern.match(lines[i]):
                # If the header has an inline empty value ({} or []),
                # convert it to block style so children can be nested below.
                lines = _expand_inline_empty(lines, i)

                # Find where this section ends
                end_idx = _find_section_end(lines, key, current_indent)
                if depth == len(section_path) - 1:
                    # This is the target section — insert before end_idx
                    # Back up past trailing blank lines to keep them after our insertion
                    insert_at = end_idx
                    while insert_at > i + 1 and not lines[insert_at - 1].strip():
                        insert_at -= 1
                    new_lines = lines[:insert_at] + [new_text] + lines[insert_at:]
                    return new_lines
                else:
                    # Descend into this section
                    search_start = i + 1
                    current_indent += 2
                    found = True
                    break
        if not found:
            break

    # Section path not found — shouldn't happen because we create missing
    # parents first, but as a fallback append to end of file.
    return lines + [new_text]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync_config(*, dry_run: bool = False) -> Dict[str, Any]:
    """Backfill missing DEFAULT_CONFIG keys into the user's config.yaml.

    Args:
        dry_run: If True, compute the diff but don't write.

    Returns a dict with:
        - ``added``: list of dotted key strings that were (or would be) added
        - ``message``: human-friendly summary string
    """
    if is_managed():
        managed_error("sync configuration")
        return {"added": [], "message": "Cannot sync in managed mode."}

    ensure_hermes_home()
    config_path = get_config_path()

    user_cfg = read_raw_config()
    missing = _collect_missing(DEFAULT_CONFIG, user_cfg)

    if not missing:
        return {
            "added": [],
            "message": "Config is up to date — no new keys to add.",
        }

    if dry_run:
        keys = [k for k, _ in missing]
        return {
            "added": keys,
            "message": f"Would add {len(keys)} new config key(s): {', '.join(keys)}",
        }

    # Read existing file text (or empty)
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
    else:
        text = ""

    lines = text.splitlines(keepends=True)
    # Ensure the last line ends with a newline for clean appending
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    added_keys: List[str] = []

    for dotted_key, default_value in missing:
        parts = dotted_key.split(".")
        key_name = parts[-1]
        parent_parts = parts[:-1]

        # Determine indentation level based on nesting depth
        indent = len(parent_parts) * 2
        comment = _KEY_COMMENTS.get(dotted_key)

        # Build the YAML text for this key
        new_yaml = _yaml_block(key_name, default_value, indent, comment)

        if parent_parts:
            # Check if parent section exists in the file
            # We need to check the *current* state of lines (may have been
            # modified by previous iterations that created parent sections)
            parent_exists = _section_exists(lines, parent_parts)

            if not parent_exists:
                # Create the entire parent chain + this key as a block
                # Find the topmost missing ancestor
                for depth in range(len(parent_parts)):
                    ancestor = parent_parts[: depth + 1]
                    if not _section_exists(lines, ancestor):
                        # Create from this level down
                        block = _build_new_section(
                            parent_parts[depth:], key_name, default_value, depth * 2, dotted_key
                        )
                        # Append to end of file with a blank line separator
                        if lines and lines[-1].strip():
                            lines.append("\n")
                        lines.extend(l + "\n" if not l.endswith("\n") else l for l in block.splitlines(keepends=True))
                        break
            else:
                lines = _insert_into_section(lines, parent_parts, new_yaml)
        else:
            # Top-level key — append to end of file
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.append(new_yaml)

        added_keys.append(dotted_key)

    # Write result
    result_text = "".join(lines)
    config_path.write_text(result_text, encoding="utf-8")
    _secure_file(config_path)

    key_list = ", ".join(added_keys)
    return {
        "added": added_keys,
        "message": f"Added {len(added_keys)} new config key(s): {key_list}",
    }


def _section_exists(lines: List[str], path: List[str]) -> bool:
    """Check whether a section header path exists in *lines*."""
    current_indent = 0
    search_from = 0
    for key in path:
        pattern = re.compile(
            r"^" + " " * current_indent + re.escape(key) + r"\s*:"
        )
        found = False
        for i in range(search_from, len(lines)):
            if pattern.match(lines[i]):
                search_from = i + 1
                current_indent += 2
                found = True
                break
        if not found:
            return False
    return True


def _build_new_section(
    section_keys: List[str],
    leaf_key: str,
    leaf_value: Any,
    base_indent: int,
    full_dotted_key: str,
) -> str:
    """Build a new nested section block from scratch.

    E.g. for section_keys=["browser", "camofox"], leaf_key="managed_persistence",
    creates::

        browser:
          camofox:
            managed_persistence: false
    """
    lines_out: List[str] = []
    for i, sk in enumerate(section_keys):
        pad = " " * (base_indent + i * 2)
        lines_out.append(f"{pad}{sk}:")

    # Leaf
    leaf_indent = base_indent + len(section_keys) * 2
    comment = _KEY_COMMENTS.get(full_dotted_key)
    leaf_yaml = _yaml_block(leaf_key, leaf_value, leaf_indent, comment)
    lines_out.append(leaf_yaml.rstrip("\n"))

    return "\n".join(lines_out) + "\n"
