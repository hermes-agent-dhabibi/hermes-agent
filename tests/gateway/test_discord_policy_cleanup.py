"""Regression tests for Discord channel policy cleanup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig


import plugins.platforms.discord.adapter as discord_platform  # noqa: E402
from gateway.config import Platform, load_gateway_config  # noqa: E402
from plugins.platforms.discord.adapter import DiscordAdapter  # noqa: E402


class FakeDMChannel(discord_platform.discord.DMChannel):
    def __init__(self, channel_id=1):
        self.id = channel_id
        self.name = "dm"


class FakeTextChannel:
    def __init__(self, channel_id=1, *, guild=None, name="general", perms=None):
        self.id = channel_id
        self.name = name
        self.guild = guild or SimpleNamespace(id=1234, name="Hermes Server", me=SimpleNamespace(id=999))
        self.topic = None
        self.sent = []
        self._perms = perms

    def permissions_for(self, member):
        return self._perms if self._perms is not None else SimpleNamespace(
            view_channel=True,
            send_messages=True,
            send_messages_in_threads=True,
            create_public_threads=True,
        )

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return SimpleNamespace(id=777)

    async def create_thread(self, *args, **kwargs):
        return FakeThread(channel_id=333, parent=self)


class FakeThread(discord_platform.discord.Thread):
    def __init__(self, channel_id=1, *, parent=None, name="thread", perms=None):
        self.id = channel_id
        self.name = name
        self.parent = parent
        self.parent_id = getattr(parent, "id", None)
        self.guild = getattr(parent, "guild", None) or SimpleNamespace(name="Hermes Server", me=SimpleNamespace(id=999))
        self.topic = None
        self.sent = []
        self._perms = perms

    def permissions_for(self, member):
        return self._perms if self._perms is not None else SimpleNamespace(
            view_channel=True,
            send_messages=True,
            send_messages_in_threads=True,
            create_public_threads=True,
        )

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return SimpleNamespace(id=778)


@pytest.fixture(autouse=True)
def _patch_discord_types(monkeypatch):
    monkeypatch.setattr(discord_platform.discord, "DMChannel", FakeDMChannel, raising=False)
    monkeypatch.setattr(discord_platform.discord, "Thread", FakeThread, raising=False)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for key in (
        "DISCORD_REQUIRE_MENTION",
        "DISCORD_FREE_RESPONSE_CHANNELS",
        "DISCORD_AUTO_THREAD",
        "DISCORD_NO_THREAD_CHANNELS",
        "DISCORD_IGNORED_CHANNELS",
        "DISCORD_ALLOWED_CHANNELS",
        "DISCORD_HOME_CHANNEL",
        "DISCORD_HOME_CHANNEL_NAME",
        "DISCORD_HOME_CHANNEL_THREAD_ID",
        "DISCORD_BOT_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def adapter():
    a = DiscordAdapter(PlatformConfig(enabled=True, token="fake-token"))
    a._client = SimpleNamespace(user=SimpleNamespace(id=999), guilds=[])
    a._text_batch_delay_seconds = 0
    a.handle_message = AsyncMock()
    return a


def make_message(*, channel, content="hello", mentions=None):
    return SimpleNamespace(
        id=123,
        content=content,
        mentions=list(mentions or []),
        attachments=[],
        reference=None,
        channel=channel,
        author=SimpleNamespace(id=42, display_name="Danny", name="Danny", bot=False),
        type=discord_platform.discord.MessageType.default,
        created_at=None,
        guild=getattr(channel, "guild", None),
    )


@pytest.mark.asyncio
async def test_free_response_channel_still_auto_threads(adapter, monkeypatch):
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    monkeypatch.setenv("DISCORD_FREE_RESPONSE_CHANNELS", "789")

    fake_thread = FakeThread(channel_id=999, parent=FakeTextChannel(channel_id=789))
    adapter._auto_create_thread = AsyncMock(return_value=fake_thread)

    await adapter._handle_message(make_message(channel=FakeTextChannel(channel_id=789), content="free chat"))

    adapter._auto_create_thread.assert_awaited_once()
    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.source.chat_type == "thread"
    assert event.source.thread_id == "999"


@pytest.mark.asyncio
async def test_ignored_parent_hard_denies_free_response_thread(adapter, monkeypatch):
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    monkeypatch.setenv("DISCORD_FREE_RESPONSE_CHANNELS", "789")
    monkeypatch.setenv("DISCORD_IGNORED_CHANNELS", "789")
    parent = FakeTextChannel(channel_id=789)
    thread = FakeThread(channel_id=790, parent=parent)

    await adapter._handle_message(make_message(channel=thread, content="ignored despite free-response parent"))

    adapter.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_participated_thread_does_not_bypass_ignored_thread(adapter, monkeypatch):
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    monkeypatch.setenv("DISCORD_IGNORED_CHANNELS", "790")
    parent = FakeTextChannel(channel_id=789)
    thread = FakeThread(channel_id=790, parent=parent)
    adapter._threads.mark("790")

    await adapter._handle_message(make_message(channel=thread, content="followup in participated ignored thread"))

    adapter.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_denied_by_ignored_parent(adapter, monkeypatch):
    monkeypatch.setenv("DISCORD_IGNORED_CHANNELS", "789")
    parent = FakeTextChannel(channel_id=789)
    thread = FakeThread(channel_id=790, parent=parent)
    adapter._client = SimpleNamespace(get_channel=lambda _id: thread, fetch_channel=AsyncMock(), user=SimpleNamespace(id=999), guilds=[])

    result = await adapter.send("789", "should not send", metadata={"thread_id": "790"})

    assert result.success is False
    assert "DISCORD_IGNORED_CHANNELS" in (result.error or "")
    assert thread.sent == []


@pytest.mark.asyncio
async def test_effective_permission_deny_blocks_processing(adapter):
    perms = SimpleNamespace(view_channel=False, send_messages=True, send_messages_in_threads=True, create_public_threads=True)
    channel = FakeTextChannel(channel_id=789, perms=perms)

    await adapter._handle_message(make_message(channel=channel, content="<@999> hello", mentions=[adapter._client.user]))

    adapter.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_effective_permission_deny_blocks_send(adapter):
    perms = SimpleNamespace(view_channel=True, send_messages=False, send_messages_in_threads=True, create_public_threads=True)
    channel = FakeTextChannel(channel_id=789, perms=perms)
    adapter._client = SimpleNamespace(get_channel=lambda _id: channel, fetch_channel=AsyncMock(), user=SimpleNamespace(id=999), guilds=[])

    result = await adapter.send("789", "blocked")

    assert result.success is False
    assert "send_messages" in (result.error or "")
    assert channel.sent == []


def test_discord_home_channel_loaded_from_config_yaml(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "discord:\n"
        "  enabled: true\n"
        "  home_channel:\n"
        "    chat_id: '12345'\n"
        "    name: Ops\n"
        "    thread_id: '67890'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    config = load_gateway_config()
    home = config.platforms[Platform.DISCORD].home_channel

    assert home is not None
    assert home.chat_id == "12345"
    assert home.name == "Ops"
    assert home.thread_id == "67890"


def test_discord_home_channel_env_overrides_config_yaml(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "discord:\n"
        "  enabled: true\n"
        "  home_channel:\n"
        "    chat_id: 'from-config'\n"
        "    name: Config Home\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("DISCORD_HOME_CHANNEL", "from-env")
    monkeypatch.setenv("DISCORD_HOME_CHANNEL_NAME", "Env Home")

    config = load_gateway_config()
    home = config.platforms[Platform.DISCORD].home_channel

    assert home is not None
    assert home.chat_id == "from-env"
    assert home.name == "Env Home"
