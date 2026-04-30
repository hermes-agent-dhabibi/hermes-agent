"""Local Discord adapter overrides for this Hermes fork."""

from __future__ import annotations

from typing import Any, Optional

from gateway.platforms.base import SendResult
from gateway.platforms.discord import DiscordAdapter


class LocalDiscordAdapter(DiscordAdapter):
    """Fork-local Discord adapter.

    This class is the home for Discord UX behavior that belongs to this fork.
    It deliberately subclasses the upstream-shaped ``DiscordAdapter`` so the
    fork keeps inheriting protocol, event-ingestion, slash-command, and general
    Discord API fixes from upstream.
    """

    async def send_trace(
        self,
        trace_state: Any,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        """Send a Discord trace message.

        Placeholder for the Components V2 implementation. Until the trace
        renderer lands, fall back to a compact text representation when one is
        provided by the trace object.
        """
        content = getattr(trace_state, "fallback_text", None)
        if callable(content):
            content = content()
        if not isinstance(content, str) or not content.strip():
            content = "💭 Trace started"
        chat_id = str(getattr(trace_state, "chat_id", "") or "")
        if not chat_id:
            return SendResult(success=False, error="trace_state missing chat_id")
        return await self.send(chat_id, content, metadata=metadata)

    async def edit_trace(
        self,
        message_id: str,
        trace_state: Any,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        """Edit a Discord trace message.

        Placeholder for Components V2 edit support. Uses the inherited text edit
        path until the component payload builder is introduced.
        """
        content = getattr(trace_state, "fallback_text", None)
        if callable(content):
            content = content()
        if not isinstance(content, str) or not content.strip():
            content = "💭 Trace updated"
        chat_id = str(getattr(trace_state, "chat_id", "") or "")
        if not chat_id:
            return SendResult(success=False, error="trace_state missing chat_id")
        return await self.edit_message(chat_id, message_id, content)
