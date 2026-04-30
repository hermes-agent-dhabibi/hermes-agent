"""Tests for fork-local Discord Components V2 trace rendering."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import gateway.local.discord_components as discord_components
from gateway.local.discord_components import (
    IS_COMPONENTS_V2,
    TRACE_ACCENT_COLOR,
    TYPE_CONTAINER,
    TYPE_SEPARATOR,
    TYPE_TEXT_DISPLAY,
    DiscordTraceRenderState,
    ToolTraceItem,
    build_trace_components_payload,
    build_trace_layout_view,
    render_trace_fallback_text,
)


@pytest.fixture(autouse=True)
def _ensure_redaction_enabled(monkeypatch):
    monkeypatch.delenv("HERMES_REDACT_SECRETS", raising=False)
    monkeypatch.setattr("agent.redact._REDACT_ENABLED", True)


def _flatten_components(payload):
    out = []

    def walk(items):
        for item in items:
            out.append(item)
            walk(item.get("components", []))

    walk(payload.get("components", []))
    return out



def test_trace_payload_uses_components_v2_without_content_or_embeds():
    state = DiscordTraceRenderState(
        reasoning_text="Checking the repo before editing.",
        tools=[ToolTraceItem(name="search_files", preview="reasoning_callback")],
    )

    payload = build_trace_components_payload(state)

    assert payload["flags"] == IS_COMPONENTS_V2
    assert "content" not in payload
    assert "embeds" not in payload
    assert payload["components"][0]["type"] == TYPE_CONTAINER
    components = _flatten_components(payload)
    assert any(c["type"] == TYPE_TEXT_DISPLAY for c in components)
    assert any(c["type"] == TYPE_SEPARATOR for c in components)
    assert len(components) <= 40



def test_trace_payload_suppresses_encrypted_reasoning():
    state = DiscordTraceRenderState(
        reasoning_text="reasoning.encrypted_content: secret blob",
        tools=[],
    )

    payload = build_trace_components_payload(state)
    rendered = str(payload)

    assert "encrypted_content" not in rendered
    assert "Waiting for reasoning" in rendered



def test_trace_payload_defensively_redacts_reasoning_and_tool_preview():
    reasoning_secret = "Authorization: Bearer sk-proj-abc123def456ghi7890"
    preview_secret = "token: ghp_abcdefghijklmnopqrstuvwxyz123456"
    state = DiscordTraceRenderState(
        reasoning_text=reasoning_secret,
        tools=[ToolTraceItem(name="read_file", preview=preview_secret)],
    )

    payload = build_trace_components_payload(state)
    fallback = render_trace_fallback_text(state)
    rendered = str(payload)

    assert "sk-proj-abc123def456ghi7890" not in rendered
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in rendered
    assert "sk-proj-abc123def456ghi7890" not in fallback
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in fallback
    assert "Authorization: Bearer ***" in rendered
    assert "ghp_ab" in rendered



def test_trace_payload_caps_long_reasoning_and_tool_list():
    state = DiscordTraceRenderState(
        reasoning_text="x" * 5000,
        tools=[ToolTraceItem(name=f"tool_{i}", preview="y" * 500) for i in range(20)],
    )

    payload = build_trace_components_payload(
        state,
        reasoning_limit=120,
        tool_limit=5,
        tool_preview_limit=30,
    )
    rendered = str(payload)

    assert "…" in rendered
    assert "tool_0" not in rendered
    assert "tool_15" in rendered
    assert "tool_19" in rendered
    assert len(_flatten_components(payload)) <= 40



def test_trace_layout_view_uses_layout_components(monkeypatch):
    class FakeLayoutView:
        def __init__(self, *, timeout=180.0):
            self.timeout = timeout
            self.children = []

        def add_item(self, item):
            self.children.append(item)
            return self

    class FakeContainer:
        def __init__(self, *children, accent_colour=None, accent_color=None, spoiler=False, id=None):
            self.children = list(children)
            self.accent_color = accent_color if accent_color is not None else accent_colour
            self.spoiler = spoiler
            self.id = id

        def add_item(self, item):
            self.children.append(item)
            return self

    class FakeTextDisplay:
        def __init__(self, content, *, id=None):
            self.content = content
            self.id = id

    class FakeSeparator:
        def __init__(self, *, visible=True, spacing=1, id=None):
            self.visible = visible
            self.spacing = spacing
            self.id = id

    fake_discord = SimpleNamespace(
        ui=SimpleNamespace(
            LayoutView=FakeLayoutView,
            Container=FakeContainer,
            TextDisplay=FakeTextDisplay,
            Separator=FakeSeparator,
        )
    )
    monkeypatch.setattr(discord_components, "discord", fake_discord)

    state = DiscordTraceRenderState(
        reasoning_text="Thinking through the edit.",
        tools=[ToolTraceItem(name="read_file", preview="gateway/local/discord_adapter.py")],
    )

    view = build_trace_layout_view(state)

    assert isinstance(view, FakeLayoutView)
    assert view.timeout is None
    assert len(view.children) == 1
    container = view.children[0]
    assert isinstance(container, FakeContainer)
    assert container.accent_color == TRACE_ACCENT_COLOR
    assert [type(child) for child in container.children] == [
        FakeTextDisplay,
        FakeSeparator,
        FakeTextDisplay,
    ]
    assert container.children[0].content.startswith("### 💭 Thinking")
    assert container.children[2].content.startswith("### 🛠 Tools")



def test_trace_layout_view_requires_supported_discord_ui(monkeypatch):
    monkeypatch.setattr(discord_components, "discord", None)

    with pytest.raises(RuntimeError, match="LayoutView"):
        build_trace_layout_view(DiscordTraceRenderState(reasoning_text="hello"))



def test_trace_fallback_text_is_plain_markdown():
    state = DiscordTraceRenderState(
        reasoning_text="Line one\nLine two",
        tools=[ToolTraceItem(name="read_file", preview="/tmp/a.py")],
    )

    text = render_trace_fallback_text(state)

    assert "💭 **Thinking**" in text
    assert "> Line one" in text
    assert "🛠 **Tools**" in text
    assert "`read_file`" in text
