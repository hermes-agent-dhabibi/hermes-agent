"""Execution State Runtime — Hermes Plugin (v0.4)

Maintains durable structured execution state across turns with REAL enforcement:
- Phase machine: IDLE → PLANNING → EXECUTING → VERIFYING → DONE/BLOCKED
- Concurrent-safe: state keyed by (session_id, task_id) via StateRegistry
- Mandatory once activated: agent must use ESR tools to manage plan
- Hard enforcement: blocked=blocked, approval=approval, phase gates tool calls
- Deterministic step advancement with concrete criteria verification
- Subagent isolation: each task_id gets its own state via pre/post_tool_call

Hook contracts verified against Hermes source (run_agent.py, model_tools.py):

  on_session_start:
    kwargs: session_id, model, platform
    return: ignored
    NOTE: no task_id — only fires for root session

  pre_llm_call:
    kwargs: session_id, user_message, conversation_history, is_first_turn,
            model, platform, sender_id
    return: {"context": "..."} → appended to user message
    NOTE: no task_id — fires once before tool loop, value captured once

  pre_tool_call:
    kwargs: tool_name, args, task_id, session_id, tool_call_id
    return: {"action": "block", "message": "..."} → tool gets JSON error
    NOTE: concurrent _invoke_tool path may not pass session_id

  post_tool_call:
    kwargs: tool_name, args, result, task_id, session_id, tool_call_id
    return: ignored
    NOTE: always has session_id

  post_llm_call:
    kwargs: session_id, user_message, assistant_response,
            conversation_history, model, platform
    return: ignored
    NOTE: no task_id

  on_session_end:
    kwargs: session_id, completed, interrupted, model, platform
    return: ignored
    NOTE: no task_id

Subagent isolation strategy:
  - pre_tool_call and post_tool_call receive task_id → we key state by it
  - pre_llm_call/post_llm_call/on_session_* don't get task_id → always
    operate on root session state (task_id="")
  - This means subagent state is isolated for tool gating/reconciliation
    but the brief only reflects root session state
  - True per-subagent briefs would require a core change to pass task_id
    to pre_llm_call (OPTIONAL ENHANCEMENT, NOT REQUIRED)

Composition:
  - Memory: both inject into user message via concatenation, no conflict
  - Todo: always allowed by validator, independent state
  - delegate_task: subagents get task_id → isolated state via registry
  - tool_result_storage: independent paths, different abstraction levels
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _get_state(session_id: str, task_id: str = ""):
    """Get state from registry. Returns None if no session_id."""
    if not session_id:
        return None
    from .state import get_registry
    return get_registry().get(session_id, task_id)


def _get_or_create_state(session_id: str, task_id: str = ""):
    """Get or create state from registry."""
    if not session_id:
        return None
    from .state import get_registry
    return get_registry().get_or_create(session_id, task_id)


# ---------------------------------------------------------------------------
# Hook implementations
# ---------------------------------------------------------------------------

def _on_session_start(session_id: str = "", **kwargs):
    """Load or create runtime state for this session.

    Always reloads policy from .hermes.md so changes are picked up
    on resumed sessions.
    """
    from .policy import load_policy_from_cwd, apply_policy_to_state

    state = _get_or_create_state(session_id)
    if state is None:
        return

    # Always reload policy
    policy = load_policy_from_cwd()
    if policy:
        apply_policy_to_state(state, policy)
        logger.info("ESR: Applied policy from .hermes.md")

    from .profiles import apply_profile
    if state.profile:
        apply_profile(state, state.profile)

    from .trace import record_event
    record_event(state, "policy_applied", source=".hermes.md", fields_set=str(bool(policy)))
    state.save()

    logger.info(
        "ESR: Session %s — phase=%s, goal=%s, steps=%d",
        session_id[:12] if session_id else "?",
        state.phase.value,
        state.goal[:40] if state.goal else "(none)",
        len(state.plan),
    )


def _pre_llm_call(
    session_id: str = "",
    **kwargs,
) -> Optional[Dict[str, str]]:
    """Compile and inject the step brief into the user message.

    NOTE: No task_id available here — always briefs from root state.
    Fires once per turn; captured value injected on every API loop iteration.
    """
    # Root state only (task_id="")
    state = _get_or_create_state(session_id)
    if state is None:
        return None

    from .brief import compile_brief
    from .status_display import format_status_compact

    brief = compile_brief(state)
    compact = format_status_compact(state)
    if brief:
        return {"context": f"{compact}\n\n{brief}"}
    elif state.goal:
        return {"context": compact}
    return None


def _pre_tool_call(
    tool_name: str = "",
    args: dict = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **kwargs,
) -> Optional[Dict[str, str]]:
    """Validate tool calls against runtime state.

    This is where real enforcement happens. Returns
    {"action": "block", "message": "..."} to reject a tool call.

    KNOWN ENFORCEMENT GAP — concurrent path:
    run_agent._invoke_tool() calls get_pre_tool_call_block_message()
    with only task_id — session_id is empty. This means tool calls
    dispatched via the concurrent execution path BYPASS ESR validation.
    The subsequent observer-only re-fire of pre_tool_call DOES have
    session_id, but by then the tool has already been allowed to run.
    post_tool_call still reconciles the result into state.

    Impact: concurrent tool calls (multiple tools in one LLM response)
    skip phase/policy gating. Sequential tool calls are fully enforced.

    Fix: one-line core change in run_agent.py:6936-6938 to pass
    session_id=self.session_id. See ARCHITECTURE.md for details.
    """
    if not session_id:
        # Concurrent path without session_id — can't validate, allow
        return None

    state = _get_state(session_id, task_id)
    if state is None:
        # No state initialized yet — allow (session_start hasn't fired
        # or this is a subagent that hasn't used ESR)
        return None

    from .validator import validate_tool_call
    from .trace import record_event

    result = validate_tool_call(state, tool_name, args or {})
    if result:
        record_event(
            state,
            "tool_blocked",
            tool_name=tool_name,
            reason=result.get("message", ""),
            phase=state.phase.value,
        )
        state.save()
        logger.warning("ESR: Blocked %s — %s", tool_name, result.get("message", ""))
    return result


def _post_tool_call(
    tool_name: str = "",
    args: dict = None,
    result: str = "",
    task_id: str = "",
    session_id: str = "",
    **kwargs,
):
    """Reconcile tool results back into runtime state.

    Has both session_id and task_id — can operate on subagent state.
    """
    if not session_id:
        return

    state = _get_state(session_id, task_id)
    if state is None:
        return

    from .reconciler import reconcile_tool_result
    from .trace import record_event

    reconcile_tool_result(state, tool_name, args or {}, result or "")
    record_event(
        state,
        "tool_executed",
        tool_name=tool_name,
        duration_hint=0,
        result_size=len(result or ""),
    )
    state.save()


def _post_llm_call(
    session_id: str = "",
    **kwargs,
):
    """Persist root state at end of turn."""
    state = _get_state(session_id)
    if state is None:
        return
    state.save()


def _on_session_end(session_id: str = "", **kwargs):
    """Final state persistence on session end."""
    state = _get_state(session_id)
    if state is None:
        return

    from .trace import get_trace_summary

    trace_summary = get_trace_summary(state)
    logger.info("ESR: Trace summary — %s", trace_summary)
    state.save()
    logger.info(
        "ESR: Session ended — phase=%s, progress=%.0f%%",
        state.phase.value,
        state.progress_fraction * 100,
    )


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

def register(ctx):
    """Register the Execution State Runtime plugin with Hermes."""
    from .schemas import (
        ESR_UPDATE_PLAN_SCHEMA,
        ESR_BLOCK_SCHEMA,
        ESR_DONE_SCHEMA,
        ESR_STATUS_SCHEMA,
        ESR_TRACE_SCHEMA,
    )
    from .tools import (
        handle_esr_update_plan,
        handle_esr_block,
        handle_esr_done,
        handle_esr_status,
        handle_esr_trace,
    )

    toolset = "execution_state"

    ctx.register_tool(
        name="esr_update_plan",
        toolset=toolset,
        schema=ESR_UPDATE_PLAN_SCHEMA,
        handler=handle_esr_update_plan,
        description="START HERE — set goal (set_goal), define plan (set_plan), advance/complete steps, record facts. Must call set_goal first before any other ESR tool.",
    )
    ctx.register_tool(
        name="esr_block",
        toolset=toolset,
        schema=ESR_BLOCK_SCHEMA,
        handler=handle_esr_block,
        description="Report a blocker preventing progress",
    )
    ctx.register_tool(
        name="esr_done",
        toolset=toolset,
        schema=ESR_DONE_SCHEMA,
        handler=handle_esr_done,
        description="Signal task completion",
    )
    ctx.register_tool(
        name="esr_status",
        toolset=toolset,
        schema=ESR_STATUS_SCHEMA,
        handler=handle_esr_status,
        description="View current execution state (requires esr_update_plan set_goal first)",
    )
    ctx.register_tool(
        name="esr_trace",
        toolset=toolset,
        schema=ESR_TRACE_SCHEMA,
        handler=handle_esr_trace,
        description="View ESR trace log (requires esr_update_plan set_goal first)",
    )

    from .schemas import ESR_OPERATOR_SCHEMA, ESR_PROFILE_SCHEMA
    from .tools import handle_esr_operator, handle_esr_profile

    ctx.register_tool(
        name='esr_operator',
        toolset=toolset,
        schema=ESR_OPERATOR_SCHEMA,
        handler=handle_esr_operator,
        description='Operator recovery controls — override phase, force-complete steps, reset state',
    )
    ctx.register_tool(
        name='esr_profile',
        toolset=toolset,
        schema=ESR_PROFILE_SCHEMA,
        handler=handle_esr_profile,
        description='Manage workflow profiles — apply, list, or check current profile',
    )

    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("post_llm_call", _post_llm_call)
    ctx.register_hook("on_session_end", _on_session_end)

    logger.info("ESR: Execution State Runtime v0.4.1 registered")
