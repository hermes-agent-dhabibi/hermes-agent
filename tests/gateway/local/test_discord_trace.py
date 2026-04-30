"""Tests for fork-local Discord trace state and sink."""

from __future__ import annotations

import asyncio

import pytest

from gateway.local.discord_trace import DiscordTraceSink, dedupe_reasoning_replay
from gateway.platforms.base import SendResult


class FakeTraceAdapter:
    def __init__(self):
        self.sent = []
        self.edits = []
        self.send_results: list[SendResult] = []
        self.edit_results: list[SendResult] = []
        self.send_started = 0
        self.send_gate = None

    async def send_trace(self, state, *, metadata=None):
        self.send_started += 1
        if self.send_gate is not None:
            await self.send_gate.wait()
        self.sent.append({"reasoning": state.reasoning_text, "tools": list(state.tools), "metadata": metadata})
        if self.send_results:
            return self.send_results.pop(0)
        return SendResult(success=True, message_id="trace-1")

    async def edit_trace(self, message_id, state, *, metadata=None):
        self.edits.append(
            {"message_id": message_id, "reasoning": state.reasoning_text, "tools": list(state.tools), "metadata": metadata}
        )
        if self.edit_results:
            return self.edit_results.pop(0)
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


@pytest.mark.asyncio
async def test_trace_sink_serializes_concurrent_first_flushes():
    adapter = FakeTraceAdapter()
    adapter.send_gate = asyncio.Event()
    sink = DiscordTraceSink(adapter, chat_id="c1", min_reasoning_chars=1, min_interval=0)

    sink.on_reasoning_delta("Thinking live")
    first = asyncio.create_task(sink.flush(force=False))
    await asyncio.sleep(0)
    second = asyncio.create_task(sink.flush(force=False))
    await asyncio.sleep(0)
    adapter.send_gate.set()

    first_result, second_result = await asyncio.gather(first, second)

    assert first_result is not None
    assert first_result.success is True
    assert second_result is None
    assert adapter.send_started == 1
    assert len(adapter.sent) == 1
    assert len(adapter.edits) == 0
    assert sink.state.message_id == "trace-1"


@pytest.mark.asyncio
async def test_trace_sink_retries_after_transient_send_failure_without_force():
    adapter = FakeTraceAdapter()
    adapter.send_results = [
        SendResult(success=False, error="temporary", retryable=True),
        SendResult(success=True, message_id="trace-2"),
    ]
    sink = DiscordTraceSink(adapter, chat_id="c1", min_reasoning_chars=1, min_interval=0)

    sink.on_reasoning_delta("Thinking live")
    first_result = await sink.flush(force=False)
    second_result = await sink.flush(force=False)

    assert first_result.success is False
    assert second_result.success is True
    assert len(adapter.sent) == 2
    assert sink.state.last_rendered_hash is not None
    assert sink.state.message_id == "trace-2"


@pytest.mark.asyncio
async def test_trace_sink_cancel_suppresses_events_and_flushes():
    adapter = FakeTraceAdapter()
    sink = DiscordTraceSink(adapter, chat_id="c1", min_reasoning_chars=1, min_interval=0)

    sink.cancel()
    sink.on_reasoning_delta("Thinking live")
    sink.on_tool_event("tool.started", "search_files", "reasoning_callback")

    flush_result = await sink.flush(force=True)
    finish_result = await sink.finish()

    assert sink.closed is True
    assert flush_result is None
    assert finish_result is None
    assert sink.state.reasoning_text == ""
    assert sink.state.tools == []
    assert sink.state.finalized is False
    assert adapter.sent == []
    assert adapter.edits == []


@pytest.mark.asyncio
async def test_trace_sink_inactive_callback_suppresses_events_and_finish():
    active = False
    adapter = FakeTraceAdapter()
    sink = DiscordTraceSink(adapter, chat_id="c1", is_active=lambda: active, min_reasoning_chars=1, min_interval=0)

    sink.on_reasoning_delta("Thinking live")
    sink.on_tool_event("tool.started", "search_files", "reasoning_callback")

    flush_result = await sink.flush(force=True)
    finish_result = await sink.finish()

    assert flush_result is None
    assert finish_result is None
    assert sink.state.reasoning_text == ""
    assert sink.state.tools == []
    assert sink.state.finalized is False
    assert adapter.sent == []
    assert adapter.edits == []


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
