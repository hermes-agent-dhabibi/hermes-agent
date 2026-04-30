"""Local Discord adapter overrides for this Hermes fork."""

from __future__ import annotations

import dataclasses
import inspect
from typing import Any, Optional

from gateway.local.discord_components import (
    build_trace_layout_view,
    render_trace_fallback_text,
)
from gateway.platforms.base import SendResult
from gateway.platforms.discord import DiscordAdapter


class LocalDiscordAdapter(DiscordAdapter):
    """Fork-local Discord adapter.

    This class is the home for Discord UX behavior that belongs to this fork.
    It deliberately subclasses the upstream-shaped ``DiscordAdapter`` so the
    fork keeps inheriting protocol, event-ingestion, slash-command, and general
    Discord API fixes from upstream.
    """

    supports_trace_components = True

    def __init__(self, config):
        super().__init__(config)
        self._trace_components_v2_disabled = False

    def _trace_target_chat_id(
        self,
        trace_state: Any,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        if metadata and metadata.get("thread_id"):
            return str(metadata["thread_id"])
        target_chat_id = getattr(trace_state, "target_chat_id", None)
        if target_chat_id:
            return str(target_chat_id)
        return str(getattr(trace_state, "chat_id", "") or "")

    def _trace_effective_chat_id(self, result: SendResult, *, fallback_chat_id: str) -> str:
        raw_response = result.raw_response if isinstance(result.raw_response, dict) else {}
        effective_chat_id = raw_response.get("effective_chat_id") or raw_response.get("thread_id")
        return str(effective_chat_id or fallback_chat_id or "")

    def _with_trace_target(
        self,
        result: SendResult,
        *,
        fallback_chat_id: str,
        components_v2: bool | None = None,
    ) -> SendResult:
        raw_response = dict(result.raw_response or {}) if isinstance(result.raw_response, dict) else {}
        effective_chat_id = self._trace_effective_chat_id(result, fallback_chat_id=fallback_chat_id)
        if effective_chat_id:
            raw_response.setdefault("effective_chat_id", effective_chat_id)
        if components_v2 is not None:
            raw_response["components_v2"] = components_v2
        return dataclasses.replace(result, raw_response=raw_response)

    def _trace_prefers_text_edit(self, trace_state: Any, metadata: Optional[dict[str, Any]] = None) -> bool:
        if metadata and metadata.get("thread_id"):
            return False
        original_chat_id = str(getattr(trace_state, "chat_id", "") or "")
        target_chat_id = str(getattr(trace_state, "target_chat_id", "") or "")
        return bool(original_chat_id and target_chat_id and target_chat_id != original_chat_id)

    def _is_components_v2_structural_error(self, error: str | None) -> bool:
        text = str(error or "").lower()
        if not text:
            return False
        structural_markers = (
            "layoutview",
            "textdisplay",
            "container",
            "separator",
            "view",
            "unexpected keyword argument 'flags'",
            "unexpected keyword argument 'components'",
            "unsupported component",
            "unsupported layout",
            "invalid form body",
            "not a valid",
            "must be an instance of view",
            "missing required positional argument",
            "takes 1 positional argument",
        )
        return any(marker in text for marker in structural_markers)

    def _latch_components_v2_fallback(self, result: SendResult) -> None:
        if not result.success and self._is_components_v2_structural_error(result.error):
            self._trace_components_v2_disabled = True

    def _trace_fallback_text(self, trace_state: Any, default: str) -> str:
        content = getattr(trace_state, "fallback_text", None)
        if callable(content):
            content = content()
        if not isinstance(content, str) or not content.strip():
            content = render_trace_fallback_text(trace_state)
        if not isinstance(content, str) or not content.strip():
            content = default
        return content

    async def _resolve_channel(self, chat_id: str) -> Any:
        if not self._client:
            return None
        channel = self._client.get_channel(int(chat_id))
        if channel:
            return channel
        fetch_channel = getattr(self._client, "fetch_channel", None)
        if fetch_channel is None:
            return None
        result = fetch_channel(int(chat_id))
        if inspect.isawaitable(result):
            return await result
        return result

    async def _send_components_v2(
        self,
        chat_id: str,
        trace_state: Any,
    ) -> SendResult:
        if not self._client:
            return SendResult(success=False, error="Not connected")
        try:
            channel = await self._resolve_channel(chat_id)
            if not channel:
                return SendResult(success=False, error=f"Channel {chat_id} not found")
            view = build_trace_layout_view(trace_state)
            msg = await channel.send(content=None, reference=None, view=view)
            return SendResult(success=True, message_id=str(msg.id), raw_response={"components_v2": True})
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    async def _edit_components_v2(
        self,
        chat_id: str,
        message_id: str,
        trace_state: Any,
    ) -> SendResult:
        if not self._client:
            return SendResult(success=False, error="Not connected")
        try:
            channel = await self._resolve_channel(chat_id)
            if not channel:
                return SendResult(success=False, error=f"Channel {chat_id} not found")
            partial = channel.get_partial_message(int(message_id))
            view = build_trace_layout_view(trace_state)
            await partial.edit(content=None, view=view)
            return SendResult(success=True, message_id=message_id, raw_response={"components_v2": True})
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    async def send_trace(
        self,
        trace_state: Any,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        """Send a Discord trace message as Components V2."""
        chat_id = self._trace_target_chat_id(trace_state, metadata)
        if not chat_id:
            return SendResult(success=False, error="trace_state missing chat_id")
        channel = await self._resolve_channel(chat_id)
        if channel is not None and self._is_forum_parent(channel) and not (metadata and metadata.get("thread_id")):
            content = self._trace_fallback_text(trace_state, "💭 Trace started")
            result = await self.send(str(getattr(trace_state, "chat_id", "") or chat_id), content, metadata=metadata)
            return self._with_trace_target(result, fallback_chat_id=chat_id, components_v2=False)
        if not self._trace_components_v2_disabled:
            result = await self._send_components_v2(chat_id, trace_state)
            if result.success:
                return self._with_trace_target(result, fallback_chat_id=chat_id, components_v2=True)
            self._latch_components_v2_fallback(result)
        content = self._trace_fallback_text(trace_state, "💭 Trace started")
        result = await self.send(chat_id, content, metadata=None)
        return self._with_trace_target(result, fallback_chat_id=chat_id, components_v2=False)

    async def edit_trace(
        self,
        message_id: str,
        trace_state: Any,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        """Edit a Discord trace message as Components V2."""
        chat_id = self._trace_target_chat_id(trace_state, metadata)
        if not chat_id:
            return SendResult(success=False, error="trace_state missing chat_id")
        if not self._trace_prefers_text_edit(trace_state, metadata) and not self._trace_components_v2_disabled:
            result = await self._edit_components_v2(chat_id, message_id, trace_state)
            if result.success:
                return self._with_trace_target(result, fallback_chat_id=chat_id, components_v2=True)
            self._latch_components_v2_fallback(result)
        content = self._trace_fallback_text(trace_state, "💭 Trace updated")
        result = await self.edit_message(chat_id, message_id, content)
        return self._with_trace_target(result, fallback_chat_id=chat_id, components_v2=False)
