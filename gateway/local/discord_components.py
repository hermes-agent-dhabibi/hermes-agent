"""Discord Components V2 rendering for fork-local trace messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

IS_COMPONENTS_V2 = 1 << 15
TYPE_ACTION_ROW = 1
TYPE_TEXT_DISPLAY = 10
TYPE_SEPARATOR = 14
TYPE_CONTAINER = 17

TRACE_ACCENT_COLOR = 0x5865F2
MAX_COMPONENTS = 40
DEFAULT_REASONING_LIMIT = 1200
DEFAULT_TOOL_LIMIT = 10
DEFAULT_TOOL_PREVIEW_LIMIT = 220


@dataclass
class ToolTraceItem:
    """A compact tool trace row for Discord display."""

    name: str
    preview: str = ""
    status: str = "started"
    count: int = 1


@dataclass
class DiscordTraceRenderState:
    """Minimal render-state protocol for trace component tests and fallback."""

    reasoning_text: str = ""
    tools: list[ToolTraceItem] = field(default_factory=list)
    finalized: bool = False


def _clean_text(text: Any) -> str:
    text = str(text or "")
    if "reasoning.encrypted_content" in text:
        return ""
    # Discord markdown tolerates normal newlines; trim pathological whitespace
    # without destroying intentional paragraph breaks.
    return text.replace("\r\n", "\n").strip()


def _truncate(text: str, limit: int) -> str:
    text = _clean_text(text)
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _text_display(content: str) -> dict[str, Any]:
    return {"type": TYPE_TEXT_DISPLAY, "content": content}


def _separator() -> dict[str, Any]:
    return {"type": TYPE_SEPARATOR, "divider": True, "spacing": 1}


def _iter_tools(state: Any) -> Iterable[Any]:
    tools = getattr(state, "tools", None) or []
    return tools


def _tool_field(tool: Any, name: str, default: Any = "") -> Any:
    if isinstance(tool, dict):
        return tool.get(name, default)
    return getattr(tool, name, default)


def _render_tools_markdown(
    state: Any,
    *,
    tool_limit: int = DEFAULT_TOOL_LIMIT,
    preview_limit: int = DEFAULT_TOOL_PREVIEW_LIMIT,
) -> str:
    rendered: list[str] = []
    tools = list(_iter_tools(state))[-tool_limit:]
    for tool in tools:
        name = _truncate(_tool_field(tool, "name", "tool"), 80) or "tool"
        preview = _truncate(_tool_field(tool, "preview", ""), preview_limit)
        status = str(_tool_field(tool, "status", "started") or "started")
        count = int(_tool_field(tool, "count", 1) or 1)
        suffix = f" ×{count}" if count > 1 else ""
        icon = "✅" if status == "completed" else "❌" if status in {"failed", "error"} else "🛠"
        if preview:
            rendered.append(f"{icon} `{name}`{suffix}: `{preview}`")
        else:
            rendered.append(f"{icon} `{name}`{suffix}")
    return "\n".join(rendered)


def build_trace_components_payload(
    state: Any,
    *,
    accent_color: int = TRACE_ACCENT_COLOR,
    reasoning_limit: int = DEFAULT_REASONING_LIMIT,
    tool_limit: int = DEFAULT_TOOL_LIMIT,
    tool_preview_limit: int = DEFAULT_TOOL_PREVIEW_LIMIT,
) -> dict[str, Any]:
    """Build a Discord Components V2 payload for a trace state.

    The returned payload is intended for raw Discord message create/edit calls.
    Components V2 messages must not include top-level content or embeds.
    """
    reasoning = _truncate(getattr(state, "reasoning_text", ""), reasoning_limit)
    tools_md = _render_tools_markdown(
        state,
        tool_limit=tool_limit,
        preview_limit=tool_preview_limit,
    )

    children: list[dict[str, Any]] = []
    if reasoning:
        children.append(_text_display(f"### 💭 Thinking\n{reasoning}"))
    if reasoning and tools_md:
        children.append(_separator())
    if tools_md:
        children.append(_text_display(f"### 🛠 Tools\n{tools_md}"))
    if not children:
        children.append(_text_display("### Trace\nWaiting for reasoning or tool activity…"))

    # Reserve one component for the top-level container.
    children = children[: MAX_COMPONENTS - 1]
    return {
        "flags": IS_COMPONENTS_V2,
        "components": [
            {
                "type": TYPE_CONTAINER,
                "accent_color": int(accent_color) & 0xFFFFFF,
                "components": children,
            }
        ],
    }


def render_trace_fallback_text(
    state: Any,
    *,
    reasoning_limit: int = DEFAULT_REASONING_LIMIT,
    tool_limit: int = DEFAULT_TOOL_LIMIT,
    tool_preview_limit: int = DEFAULT_TOOL_PREVIEW_LIMIT,
) -> str:
    """Render trace state as plain markdown for non-component fallback."""
    parts: list[str] = []
    reasoning = _truncate(getattr(state, "reasoning_text", ""), reasoning_limit)
    if reasoning:
        quoted = "\n".join(f"> {line}" for line in reasoning.splitlines())
        parts.append(f"💭 **Thinking**\n{quoted}")
    tools_md = _render_tools_markdown(
        state,
        tool_limit=tool_limit,
        preview_limit=tool_preview_limit,
    )
    if tools_md:
        parts.append(f"🛠 **Tools**\n{tools_md}")
    return "\n\n".join(parts) or "Trace started"
