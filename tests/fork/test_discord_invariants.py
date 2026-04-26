"""Fork-specific Discord invariants.

These tests pin local Habibi/Hermes UX expectations that may intentionally
contradict upstream defaults. Keep them small and behavior-focused so rebases
fail on semantic drift instead of requiring manual commit archaeology.
"""

from unittest.mock import AsyncMock

import pytest

from tests.gateway.test_discord_free_response import (
    FakeTextChannel,
    FakeThread,
    adapter,  # imported fixture
    discord_platform,
    make_message,
)

FREE_RESPONSE_CHANNEL_ID = 123456789012345678
AUTO_THREAD_ID = 223456789012345678


@pytest.mark.asyncio
async def test_free_response_channels_do_not_suppress_auto_thread(adapter, monkeypatch):
    """free_response_channels controls mentions; auto_thread controls threads.

    A top-level message in a free-response channel should bypass @mention and
    still create a thread when auto-threading is enabled. Inline free-response
    requires DISCORD_NO_THREAD_CHANNELS or DISCORD_AUTO_THREAD=false.
    """
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    monkeypatch.setenv("DISCORD_FREE_RESPONSE_CHANNELS", str(FREE_RESPONSE_CHANNEL_ID))
    monkeypatch.delenv("DISCORD_AUTO_THREAD", raising=False)  # default true
    monkeypatch.delenv("DISCORD_NO_THREAD_CHANNELS", raising=False)

    fake_thread = FakeThread(channel_id=AUTO_THREAD_ID, name="auto-thread")
    adapter._auto_create_thread = AsyncMock(return_value=fake_thread)

    message = make_message(
        channel=FakeTextChannel(channel_id=FREE_RESPONSE_CHANNEL_ID, name="general"),
        content="free chat message",
    )

    await adapter._handle_message(message)

    adapter._auto_create_thread.assert_awaited_once()
    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.source.chat_type == "thread"
    assert event.source.thread_id == str(AUTO_THREAD_ID)


@pytest.mark.asyncio
async def test_discord_reply_messages_do_not_auto_thread(adapter, monkeypatch):
    """Discord quote-replies should stay in-channel, never create nested threads."""
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    monkeypatch.setenv("DISCORD_FREE_RESPONSE_CHANNELS", str(FREE_RESPONSE_CHANNEL_ID))
    monkeypatch.delenv("DISCORD_AUTO_THREAD", raising=False)
    monkeypatch.delenv("DISCORD_NO_THREAD_CHANNELS", raising=False)

    adapter._auto_create_thread = AsyncMock()

    message = make_message(
        channel=FakeTextChannel(channel_id=FREE_RESPONSE_CHANNEL_ID, name="general"),
        content="reply without mention",
        msg_type=discord_platform.discord.MessageType.reply,
    )

    await adapter._handle_message(message)

    adapter._auto_create_thread.assert_not_awaited()
    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.source.chat_type == "group"
    assert event.source.chat_id == str(FREE_RESPONSE_CHANNEL_ID)
