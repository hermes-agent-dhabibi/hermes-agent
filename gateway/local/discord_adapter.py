"""Local Discord adapter overrides for this Hermes fork."""

from __future__ import annotations

from typing import Any, Optional

from gateway.local.discord_components import build_trace_components_payload
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

    def _trace_target_chat_id(
        self,
        trace_state: Any,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        if metadata and metadata.get("thread_id"):
            return str(metadata["thread_id"])
        return str(getattr(trace_state, "chat_id", "") or "")

    async def _send_components_v2(
        self,
        chat_id: str,
        payload: dict[str, Any],
    ) -> SendResult:
        if not self._client:
            return SendResult(success=False, error="Not connected")
        try:
            channel = self._client.get_channel(int(chat_id))
            if not channel:
                channel = await self._client.fetch_channel(int(chat_id))
            if not channel:
                return SendResult(success=False, error=f"Channel {chat_id} not found")
            msg = await channel.send(**payload)
            return SendResult(success=True, message_id=str(msg.id), raw_response={"components_v2": True})
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    async def _edit_components_v2(
        self,
        chat_id: str,
        message_id: str,
        payload: dict[str, Any],
    ) -> SendResult:
        if not self._client:
            return SendResult(success=False, error="Not connected")
        try:
            channel = self._client.get_channel(int(chat_id))
            if not channel:
                channel = await self._client.fetch_channel(int(chat_id))
            if not channel:
                return SendResult(success=False, error=f"Channel {chat_id} not found")
            partial = channel.get_partial_message(int(message_id))
            await partial.edit(**payload)
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
        payload = build_trace_components_payload(trace_state)
        result = await self._send_components_v2(chat_id, payload)
        if result.success:
            return result
        # Components V2 can fail if the library/API shape changes. Fall back to
        # a compact markdown trace instead of losing the user's live feedback.
        content = getattr(trace_state, "fallback_text", None)
        if callable(content):
            content = content()
        if not isinstance(content, str) or not content.strip():
            content = "💭 Trace started"
        return await self.send(chat_id, content, metadata=None)

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
        payload = build_trace_components_payload(trace_state)
        result = await self._edit_components_v2(chat_id, message_id, payload)
        if result.success:
            return result
        content = getattr(trace_state, "fallback_text", None)
        if callable(content):
            content = content()
        if not isinstance(content, str) or not content.strip():
            content = "💭 Trace updated"
        return await self.edit_message(chat_id, message_id, content)
