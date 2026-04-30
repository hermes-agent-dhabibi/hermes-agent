"""Tests for fork-local Discord Components V2 trace rendering."""

from __future__ import annotations

from gateway.local.discord_components import (
    IS_COMPONENTS_V2,
    TYPE_CONTAINER,
    TYPE_SEPARATOR,
    TYPE_TEXT_DISPLAY,
    DiscordTraceRenderState,
    ToolTraceItem,
    build_trace_components_payload,
    render_trace_fallback_text,
)


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
