"""Tests for fork-local Discord trace state and sink."""

from __future__ import annotations

import pytest

from gateway.local.discord_trace import DiscordTraceSink, dedupe_reasoning_replay
from gateway.platforms.base import SendResult


class FakeTraceAdapter:
    def __init__(self):
        self.sent = []
        self.edits = []

    async def send_trace(self, state, *, metadata=None):
        self.sent.append({"reasoning": state.reasoning_text, "tools": list(state.tools), "metadata": metadata})
        return SendResult(success=True, message_id="trace-1")

    async def edit_trace(self, message_id, state, *, metadata=None):
        self.edits.append(
            {"message_id": message_id, "reasoning": state.reasoning_text, "tools": list(state.tools), "metadata": metadata}
        )
        return SendResult(success=True, message_id=message_id)


def test_dedupe_reasoning_replay_collapses_heading_replay():
    text = (
        "**Inspecting links**\n\nI need to inspect links."
        "**Inspecting links**\n\nI need to inspect links and files."
    )

    result = dedupe_reasoning_replay(text)

    assert result.count("**Inspecting links**") == 1
    assert "files" in result


@pytest.mark.asyncio
async def test_trace_sink_sends_reasoning_and_tools():
    adapter = FakeTraceAdapter()
    sink = DiscordTraceSink(adapter, chat_id="c1", metadata={"thread_id": "t1"}, min_reasoning_chars=1, min_interval=0)

    sink.on_reasoning_delta("Thinking live")
    sink.on_tool_event("tool.started", "search_files", "reasoning_callback")
    result = await sink.flush(force=True)

    assert result.success is True
    assert sink.state.message_id == "trace-1"
    assert adapter.sent[0]["reasoning"] == "Thinking live"
    assert adapter.sent[0]["tools"][0].name == "search_files"


@pytest.mark.asyncio
async def test_trace_sink_edits_existing_trace_message():
    adapter = FakeTraceAdapter()
    sink = DiscordTraceSink(adapter, chat_id="c1", min_reasoning_chars=1, min_interval=0)

    sink.on_reasoning_delta("First")
    await sink.flush(force=True)
    sink.on_reasoning_delta(" second")
    await sink.flush(force=True)

    assert len(adapter.sent) == 1
    assert len(adapter.edits) == 1
    assert adapter.edits[0]["message_id"] == "trace-1"
    assert adapter.edits[0]["reasoning"] == "First second"


def test_trace_sink_suppresses_encrypted_reasoning():
    sink = DiscordTraceSink(FakeTraceAdapter(), chat_id="c1", min_reasoning_chars=1, min_interval=0)

    sink.on_reasoning_delta("reasoning.encrypted_content: nope")
    sink.flush_reasoning_buffer(force=True)

    assert sink.state.reasoning_text == ""


def test_trace_sink_dedupes_repeated_tool_events():
    sink = DiscordTraceSink(FakeTraceAdapter(), chat_id="c1")

    sink.on_tool_event("tool.started", "read_file", "/tmp/a")
    sink.on_tool_event("tool.started", "read_file", "/tmp/a")

    assert len(sink.state.tools) == 1
    assert sink.state.tools[0].count == 2
