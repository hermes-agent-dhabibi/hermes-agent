"""Fork-specific gateway/process invariants."""

# Re-export the strongest existing invariant into tests/fork so rebase checks
# have one small, obvious entrypoint for Habibi-specific gateway behavior.
from tests.gateway.test_background_process_notifications import (  # noqa: F401
    test_agent_notify_skips_completely_when_already_consumed,
    test_agent_notify_suppresses_user_facing_text_notification,
)
