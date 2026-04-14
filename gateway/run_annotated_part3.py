from __future__ import annotations

"""
Annotated reference for gateway/run.py final section.

Source coverage requested: run.py lines 6001-9003.
Actual source coverage available: lines 6001-7780 (the file currently ends at 7780).

Notes:
- The original task referenced ANNOTATION_INSTRUCTIONS.md, but that file is not present
  anywhere in this checkout. This annotation therefore follows the inferred house style:
  explain control flow, call out cross-thread/cross-platform constraints, and include
  targeted historical context from git blame/log where the code exists for non-obvious
  reasons.
- Lines 6001-6011 are only the tail of the previous helper, so this file summarizes that
  fragment in comments and then starts with the next complete method definition.
"""

# Source lines 6001-6011 (tail of the previous helper) handle the cleanup path after
# a gateway self-update/post-update notification attempt:
# - log a best-effort warning if the notification send failed,
# - remove the pending/claimed/output/exit-code marker files when cleanup is requested,
# - and return True once that update bookkeeping finishes.

class GatewayRunnerAnnotatedPart3:
    # Added in 1e68bd46 while wiring richer gateway config/session sync.
    # These environment variables are a low-friction bridge for subprocesses,
    # tools, and helper code that only know how to read process env, not the
    # gateway's in-memory SessionContext object.
    def _set_session_env(self, context: SessionContext) -> None:
        """Set environment variables for the current session."""
        # Set the minimal cross-cutting identifiers first; downstream code can
        # derive most other behavior from platform/chat/thread alone.
        os.environ["HERMES_SESSION_PLATFORM"] = context.source.platform.value
        os.environ["HERMES_SESSION_CHAT_ID"] = context.source.chat_id
        if context.source.chat_name:
            os.environ["HERMES_SESSION_CHAT_NAME"] = context.source.chat_name
        if context.source.thread_id:
            os.environ["HERMES_SESSION_THREAD_ID"] = str(context.source.thread_id)
    
    # Explicit cleanup matters because the gateway is long-lived and handles many
    # sessions in one process. Without this, a later request could accidentally
    # inherit metadata from the previous chat.
    def _clear_session_env(self) -> None:
        """Clear session environment variables."""
        for var in ["HERMES_SESSION_PLATFORM", "HERMES_SESSION_CHAT_ID", "HERMES_SESSION_CHAT_NAME", "HERMES_SESSION_THREAD_ID"]:
            if var in os.environ:
                del os.environ[var]
    
    # Historical note: introduced by 5404a8fc when adapters began caching user
    # uploads locally. The key idea is to front-load a general image description
    # so the model immediately understands what arrived, while still preserving a
    # stable local path for follow-up vision_analyze calls.
    async def _enrich_message_with_vision(
        self,
        user_text: str,
        image_paths: List[str],
    ) -> str:
        """
        Auto-analyze user-attached images with the vision tool and prepend
        the descriptions to the message text.

        Each image is analyzed with a general-purpose prompt.  The resulting
        description *and* the local cache path are injected so the model can:
          1. Immediately understand what the user sent (no extra tool call).
          2. Re-examine the image with vision_analyze if it needs more detail.

        Args:
            user_text:   The user's original caption / message text.
            image_paths: List of local file paths to cached images.

        Returns:
            The enriched message string with vision descriptions prepended.
        """
        from tools.vision_tools import vision_analyze_tool
        import json as _json

        analysis_prompt = (
            "Describe everything visible in this image in thorough detail. "
            "Include any text, code, data, objects, people, layout, colors, "
            "and any other notable visual information."
        )

        enriched_parts = []
        for path in image_paths:
            try:
                logger.debug("Auto-analyzing user image: %s", path)
                # Use the cached local file path, not the platform's original attachment URL.
                # That avoids expiry/race problems with ephemeral media links.
                result_json = await vision_analyze_tool(
                    image_url=path,
                    user_prompt=analysis_prompt,
                )
                result = _json.loads(result_json)
                if result.get("success"):
                    description = result.get("analysis", "")
                    enriched_parts.append(
                        f"[The user sent an image~ Here's what I can see:\n{description}]\n"
                        f"[If you need a closer look, use vision_analyze with "
                        f"image_url: {path} ~]"
                    )
                else:
                    enriched_parts.append(
                        "[The user sent an image but I couldn't quite see it "
                        "this time (>_<) You can try looking at it yourself "
                        f"with vision_analyze using image_url: {path}]"
                    )
            except Exception as e:
                logger.error("Vision auto-analysis error: %s", e)
                enriched_parts.append(
                    f"[The user sent an image but something went wrong when I "
                    f"tried to look at it~ You can try examining it yourself "
                    f"with vision_analyze using image_url: {path}]"
                )

        # Combine: vision descriptions first, then the user's original text
        if enriched_parts:
            prefix = "\n\n".join(enriched_parts)
            if user_text:
                return f"{prefix}\n\n{user_text}"
            return prefix
        return user_text

    # Voice messages follow the same pattern as images: enrich the user turn up
    # front so the core agent can reason over text instead of having to discover
    # and call STT tools itself.
    async def _enrich_message_with_transcription(
        self,
        user_text: str,
        audio_paths: List[str],
    ) -> str:
        """
        Auto-transcribe user voice/audio messages using the configured STT provider
        and prepend the transcript to the message text.

        Args:
            user_text:   The user's original caption / message text.
            audio_paths: List of local file paths to cached audio files.

        Returns:
            The enriched message string with transcriptions prepended.
        """
        # Fail soft when speech-to-text is disabled. The gateway still preserves the
        # fact that audio arrived and, when available, nudges the model toward the
        # setup skill instead of silently dropping the attachment context.
        if not getattr(self.config, "stt_enabled", True):
            disabled_note = "[The user sent voice message(s), but transcription is disabled in config."
            if self._has_setup_skill():
                disabled_note += (
                    " You have a skill called hermes-agent-setup that can help "
                    "users configure Hermes features including voice, tools, and more."
                )
            disabled_note += "]"
            if user_text:
                return f"{disabled_note}\n\n{user_text}"
            return disabled_note

        from tools.transcription_tools import transcribe_audio, get_stt_model_from_config
        import asyncio

        # The model choice is centralized so CLI and gateway transcription behavior
        # stay aligned after config changes.
        stt_model = get_stt_model_from_config()

        enriched_parts = []
        for path in audio_paths:
            try:
                logger.debug("Transcribing user voice: %s", path)
                # STT implementations are synchronous/CPU- or network-bound, so push them into
                # a worker thread rather than blocking the asyncio event loop.
                result = await asyncio.to_thread(transcribe_audio, path, model=stt_model)
                if result["success"]:
                    transcript = result["transcript"]
                    enriched_parts.append(
                        f'[The user sent a voice message~ '
                        f'Here\'s what they said: "{transcript}"]'
                    )
                else:
                    error = result.get("error", "unknown error")
                    if (
                        "No STT provider" in error
                        or error.startswith("Neither VOICE_TOOLS_OPENAI_KEY nor OPENAI_API_KEY is set")
                    ):
                        _no_stt_note = (
                            "[The user sent a voice message but I can't listen "
                            "to it right now — no STT provider is configured. "
                            "A direct message has already been sent to the user "
                            "with setup instructions."
                        )
                        if self._has_setup_skill():
                            _no_stt_note += (
                                " You have a skill called hermes-agent-setup "
                                "that can help users configure Hermes features "
                                "including voice, tools, and more."
                            )
                        _no_stt_note += "]"
                        enriched_parts.append(_no_stt_note)
                    else:
                        enriched_parts.append(
                            "[The user sent a voice message but I had trouble "
                            f"transcribing it~ ({error})]"
                        )
            except Exception as e:
                logger.error("Transcription error: %s", e)
                enriched_parts.append(
                    "[The user sent a voice message but something went wrong "
                    "when I tried to listen to it~ Let them know!]"
                )

        if enriched_parts:
            prefix = "\n\n".join(enriched_parts)
            # Strip the empty-content placeholder from the Discord adapter
            # when we successfully transcribed the audio — it's redundant.
            # Discord sometimes supplies an explicit placeholder for attachment-only posts.
            # Once we have a transcript, that placeholder only adds noise, so strip it.
            _placeholder = "(The user sent a message with no text content)"
            if user_text and user_text.strip() == _placeholder:
                return prefix
            if user_text:
                return f"{prefix}\n\n{user_text}"
            return prefix
        return user_text

    # Background-process watchers are the gateway-side half of terminal/process
    # tool sessions. They poll the registry and translate state changes back into
    # platform messages or synthetic gateway events.
    async def _run_process_watcher(self, watcher: dict) -> None:
        """
        Periodically check a background process and push updates to the user.

        Runs as an asyncio task. Stays silent when nothing changed.
        Auto-removes when the process exits or is killed.

        Notification mode (from ``display.background_process_notifications``):
          - ``all``    — running-output updates + final message
          - ``result`` — final completion message only
          - ``error``  — final message only when exit code != 0
          - ``off``    — no messages at all
        """
        from tools.process_registry import process_registry

        session_id = watcher["session_id"]
        interval = watcher["check_interval"]
        session_key = watcher.get("session_key", "")
        platform_name = watcher.get("platform", "")
        chat_id = watcher.get("chat_id", "")
        thread_id = watcher.get("thread_id", "")
        agent_notify = watcher.get("notify_on_complete", False)
        notify_mode = self._load_background_notifications_mode()

        logger.debug("Process watcher started: %s (every %ss, notify=%s, agent_notify=%s)",
                      session_id, interval, notify_mode, agent_notify)

        # Even in silent mode we keep polling until exit so crash recovery/checkpoint
        # logic can observe completion and retire the watcher cleanly.
        if notify_mode == "off" and not agent_notify:
            # Still wait for the process to exit so we can log it, but don't
            # push any messages to the user.
            while True:
                await asyncio.sleep(interval)
                session = process_registry.get(session_id)
                if session is None or session.exited:
                    break
            logger.debug("Process watcher ended (silent): %s", session_id)
            return

        last_output_len = 0
        while True:
            await asyncio.sleep(interval)

            session = process_registry.get(session_id)
            if session is None:
                break

            current_output_len = len(session.output_buffer)
            has_new_output = current_output_len > last_output_len
            last_output_len = current_output_len

            # Exit is the only time we emit a completion payload; all other polls are
            # best-effort progress updates.
            if session.exited:
                # --- Agent-triggered completion: inject synthetic message ---
                # Added around e120d2afa/d87655af. Instead of merely texting the user that a
                # background job finished, this injects an internal synthetic message back into
                # the normal gateway pipeline so the agent can interpret the result and decide
                # what to do next.
                if agent_notify:
                    from tools.ansi_strip import strip_ansi
                    _out = strip_ansi(session.output_buffer[-2000:]) if session.output_buffer else ""
                    synth_text = (
                        f"[SYSTEM: Background process {session_id} completed "
                        f"(exit code {session.exit_code}).\n"
                        f"Command: {session.command}\n"
                        f"Output:\n{_out}]"
                    )
                    adapter = None
                    for p, a in self.adapters.items():
                        if p.value == platform_name:
                            adapter = a
                            break
                    if adapter and chat_id:
                        try:
                            from gateway.platforms.base import MessageEvent, MessageType
                            from gateway.session import SessionSource
                            from gateway.config import Platform
                            _platform_enum = Platform(platform_name)
                            _source = SessionSource(
                                platform=_platform_enum,
                                chat_id=chat_id,
                                thread_id=thread_id or None,
                            )
                            synth_event = MessageEvent(
                                text=synth_text,
                                message_type=MessageType.TEXT,
                                source=_source,
                                internal=True,
                            )
                            logger.info(
                                "Process %s finished — injecting agent notification for session %s",
                                session_id, session_key,
                            )
                            await adapter.handle_message(synth_event)
                        except Exception as e:
                            logger.error("Agent notify injection error: %s", e)
                    break

                # --- Normal text-only notification ---
                # Decide whether to notify based on mode
                # Plain notification mode is intentionally simpler than agent_notify: send a
                # human-readable status line, but do not re-enter the full agent loop.
                should_notify = (
                    notify_mode in ("all", "result")
                    or (notify_mode == "error" and session.exit_code not in (0, None))
                )
                if should_notify:
                    new_output = session.output_buffer[-1000:] if session.output_buffer else ""
                    message_text = (
                        f"[Background process {session_id} finished with exit code {session.exit_code}~ "
                        f"Here's the final output:\n{new_output}]"
                    )
                    adapter = None
                    for p, a in self.adapters.items():
                        if p.value == platform_name:
                            adapter = a
                            break
                    if adapter and chat_id:
                        try:
                            send_meta = {"thread_id": thread_id} if thread_id else None
                            await adapter.send(chat_id, message_text, metadata=send_meta)
                        except Exception as e:
                            logger.error("Watcher delivery error: %s", e)
                break

            # Periodic running-output updates are suppressed for agent_notify sessions
            # because those flows only care about the final completion event.
            elif has_new_output and notify_mode == "all" and not agent_notify:
                # New output available -- deliver status update (only in "all" mode)
                # Skip periodic updates for agent_notify watchers (they only care about completion)
                new_output = session.output_buffer[-500:] if session.output_buffer else ""
                message_text = (
                    f"[Background process {session_id} is still running~ "
                    f"New output:\n{new_output}]"
                )
                adapter = None
                for p, a in self.adapters.items():
                    if p.value == platform_name:
                        adapter = a
                        break
                if adapter and chat_id:
                    try:
                        send_meta = {"thread_id": thread_id} if thread_id else None
                        await adapter.send(chat_id, message_text, metadata=send_meta)
                    except Exception as e:
                        logger.error("Watcher delivery error: %s", e)

        logger.debug("Process watcher ended: %s", session_id)

    # This guard exists because queued/interrupt follow-ups recurse back into
    # _run_agent. A hard cap prevents pathological message storms from consuming
    # unbounded stack, tasks, or token budget.
    _MAX_INTERRUPT_DEPTH = 3  # Cap recursive interrupt handling (#816)

    @staticmethod
    # Introduced in 342096b4 for prompt-prefix caching. The gateway now reuses a
    # single AIAgent per session when the effective config is unchanged, which
    # preserves expensive frozen prefixes (system prompt, skills, tool schemas).
    def _agent_config_signature(
        model: str,
        runtime: dict,
        enabled_toolsets: list,
        ephemeral_prompt: str,
    ) -> str:
        """Compute a stable string key from agent config values.

        When this signature changes between messages, the cached AIAgent is
        discarded and rebuilt.  When it stays the same, the cached agent is
        reused — preserving the frozen system prompt and tool schemas for
        prompt cache hits.
        """
        import hashlib, json as _j

        # Fingerprint the FULL credential string instead of using a short
        # prefix. OAuth/JWT-style tokens frequently share a common prefix
        # (e.g. "eyJhbGci"), which can cause false cache hits across auth
        # switches if only the first few characters are considered.
        # Later hardened in c6fe75e99: hash the full credential string, not a short
        # prefix, because JWT/OAuth tokens often share the same opening characters.
        _api_key = str(runtime.get("api_key", "") or "")
        _api_key_fingerprint = hashlib.sha256(_api_key.encode()).hexdigest() if _api_key else ""

        blob = _j.dumps(
            [
                model,
                _api_key_fingerprint,
                runtime.get("base_url", ""),
                runtime.get("provider", ""),
                runtime.get("api_mode", ""),
                sorted(enabled_toolsets) if enabled_toolsets else [],
                # reasoning_config excluded — it's set per-message on the
                # cached agent and doesn't affect system prompt or tools.
                ephemeral_prompt or "",
            ],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # Central helper used by /new, /model, fallback recovery, and other resets to
    # drop stale cached agents safely under the shared cache lock.
    def _evict_cached_agent(self, session_key: str) -> None:
        """Remove a cached agent for a session (called on /new, /model, etc)."""
        _lock = getattr(self, "_agent_cache_lock", None)
        if _lock:
            with _lock:
                self._agent_cache.pop(session_key, None)

    # This is the gateway's main orchestration bridge: async platform IO on the
    # outside, synchronous AIAgent.run_conversation() in a worker thread on the
    # inside, plus all the glue for progress, streaming, approvals, interrupts,
    # timeouts, and transcript bookkeeping.
    async def _run_agent(
        self,
        message: str,
        context_prompt: str,
        history: List[Dict[str, Any]],
        source: SessionSource,
        session_id: str,
        session_key: str = None,
        _interrupt_depth: int = 0,
        event_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the agent with the given message and context.
        
        Returns the full result dict from run_conversation, including:
          - "final_response": str (the text to send back)
          - "messages": list (full conversation including tool calls)
          - "api_calls": int
          - "completed": bool
        
        This is run in a thread pool to not block the event loop.
        Supports interruption via new messages.
        """
        from run_agent import AIAgent
        import queue
        
        # Reload config per turn instead of only at process start. The gateway is a
        # daemon, so users expect model/tool/display tweaks to take effect without a
        # restart.
        user_config = _load_gateway_config()
        platform_key = _platform_config_key(source.platform)

        from hermes_cli.tools_config import _get_platform_tools
        enabled_toolsets = sorted(_get_platform_tools(user_config, platform_key))

        # Apply tool preview length config (0 = no limit)
        try:
            from agent.display import set_tool_preview_max_len
            _tpl = user_config.get("display", {}).get("tool_preview_length", 0)
            set_tool_preview_max_len(int(_tpl) if _tpl else 0)
        except Exception:
            pass

        # Tool progress mode from config.yaml: "all", "new", "verbose", "off"
        # Falls back to env vars for backward compatibility.
        # YAML 1.1 parses bare `off` as boolean False — normalise before
        # the `or` chain so it doesn't silently fall through to "all".
        #
        # Per-platform overrides (display.tool_progress_overrides) take
        # priority over the global setting — e.g. Signal users can set
        # tool_progress to "off" while keeping Telegram on "all".
        _display_cfg = user_config.get("display", {})
        _overrides = _display_cfg.get("tool_progress_overrides", {})
        # The display.tool_progress setting ended up needing platform overrides and
        # YAML-boolean normalization because bare `off` can deserialize as False under
        # YAML 1.1.
        _raw_tp = _overrides.get(platform_key)
        if _raw_tp is None:
            _raw_tp = _display_cfg.get("tool_progress")
        if _raw_tp is False:
            _raw_tp = "off"
        progress_mode = (
            _raw_tp
            or os.getenv("HERMES_TOOL_PROGRESS_MODE")
            or "all"
        )
        # Disable tool progress for webhooks - they don't support message editing,
        # so each progress line would be sent as a separate message.
        from gateway.config import Platform
        tool_progress_enabled = progress_mode != "off" and source.platform != Platform.WEBHOOK
        
        # Queue for progress messages (thread-safe)
        progress_queue = queue.Queue() if tool_progress_enabled else None
        last_tool = [None]  # Mutable container for tracking in closure
        last_progress_msg = [None]  # Track last message for dedup
        repeat_count = [0]  # How many times the same message repeated
        
        # This callback runs inside the agent thread, so it cannot touch adapters
        # directly. Instead it writes compact progress records into a thread-safe queue
        # that the async sender task drains on the event loop side.
        def progress_callback(event_type: str, tool_name: str = None, preview: str = None, args: dict = None, **kwargs):
            """Callback invoked by agent on tool lifecycle events."""
            if not progress_queue:
                return

            # Only act on tool.started events (ignore tool.completed, reasoning.available, etc.)
            # Only surface tool-start events to users. Completion/reasoning/status events
            # would explode message volume in chat UIs.
            if event_type not in ("tool.started",):
                return

            # "new" mode: only report when tool changes
            if progress_mode == "new" and tool_name == last_tool[0]:
                return
            last_tool[0] = tool_name
            
            # Build progress message with primary argument preview
            from agent.display import get_tool_emoji
            emoji = get_tool_emoji(tool_name, default="⚙️")
            
            # Verbose mode: show detailed arguments, respects tool_preview_length
            # Verbose mode is mainly for debugging: show argument keys and a capped JSON
            # payload so users can inspect what the model is actually invoking.
            if progress_mode == "verbose":
                if args:
                    from agent.display import get_tool_preview_max_len
                    _pl = get_tool_preview_max_len()
                    import json as _json
                    args_str = _json.dumps(args, ensure_ascii=False, default=str)
                    _cap = _pl if _pl > 0 else 200
                    if len(args_str) > _cap:
                        args_str = args_str[:_cap - 3] + "..."
                    msg = f"{emoji} {tool_name}({list(args.keys())})\n{args_str}"
                elif preview:
                    msg = f"{emoji} {tool_name}: \"{preview}\""
                else:
                    msg = f"{emoji} {tool_name}..."
                progress_queue.put(msg)
                return
            
            # "all" / "new" modes: short preview, respects tool_preview_length
            # config (defaults to 40 chars when unset to keep gateway messages
            # compact — unlike CLI spinners, these persist as permanent messages).
            if preview:
                from agent.display import get_tool_preview_max_len
                _pl = get_tool_preview_max_len()
                _cap = _pl if _pl > 0 else 40
                if len(preview) > _cap:
                    preview = preview[:_cap - 3] + "..."
                msg = f"{emoji} {tool_name}: \"{preview}\""
            else:
                msg = f"{emoji} {tool_name}..."
            
            # Dedup: collapse consecutive identical progress messages.
            # Common with execute_code where models iterate with the same
            # code (same boilerplate imports → identical previews).
            # Dedup repeated previews instead of sending the same line over and over.
            # execute_code loops were a common offender here.
            if msg == last_progress_msg[0]:
                repeat_count[0] += 1
                # Update the last line in progress_lines with a counter
                # via a special "dedup" queue message.
                progress_queue.put(("__dedup__", msg, repeat_count[0]))
                return
            last_progress_msg[0] = msg
            repeat_count[0] = 0
            
            progress_queue.put(msg)
        
        # Background task to send progress messages
        # Accumulates tool lines into a single message that gets edited.
        #
        # Threading metadata is platform-specific:
        # - Slack DM threading needs event_message_id fallback (reply thread)
        # - Telegram uses message_thread_id only for forum topics; passing a
        #   normal DM/group message id as thread_id causes send failures
        # - Other platforms should use explicit source.thread_id only
        # Thread metadata is annoyingly platform-specific. Slack DMs treat the event
        # message id as a reply-thread anchor, while Telegram only wants thread ids for
        # forum topics, not ordinary chats.
        if source.platform == Platform.SLACK:
            _progress_thread_id = source.thread_id or event_message_id
        else:
            _progress_thread_id = source.thread_id
        _progress_metadata = {"thread_id": _progress_thread_id} if _progress_thread_id else None

        # Async side of the progress bridge. It batches tool lines into one editable
        # message when the platform supports edits, falling back to discrete sends when
        # it does not.
        async def send_progress_messages():
            if not progress_queue:
                return

            adapter = self.adapters.get(source.platform)
            if not adapter:
                return

            # Skip tool progress for platforms that don't support message
            # editing (e.g. iMessage/BlueBubbles) — each progress update
            # would become a separate message bubble, which is noisy.
            from gateway.platforms.base import BasePlatformAdapter as _BaseAdapter
            # Detect "no custom edit support" by checking the class method directly.
            # That avoids false positives from mocked instances in tests and prevents noisy
            # one-line-per-update behavior on adapters like BlueBubbles/iMessage.
            if type(adapter).edit_message is _BaseAdapter.edit_message:
                while not progress_queue.empty():
                    try:
                        progress_queue.get_nowait()
                    except Exception:
                        break
                return

            progress_lines = []      # Accumulated tool lines
            progress_msg_id = None   # ID of the progress message to edit
            can_edit = True          # False once an edit fails (platform doesn't support it)
            _last_edit_ts = 0.0      # Throttle edits to avoid Telegram flood control
            _PROGRESS_EDIT_INTERVAL = 1.5  # Minimum seconds between edits

            while True:
                try:
                    raw = progress_queue.get_nowait()

                    # Handle dedup messages: update last line with repeat counter
                    if isinstance(raw, tuple) and len(raw) == 3 and raw[0] == "__dedup__":
                        _, base_msg, count = raw
                        if progress_lines:
                            progress_lines[-1] = f"{base_msg} (×{count + 1})"
                        msg = progress_lines[-1] if progress_lines else base_msg
                    else:
                        msg = raw
                        progress_lines.append(msg)

                    # Throttle edits: batch rapid tool updates into fewer
                    # API calls to avoid hitting Telegram flood control.
                    # (grammY auto-retry pattern: proactively rate-limit
                    # instead of reacting to 429s.)
                    _now = time.monotonic()
                    # Proactive throttling was added after Telegram flood-control issues. Batching
                    # many quick tool-start events into fewer edits is better than repeatedly
                    # hitting 429/retry-after responses.
                    _remaining = _PROGRESS_EDIT_INTERVAL - (_now - _last_edit_ts)
                    if _remaining > 0:
                        # Wait out the throttle interval, then loop back to
                        # drain any additional queued messages before sending
                        # a single batched edit.
                        await asyncio.sleep(_remaining)
                        continue

                    if can_edit and progress_msg_id is not None:
                        # Try to edit the existing progress message
                        full_text = "\n".join(progress_lines)
                        result = await adapter.edit_message(
                            chat_id=source.chat_id,
                            message_id=progress_msg_id,
                            content=full_text,
                        )
                        # One failed edit is treated as a capability/rate-limit signal: disable future
                        # edits and degrade gracefully to normal sends instead of retry-storming.
                        if not result.success:
                            _err = (getattr(result, "error", "") or "").lower()
                            if "flood" in _err or "retry after" in _err:
                                # Flood control hit — disable further edits,
                                # switch to sending new messages only for
                                # important updates.  Don't block 23s.
                                logger.info(
                                    "[%s] Progress edits disabled due to flood control",
                                    adapter.name,
                                )
                            can_edit = False
                            await adapter.send(chat_id=source.chat_id, content=msg, metadata=_progress_metadata)
                    else:
                        if can_edit:
                            # First tool: send all accumulated text as new message
                            full_text = "\n".join(progress_lines)
                            result = await adapter.send(chat_id=source.chat_id, content=full_text, metadata=_progress_metadata)
                        else:
                            # Editing unsupported: send just this line
                            result = await adapter.send(chat_id=source.chat_id, content=msg, metadata=_progress_metadata)
                        if result.success and result.message_id:
                            progress_msg_id = result.message_id

                    _last_edit_ts = time.monotonic()

                    # Restore typing indicator
                    await asyncio.sleep(0.3)
                    await adapter.send_typing(source.chat_id, metadata=_progress_metadata)

                except queue.Empty:
                    await asyncio.sleep(0.3)
                # On shutdown/cancel, drain the queue and attempt one last edit so the final
                # progress state is not silently lost.
                except asyncio.CancelledError:
                    # Drain remaining queued messages
                    while not progress_queue.empty():
                        try:
                            raw = progress_queue.get_nowait()
                            if isinstance(raw, tuple) and len(raw) == 3 and raw[0] == "__dedup__":
                                _, base_msg, count = raw
                                if progress_lines:
                                    progress_lines[-1] = f"{base_msg} (×{count + 1})"
                            else:
                                progress_lines.append(raw)
                        except Exception:
                            break
                    # Final edit with all remaining tools (only if editing works)
                    if can_edit and progress_lines and progress_msg_id:
                        full_text = "\n".join(progress_lines)
                        try:
                            await adapter.edit_message(
                                chat_id=source.chat_id,
                                message_id=progress_msg_id,
                                content=full_text,
                            )
                        except Exception:
                            pass
                    return
                except Exception as e:
                    logger.error("Progress message error: %s", e)
                    await asyncio.sleep(1)
        
        # We need to share the agent instance for interrupt support
        # Mutable one-element containers are the simplest cross-scope/shared-state
        # bridge between nested functions, background tasks, and the executor worker.
        agent_holder = [None]  # Mutable container for the agent instance
        result_holder = [None]  # Mutable container for the result
        tools_holder = [None]   # Mutable container for the tool definitions
        stream_consumer_holder = [None]  # Mutable container for stream consumer
        
        # Bridge sync step_callback → async hooks.emit for agent:step events
        _loop_for_step = asyncio.get_event_loop()
        _hooks_ref = self.hooks

        # Hooks are async, but AIAgent invokes callbacks synchronously from the worker
        # thread. run_coroutine_threadsafe preserves that contract without blocking the
        # main event loop.
        def _step_callback_sync(iteration: int, prev_tools: list) -> None:
            try:
                # prev_tools may be list[str] or list[dict] with "name"/"result"
                # keys.  Normalise to keep "tool_names" backward-compatible for
                # user-authored hooks that do ', '.join(tool_names)'.
                _names: list[str] = []
                for _t in (prev_tools or []):
                    if isinstance(_t, dict):
                        _names.append(_t.get("name") or "")
                    else:
                        _names.append(str(_t))
                asyncio.run_coroutine_threadsafe(
                    _hooks_ref.emit("agent:step", {
                        "platform": source.platform.value if source.platform else "",
                        "user_id": source.user_id,
                        "session_id": session_id,
                        "iteration": iteration,
                        "tool_names": _names,
                        "tools": prev_tools,
                    }),
                    _loop_for_step,
                )
            except Exception as _e:
                logger.debug("agent:step hook error: %s", _e)

        # Bridge sync status_callback → async adapter.send for context pressure
        _status_adapter = self.adapters.get(source.platform)
        _status_chat_id = source.chat_id
        _status_thread_metadata = {"thread_id": _progress_thread_id} if _progress_thread_id else None

        # Status callbacks are a lighter-weight path for one-off gateway notices such
        # as context-pressure warnings.
        def _status_callback_sync(event_type: str, message: str) -> None:
            if not _status_adapter:
                return
            try:
                asyncio.run_coroutine_threadsafe(
                    _status_adapter.send(
                        _status_chat_id,
                        message,
                        metadata=_status_thread_metadata,
                    ),
                    _loop_for_step,
                )
            except Exception as _e:
                logger.debug("status_callback error (%s): %s", event_type, _e)

        # Everything below executes inside the executor thread. It is where the
        # synchronous AIAgent instance is created/reused and run_conversation() is
        # finally invoked.
        def run_sync():
            # The conditional re-assignment of `message` further below
            # (prepending model-switch notes) makes Python treat it as a
            # local variable in the entire function.  `nonlocal` lets us
            # read *and* reassign the outer `_run_agent` parameter without
            # triggering an UnboundLocalError on the earlier read at
            # `_resolve_turn_agent_config(message, …)`.
            # Required because later code prepends model-switch notes to `message`.
            # Without nonlocal, Python would treat `message` as a purely local variable and
            # the earlier read would crash with UnboundLocalError.
            nonlocal message

            # Pass session_key to process registry via env var so background
            # processes can be mapped back to this gateway session
            # Background terminal/process sessions store only lightweight metadata; this
            # env var gives tool-side code a way to map spawned work back to the gateway
            # session that created it.
            os.environ["HERMES_SESSION_KEY"] = session_key or ""

            # Read from env var or use default (same as CLI)
            max_iterations = int(os.getenv("HERMES_MAX_ITERATIONS", "90"))
            
            # Map platform enum to the platform hint key the agent understands.
            # Platform.LOCAL ("local") maps to "cli"; others pass through as-is.
            platform_key = "cli" if source.platform == Platform.LOCAL else source.platform.value
            
            # Combine platform context with user-configured ephemeral system prompt
            combined_ephemeral = context_prompt or ""
            if self._ephemeral_system_prompt:
                combined_ephemeral = (combined_ephemeral + "\n\n" + self._ephemeral_system_prompt).strip()

            # Re-read .env and config for fresh credentials (gateway is long-lived,
            # keys may change without restart).
            try:
                # Credential refresh is deliberate: long-running gateway processes should pick
                # up .env changes without needing a restart.
                load_dotenv(_env_path, override=True, encoding="utf-8")
            except UnicodeDecodeError:
                load_dotenv(_env_path, override=True, encoding="latin-1")
            except Exception:
                pass

            model = _resolve_gateway_model(user_config)

            try:
                runtime_kwargs = _resolve_runtime_agent_kwargs()
            except Exception as exc:
                return {
                    "final_response": f"⚠️ Provider authentication failed: {exc}",
                    "messages": [],
                    "api_calls": 0,
                    "tools": [],
                }

            pr = self._provider_routing
            reasoning_config = self._load_reasoning_config()
            self._reasoning_config = reasoning_config
            # Set up streaming consumer if enabled
            _stream_consumer = None
            _stream_delta_cb = None
            _scfg = getattr(getattr(self, 'config', None), 'streaming', None)
            if _scfg is None:
                from gateway.config import StreamingConfig
                _scfg = StreamingConfig()

            if _scfg.enabled and _scfg.transport != "off":
                try:
                    from gateway.stream_consumer import GatewayStreamConsumer, StreamConsumerConfig
                    _adapter = self.adapters.get(source.platform)
                    if _adapter:
                        # Platforms that don't support editing sent messages
                        # (e.g. WeChat) must not show a cursor in intermediate
                        # sends — the cursor would be permanently visible because
                        # it can never be edited away.  Use an empty cursor for
                        # such platforms so streaming still delivers the final
                        # response, just without the typing indicator.
                        _adapter_supports_edit = getattr(_adapter, "SUPPORTS_MESSAGE_EDITING", True)
                        _effective_cursor = _scfg.cursor if _adapter_supports_edit else ""
                        # Some Matrix clients render the streaming cursor
                        # as a visible tofu/white-box artifact.  Keep
                        # streaming text on Matrix, but suppress the cursor.
                        if source.platform == Platform.MATRIX:
                            _effective_cursor = ""
                        _consumer_cfg = StreamConsumerConfig(
                            edit_interval=_scfg.edit_interval,
                            buffer_threshold=_scfg.buffer_threshold,
                            cursor=_effective_cursor,
                        )
                        _stream_consumer = GatewayStreamConsumer(
                            adapter=_adapter,
                            chat_id=source.chat_id,
                            config=_consumer_cfg,
                            metadata={"thread_id": _progress_thread_id} if _progress_thread_id else None,
                        )
                        _stream_delta_cb = _stream_consumer.on_delta
                        stream_consumer_holder[0] = _stream_consumer
                except Exception as _sc_err:
                    logger.debug("Could not set up stream consumer: %s", _sc_err)

            # Turn routing can override the base model/runtime on a per-message basis, so
            # cache decisions must happen after this resolution step, not before it.
            turn_route = self._resolve_turn_agent_config(message, model, runtime_kwargs)

            # Check agent cache — reuse the AIAgent from the previous message
            # in this session to preserve the frozen system prompt and tool
            # schemas for prompt cache hits.
            _sig = self._agent_config_signature(
                turn_route["model"],
                turn_route["runtime"],
                enabled_toolsets,
                combined_ephemeral,
            )
            agent = None
            _cache_lock = getattr(self, "_agent_cache_lock", None)
            _cache = getattr(self, "_agent_cache", None)
            if _cache_lock and _cache is not None:
                with _cache_lock:
                    cached = _cache.get(session_key)
                    # Only reuse the cached agent when the full signature matches. Otherwise a
                    # fresh agent is safer than accidentally reusing stale provider/tool/system
                    # state.
                    if cached and cached[1] == _sig:
                        agent = cached[0]
                        logger.debug("Reusing cached agent for session %s", session_key)

            # Cold path: first turn for the session, or any config/fallback/reset change
            # that invalidated the cached instance.
            if agent is None:
                # Config changed or first message — create fresh agent
                agent = AIAgent(
                    model=turn_route["model"],
                    **turn_route["runtime"],
                    max_iterations=max_iterations,
                    quiet_mode=True,
                    verbose_logging=False,
                    enabled_toolsets=enabled_toolsets,
                    ephemeral_system_prompt=combined_ephemeral or None,
                    prefill_messages=self._prefill_messages or None,
                    reasoning_config=reasoning_config,
                    providers_allowed=pr.get("only"),
                    providers_ignored=pr.get("ignore"),
                    providers_order=pr.get("order"),
                    provider_sort=pr.get("sort"),
                    provider_require_parameters=pr.get("require_parameters", False),
                    provider_data_collection=pr.get("data_collection"),
                    session_id=session_id,
                    platform=platform_key,
                    user_id=source.user_id,
                    session_db=self._session_db,
                    fallback_model=self._fallback_model,
                )
                if _cache_lock and _cache is not None:
                    with _cache_lock:
                        _cache[session_key] = (agent, _sig)
                logger.debug("Created new agent for session %s (sig=%s)", session_key, _sig)

            # Per-message state — callbacks and reasoning config change every
            # turn and must not be baked into the cached agent constructor.
            # Callbacks are intentionally assigned per turn, not baked into the cached
            # constructor state. They depend on transient gateway objects like queues,
            # stream consumers, adapters, and loaded hooks.
            agent.tool_progress_callback = progress_callback if tool_progress_enabled else None
            agent.step_callback = _step_callback_sync if _hooks_ref.loaded_hooks else None
            agent.stream_delta_callback = _stream_delta_cb
            agent.status_callback = _status_callback_sync
            agent.reasoning_config = reasoning_config

            # Background review delivery — send "💾 Memory updated" etc. to user
            def _bg_review_send(message: str) -> None:
                if not _status_adapter:
                    return
                try:
                    asyncio.run_coroutine_threadsafe(
                        _status_adapter.send(
                            _status_chat_id,
                            message,
                            metadata=_status_thread_metadata,
                        ),
                        _loop_for_step,
                    )
                except Exception as _e:
                    logger.debug("background_review_callback error: %s", _e)

            agent.background_review_callback = _bg_review_send

            # Store agent reference for interrupt support
            agent_holder[0] = agent
            # Capture the full tool definitions for transcript logging
            tools_holder[0] = agent.tools if hasattr(agent, 'tools') else None
            
            # Convert history to agent format.
            # Two cases:
            #   1. Normal path (from transcript): simple {role, content, timestamp} dicts
            #      - Strip timestamps, keep role+content
            #   2. Interrupt path (from agent result["messages"]): full agent messages
            #      that may include tool_calls, tool_call_id, reasoning, etc.
            #      - These must be passed through intact so the API sees valid
            #        assistant→tool sequences (dropping tool_calls causes 500 errors)
            agent_history = []
            # Transcript normalization has to preserve both simple chat history and rich
            # assistant/tool message chains produced by interrupted or resumed runs.
            for msg in history:
                role = msg.get("role")
                if not role:
                    continue
                
                # Skip metadata entries (tool definitions, session info)
                # -- these are for transcript logging, not for the LLM
                if role in ("session_meta",):
                    continue
                
                # Skip system messages -- the agent rebuilds its own system prompt
                if role == "system":
                    continue
                
                # Rich agent messages (tool_calls, tool results) must be passed
                # through intact so the API sees valid assistant→tool sequences
                has_tool_calls = "tool_calls" in msg
                has_tool_call_id = "tool_call_id" in msg
                is_tool_message = role == "tool"
                
                # Do not flatten these messages. Providers expect strict assistant→tool→
                # assistant ordering, and dropping tool_call metadata can turn a recoverable
                # resume into a provider 500.
                if has_tool_calls or has_tool_call_id or is_tool_message:
                    clean_msg = {k: v for k, v in msg.items() if k != "timestamp"}
                    agent_history.append(clean_msg)
                else:
                    # Simple text message - just need role and content
                    content = msg.get("content")
                    if content:
                        # Tag cross-platform mirror messages so the agent knows their origin
                        if msg.get("mirror"):
                            mirror_src = msg.get("mirror_source", "another session")
                            content = f"[Delivered from {mirror_src}] {content}"
                        entry = {"role": role, "content": content}
                        # Preserve reasoning fields on assistant messages so
                        # multi-turn reasoning context survives session reload.
                        # The agent's _build_api_kwargs converts these to the
                        # provider-specific format (reasoning_content, etc.).
                        # Reasoning traces are preserved across reloads so multi-turn reasoning-capable
                        # models keep their own prior scratchpad/context where supported.
                        if role == "assistant":
                            for _rkey in ("reasoning", "reasoning_details",
                                          "codex_reasoning_items"):
                                _rval = msg.get(_rkey)
                                if _rval:
                                    entry[_rkey] = _rval
                        agent_history.append(entry)
            
            # Collect MEDIA paths already in history so we can exclude them
            # from the current turn's extraction. This is compression-safe:
            # even if the message list shrinks, we know which paths are old.
            # Path-based MEDIA dedup is more robust than slicing by message index. Context
            # compression can rewrite or shrink history, but file paths still tell us which
            # attachments were already delivered.
            _history_media_paths: set = set()
            for _hm in agent_history:
                if _hm.get("role") in ("tool", "function"):
                    _hc = _hm.get("content", "")
                    if "MEDIA:" in _hc:
                        for _match in re.finditer(r'MEDIA:(\S+)', _hc):
                            _p = _match.group(1).strip().rstrip('",}')
                            if _p:
                                _history_media_paths.add(_p)
            
            # Register per-session gateway approval callback so dangerous
            # command approval blocks the agent thread (mirrors CLI input()).
            # The callback bridges sync→async to send the approval request
            # to the user immediately.
            from tools.approval import (
                register_gateway_notify,
                reset_current_session_key,
                set_current_session_key,
                unregister_gateway_notify,
            )

            # Dangerous-command approval happens in the sync agent thread, but the prompt
            # must be delivered through async adapters immediately. This callback is the
            # bridge between those two worlds.
            def _approval_notify_sync(approval_data: dict) -> None:
                """Send the approval request to the user from the agent thread.

                If the adapter supports interactive button-based approvals
                (e.g. Discord's ``send_exec_approval``), use that for a richer
                UX.  Otherwise fall back to a plain text message with
                ``/approve`` instructions.
                """
                # Pause the typing indicator while the agent waits for
                # user approval.  Critical for Slack's Assistant API where
                # assistant_threads_setStatus disables the compose box — the
                # user literally cannot type /approve while "is thinking..."
                # is active.  The approval message send auto-clears the Slack
                # status; pausing prevents _keep_typing from re-setting it.
                # Typing resumes in _handle_approve_command/_handle_deny_command.
                _status_adapter.pause_typing_for_chat(_status_chat_id)

                cmd = approval_data.get("command", "")
                desc = approval_data.get("description", "dangerous command")

                # Prefer button-based approval when the adapter supports it.
                # Check the *class* for the method, not the instance — avoids
                # false positives from MagicMock auto-attribute creation in tests.
                # Check the adapter class, not the instance, so tests using MagicMock do not
                # pretend every adapter has rich button-based approval support.
                if getattr(type(_status_adapter), "send_exec_approval", None) is not None:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            _status_adapter.send_exec_approval(
                                chat_id=_status_chat_id,
                                command=cmd,
                                session_key=_approval_session_key,
                                description=desc,
                                metadata=_status_thread_metadata,
                            ),
                            _loop_for_step,
                        ).result(timeout=15)
                        return
                    except Exception as _e:
                        logger.warning(
                            "Button-based approval failed, falling back to text: %s", _e
                        )

                # Fallback: plain text approval prompt
                cmd_preview = cmd[:200] + "..." if len(cmd) > 200 else cmd
                msg = (
                    f"⚠️ **Dangerous command requires approval:**\n"
                    f"```\n{cmd_preview}\n```\n"
                    f"Reason: {desc}\n\n"
                    f"Reply `/approve` to execute, `/approve session` to approve this pattern "
                    f"for the session, `/approve always` to approve permanently, or `/deny` to cancel."
                )
                try:
                    asyncio.run_coroutine_threadsafe(
                        _status_adapter.send(
                            _status_chat_id,
                            msg,
                            metadata=_status_thread_metadata,
                        ),
                        _loop_for_step,
                    ).result(timeout=15)
                except Exception as _e:
                    logger.error("Failed to send approval request: %s", _e)

            # Prepend pending model switch note so the model knows about the switch
            _pending_notes = getattr(self, '_pending_model_notes', {})
            # Model-switch commands can schedule a note for the very next turn so the
            # model itself is aware that routing/provider state just changed.
            _msn = _pending_notes.pop(session_key, None) if session_key else None
            if _msn:
                message = _msn + "\n\n" + message

            _approval_session_key = session_key or ""
            _approval_session_token = set_current_session_key(_approval_session_key)
            register_gateway_notify(_approval_session_key, _approval_notify_sync)
            try:
                # This is the blocking core call. Everything else in _run_agent exists to make
                # this synchronous agent invocation fit safely into an async multi-platform
                # gateway.
                result = agent.run_conversation(message, conversation_history=agent_history, task_id=session_id)
            finally:
                unregister_gateway_notify(_approval_session_key)
                reset_current_session_key(_approval_session_token)
            result_holder[0] = result

            # Signal the stream consumer that the agent is done
            # Signal the streaming bridge promptly so it can flush/remove its cursor and
            # perform any final message edit before the outer coroutine returns.
            if _stream_consumer is not None:
                _stream_consumer.finish()
            
            # Return final response, or a message if something went wrong
            final_response = result.get("final_response")

            # Extract actual token counts from the agent instance used for this run
            _last_prompt_toks = 0
            _input_toks = 0
            _output_toks = 0
            _agent = agent_holder[0]
            if _agent and hasattr(_agent, "context_compressor"):
                _last_prompt_toks = getattr(_agent.context_compressor, "last_prompt_tokens", 0)
                _input_toks = getattr(_agent, "session_prompt_tokens", 0)
                _output_toks = getattr(_agent, "session_completion_tokens", 0)
            _resolved_model = getattr(_agent, "model", None) if _agent else None

            # Normalize empty/failed runs into a user-visible diagnostic payload so the
            # caller never has to special-case a missing final_response field.
            if not final_response:
                error_msg = f"⚠️ {result['error']}" if result.get("error") else "(No response generated)"
                return {
                    "final_response": error_msg,
                    "messages": result.get("messages", []),
                    "api_calls": result.get("api_calls", 0),
                    "tools": tools_holder[0] or [],
                    "history_offset": len(agent_history),
                    "last_prompt_tokens": _last_prompt_toks,
                    "input_tokens": _input_toks,
                    "output_tokens": _output_toks,
                    "model": _resolved_model,
                }
            
            # Scan tool results for MEDIA:<path> tags that need to be delivered
            # as native audio/file attachments.  The TTS tool embeds MEDIA: tags
            # in its JSON response, but the model's final text reply usually
            # doesn't include them.  We collect unique tags from tool results and
            # append any that aren't already present in the final response, so the
            # adapter's extract_media() can find and deliver the files exactly once.
            #
            # Uses path-based deduplication against _history_media_paths (collected
            # before run_conversation) instead of index slicing. This is safe even
            # when context compression shrinks the message list. (Fixes #160)
            # The model often omits MEDIA tags that were present only in tool results
            # (notably TTS/audio tools). Re-attach them here so adapters can still send the
            # generated files exactly once.
            if "MEDIA:" not in final_response:
                media_tags = []
                has_voice_directive = False
                for msg in result.get("messages", []):
                    if msg.get("role") in ("tool", "function"):
                        content = msg.get("content", "")
                        if "MEDIA:" in content:
                            for match in re.finditer(r'MEDIA:(\S+)', content):
                                path = match.group(1).strip().rstrip('",}')
                                if path and path not in _history_media_paths:
                                    media_tags.append(f"MEDIA:{path}")
                            if "[[audio_as_voice]]" in content:
                                has_voice_directive = True
                
                if media_tags:
                    seen = set()
                    unique_tags = []
                    for tag in media_tags:
                        if tag not in seen:
                            seen.add(tag)
                            unique_tags.append(tag)
                    if has_voice_directive:
                        unique_tags.insert(0, "[[audio_as_voice]]")
                    final_response = final_response + "\n" + "\n".join(unique_tags)
            
            # Sync session_id: the agent may have created a new session during
            # mid-run context compression (_compress_context splits sessions).
            # If so, update the session store entry so the NEXT message loads
            # the compressed transcript, not the stale pre-compression one.
            agent = agent_holder[0]
            _session_was_split = False
            # Context compression can fork the conversation into a new backing session id.
            # The gateway must update its session-store pointer so the next inbound message
            # loads the compressed transcript instead of the stale pre-split one.
            if agent and session_key and hasattr(agent, 'session_id') and agent.session_id != session_id:
                _session_was_split = True
                logger.info(
                    "Session split detected: %s → %s (compression)",
                    session_id, agent.session_id,
                )
                entry = self.session_store._entries.get(session_key)
                if entry:
                    entry.session_id = agent.session_id
                    self.session_store._save()

            effective_session_id = getattr(agent, 'session_id', session_id) if agent else session_id

            # When compression created a new session, the messages list was
            # shortened.  Using the original history offset would produce an
            # empty new_messages slice, causing the gateway to write only a
            # user/assistant pair — losing the compressed summary and tail.
            # Reset to 0 so the gateway writes ALL compressed messages.
            _effective_history_offset = 0 if _session_was_split else len(agent_history)

            # Auto-generate session title after first exchange (non-blocking)
            if final_response and self._session_db:
                try:
                    from agent.title_generator import maybe_auto_title
                    all_msgs = result_holder[0].get("messages", []) if result_holder[0] else []
                    # Title generation is best-effort and intentionally non-fatal. It improves UX
                    # for transcript browsing but should never block a reply.
                    maybe_auto_title(
                        self._session_db,
                        effective_session_id,
                        message,
                        final_response,
                        all_msgs,
                    )
                except Exception:
                    pass

            return {
                "final_response": final_response,
                "last_reasoning": result.get("last_reasoning"),
                "messages": result_holder[0].get("messages", []) if result_holder[0] else [],
                "api_calls": result_holder[0].get("api_calls", 0) if result_holder[0] else 0,
                "tools": tools_holder[0] or [],
                "history_offset": _effective_history_offset,
                "last_prompt_tokens": _last_prompt_toks,
                "input_tokens": _input_toks,
                "output_tokens": _output_toks,
                "model": _resolved_model,
                "session_id": effective_session_id,
            }
        
        # Start progress message sender if enabled
        progress_task = None
        # The remaining tasks run alongside the executor worker: progress delivery,
        # streaming, agent tracking, interrupt polling, and long-running notices.
        if tool_progress_enabled:
            progress_task = asyncio.create_task(send_progress_messages())

        # Start stream consumer task — polls for consumer creation since it
        # happens inside run_sync (thread pool) after the agent is constructed.
        stream_task = None

        # Consumer construction happens inside run_sync after adapter/config checks, so
        # the async side briefly polls for its creation before starting it.
        async def _start_stream_consumer():
            """Wait for the stream consumer to be created, then run it."""
            for _ in range(200):  # Up to 10s wait
                if stream_consumer_holder[0] is not None:
                    await stream_consumer_holder[0].run()
                    return
                await asyncio.sleep(0.05)

        stream_task = asyncio.create_task(_start_stream_consumer())
        
        # Track this agent as running for this session (for interrupt support)
        # We do this in a callback after the agent is created
        # Expose the live agent in _running_agents so external commands like /stop can
        # find and interrupt it.
        async def track_agent():
            # Wait for agent to be created
            while agent_holder[0] is None:
                await asyncio.sleep(0.05)
            if session_key:
                self._running_agents[session_key] = agent_holder[0]
        
        tracking_task = asyncio.create_task(track_agent())
        
        # Monitor for interrupts from the adapter (new messages arriving)
        # Adapters can queue or signal newer user messages while a turn is still
        # running. This watcher translates those adapter-level interrupts into
        # agent.interrupt(...) calls.
        async def monitor_for_interrupt():
            adapter = self.adapters.get(source.platform)
            if not adapter or not session_key:
                return
            
            while True:
                await asyncio.sleep(0.2)  # Check every 200ms
                # Check if adapter has a pending interrupt for this session.
                # Must use session_key (build_session_key output) — NOT
                # source.chat_id — because the adapter stores interrupt events
                # under the full session key.
                if hasattr(adapter, 'has_pending_interrupt') and adapter.has_pending_interrupt(session_key):
                    agent = agent_holder[0]
                    if agent:
                        pending_event = adapter.get_pending_message(session_key)
                        pending_text = pending_event.text if pending_event else None
                        logger.debug("Interrupt detected from adapter, signaling agent...")
                        agent.interrupt(pending_text)
                        break
        
        interrupt_monitor = asyncio.create_task(monitor_for_interrupt())

        # Periodic "still working" notifications for long-running tasks.
        # Fires every 10 minutes so the user knows the agent hasn't died.
        _NOTIFY_INTERVAL = 600  # 10 minutes
        _notify_start = time.time()

        # Human-facing heartbeat for very long tasks. This is intentionally sparse
        # (10-minute cadence) so it reassures users without becoming chat spam.
        async def _notify_long_running():
            _notify_adapter = self.adapters.get(source.platform)
            if not _notify_adapter:
                return
            while True:
                await asyncio.sleep(_NOTIFY_INTERVAL)
                _elapsed_mins = int((time.time() - _notify_start) // 60)
                # Include agent activity context if available.
                _agent_ref = agent_holder[0]
                _status_detail = ""
                if _agent_ref and hasattr(_agent_ref, "get_activity_summary"):
                    try:
                        _a = _agent_ref.get_activity_summary()
                        _parts = [f"iteration {_a['api_call_count']}/{_a['max_iterations']}"]
                        if _a.get("current_tool"):
                            _parts.append(f"running: {_a['current_tool']}")
                        else:
                            _parts.append(_a.get("last_activity_desc", ""))
                        _status_detail = " — " + ", ".join(_parts)
                    except Exception:
                        pass
                try:
                    await _notify_adapter.send(
                        source.chat_id,
                        f"⏳ Still working... ({_elapsed_mins} min elapsed{_status_detail})",
                        metadata=_status_thread_metadata,
                    )
                except Exception as _ne:
                    logger.debug("Long-running notification error: %s", _ne)

        _notify_task = asyncio.create_task(_notify_long_running())

        try:
            # Run in thread pool to not block.  Use an *inactivity*-based
            # timeout instead of a wall-clock limit: the agent can run for
            # hours if it's actively calling tools / receiving stream tokens,
            # but a hung API call or stuck tool with no activity for the
            # configured duration is caught and killed.  (#4815)
            #
            # Config: agent.gateway_timeout in config.yaml, or
            # HERMES_AGENT_TIMEOUT env var (env var takes precedence).
            # Default 1800s (30 min inactivity).  0 = unlimited.
            # fec58ad99 replaced the old wall-clock timeout with inactivity-based polling.
            # Long research/tool runs are fine now as long as the agent keeps making
            # observable progress.
            _agent_timeout_raw = float(os.getenv("HERMES_AGENT_TIMEOUT", 1800))
            _agent_timeout = _agent_timeout_raw if _agent_timeout_raw > 0 else None
            _agent_warning_raw = float(os.getenv("HERMES_AGENT_TIMEOUT_WARNING", 900))
            _agent_warning = _agent_warning_raw if _agent_warning_raw > 0 else None
            _warning_fired = False
            loop = asyncio.get_event_loop()
            _executor_task = asyncio.ensure_future(
                loop.run_in_executor(None, run_sync)
            )

            _inactivity_timeout = False
            _POLL_INTERVAL = 5.0

            # A timeout of 0 means "unlimited"; skip the polling/idle checks entirely and
            # just await the executor result.
            if _agent_timeout is None:
                # Unlimited — just await the result.
                response = await _executor_task
            else:
                # Poll loop: check the agent's built-in activity tracker
                # (updated by _touch_activity() on every tool call, API
                # call, and stream delta) every few seconds.
                response = None
                # Poll every few seconds instead of wrapping the whole executor future in
                # asyncio.wait_for(). That lets the gateway inspect activity and warn before
                # declaring the run hung.
                while True:
                    done, _ = await asyncio.wait(
                        {_executor_task}, timeout=_POLL_INTERVAL
                    )
                    if done:
                        response = _executor_task.result()
                        break
                    # Agent still running — check inactivity.
                    _agent_ref = agent_holder[0]
                    _idle_secs = 0.0
                    if _agent_ref and hasattr(_agent_ref, "get_activity_summary"):
                        try:
                            _act = _agent_ref.get_activity_summary()
                            _idle_secs = _act.get("seconds_since_activity", 0.0)
                        except Exception:
                            pass
                    # Staged warning: fire once before escalating to full timeout.
                    # Staged warning gives the user context before the gateway forcibly times out
                    # the run. This is especially useful for slow providers or long tools that may
                    # still recover.
                    if (not _warning_fired and _agent_warning is not None
                            and _idle_secs >= _agent_warning):
                        _warning_fired = True
                        _warn_adapter = self.adapters.get(source.platform)
                        if _warn_adapter:
                            _elapsed_warn = int(_agent_warning // 60) or 1
                            _remaining_mins = int((_agent_timeout - _agent_warning) // 60) or 1
                            try:
                                await _warn_adapter.send(
                                    source.chat_id,
                                    f"⚠️ No activity for {_elapsed_warn} min. "
                                    f"If the agent does not respond soon, it will "
                                    f"be timed out in {_remaining_mins} min. "
                                    f"You can continue waiting or use /reset.",
                                    metadata=_status_thread_metadata,
                                )
                            except Exception as _warn_err:
                                logger.debug("Inactivity warning send error: %s", _warn_err)
                    if _idle_secs >= _agent_timeout:
                        _inactivity_timeout = True
                        break

            # On timeout, build both an operator-friendly log entry and a user-friendly
            # diagnostic reply from the same activity summary.
            if _inactivity_timeout:
                # Build a diagnostic summary from the agent's activity tracker.
                _timed_out_agent = agent_holder[0]
                _activity = {}
                if _timed_out_agent and hasattr(_timed_out_agent, "get_activity_summary"):
                    try:
                        _activity = _timed_out_agent.get_activity_summary()
                    except Exception:
                        pass

                _last_desc = _activity.get("last_activity_desc", "unknown")
                _secs_ago = _activity.get("seconds_since_activity", 0)
                _cur_tool = _activity.get("current_tool")
                _iter_n = _activity.get("api_call_count", 0)
                _iter_max = _activity.get("max_iterations", 0)

                logger.error(
                    "Agent idle for %.0fs (timeout %.0fs) in session %s "
                    "| last_activity=%s | iteration=%s/%s | tool=%s",
                    _secs_ago, _agent_timeout, session_key,
                    _last_desc, _iter_n, _iter_max,
                    _cur_tool or "none",
                )

                # Interrupt the agent if it's still running so the thread
                # pool worker is freed.
                if _timed_out_agent and hasattr(_timed_out_agent, "interrupt"):
                    _timed_out_agent.interrupt("Execution timed out (inactivity)")

                _timeout_mins = int(_agent_timeout // 60) or 1

                # Construct a user-facing message with diagnostic context.
                _diag_lines = [
                    f"⏱️ Agent inactive for {_timeout_mins} min — no tool calls "
                    f"or API responses."
                ]
                if _cur_tool:
                    _diag_lines.append(
                        f"The agent appears stuck on tool `{_cur_tool}` "
                        f"({_secs_ago:.0f}s since last activity, "
                        f"iteration {_iter_n}/{_iter_max})."
                    )
                else:
                    _diag_lines.append(
                        f"Last activity: {_last_desc} ({_secs_ago:.0f}s ago, "
                        f"iteration {_iter_n}/{_iter_max}). "
                        "The agent may have been waiting on an API response."
                    )
                _diag_lines.append(
                    "To increase the limit, set agent.gateway_timeout in config.yaml "
                    "(value in seconds, 0 = no limit) and restart the gateway.\n"
                    "Try again, or use /reset to start fresh."
                )

                response = {
                    "final_response": "\n".join(_diag_lines),
                    "messages": result_holder[0].get("messages", []) if result_holder[0] else [],
                    "api_calls": _iter_n,
                    "tools": tools_holder[0] or [],
                    "history_offset": 0,
                    "failed": True,
                }

            # Track fallback model state: if the agent switched to a
            # fallback model during this run, persist it so /model shows
            # the actually-active model instead of the config default.
            _agent = agent_holder[0]
            # Persist fallback-model state outside the agent so /model reports what is
            # actually active right now, not merely the configured default.
            if _agent is not None and hasattr(_agent, 'model'):
                _cfg_model = _resolve_gateway_model()
                if _agent.model != _cfg_model:
                    self._effective_model = _agent.model
                    self._effective_provider = getattr(_agent, 'provider', None)
                    # Fallback activated — evict cached agent so the next
                    # message starts fresh and retries the primary model.
                    self._evict_cached_agent(session_key)
                else:
                    # Primary model worked — clear any stale fallback state
                    self._effective_model = None
                    self._effective_provider = None

            # Check if we were interrupted OR have a queued message (/queue).
            result = result_holder[0]
            adapter = self.adapters.get(source.platform)
            
            # Get pending message from adapter.
            # Use session_key (not source.chat_id) to match adapter's storage keys.
            pending = None
            # After the main turn finishes, check whether a newer queued/interrupting
            # message should immediately chain into another _run_agent call.
            if result and adapter and session_key:
                if result.get("interrupted"):
                    pending = _dequeue_pending_text(adapter, session_key)
                    if not pending and result.get("interrupt_message"):
                        pending = result.get("interrupt_message")
                else:
                    pending = _dequeue_pending_text(adapter, session_key)
                    if pending:
                        logger.debug("Processing queued message after agent completion: '%s...'", pending[:40])
            
            # Safety net: if the pending text is a slash command (e.g. "/stop",
            # "/new"), discard it — commands should never be passed to the agent
            # as user input.  The primary fix is in base.py (commands bypass the
            # active-session guard), but this catches edge cases where command
            # text leaks through the interrupt_message fallback.
            # Defense in depth: slash commands should be handled by command routing, not
            # fed back into the model as plain user text.
            if pending and pending.strip().startswith("/"):
                _pending_parts = pending.strip().split(None, 1)
                _pending_cmd_word = _pending_parts[0][1:].lower() if _pending_parts else ""
                if _pending_cmd_word:
                    try:
                        from hermes_cli.commands import resolve_command as _rc_pending
                        if _rc_pending(_pending_cmd_word):
                            logger.info(
                                "Discarding command '/%s' from pending queue — "
                                "commands must not be passed as agent input",
                                _pending_cmd_word,
                            )
                            pending = None
                    except Exception:
                        pass

            if pending:
                logger.debug("Processing pending message: '%s...'", pending[:40])
                
                # Clear the adapter's interrupt event so the next _run_agent call
                # doesn't immediately re-trigger the interrupt before the new agent
                # even makes its first API call (this was causing an infinite loop).
                if adapter and hasattr(adapter, '_active_sessions') and session_key and session_key in adapter._active_sessions:
                    adapter._active_sessions[session_key].clear()
                
                # Cap recursion depth to prevent resource exhaustion when the
                # user sends multiple messages while the agent keeps failing. (#816)
                # Recursion cap fallback: re-queue the message and stop recursing so one noisy
                # session cannot spiral into infinite nested retries.
                if _interrupt_depth >= self._MAX_INTERRUPT_DEPTH:
                    logger.warning(
                        "Interrupt recursion depth %d reached for session %s — "
                        "queueing message instead of recursing.",
                        _interrupt_depth, session_key,
                    )
                    # Queue the pending message for normal processing on next turn
                    adapter = self.adapters.get(source.platform)
                    if adapter and hasattr(adapter, 'queue_message'):
                        adapter.queue_message(session_key, pending)
                    return result_holder[0] or {"final_response": response, "messages": history}

                was_interrupted = result.get("interrupted")
                # For queued follow-ups after a normal completion, deliver the first answer
                # before starting the next run. Interrupted responses, by contrast, are mostly
                # noise and are intentionally discarded.
                if not was_interrupted:
                    # Queued message after normal completion — deliver the first
                    # response before processing the queued follow-up.
                    # Skip if streaming already delivered it.
                    _sc = stream_consumer_holder[0]
                    _already_streamed = _sc and getattr(_sc, "already_sent", False)
                    first_response = result.get("final_response", "")
                    if first_response and not _already_streamed:
                        try:
                            await adapter.send(source.chat_id, first_response,
                                               metadata=getattr(event, "metadata", None))
                        except Exception as e:
                            logger.warning("Failed to send first response before queued message: %s", e)
                # else: interrupted — discard the interrupted response ("Operation
                # interrupted." is just noise; the user already knows they sent a
                # new message).

                # Process the pending message with updated history
                updated_history = result.get("messages", history)
                # Tail-recursive handoff: continue with the pending message while preserving the
                # updated agent-produced history from the just-finished turn.
                return await self._run_agent(
                    message=pending,
                    context_prompt=context_prompt,
                    history=updated_history,
                    source=source,
                    session_id=session_id,
                    session_key=session_key,
                    _interrupt_depth=_interrupt_depth + 1,
                )
        # Every auxiliary task created above must be cancelled/joined here so the
        # gateway does not leak background tasks across turns.
        finally:
            # Stop progress sender, interrupt monitor, and notification task
            if progress_task:
                progress_task.cancel()
            interrupt_monitor.cancel()
            _notify_task.cancel()

            # Wait for stream consumer to finish its final edit
            if stream_task:
                try:
                    await asyncio.wait_for(stream_task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    stream_task.cancel()
                    try:
                        await stream_task
                    except asyncio.CancelledError:
                        pass
            
            # Clean up tracking
            tracking_task.cancel()
            if session_key and session_key in self._running_agents:
                del self._running_agents[session_key]
            if session_key:
                self._running_agents_ts.pop(session_key, None)
            
            # Wait for cancelled tasks
            for task in [progress_task, interrupt_monitor, tracking_task, _notify_task]:
                if task:
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        # If streaming already delivered the response, mark it so the
        # caller's send() is skipped (avoiding duplicate messages).
        _sc = stream_consumer_holder[0]
        # Streaming may have already emitted the final answer message. Mark that fact so
        # outer caller code does not send a duplicate static reply afterward.
        if _sc and _sc.already_sent and isinstance(response, dict):
            response["already_sent"] = True
        
        return response

# Gateway-local cron runner. Keeping this inside the gateway process avoids the
# need for a separate daemon/service just to execute scheduled jobs.
def _start_cron_ticker(stop_event: threading.Event, adapters=None, loop=None, interval: int = 60):
    """
    Background thread that ticks the cron scheduler at a regular interval.
    
    Runs inside the gateway process so cronjobs fire automatically without
    needing a separate `hermes cron daemon` or system cron entry.

    When ``adapters`` and ``loop`` are provided, passes them through to the
    cron delivery path so live adapters can be used for E2EE rooms.

    Also refreshes the channel directory every 5 minutes and prunes the
    image/audio/document cache once per hour.
    """
    from cron.scheduler import tick as cron_tick
    from gateway.platforms.base import cleanup_image_cache, cleanup_document_cache

    IMAGE_CACHE_EVERY = 60   # ticks — once per hour at default 60s interval
    CHANNEL_DIR_EVERY = 5    # ticks — every 5 minutes

    logger.info("Cron ticker started (interval=%ds)", interval)
    tick_count = 0
    while not stop_event.is_set():
        try:
            # Passing adapters/loop allows cron deliveries to reuse live platform clients,
            # which matters for transports that need in-process state such as E2EE rooms.
            cron_tick(verbose=False, adapters=adapters, loop=loop)
        except Exception as e:
            logger.debug("Cron tick error: %s", e)

        tick_count += 1

        # The ticker also handles cheap maintenance chores so they piggyback on an
        # already-running background thread instead of each needing its own scheduler.
        if tick_count % CHANNEL_DIR_EVERY == 0 and adapters:
            try:
                from gateway.channel_directory import build_channel_directory
                build_channel_directory(adapters)
            except Exception as e:
                logger.debug("Channel directory refresh error: %s", e)

        # Attachment caches are pruned lazily here to keep disk usage bounded without
        # making every send/receive path pay cleanup costs.
        if tick_count % IMAGE_CACHE_EVERY == 0:
            try:
                removed = cleanup_image_cache(max_age_hours=24)
                if removed:
                    logger.info("Image cache cleanup: removed %d stale file(s)", removed)
            except Exception as e:
                logger.debug("Image cache cleanup error: %s", e)
            try:
                removed = cleanup_document_cache(max_age_hours=24)
                if removed:
                    logger.info("Document cache cleanup: removed %d stale file(s)", removed)
            except Exception as e:
                logger.debug("Document cache cleanup error: %s", e)

        stop_event.wait(timeout=interval)
    logger.info("Cron ticker stopped")


# High-level lifecycle entrypoint used by CLI/service code. Returns bool instead
# of exiting directly so callers can decide whether failure should trigger a
# restart policy.
async def start_gateway(config: Optional[GatewayConfig] = None, replace: bool = False, verbosity: Optional[int] = 0) -> bool:
    """
    Start the gateway and run until interrupted.
    
    This is the main entry point for running the gateway.
    Returns True if the gateway ran successfully, False if it failed to start.
    A False return causes a non-zero exit code so systemd can auto-restart.
    
    Args:
        config: Optional gateway configuration override.
        replace: If True, kill any existing gateway instance before starting.
                 Useful for systemd services to avoid restart-loop deadlocks
                 when the previous process hasn't fully exited yet.
    """
    # ── Duplicate-instance guard ──────────────────────────────────────
    # Prevent two gateways from running under the same HERMES_HOME.
    # The PID file is scoped to HERMES_HOME, so future multi-profile
    # setups (each profile using a distinct HERMES_HOME) will naturally
    # allow concurrent instances without tripping this guard.
    import time as _time
    from gateway.status import get_running_pid, remove_pid_file
    # Single-instance guard is scoped to HERMES_HOME, not machine-wide, so future
    # multi-profile installs can run separate gateways side by side.
    existing_pid = get_running_pid()
    # If another gateway already owns this profile, either refuse to start or, when
    # --replace is set, actively take over after terminating the old process.
    if existing_pid is not None and existing_pid != os.getpid():
        # Systemd-friendly takeover path: attempt SIGTERM first, then escalate to
        # SIGKILL only if the old process stays alive.
        if replace:
            logger.info(
                "Replacing existing gateway instance (PID %d) with --replace.",
                existing_pid,
            )
            try:
                os.kill(existing_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # Already gone
            except PermissionError:
                logger.error(
                    "Permission denied killing PID %d. Cannot replace.",
                    existing_pid,
                )
                return False
            # Wait up to 10 seconds for the old process to exit
            for _ in range(20):
                try:
                    os.kill(existing_pid, 0)
                    _time.sleep(0.5)
                except (ProcessLookupError, PermissionError):
                    break  # Process is gone
            else:
                # Still alive after 10s — force kill
                logger.warning(
                    "Old gateway (PID %d) did not exit after SIGTERM, sending SIGKILL.",
                    existing_pid,
                )
                try:
                    os.kill(existing_pid, signal.SIGKILL)
                    _time.sleep(0.5)
                except (ProcessLookupError, PermissionError):
                    pass
            # Once the old process is gone, proactively clear its pid file and stale scoped
            # locks so the replacement instance does not deadlock on leftover state.
            remove_pid_file()
            # Also release all scoped locks left by the old process.
            # Stopped (Ctrl+Z) processes don't release locks on exit,
            # leaving stale lock files that block the new gateway from starting.
            try:
                from gateway.status import release_all_scoped_locks
                _released = release_all_scoped_locks()
                if _released:
                    logger.info("Released %d stale scoped lock(s) from old gateway.", _released)
            except Exception:
                pass
        else:
            # The user-facing error includes HERMES_HOME because that is the true unit of
            # gateway isolation and the most useful clue when multiple profiles exist.
            hermes_home = str(get_hermes_home())
            logger.error(
                "Another gateway instance is already running (PID %d, HERMES_HOME=%s). "
                "Use 'hermes gateway restart' to replace it, or 'hermes gateway stop' first.",
                existing_pid, hermes_home,
            )
            print(
                f"\n❌ Gateway already running (PID {existing_pid}).\n"
                f"   Use 'hermes gateway restart' to replace it,\n"
                f"   or 'hermes gateway stop' to kill it first.\n"
                f"   Or use 'hermes gateway run --replace' to auto-replace.\n"
            )
            return False

    # Sync bundled skills on gateway start (fast -- skips unchanged)
    try:
        from tools.skills_sync import sync_skills
        # Bundled skills are synced opportunistically at startup so newly shipped skills
        # appear automatically, while unchanged installs stay fast.
        sync_skills(quiet=True)
    except Exception:
        pass

    # Centralized logging — agent.log (INFO+) and errors.log (WARNING+).
    # Idempotent, so repeated calls from AIAgent.__init__ won't duplicate.
    from hermes_logging import setup_logging
    # Logging setup is intentionally idempotent because agent construction may also
    # touch logging code; duplicate handlers would otherwise explode log volume.
    log_dir = setup_logging(hermes_home=_hermes_home, mode="gateway")

    # Gateway-specific rotating log — captures all gateway-level messages
    # (session management, platform adapters, slash commands, etc.).
    from agent.redact import RedactingFormatter
    from hermes_logging import _add_rotating_handler
    # Separate gateway.log keeps adapter/session/router noise distinct from the
    # core agent log stream, while RedactingFormatter strips sensitive values.
    _add_rotating_handler(
        logging.getLogger(),
        log_dir / 'gateway.log',
        level=logging.INFO,
        max_bytes=5 * 1024 * 1024,
        backup_count=3,
        formatter=RedactingFormatter('%(asctime)s %(levelname)s %(name)s: %(message)s'),
    )

    # Optional stderr handler — level driven by -v/-q flags on the CLI.
    # verbosity=None (-q/--quiet): no stderr output
    # verbosity=0    (default):    WARNING and above
    # verbosity=1    (-v):         INFO and above
    # verbosity=2+   (-vv/-vvv):   DEBUG
    # CLI verbosity only controls stderr mirroring; persistent file logging stays
    # enabled regardless so service operators still get forensic logs.
    if verbosity is not None:
        _stderr_level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)
        _stderr_handler = logging.StreamHandler()
        _stderr_handler.setLevel(_stderr_level)
        _stderr_handler.setFormatter(RedactingFormatter('%(levelname)s %(name)s: %(message)s'))
        logging.getLogger().addHandler(_stderr_handler)
        # Lower root logger level if needed so DEBUG records can reach the handler
        if _stderr_level < logging.getLogger().level:
            logging.getLogger().setLevel(_stderr_level)

    runner = GatewayRunner(config)
    
    # Set up signal handlers
    # Convert POSIX signals into the same async stop path used elsewhere so
    # shutdown behavior stays consistent.
    def signal_handler():
        asyncio.create_task(runner.stop())
    
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass
    
    # Start the gateway
    # Runner.start() performs platform adapter startup. A False here means startup
    # failed before the gateway entered its steady-state wait loop.
    success = await runner.start()
    if not success:
        return False
    # Some startup paths intentionally exit without being considered failures
    # (for example, a self-update/restart handoff). Preserve that distinction for
    # supervisors like systemd.
    if runner.should_exit_cleanly:
        if runner.exit_reason:
            logger.error("Gateway exiting cleanly: %s", runner.exit_reason)
        return True
    
    # Write PID file so CLI can detect gateway is running
    import atexit
    from gateway.status import write_pid_file, remove_pid_file
    # PID file is written only after a successful start so CLI status checks do not
    # see a half-initialized gateway as healthy.
    write_pid_file()
    atexit.register(remove_pid_file)
    
    # Start background cron ticker so scheduled jobs fire automatically.
    # Pass the event loop so cron delivery can use live adapters (E2EE support).
    cron_stop = threading.Event()
    # Cron runs in a daemon thread because its scheduler is synchronous and mostly
    # sleep-based; there is no need to burden the main asyncio loop with it.
    cron_thread = threading.Thread(
        target=_start_cron_ticker,
        args=(cron_stop,),
        kwargs={"adapters": runner.adapters, "loop": asyncio.get_running_loop()},
        daemon=True,
        name="cron-ticker",
    )
    cron_thread.start()
    
    # Wait for shutdown
    await runner.wait_for_shutdown()

    # Mirror the clean-exit check above, but classify this path as a failure so
    # Restart=on-failure style supervisors will relaunch the gateway.
    if runner.should_exit_with_failure:
        if runner.exit_reason:
            logger.error("Gateway exiting with failure: %s", runner.exit_reason)
        return False
    
    # Stop cron ticker cleanly
    cron_stop.set()
    cron_thread.join(timeout=5)

    # Close MCP server connections
    try:
        from tools.mcp_tool import shutdown_mcp_servers
        # Best-effort cleanup for long-lived MCP subprocess/server connections; do not
        # let teardown failures mask an otherwise successful shutdown.
        shutdown_mcp_servers()
    except Exception:
        pass

    return True


# Thin CLI wrapper: parse args, optionally load a config override, then hand
# control to start_gateway().
def main():
    """CLI entry point for the gateway."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Hermes Gateway - Multi-platform messaging")
    parser.add_argument("--config", "-c", help="Path to gateway config file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    config = None
    if args.config:
        import json
        with open(args.config, encoding="utf-8") as f:
            data = json.load(f)
            config = GatewayConfig.from_dict(data)
    
    # Run the gateway - exit with code 1 if no platforms connected,
    # so systemd Restart=on-failure will retry on transient errors (e.g. DNS)
    # Non-zero exit on startup/runtime failure is intentional so service managers
    # can retry transient platform/network problems automatically.
    success = asyncio.run(start_gateway(config))
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
