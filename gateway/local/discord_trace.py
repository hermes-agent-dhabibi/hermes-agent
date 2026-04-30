"""Structured Discord trace state for fork-local gateway UX."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from gateway.local.discord_components import (
    ToolTraceItem,
    build_trace_components_payload,
    render_trace_fallback_text,
)
from gateway.platforms.base import SendResult

TraceEventKind = Literal[
    "reasoning.delta",
    "assistant.commentary",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "gateway.lifecycle",
    "approval.requested",
    "interrupt",
    "suppression",
]


@dataclass
class TraceEvent:
    kind: TraceEventKind
    text: str | None = None
    tool_name: str | None = None
    preview: str | None = None
    args: dict[str, Any] | None = None
    ts: float = field(default_factory=time.monotonic)


@dataclass
class DiscordTraceState:
    chat_id: str
    reasoning_text: str = ""
    tools: list[ToolTraceItem] = field(default_factory=list)
    message_id: str | None = None
    finalized: bool = False
    last_rendered_hash: str | None = None

    def fallback_text(self) -> str:
        return render_trace_fallback_text(self)


_HEADING_RE = re.compile(r"(?m)^\*\*([^\n*][^\n]*?)\*\*\s*\n\n")


def dedupe_reasoning_replay(text: str) -> str:
    """Collapse a provider replaying a full reasoning summary after a prefix."""
    text = str(text or "").strip()
    if not text:
        return ""
    match = _HEADING_RE.search(text)
    if not match:
        return text
    heading_block = match.group(0)
    second_idx = text.find(heading_block, match.end())
    if second_idx == -1:
        return text
    first_body = text[match.end():second_idx].strip()
    second_body = text[second_idx + len(heading_block):].strip()
    if first_body and second_body:
        if second_body.startswith(first_body):
            return f"{heading_block}{second_body}".strip()
        if first_body.startswith(second_body):
            return f"{heading_block}{first_body}".strip()
    if second_body:
        return f"{heading_block}{second_body}".strip()
    return text


class DiscordTraceSink:
    """Per-turn trace collector that sends/edits one Discord trace message."""

    def __init__(
        self,
        adapter: Any,
        *,
        chat_id: str,
        metadata: Optional[dict[str, Any]] = None,
        is_active: Callable[[], bool] | None = None,
        show_reasoning: bool = True,
        show_tools: bool = True,
        min_reasoning_chars: int = 240,
        min_interval: float = 1.5,
    ):
        self.adapter = adapter
        self.metadata = metadata
        self._is_active_callback = is_active
        self.show_reasoning = show_reasoning
        self.show_tools = show_tools
        self.min_reasoning_chars = min_reasoning_chars
        self.min_interval = min_interval
        self.state = DiscordTraceState(chat_id=str(chat_id))
        self._reasoning_buffer: list[str] = []
        self._last_flush = time.monotonic()
        self._flush_lock = asyncio.Lock()
        self._cancelled = False

    @property
    def closed(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def is_active(self) -> bool:
        if self._cancelled:
            return False
        if self._is_active_callback is None:
            return True
        return bool(self._is_active_callback())

    def on_reasoning_delta(self, text: str) -> None:
        chunk = str(text or "")
        if not self.is_active():
            return
        if not self.show_reasoning or not chunk.strip():
            return
        if "reasoning.encrypted_content" in chunk:
            return
        self._reasoning_buffer.append(chunk)
        buffered = "".join(self._reasoning_buffer)
        if len(buffered.strip()) >= self.min_reasoning_chars:
            self.flush_reasoning_buffer(force=False)

    def on_tool_event(
        self,
        event_type: str,
        tool_name: str | None = None,
        preview: str | None = None,
        args: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        if not self.is_active():
            return
        if not self.show_tools or not tool_name:
            return
        if event_type not in {"tool.started", "tool.completed", "tool.failed"}:
            return
        status = event_type.split(".", 1)[1]
        preview_text = str(preview or "")
        if self.state.tools:
            last = self.state.tools[-1]
            if last.name == tool_name and last.preview == preview_text and last.status == status:
                last.count += 1
                return
        self.state.tools.append(ToolTraceItem(name=str(tool_name), preview=preview_text, status=status))

    def on_assistant_commentary(self, text: str) -> None:
        # Commentary is representable in the model but not rendered in the first
        # slice unless/until we add an explicit commentary component section.
        return

    def flush_reasoning_buffer(self, *, force: bool = False) -> None:
        if not self.is_active():
            return
        if not self._reasoning_buffer:
            return
        buffered = "".join(self._reasoning_buffer)
        if not buffered.strip():
            self._reasoning_buffer.clear()
            return
        now = time.monotonic()
        if not force and now - self._last_flush < self.min_interval:
            return
        combined = f"{self.state.reasoning_text}{buffered}"
        self.state.reasoning_text = dedupe_reasoning_replay(combined.strip())
        self._reasoning_buffer.clear()
        self._last_flush = now

    async def _flush_locked(self, *, force: bool = False) -> SendResult | None:
        if not self.is_active():
            return None
        self.flush_reasoning_buffer(force=force)
        if not self.is_active():
            return None
        if not self.state.reasoning_text and not self.state.tools:
            return None
        rendered_hash = repr(build_trace_components_payload(self.state))
        if not force and rendered_hash == self.state.last_rendered_hash:
            return None
        if not self.is_active():
            return None
        if self.state.message_id:
            result = await self.adapter.edit_trace(
                self.state.message_id,
                self.state,
                metadata=self.metadata,
            )
        else:
            result = await self.adapter.send_trace(self.state, metadata=self.metadata)
        if result and result.success:
            if not self.state.message_id and result.message_id:
                self.state.message_id = str(result.message_id)
            self.state.last_rendered_hash = rendered_hash
        return result

    async def flush(self, *, force: bool = False) -> SendResult | None:
        async with self._flush_lock:
            return await self._flush_locked(force=force)

    async def finish(self) -> SendResult | None:
        async with self._flush_lock:
            if not self.is_active():
                return None
            self.state.finalized = True
            return await self._flush_locked(force=True)
