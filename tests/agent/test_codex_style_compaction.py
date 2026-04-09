"""Tests for Codex-style compaction improvements in context_compressor.py.

Covers:
- User message extraction from summarized regions (_collect_user_messages)
- Post-compaction message ordering: [head] → [user msgs] → [summary] → [tail]
- SUMMARY_PREFIX framing ("Another language model...")
- Summary always uses "user" role
- Backward compat: legacy prefixes are still stripped
"""

import pytest
from unittest.mock import patch, MagicMock

from agent.context_compressor import (
    ContextCompressor,
    SUMMARY_PREFIX,
    LEGACY_SUMMARY_PREFIX,
    _LEGACY_COMPACTION_PREFIX,
    _USER_MESSAGE_MAX_TOKENS,
    _CHARS_PER_TOKEN,
)


@pytest.fixture()
def compressor():
    """Create a ContextCompressor with mocked dependencies."""
    with patch("agent.context_compressor.get_model_context_length", return_value=100000):
        c = ContextCompressor(
            model="test/model",
            threshold_percent=0.85,
            protect_first_n=2,
            protect_last_n=2,
            quiet_mode=True,
        )
        return c


def _mock_summary_response(text="summary of work done"):
    """Create a mock LLM response for compression summary."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = text
    return mock_response


# ------------------------------------------------------------------
# SUMMARY_PREFIX framing
# ------------------------------------------------------------------

class TestSummaryPrefixFraming:
    """The SUMMARY_PREFIX should use identity-preserving checkpoint framing."""

    def test_summary_prefix_mentions_earlier_work(self):
        assert "Earlier in this conversation" in SUMMARY_PREFIX

    def test_summary_prefix_mentions_building_on_work(self):
        assert "Build on" in SUMMARY_PREFIX

    def test_summary_prefix_mentions_avoid_redoing(self):
        assert "avoid re-doing" in SUMMARY_PREFIX

    def test_summary_prefix_mentions_tool_state(self):
        assert "tools you used" in SUMMARY_PREFIX

    def test_summary_prefix_does_not_use_old_context_compaction_prefix(self):
        assert not SUMMARY_PREFIX.startswith("[CONTEXT COMPACTION]")


class TestLegacyPrefixStripping:
    """_with_summary_prefix should strip all known legacy prefixes."""

    def test_strips_legacy_context_summary_prefix(self, compressor):
        result = compressor._with_summary_prefix("[CONTEXT SUMMARY]: old summary here")
        assert result.startswith(SUMMARY_PREFIX)
        assert "old summary here" in result
        assert LEGACY_SUMMARY_PREFIX not in result.split("\n", 1)[-1]

    def test_strips_legacy_compaction_prefix(self, compressor):
        old = "[CONTEXT COMPACTION] Earlier turns were compacted. Summary here."
        result = compressor._with_summary_prefix(old)
        assert result.startswith(SUMMARY_PREFIX)
        # The old prefix text should be stripped, leaving just the content
        assert _LEGACY_COMPACTION_PREFIX not in result.split("\n", 1)[-1]

    def test_strips_current_prefix_without_duplication(self, compressor):
        text = f"{SUMMARY_PREFIX}\nsome summary"
        result = compressor._with_summary_prefix(text)
        # Should not double-prefix
        assert result.count("Earlier in this conversation") == 1


# ------------------------------------------------------------------
# _collect_user_messages
# ------------------------------------------------------------------

class TestCollectUserMessages:
    """User message extraction from the summarized region."""

    def test_extracts_only_user_role_messages(self, compressor):
        msgs = [
            {"role": "user", "content": "ask 1"},
            {"role": "assistant", "content": "reply 1"},
            {"role": "user", "content": "ask 2"},
            {"role": "tool", "tool_call_id": "c1", "content": "result"},
        ]
        result = compressor._collect_user_messages(msgs)
        assert len(result) == 2
        assert all(m["role"] == "user" for m in result)

    def test_skips_summary_prefixed_messages(self, compressor):
        msgs = [
            {"role": "user", "content": "real ask"},
            {"role": "user", "content": f"{SUMMARY_PREFIX}\nold summary"},
            {"role": "user", "content": f"{LEGACY_SUMMARY_PREFIX} older summary"},
            {"role": "user", "content": f"{_LEGACY_COMPACTION_PREFIX} even older"},
        ]
        result = compressor._collect_user_messages(msgs)
        assert len(result) == 1
        assert result[0]["content"] == "real ask"

    def test_skips_empty_content(self, compressor):
        msgs = [
            {"role": "user", "content": ""},
            {"role": "user", "content": None},
            {"role": "user", "content": "real"},
        ]
        result = compressor._collect_user_messages(msgs)
        assert len(result) == 1
        assert result[0]["content"] == "real"

    def test_newest_first_selection(self, compressor):
        """When budget is limited, should select newest messages first."""
        # Each message ~35 tokens (100 chars / 4 + 10 overhead)
        # Budget of 75 tokens should get exactly 2 messages (35 + 35 = 70)
        msgs = [
            {"role": "user", "content": "a" * 100},  # ~35 tokens
            {"role": "user", "content": "b" * 100},
            {"role": "user", "content": "c" * 100},
        ]
        result = compressor._collect_user_messages(msgs, max_tokens=75)
        assert len(result) == 2
        assert "b" in result[0]["content"]
        assert "c" in result[1]["content"]

    def test_returns_chronological_order(self, compressor):
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        result = compressor._collect_user_messages(msgs)
        contents = [m["content"] for m in result]
        assert contents == ["first", "second", "third"]

    def test_truncates_oversized_message(self, compressor):
        """When a message exceeds remaining budget, it should be truncated."""
        huge_content = "x" * 100000  # ~25k tokens
        msgs = [{"role": "user", "content": huge_content}]
        result = compressor._collect_user_messages(msgs, max_tokens=100)
        assert len(result) == 1
        assert len(result[0]["content"]) < len(huge_content)
        assert result[0]["content"].endswith("...[truncated]")

    def test_empty_input_returns_empty(self, compressor):
        assert compressor._collect_user_messages([]) == []

    def test_no_user_messages_returns_empty(self, compressor):
        msgs = [
            {"role": "assistant", "content": "reply"},
            {"role": "tool", "content": "result"},
        ]
        assert compressor._collect_user_messages(msgs) == []

    def test_zero_budget_returns_empty(self, compressor):
        msgs = [{"role": "user", "content": "ask"}]
        assert compressor._collect_user_messages(msgs, max_tokens=0) == []

    def test_copies_messages_not_references(self, compressor):
        """Returned messages should be copies, not references to originals."""
        msgs = [{"role": "user", "content": "ask"}]
        result = compressor._collect_user_messages(msgs)
        assert result[0] is not msgs[0]

    def test_default_budget_is_20k(self):
        assert _USER_MESSAGE_MAX_TOKENS == 20_000


# ------------------------------------------------------------------
# compress() — post-compaction message ordering
# ------------------------------------------------------------------

class TestCompressOrdering:
    """After compaction, messages should be: [head] → [user msgs] → [summary] → [tail]."""

    def test_user_messages_appear_before_summary(self):
        """User messages from the summarized region should appear BEFORE the summary."""
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=2, protect_last_n=2)

        msgs = [
            {"role": "user", "content": "msg 0"},          # head
            {"role": "assistant", "content": "msg 1"},      # head
            {"role": "user", "content": "important ask"},   # summarized — should be preserved
            {"role": "assistant", "content": "msg 3"},      # summarized
            {"role": "user", "content": "another ask"},     # summarized — should be preserved
            {"role": "assistant", "content": "msg 5"},      # tail
            {"role": "user", "content": "msg 6"},           # tail
            {"role": "assistant", "content": "msg 7"},      # tail
        ]
        with patch("agent.context_compressor.call_llm", return_value=mock_response):
            result = c.compress(msgs)

        # Find the summary message
        summary_idx = None
        for i, m in enumerate(result):
            if (m.get("content") or "").startswith(SUMMARY_PREFIX):
                summary_idx = i
                break
        assert summary_idx is not None, "Summary message should be present"

        # Find preserved user messages from summarized region
        preserved = [
            (i, m) for i, m in enumerate(result)
            if m.get("content") in ("important ask", "another ask")
        ]
        assert len(preserved) >= 1, "At least one user message from summarized region should be preserved"

        # All preserved user messages should come BEFORE the summary
        for idx, msg in preserved:
            assert idx < summary_idx, f"Preserved user msg at {idx} should be before summary at {summary_idx}"

    def test_summary_appears_before_tail(self):
        """Summary should appear before tail messages."""
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=2, protect_last_n=2)

        msgs = [
            {"role": "user", "content": "msg 0"},
            {"role": "assistant", "content": "msg 1"},
            {"role": "user", "content": "middle ask"},
            {"role": "assistant", "content": "msg 3"},
            {"role": "user", "content": "msg 4"},
            {"role": "assistant", "content": "tail msg 5"},
            {"role": "user", "content": "tail msg 6"},
            {"role": "assistant", "content": "tail msg 7"},
        ]
        with patch("agent.context_compressor.call_llm", return_value=mock_response):
            result = c.compress(msgs)

        summary_idx = None
        tail_start_idx = None
        for i, m in enumerate(result):
            if (m.get("content") or "").startswith(SUMMARY_PREFIX):
                summary_idx = i
            if "tail msg" in (m.get("content") or "") and tail_start_idx is None:
                tail_start_idx = i

        assert summary_idx is not None
        assert tail_start_idx is not None
        assert summary_idx < tail_start_idx, "Summary should come before tail"

    def test_full_ordering_head_user_summary_tail(self):
        """Verify the complete ordering: head → preserved user → summary → tail."""
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=2, protect_last_n=2)

        msgs = [
            {"role": "user", "content": "HEAD_0"},
            {"role": "assistant", "content": "HEAD_1"},
            {"role": "user", "content": "MIDDLE_USER_ASK"},
            {"role": "assistant", "content": "middle_reply"},
            {"role": "user", "content": "MIDDLE_USER_ASK_2"},
            {"role": "assistant", "content": "TAIL_0"},
            {"role": "user", "content": "TAIL_1"},
            {"role": "assistant", "content": "TAIL_2"},
        ]
        with patch("agent.context_compressor.call_llm", return_value=mock_response):
            result = c.compress(msgs)

        contents = [m.get("content", "") for m in result]

        # Head messages preserved at start
        assert contents[0] == "HEAD_0"
        assert contents[1] == "HEAD_1"

        # Find positions
        user_ask_positions = [i for i, c_ in enumerate(contents) if "MIDDLE_USER_ASK" in c_]
        summary_positions = [i for i, c_ in enumerate(contents) if c_.startswith(SUMMARY_PREFIX)]
        tail_positions = [i for i, c_ in enumerate(contents) if c_.startswith("TAIL_")]

        assert user_ask_positions, "Preserved user messages should exist"
        assert summary_positions, "Summary should exist"
        assert tail_positions, "Tail messages should exist"

        # Ordering: user asks < summary < tail
        assert max(user_ask_positions) < min(summary_positions), "User asks should come before summary"
        assert max(summary_positions) < min(tail_positions), "Summary should come before tail"


class TestSummaryRole:
    """Summary should always use 'user' role (Codex convention)."""

    def test_summary_always_user_role(self):
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=2, protect_last_n=2)

        msgs = [
            {"role": "user", "content": "msg 0"},
            {"role": "assistant", "content": "msg 1"},
            {"role": "user", "content": "msg 2"},
            {"role": "assistant", "content": "msg 3"},
            {"role": "user", "content": "msg 4"},
            {"role": "assistant", "content": "msg 5"},
            {"role": "user", "content": "msg 6"},
            {"role": "assistant", "content": "msg 7"},
        ]
        with patch("agent.context_compressor.call_llm", return_value=mock_response):
            result = c.compress(msgs)

        summary_msgs = [m for m in result if (m.get("content") or "").startswith(SUMMARY_PREFIX)]
        assert len(summary_msgs) == 1
        assert summary_msgs[0]["role"] == "user"

    def test_summary_user_role_regardless_of_head(self):
        """Even when head ends with 'user', summary should be 'user' (Codex style)."""
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=3, protect_last_n=2)

        msgs = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "msg 1"},
            {"role": "user", "content": "msg 2"},       # last head — user
            {"role": "assistant", "content": "msg 3"},
            {"role": "user", "content": "msg 4"},
            {"role": "assistant", "content": "msg 5"},
            {"role": "user", "content": "msg 6"},
            {"role": "assistant", "content": "msg 7"},
        ]
        with patch("agent.context_compressor.call_llm", return_value=mock_response):
            result = c.compress(msgs)

        summary_msgs = [m for m in result if (m.get("content") or "").startswith(SUMMARY_PREFIX)]
        assert len(summary_msgs) == 1
        assert summary_msgs[0]["role"] == "user"


# ------------------------------------------------------------------
# compress() — user messages from summarized region survive
# ------------------------------------------------------------------

class TestUserMessagePreservation:
    """Real user messages should survive compaction."""

    def test_user_asks_preserved_from_middle(self):
        """User messages from the summarized middle region should appear in output."""
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=2, protect_last_n=2)

        msgs = [
            {"role": "user", "content": "msg 0"},
            {"role": "assistant", "content": "msg 1"},
            {"role": "user", "content": "Fix the login bug"},       # should survive
            {"role": "assistant", "content": "msg 3"},
            {"role": "user", "content": "Also update the tests"},   # should survive
            {"role": "assistant", "content": "msg 5"},
            {"role": "user", "content": "msg 6"},
            {"role": "assistant", "content": "msg 7"},
        ]
        with patch("agent.context_compressor.call_llm", return_value=mock_response):
            result = c.compress(msgs)

        all_content = " ".join(m.get("content", "") for m in result)
        assert "Fix the login bug" in all_content
        assert "Also update the tests" in all_content

    def test_no_user_messages_in_middle_still_works(self):
        """If summarized region has no user messages, compression still works."""
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=2, protect_last_n=2)

        msgs = [
            {"role": "user", "content": "msg 0"},
            {"role": "assistant", "content": "msg 1"},
            {"role": "assistant", "content": "msg 2"},  # middle — no user
            {"role": "assistant", "content": "msg 3"},  # middle — no user
            {"role": "assistant", "content": "msg 4"},  # middle — no user
            {"role": "assistant", "content": "msg 5"},
            {"role": "user", "content": "msg 6"},
            {"role": "assistant", "content": "msg 7"},
        ]
        with patch("agent.context_compressor.call_llm", return_value=mock_response):
            result = c.compress(msgs)

        # Should still produce a valid compressed result with summary
        summary_msgs = [m for m in result if (m.get("content") or "").startswith(SUMMARY_PREFIX)]
        assert len(summary_msgs) == 1

    def test_previous_summaries_not_preserved_as_user_messages(self):
        """Previous compaction summaries in the middle should NOT be re-preserved."""
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=2, protect_last_n=2)

        msgs = [
            {"role": "user", "content": "msg 0"},
            {"role": "assistant", "content": "msg 1"},
            {"role": "user", "content": f"{SUMMARY_PREFIX}\nold summary from prior compaction"},
            {"role": "assistant", "content": "msg 3"},
            {"role": "user", "content": "real user ask"},
            {"role": "assistant", "content": "msg 5"},
            {"role": "user", "content": "msg 6"},
            {"role": "assistant", "content": "msg 7"},
        ]
        with patch("agent.context_compressor.call_llm", return_value=mock_response):
            result = c.compress(msgs)

        # Should have exactly one summary (the new one), not the old one as a preserved user message
        summary_msgs = [m for m in result if (m.get("content") or "").startswith(SUMMARY_PREFIX)]
        assert len(summary_msgs) == 1  # only the new summary

        # But the real user ask should be preserved
        all_content = " ".join(m.get("content", "") for m in result)
        assert "real user ask" in all_content


# ------------------------------------------------------------------
# compress() — no summary (summaryless fallback)
# ------------------------------------------------------------------

class TestSummarylessFallback:
    """When summary generation fails, compress should still work without user message extraction breaking."""

    def test_summaryless_compression_still_works(self, compressor):
        """When no summary model is available, compression drops middle turns."""
        msgs = [
            {"role": "user", "content": "msg 0"},
            {"role": "assistant", "content": "msg 1"},
            {"role": "user", "content": "msg 2"},
            {"role": "assistant", "content": "msg 3"},
            {"role": "user", "content": "msg 4"},
            {"role": "assistant", "content": "msg 5"},
            {"role": "user", "content": "msg 6"},
            {"role": "assistant", "content": "msg 7"},
        ]
        # Simulate summary failure
        with patch("agent.context_compressor.call_llm", side_effect=RuntimeError("no provider")):
            result = compressor.compress(msgs)

        # Should still produce output with fewer messages
        assert len(result) < len(msgs)
        # No summary message should be present
        summary_msgs = [m for m in result if (m.get("content") or "").startswith(SUMMARY_PREFIX)]
        assert len(summary_msgs) == 0
        # But preserved user messages from the middle should still be there
        all_content = " ".join(m.get("content", "") for m in result)
        # At least some middle user asks should survive via _collect_user_messages
        user_contents = [m["content"] for m in result if m.get("role") == "user"]
        assert len(user_contents) >= 1  # at least the head user msg


# ------------------------------------------------------------------
# Summarization prompt
# ------------------------------------------------------------------

class TestSummarizationPrompt:
    """The first-compaction prompt should use Codex's forward-looking framing."""

    def test_first_compaction_prompt_is_forward_looking(self):
        """The summarization prompt should mention 'CONTEXT CHECKPOINT COMPACTION' and 'another LLM'."""
        mock_response = _mock_summary_response()

        with patch("agent.context_compressor.get_model_context_length", return_value=100000):
            c = ContextCompressor(model="test", quiet_mode=True, protect_first_n=2, protect_last_n=2)

        msgs = [
            {"role": "user", "content": "msg 0"},
            {"role": "assistant", "content": "msg 1"},
            {"role": "user", "content": "msg 2"},
            {"role": "assistant", "content": "msg 3"},
            {"role": "user", "content": "msg 4"},
            {"role": "assistant", "content": "msg 5"},
            {"role": "user", "content": "msg 6"},
            {"role": "assistant", "content": "msg 7"},
        ]

        captured_kwargs = {}
        def capture_call_llm(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_response

        with patch("agent.context_compressor.call_llm", side_effect=capture_call_llm):
            c.compress(msgs)

        prompt_content = captured_kwargs.get("messages", [{}])[0].get("content", "")
        assert "CONTEXT CHECKPOINT COMPACTION" in prompt_content
        assert "handoff summary" in prompt_content.lower()
        assert "another LLM" in prompt_content
