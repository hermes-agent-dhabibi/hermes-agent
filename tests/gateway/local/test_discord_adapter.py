"""Tests for the fork-local Discord adapter layer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.local.discord_adapter import LocalDiscordAdapter
from gateway.platforms.discord import DiscordAdapter
from gateway.run import GatewayRunner


def test_local_discord_adapter_subclasses_upstream_adapter():
    assert issubclass(LocalDiscordAdapter, DiscordAdapter)


def test_gateway_uses_local_discord_adapter_for_discord(monkeypatch):
    import gateway.platforms.discord as discord_platform

    monkeypatch.setattr(discord_platform, "check_discord_requirements", lambda: True)
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.DISCORD: PlatformConfig(enabled=True, token="fake-token")}
    )

    adapter = runner._create_adapter(
        Platform.DISCORD,
        PlatformConfig(enabled=True, token="fake-token"),
    )

    assert isinstance(adapter, LocalDiscordAdapter)


@pytest.mark.asyncio
async def test_local_discord_adapter_trace_uses_components_v2(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    calls = []

    async def fake_send_components(chat_id, payload):
        calls.append({"chat_id": chat_id, "payload": payload})
        from gateway.platforms.base import SendResult

        return SendResult(success=True, message_id="m1")

    monkeypatch.setattr(adapter, "_send_components_v2", fake_send_components)
    state = SimpleNamespace(chat_id="c1", reasoning_text="hello", tools=[])

    result = await adapter.send_trace(state, metadata={"thread_id": "t1"})

    assert result.success is True
    assert calls[0]["chat_id"] == "t1"
    assert calls[0]["payload"]["flags"] == 32768
    assert "content" not in calls[0]["payload"]


@pytest.mark.asyncio
async def test_local_discord_adapter_trace_text_fallback(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    calls = []

    async def fake_send_components(chat_id, payload):
        from gateway.platforms.base import SendResult

        return SendResult(success=False, error="components unsupported")

    async def fake_send(chat_id, content, reply_to=None, metadata=None):
        calls.append({"chat_id": chat_id, "content": content, "metadata": metadata})
        from gateway.platforms.base import SendResult

        return SendResult(success=True, message_id="m1")

    monkeypatch.setattr(adapter, "_send_components_v2", fake_send_components)
    monkeypatch.setattr(adapter, "send", fake_send)
    state = SimpleNamespace(chat_id="c1", fallback_text=lambda: "💭 Thinking\n> hello")

    result = await adapter.send_trace(state, metadata={"thread_id": "t1"})

    assert result.success is True
    assert calls == [
        {"chat_id": "t1", "content": "💭 Thinking\n> hello", "metadata": None}
    ]
