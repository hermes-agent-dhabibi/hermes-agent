"""Tests for gateway reasoning display formatting and Discord overflow fallback."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import gateway.run as gateway_run
from gateway.platforms.discord import DiscordAdapter
from gateway.stream_consumer import GatewayStreamConsumer, StreamConsumerConfig


class _AdapterStub:
    MAX_MESSAGE_LENGTH = 2000

    def __init__(self):
        self.send = AsyncMock(return_value=MagicMock(success=True, message_id="m1"))
        self.edit_message = AsyncMock(return_value=MagicMock(success=True, message_id="m1"))


def test_reasoning_formatter_keeps_short_reasoning_untouched():
    reasoning = "line 1\nline 2\nline 3"

    result = gateway_run._format_reasoning_for_display(reasoning)

    assert result == reasoning


def test_reasoning_formatter_preserves_large_head_and_tail_with_omission_marker():
    reasoning = "\n".join(f"step {i}" for i in range(1, 181))

    result = gateway_run._format_reasoning_for_display(
        reasoning,
        max_lines=20,
        max_chars=2000,
        tail_lines=5,
        tail_chars=400,
    )

    assert "step 1" in result
    assert "step 15" in result
    assert "step 176" in result
    assert "step 180" in result
    assert "omitted" in result
    assert "step 90" not in result


def test_discord_edit_message_returns_message_too_long_for_oversized_edit():
    adapter = object.__new__(DiscordAdapter)
    adapter.MAX_MESSAGE_LENGTH = DiscordAdapter.MAX_MESSAGE_LENGTH
    adapter._client = SimpleNamespace()
    adapter.format_message = lambda content: content

    async def _run():
        msg = SimpleNamespace(edit=AsyncMock())
        channel = SimpleNamespace(fetch_message=AsyncMock(return_value=msg))
        adapter._client.get_channel = lambda _chat_id: channel
        adapter._client.fetch_channel = AsyncMock(return_value=channel)
        result = await DiscordAdapter.edit_message(adapter, "123", "456", "x" * (adapter.MAX_MESSAGE_LENGTH + 20))
        return result, msg

    result, msg = asyncio.run(_run())

    assert result.success is False
    assert result.error == "message_too_long"
    msg.edit.assert_not_called()


def test_stream_consumer_switches_to_fallback_when_edit_reports_message_too_long():
    adapter = _AdapterStub()
    adapter.edit_message = AsyncMock(return_value=MagicMock(success=False, error="message_too_long"))
    consumer = GatewayStreamConsumer(
        adapter=adapter,
        chat_id="discord-chat",
        config=StreamConsumerConfig(cursor=""),
    )
    consumer._message_id = "m1"
    consumer._already_sent = True
    consumer._last_sent_text = "visible prefix"

    asyncio.run(consumer._send_or_edit("x" * 2500))

    assert consumer._fallback_final_send is True
    assert consumer._edit_supported is False
    assert consumer._already_sent is True


def test_stream_consumer_edits_normally_when_content_fits():
    adapter = _AdapterStub()
    consumer = GatewayStreamConsumer(
        adapter=adapter,
        chat_id="discord-chat",
        config=StreamConsumerConfig(cursor=""),
    )
    consumer._message_id = "m1"
    consumer._already_sent = True

    asyncio.run(consumer._send_or_edit("still fits"))

    adapter.edit_message.assert_awaited_once()
    assert consumer._fallback_final_send is False
    assert consumer._edit_supported is True