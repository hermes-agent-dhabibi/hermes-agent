"""Fork-specific terminal invariants."""

import pytest

from tools.terminal_tool import _should_auto_background


@pytest.mark.parametrize(
    "command",
    [
        "python -m http.server 8080",
        "python3 -m http.server",
        "npx serve dist -l 4321",
        "npm run dev",
        "uvicorn app:app --reload",
        "journalctl -fu hermes-gateway",
    ],
)
def test_long_lived_commands_auto_background(command):
    """Known hang-prone commands must never run as foreground terminal calls."""
    assert _should_auto_background(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "python -c 'print(123)'",
        "npm test",
        "pytest tests/fork -q",
    ],
)
def test_short_lived_commands_do_not_auto_background(command):
    """Do not turn ordinary finite commands into background jobs."""
    assert _should_auto_background(command) is False
