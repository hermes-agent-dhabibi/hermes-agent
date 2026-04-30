"""Tests for the fork-local Discord adapter layer."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.local.discord_adapter import LocalDiscordAdapter
from gateway.platforms.base import SendResult
from gateway.platforms.discord import DiscordAdapter
from gateway.run import GatewayRunner


def test_local_discord_adapter_subclasses_upstream_adapter():
    assert issubclass(LocalDiscordAdapter, DiscordAdapter)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("LayoutView/TextDisplay/Container/Separator unavailable", True),
        ("discord.ui has no attribute 'LayoutView'", True),
        ("discord.ui has no attribute 'TextDisplay'", True),
        ("Container unsupported by this discord.py build", True),
        ("Separator unsupported by this discord.py build", True),
        ("send() got an unexpected keyword argument 'view'", True),
        ("unsupported layout view payload", True),
        ("unsupported component type 17", True),
        ("Invalid Form Body", False),
        ("foo is not a valid choice", False),
        ("View timed out", False),
        ("ReadTimeout while waiting for Discord", False),
    ],
)
def test_is_components_v2_structural_error_is_narrow(error, expected):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))

    assert adapter._is_components_v2_structural_error(error) is expected


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

    async def fake_send_components(chat_id, trace_state):
        calls.append({"chat_id": chat_id, "trace_state": trace_state})
        return SendResult(success=True, message_id="m1")

    monkeypatch.setattr(adapter, "_send_components_v2", fake_send_components)
    state = SimpleNamespace(chat_id="c1", reasoning_text="hello", tools=[])

    result = await adapter.send_trace(state, metadata={"thread_id": "t1"})

    assert result.success is True
    assert calls == [{"chat_id": "t1", "trace_state": state}]


@pytest.mark.asyncio
async def test_local_discord_adapter_send_components_v2_uses_view_signature(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))

    class StrictChannel:
        def __init__(self):
            self.calls = []

        async def send(self, *, content=None, reference=None, view=None):
            self.calls.append({"content": content, "reference": reference, "view": view})
            return SimpleNamespace(id=1234)

    channel = StrictChannel()
    adapter._client = SimpleNamespace(
        get_channel=lambda channel_id: channel,
        fetch_channel=None,
    )
    built_view = object()
    build_calls = []

    def fake_build_view(trace_state):
        build_calls.append(trace_state)
        return built_view

    monkeypatch.setattr("gateway.local.discord_adapter.build_trace_layout_view", fake_build_view)

    state = SimpleNamespace(chat_id="c1", reasoning_text="hello", tools=[])

    result = await adapter._send_components_v2("42", state)

    assert result.success is True
    assert build_calls == [state]
    assert channel.calls == [{"content": None, "reference": None, "view": built_view}]
    assert result.raw_response == {"components_v2": True}


@pytest.mark.asyncio
async def test_local_discord_adapter_edit_components_v2_uses_view_signature(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))

    class StrictPartialMessage:
        def __init__(self):
            self.calls = []

        async def edit(self, *, content=None, view=None):
            self.calls.append({"content": content, "view": view})
            return SimpleNamespace(id=999)

    partial = StrictPartialMessage()

    class StrictChannel:
        def get_partial_message(self, message_id):
            assert message_id == 55
            return partial

    channel = StrictChannel()
    adapter._client = SimpleNamespace(
        get_channel=lambda channel_id: channel,
        fetch_channel=None,
    )
    built_view = object()
    build_calls = []

    def fake_build_view(trace_state):
        build_calls.append(trace_state)
        return built_view

    monkeypatch.setattr("gateway.local.discord_adapter.build_trace_layout_view", fake_build_view)

    state = SimpleNamespace(chat_id="c1", reasoning_text="hello", tools=[])

    result = await adapter._edit_components_v2("42", "55", state)

    assert result.success is True
    assert build_calls == [state]
    assert partial.calls == [{"content": None, "view": built_view}]
    assert result.raw_response == {"components_v2": True}


@pytest.mark.asyncio
async def test_local_discord_adapter_trace_text_fallback(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    calls = []

    async def fake_send_components(chat_id, trace_state):
        return SendResult(
            success=False,
            error="components unsupported",
            raw_response={"components_v2": True, "failure_kind": "structural"},
        )

    async def fake_send(chat_id, content, reply_to=None, metadata=None):
        calls.append({"chat_id": chat_id, "content": content, "metadata": metadata})
        return SendResult(success=True, message_id="m1")

    monkeypatch.setattr(adapter, "_send_components_v2", fake_send_components)
    monkeypatch.setattr(adapter, "send", fake_send)
    state = SimpleNamespace(chat_id="c1", fallback_text=lambda: "💭 Thinking\n> hello")

    result = await adapter.send_trace(state, metadata={"thread_id": "t1"})

    assert result.success is True
    assert calls == [
        {"chat_id": "t1", "content": "💭 Thinking\n> hello", "metadata": None}
    ]
    assert result.raw_response == {
        "effective_chat_id": "t1",
        "components_v2": False,
    }


@pytest.mark.asyncio
async def test_local_discord_adapter_send_trace_forum_parent_reuses_forum_aware_send(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    forum_channel = SimpleNamespace(id=42, type=15)
    adapter._client = SimpleNamespace(
        get_channel=lambda channel_id: forum_channel,
        fetch_channel=None,
    )
    component_calls = []
    send_calls = []

    async def fake_send_components(chat_id, trace_state):
        component_calls.append({"chat_id": chat_id, "trace_state": trace_state})
        return SendResult(success=True, message_id="m-components")

    async def fake_send(chat_id, content, reply_to=None, metadata=None):
        send_calls.append({"chat_id": chat_id, "content": content, "metadata": metadata})
        return SendResult(success=True, message_id="m-forum", raw_response={"thread_id": "thread-99"})

    monkeypatch.setattr(adapter, "_send_components_v2", fake_send_components)
    monkeypatch.setattr(adapter, "send", fake_send)

    state = SimpleNamespace(chat_id="42", reasoning_text="hello", tools=[], fallback_text=lambda: "forum trace")

    result = await adapter.send_trace(state)

    assert component_calls == []
    assert send_calls == [{"chat_id": "42", "content": "forum trace", "metadata": None}]
    assert result.success is True
    assert result.raw_response == {
        "thread_id": "thread-99",
        "effective_chat_id": "thread-99",
        "components_v2": False,
    }


@pytest.mark.asyncio
async def test_local_discord_adapter_send_trace_returns_transient_failure_without_fallback(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    component_calls = []
    fallback_calls = []
    state = SimpleNamespace(chat_id="c1", fallback_text=lambda: "ignored")

    async def fake_send_components(chat_id, trace_state):
        component_calls.append({"chat_id": chat_id, "trace_state": trace_state})
        return SendResult(
            success=False,
            error="ConnectionError: reset by peer",
            retryable=True,
            raw_response={"components_v2": True, "failure_kind": "transient"},
        )

    async def fake_send(chat_id, content, reply_to=None, metadata=None):
        fallback_calls.append({"chat_id": chat_id, "content": content, "metadata": metadata})
        return SendResult(success=True, message_id="fallback")

    monkeypatch.setattr(adapter, "_send_components_v2", fake_send_components)
    monkeypatch.setattr(adapter, "send", fake_send)

    result = await adapter.send_trace(state)

    assert result.success is False
    assert result.retryable is True
    assert result.error == "ConnectionError: reset by peer"
    assert result.raw_response == {"components_v2": True, "failure_kind": "transient"}
    assert component_calls == [{"chat_id": "c1", "trace_state": state}]
    assert fallback_calls == []
    assert adapter._trace_components_v2_disabled is False


@pytest.mark.asyncio
async def test_local_discord_adapter_send_trace_latches_after_structural_failure(monkeypatch, caplog):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    component_calls = []
    fallback_calls = []

    async def fake_send_components(chat_id, trace_state):
        component_calls.append({"chat_id": chat_id, "trace_state": trace_state})
        return SendResult(
            success=False,
            error="LayoutView unsupported",
            raw_response={"components_v2": True, "failure_kind": "structural"},
        )

    async def fake_send(chat_id, content, reply_to=None, metadata=None):
        fallback_calls.append({"chat_id": chat_id, "content": content})
        return SendResult(success=True, message_id=f"m{len(fallback_calls)}")

    monkeypatch.setattr(adapter, "_send_components_v2", fake_send_components)
    monkeypatch.setattr(adapter, "send", fake_send)

    first_state = SimpleNamespace(chat_id="c1", fallback_text=lambda: "first")
    second_state = SimpleNamespace(chat_id="c1", fallback_text=lambda: "second")

    with caplog.at_level(logging.WARNING, logger="gateway.local.discord_adapter"):
        first = await adapter.send_trace(first_state)
        second = await adapter.send_trace(second_state)

    assert first.success is True
    assert second.success is True
    assert adapter._trace_components_v2_disabled is True
    assert len(component_calls) == 1
    assert fallback_calls == [
        {"chat_id": "c1", "content": "first"},
        {"chat_id": "c1", "content": "second"},
    ]
    warnings = [
        record.message
        for record in caplog.records
        if "trace components" in record.message.lower() and "plain text" in record.message.lower()
    ]
    assert len(warnings) == 1


@pytest.mark.asyncio
async def test_local_discord_adapter_edit_trace_returns_ambiguous_failure_without_fallback(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    component_calls = []
    fallback_calls = []
    state = SimpleNamespace(chat_id="c1", fallback_text=lambda: "ignored")

    async def fake_edit_components(chat_id, message_id, trace_state):
        component_calls.append({"chat_id": chat_id, "message_id": message_id, "trace_state": trace_state})
        return SendResult(
            success=False,
            error="ReadTimeout while waiting for Discord",
            raw_response={"components_v2": True, "failure_kind": "ambiguous"},
        )

    async def fake_edit_message(chat_id, message_id, content, finalize=False):
        fallback_calls.append({"chat_id": chat_id, "message_id": message_id, "content": content, "finalize": finalize})
        return SendResult(success=True, message_id=message_id)

    monkeypatch.setattr(adapter, "_edit_components_v2", fake_edit_components)
    monkeypatch.setattr(adapter, "edit_message", fake_edit_message)

    result = await adapter.edit_trace("m1", state)

    assert result.success is False
    assert result.retryable is False
    assert result.error == "ReadTimeout while waiting for Discord"
    assert result.raw_response == {"components_v2": True, "failure_kind": "ambiguous"}
    assert component_calls == [{"chat_id": "c1", "message_id": "m1", "trace_state": state}]
    assert fallback_calls == []
    assert adapter._trace_components_v2_disabled is False


@pytest.mark.asyncio
async def test_local_discord_adapter_edit_trace_latches_after_structural_failure(monkeypatch, caplog):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    component_calls = []
    fallback_calls = []

    async def fake_edit_components(chat_id, message_id, trace_state):
        component_calls.append({"chat_id": chat_id, "message_id": message_id, "trace_state": trace_state})
        return SendResult(
            success=False,
            error="TextDisplay unsupported",
            raw_response={"components_v2": True, "failure_kind": "structural"},
        )

    async def fake_edit_message(chat_id, message_id, content, finalize=False):
        fallback_calls.append({"chat_id": chat_id, "message_id": message_id, "content": content, "finalize": finalize})
        return SendResult(success=True, message_id=message_id)

    monkeypatch.setattr(adapter, "_edit_components_v2", fake_edit_components)
    monkeypatch.setattr(adapter, "edit_message", fake_edit_message)

    first_state = SimpleNamespace(chat_id="c1", fallback_text=lambda: "first edit")
    second_state = SimpleNamespace(chat_id="c1", fallback_text=lambda: "second edit")

    with caplog.at_level(logging.WARNING, logger="gateway.local.discord_adapter"):
        first = await adapter.edit_trace("m1", first_state)
        second = await adapter.edit_trace("m1", second_state)

    assert first.success is True
    assert second.success is True
    assert adapter._trace_components_v2_disabled is True
    assert len(component_calls) == 1
    assert fallback_calls == [
        {"chat_id": "c1", "message_id": "m1", "content": "first edit", "finalize": False},
        {"chat_id": "c1", "message_id": "m1", "content": "second edit", "finalize": False},
    ]
    assert first.raw_response == {
        "effective_chat_id": "c1",
        "components_v2": False,
    }
    assert second.raw_response == {
        "effective_chat_id": "c1",
        "components_v2": False,
    }
    warnings = [
        record.message
        for record in caplog.records
        if "trace components" in record.message.lower() and "plain text" in record.message.lower()
    ]
    assert len(warnings) == 1


@pytest.mark.asyncio
async def test_local_discord_adapter_edit_trace_uses_effective_forum_thread_target(monkeypatch):
    adapter = LocalDiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    component_calls = []
    edit_calls = []

    async def fake_edit_components(chat_id, message_id, trace_state):
        component_calls.append({"chat_id": chat_id, "message_id": message_id})
        return SendResult(success=True, message_id=message_id)

    async def fake_edit_message(chat_id, message_id, content, finalize=False):
        edit_calls.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "content": content,
                "finalize": finalize,
            }
        )
        return SendResult(success=True, message_id=message_id)

    monkeypatch.setattr(adapter, "_edit_components_v2", fake_edit_components)
    monkeypatch.setattr(adapter, "edit_message", fake_edit_message)

    state = SimpleNamespace(
        chat_id="42",
        target_chat_id="thread-99",
        fallback_text=lambda: "forum trace edit",
    )

    result = await adapter.edit_trace("m-forum", state)

    assert component_calls == []
    assert edit_calls == [
        {
            "chat_id": "thread-99",
            "message_id": "m-forum",
            "content": "forum trace edit",
            "finalize": False,
        }
    ]
    assert result.raw_response == {
        "effective_chat_id": "thread-99",
        "components_v2": False,
    }
