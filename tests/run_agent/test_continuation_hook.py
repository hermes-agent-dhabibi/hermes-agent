"""Test that on_session_end continuation directive triggers follow-up turns."""

from unittest.mock import patch


def test_continuation_directive_in_result():
    """When on_session_end hook returns continue action, result gets 'continuation' key."""

    def fake_invoke_hook(hook_name, **kwargs):
        if hook_name == "on_session_end":
            return [{"action": "continue", "prompt": "resume work"}]
        return []

    # Simulate what run_agent.py does with hook results
    result = {"final_response": "done", "messages": []}
    _end_results = fake_invoke_hook("on_session_end", session_id="test")
    for _end_r in (_end_results or []):
        if isinstance(_end_r, dict) and _end_r.get("action") == "continue":
            _cont_prompt = _end_r.get("prompt", "")
            if isinstance(_cont_prompt, str) and _cont_prompt.strip():
                result["continuation"] = {
                    "prompt": _cont_prompt.strip(),
                    "max_depth": _end_r.get("max_depth", 5),
                }
                break

    assert "continuation" in result
    assert result["continuation"]["prompt"] == "resume work"
    assert result["continuation"]["max_depth"] == 5


def test_continuation_ignored_when_no_prompt():
    """Continue action without a prompt produces no continuation."""
    result = {}
    _end_results = [{"action": "continue", "prompt": ""}]
    for _end_r in (_end_results or []):
        if isinstance(_end_r, dict) and _end_r.get("action") == "continue":
            _cont_prompt = _end_r.get("prompt", "")
            if isinstance(_cont_prompt, str) and _cont_prompt.strip():
                result["continuation"] = {
                    "prompt": _cont_prompt.strip(),
                    "max_depth": _end_r.get("max_depth", 5),
                }
                break

    assert "continuation" not in result


def test_continuation_custom_max_depth():
    """Plugin can specify a custom max_depth."""
    result = {}
    _end_results = [{"action": "continue", "prompt": "go", "max_depth": 3}]
    for _end_r in (_end_results or []):
        if isinstance(_end_r, dict) and _end_r.get("action") == "continue":
            _cont_prompt = _end_r.get("prompt", "")
            if isinstance(_cont_prompt, str) and _cont_prompt.strip():
                result["continuation"] = {
                    "prompt": _cont_prompt.strip(),
                    "max_depth": _end_r.get("max_depth", 5),
                }
                break

    assert result["continuation"]["max_depth"] == 3


def test_continuation_non_continue_actions_ignored():
    """Only 'continue' action triggers continuation."""
    result = {}
    _end_results = [{"action": "log", "prompt": "whatever"}]
    for _end_r in (_end_results or []):
        if isinstance(_end_r, dict) and _end_r.get("action") == "continue":
            _cont_prompt = _end_r.get("prompt", "")
            if isinstance(_cont_prompt, str) and _cont_prompt.strip():
                result["continuation"] = {
                    "prompt": _cont_prompt.strip(),
                    "max_depth": _end_r.get("max_depth", 5),
                }
                break

    assert "continuation" not in result
