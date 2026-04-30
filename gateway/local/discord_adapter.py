"""Local Discord adapter overrides for this Hermes fork."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

from gateway.local.discord_components import (
    build_trace_layout_view,
    render_trace_fallback_text,
)
from gateway.platforms.base import SendResult
from gateway.platforms.discord import DiscordAdapter

logger = logging.getLogger(__name__)


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
        return str(getattr(trace_state, "chat_id", "") or "")

    def _is_components_v2_structural_error(self, error: str | None) -> bool:
        text = str(error or "").lower()
        if not text:
            return False

        required_components = ("layoutview", "textdisplay", "container", "separator")
        if "layoutview/textdisplay/container/separator unavailable" in text:
            return True
        if any(f"has no attribute '{name}'" in text for name in required_components):
            return True
        if any(f"{name} unsupported" in text for name in required_components):
            return True
        if "unexpected keyword argument 'view'" in text:
            return True
        if "unsupported layout view" in text or "unsupported layoutview" in text:
            return True
        if "unsupported components v2" in text:
            return True
        if "unsupported component type" in text:
            return True
        return False

    def _classify_components_v2_failure(self, error: str | None) -> tuple[str, bool]:
        if self._is_components_v2_structural_error(error):
            return "structural", False
        if error and (
            self._is_retryable_error(error)
            or "not connected" in error.lower()
            or "connection closed" in error.lower()
        ):
            return "transient", True
        return "ambiguous", False

    def _components_v2_failure_result(self, error: str | None) -> SendResult:
        failure_kind, retryable = self._classify_components_v2_failure(error)
        return SendResult(
            success=False,
            error=error,
            retryable=retryable,
            raw_response={"components_v2": True, "failure_kind": failure_kind},
        )

    def _is_components_v2_structural_failure(self, result: SendResult) -> bool:
        failure_kind = None
        if isinstance(result.raw_response, dict):
            failure_kind = result.raw_response.get("failure_kind")
        if failure_kind:
            return failure_kind == "structural"
        return self._is_components_v2_structural_error(result.error)

    def _latch_components_v2_fallback(self, result: SendResult) -> bool:
        if result.success or not self._is_components_v2_structural_failure(result):
            return False
        if self._trace_components_v2_disabled:
            return True
        self._trace_components_v2_disabled = True
        logger.warning(
            "Discord trace components v2 disabled after structural incompatibility; "
            "falling back to plain text for subsequent trace updates: %s",
            result.error,
        )
        return True

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
            return self._components_v2_failure_result("Not connected")
        try:
            channel = await self._resolve_channel(chat_id)
            if not channel:
                return self._components_v2_failure_result(f"Channel {chat_id} not found")
            view = build_trace_layout_view(trace_state)
            msg = await channel.send(content=None, reference=None, view=view)
            return SendResult(success=True, message_id=str(msg.id), raw_response={"components_v2": True})
        except Exception as exc:
            return self._components_v2_failure_result(str(exc))

    async def _edit_components_v2(
        self,
        chat_id: str,
        message_id: str,
        trace_state: Any,
    ) -> SendResult:
        if not self._client:
            return self._components_v2_failure_result("Not connected")
        try:
            channel = await self._resolve_channel(chat_id)
            if not channel:
                return self._components_v2_failure_result(f"Channel {chat_id} not found")
            partial = channel.get_partial_message(int(message_id))
            view = build_trace_layout_view(trace_state)
            await partial.edit(content=None, view=view)
            return SendResult(success=True, message_id=message_id, raw_response={"components_v2": True})
        except Exception as exc:
            return self._components_v2_failure_result(str(exc))

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
        if self._trace_components_v2_disabled:
            content = self._trace_fallback_text(trace_state, "💭 Trace started")
            return await self.send(chat_id, content, metadata=None)

        result = await self._send_components_v2(chat_id, trace_state)
        if result.success:
            return result
        if self._latch_components_v2_fallback(result):
            content = self._trace_fallback_text(trace_state, "💭 Trace started")
            return await self.send(chat_id, content, metadata=None)
        return result

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
        if self._trace_components_v2_disabled:
            content = self._trace_fallback_text(trace_state, "💭 Trace updated")
            return await self.edit_message(chat_id, message_id, content)

        result = await self._edit_components_v2(chat_id, message_id, trace_state)
        if result.success:
            return result
        if self._latch_components_v2_fallback(result):
            content = self._trace_fallback_text(trace_state, "💭 Trace updated")
            return await self.edit_message(chat_id, message_id, content)
        return result
