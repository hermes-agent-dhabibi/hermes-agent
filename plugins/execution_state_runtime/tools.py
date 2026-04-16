"""ESR tool handlers — session/task-aware, phase-enforced.

These are the tools the model uses to manage execution state.
Each handler resolves state via the registry using session_id
and task_id from kwargs (passed by Hermes model_tools.py).

Tools:
- esr_update_plan: Set goal, plan, advance steps, record facts
- esr_block: Report a blocker
- esr_done: Signal task completion
- esr_status: View current state
- esr_trace: View recent trace events or trace summary
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict

from .state import Phase, PlanStep, get_registry
from .trace import record_event, get_trace_summary, get_events_by_type, format_trace_log, get_recent_events

logger = logging.getLogger(__name__)


def _resolve_state(kwargs: Dict[str, Any]):
    """Resolve RuntimeState from tool kwargs.

    Tool handlers receive session_id and task_id from Hermes
    (model_tools.py passes these via handle_function_call).
    """
    session_id = kwargs.get("session_id", "")
    task_id = kwargs.get("task_id", "")
    if not session_id:
        return None
    return get_registry().get_or_create(session_id, task_id)


def _format_trace_entries(events: list[Dict[str, Any]]) -> list[str]:
    """Format trace entries similarly to format_trace_log()."""
    formatted = []
    for entry in events:
        ts = entry.get("timestamp", 0.0)
        stamp = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "00:00:00"
        phase = str(entry.get("phase_at_time", "unknown") or "unknown").upper()
        event_type = str(entry.get("event_type", "unknown") or "unknown")
        detail = entry.get("detail", {})
        detail_str = ", ".join(
            f"{key}={json.dumps(value, ensure_ascii=False)}" if isinstance(value, (dict, list)) else f"{key}={value}"
            for key, value in detail.items()
        )
        if detail_str:
            formatted.append(f"[{stamp}] [{phase}] {event_type}: {detail_str}")
        else:
            formatted.append(f"[{stamp}] [{phase}] {event_type}:")
    return formatted


def handle_esr_update_plan(args: Dict[str, Any], **kwargs) -> str:
    """Handle the esr_update_plan tool call.

    Actions:
    - set_goal: Set/change goal and success criteria
    - set_plan: Replace plan with new steps
    - advance_step: Mark current step done and move to next
    - complete_step: Mark current step done without advancing
    - add_fact: Record a working fact
    - clear_blocker: Unblock and resume
    """
    state = _resolve_state(kwargs)
    if state is None:
        return json.dumps({"error": "ESR not activated. Call esr_update_plan(action='set_goal', goal='...', success_criteria=[...]) first to initialize execution state."})

    action = args.get("action", "")

    if action == "set_goal":
        # If reopening from DONE, transition back to IDLE first
        if state.phase == Phase.DONE:
            state.transition_to(Phase.IDLE, "reopened with new goal")
        state.goal = args.get("goal", state.goal)
        if args.get("success_criteria"):
            state.success_criteria = args["success_criteria"]
        if args.get("hard_constraints"):
            state.hard_constraints = args["hard_constraints"]
        record_event(state, "goal_set", goal_text=state.goal)
        state.save()
        return json.dumps({
            "status": "ok",
            "phase": state.phase.value,
            "goal": state.goal,
        })

    elif action == "set_plan":
        steps = args.get("steps", [])
        if not steps:
            return json.dumps({"error": "No steps provided"})

        try:
            state.set_plan(steps)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

        # Auto-start first step and transition to EXECUTING
        if state.plan:
            state.start_current_step()

        record_event(
            state,
            "plan_set",
            step_count=len(state.plan),
            step_ids=[s.id for s in state.plan],
        )
        state.save()
        return json.dumps({
            "status": "ok",
            "phase": state.phase.value,
            "steps": len(state.plan),
            "current_step": state.get_current_step().id if state.get_current_step() else None,
        })

    elif action == "advance_step":
        step = state.get_current_step()
        if step is None:
            return json.dumps({"error": "No active step to advance from"})

        result_summary = args.get("step_result", "")
        completed = state.complete_current_step(result=result_summary)

        next_step = state.get_current_step()
        record_event(
            state,
            "step_completed",
            step_id=completed.id,
            result_summary=result_summary,
            criteria=completed.success_criteria,
            auto_advanced=bool(next_step),
        )
        state.save()

        return json.dumps({
            "status": "ok",
            "completed_step": completed.id if completed else None,
            "next_step": next_step.id if next_step else None,
            "phase": state.phase.value,
            "progress": f"{state.progress_fraction:.0%}",
        })

    elif action == "complete_step":
        step = state.get_current_step()
        if step is None:
            return json.dumps({"error": "No active step to complete"})

        result_summary = args.get("step_result", "")
        # Go through state machine — not direct step.status assignment.
        # complete_current_step() handles index advancement and phase transitions.
        completed = state.complete_current_step(result=result_summary)

        next_step = state.get_current_step()
        record_event(
            state,
            "step_completed",
            step_id=completed.id,
            result_summary=result_summary,
            criteria=completed.success_criteria,
            auto_advanced=bool(next_step),
        )
        state.save()
        return json.dumps({
            "status": "ok",
            "completed_step": completed.id if completed else step.id,
            "next_step": next_step.id if next_step else None,
            "phase": state.phase.value,
            "progress": f"{state.progress_fraction:.0%}",
        })

    elif action == "add_fact":
        key = args.get("fact_key", "")
        value = args.get("fact_value", "")
        if not key:
            return json.dumps({"error": "fact_key required"})

        state.working_facts[key] = value[:500]

        # Check if this is an approval fact
        if key.startswith("approve:"):
            tool_name = key[len("approve:"):]
            if value.lower() in ("yes", "true", "1", "approved"):
                state.approved_tools[tool_name] = True
                logger.info("ESR: Approved tool %s", tool_name)

        state.save()
        return json.dumps({"status": "ok", "fact": {key: value}})

    elif action == "clear_blocker":
        if not state.is_blocked:
            return json.dumps({"error": "Not currently blocked"})

        prev_reason = state.blocked_on
        success = state.unblock()
        if success:
            record_event(state, "blocker_cleared", previous_reason=prev_reason)
        state.save()
        return json.dumps({
            "status": "ok" if success else "transition_failed",
            "phase": state.phase.value,
        })

    else:
        return json.dumps({
            "error": f"Unknown action: {action}",
            "valid_actions": [
                "set_goal", "set_plan", "advance_step",
                "complete_step", "add_fact", "clear_blocker",
            ],
        })


def handle_esr_block(args: Dict[str, Any], **kwargs) -> str:
    """Report that progress is blocked."""
    state = _resolve_state(kwargs)
    if state is None:
        return json.dumps({"error": "ESR not activated. Call esr_update_plan(action='set_goal', goal='...', success_criteria=[...]) first to initialize execution state."})

    reason = args.get("reason", "Unknown blocker")
    needs = args.get("needs", "")

    success = state.block(reason, needs)
    if success:
        record_event(state, "blocker_set", reason=reason, needs=needs)
    state.save()

    return json.dumps({
        "status": "ok" if success else "transition_failed",
        "phase": state.phase.value,
        "blocked_on": state.blocked_on,
    })


def handle_esr_done(args: Dict[str, Any], **kwargs) -> str:
    """Signal task completion.

    Validates:
    1. If enforce_plan, all steps must be completed/cancelled
    2. Summary is recorded
    3. Artifact handles are validated (if provided)
    """
    state = _resolve_state(kwargs)
    if state is None:
        return json.dumps({"error": "ESR not activated. Call esr_update_plan(action='set_goal', goal='...', success_criteria=[...]) first to initialize execution state."})

    summary = args.get("summary", "")
    artifact_handles = args.get("artifacts", [])

    # Validate artifact handles if provided
    if artifact_handles:
        known_handles = {a.handle for a in state.artifacts}
        unknown = [h for h in artifact_handles if h not in known_handles]
        if unknown:
            return json.dumps({
                "error": f"Unknown artifact handles: {unknown}",
                "known_handles": list(known_handles),
            })

    success = state.finalize(summary)
    if not success:
        # finalize() sets self.finalize_error with the specific reason
        error_detail = getattr(state, "finalize_error", "")
        incomplete = [
            s.id for s in state.plan
            if s.status not in ("completed", "cancelled", "skipped")
        ]
        unverified = [
            c for i, c in enumerate(state.success_criteria)
            if not state.working_facts.get(f"verified:{i}")
            and not state.working_facts.get(f"verified:{c[:80]}")
        ]
        return json.dumps({
            "error": error_detail or "Cannot finalize",
            "incomplete_steps": incomplete if incomplete else None,
            "unverified_criteria": unverified if unverified else None,
            "phase": state.phase.value,
        })

    record_event(state, "done", summary=summary)
    state.save()
    return json.dumps({
        "status": "done",
        "phase": state.phase.value,
        "summary": summary[:200],
        "progress": f"{state.progress_fraction:.0%}",
    })


def handle_esr_status(args: Dict[str, Any], **kwargs) -> str:
    """View current execution state."""
    state = _resolve_state(kwargs)
    if state is None:
        return json.dumps({"error": "ESR not activated. Call esr_update_plan(action='set_goal', goal='...', success_criteria=[...]) first to initialize execution state."})

    current_step = state.get_current_step()
    recent_trace = get_recent_events(state, count=3)

    status = {
        "phase": state.phase.value,
        "goal": state.goal,
        "profile": state.profile,
        "progress": f"{state.progress_fraction:.0%}",
        "plan": [
            {
                "id": s.id,
                "description": s.description[:100],
                "status": s.status,
                "criteria": s.success_criteria[:100] if s.success_criteria else "",
            }
            for s in state.plan
        ],
        "current_step": current_step.id if current_step else None,
        "working_facts": state.working_facts,
        "artifacts": [
            {"handle": a.handle, "summary": a.summary}
            for a in state.artifacts
        ],
        "blocked_on": state.blocked_on or None,
        "trace_recent": _format_trace_entries(recent_trace),
        "enforcement": {
            "enforce_plan": state.enforce_plan,
            "mandatory": state.mandatory,
            "blocked_tools": state.blocked_tools,
            "approval_required": state.approval_required_tools,
        },
    }

    return json.dumps(status, indent=2)


def handle_esr_trace(args: Dict[str, Any], **kwargs) -> str:
    """View recent ESR trace events or aggregate trace summary."""
    state = _resolve_state(kwargs)
    if state is None:
        return json.dumps({"error": "ESR not activated. Call esr_update_plan(action='set_goal', goal='...', success_criteria=[...]) first to initialize execution state."})

    count = args.get("count", 20)
    event_type = args.get("event_type", "")
    summary = args.get("summary", False)

    if summary:
        return json.dumps(get_trace_summary(state), indent=2)

    if event_type:
        events = get_events_by_type(state, event_type)
        formatted = _format_trace_entries(events)
        return "\n".join(formatted) if formatted else f"No trace events recorded for event_type '{event_type}'."

    return format_trace_log(state, count)


def handle_esr_operator(args: Dict[str, Any], **kwargs) -> str:
    """Handle ESR operator recovery and override actions."""
    state = _resolve_state(kwargs)
    if state is None:
        return json.dumps({"error": "ESR not activated. Call esr_update_plan(action='set_goal', goal='...', success_criteria=[...]) first to initialize execution state."})

    action = args.get("action", "")

    if action == "override_phase":
        from .operator import override_phase
        from .state import Phase

        target_phase_raw = args.get("target_phase", "")
        reason = args.get("reason", "")
        try:
            result = override_phase(state, Phase(target_phase_raw), reason)
        except ValueError:
            return json.dumps({
                "error": f"Invalid target_phase: {target_phase_raw}",
                "valid_phases": ["idle", "planning", "executing", "verifying", "done", "blocked"],
            })
        record_event(state, "operator_override", action="override_phase", reason=reason)
        state.save()
        return json.dumps({
            "status": "ok" if result else "failed",
            "phase": state.phase.value,
            "action": action,
            "target_phase": target_phase_raw,
            "reason": reason,
        })

    elif action == "force_complete_step":
        from .operator import force_complete_step

        step_id = args.get("step_id", "")
        reason = args.get("reason", "")
        result = force_complete_step(state, step_id, reason)
        record_event(state, "operator_override", action="force_complete_step", reason=reason)
        state.save()
        return json.dumps({
            "status": "ok" if result else "failed",
            "phase": state.phase.value,
            "action": action,
            "step_id": step_id,
            "reason": reason,
        })

    elif action == "force_done":
        from .operator import force_done

        summary = args.get("summary", "")
        result = force_done(state, summary)
        record_event(state, "operator_override", action="force_done", reason=summary)
        state.save()
        return json.dumps({
            "status": "ok" if result else "failed",
            "phase": state.phase.value,
            "action": action,
            "summary": summary,
        })

    elif action == "verification_override":
        from .operator import verification_override

        criterion_index = args.get("criterion_index", 0)
        reason = args.get("reason", "")
        result = verification_override(state, criterion_index, reason)
        record_event(state, "operator_override", action="verification_override", reason=reason)
        state.save()
        return json.dumps({
            "status": "ok" if result else "failed",
            "phase": state.phase.value,
            "action": action,
            "criterion_index": criterion_index,
            "reason": reason,
        })

    elif action == "clear_errors":
        from .operator import clear_all_errors

        count = clear_all_errors(state)
        record_event(state, "operator_override", action="clear_errors", reason=args.get("reason", ""))
        state.save()
        return json.dumps({
            "status": "ok",
            "phase": state.phase.value,
            "action": action,
            "cleared_errors": count,
        })

    elif action == "reset":
        from .operator import reset_to_idle

        reason = args.get("reason", "")
        result = reset_to_idle(state)
        record_event(state, "operator_override", action="reset", reason=reason)
        state.save()
        return json.dumps({
            "status": "ok" if result else "failed",
            "phase": state.phase.value,
            "action": action,
            "reason": reason,
        })

    else:
        return json.dumps({
            "error": f"Unknown action: {action}",
            "valid_actions": [
                "override_phase",
                "force_complete_step",
                "force_done",
                "verification_override",
                "clear_errors",
                "reset",
            ],
        })


def handle_esr_profile(args: Dict[str, Any], **kwargs) -> str:
    """Handle ESR workflow profile actions."""
    state = _resolve_state(kwargs)
    if state is None:
        return json.dumps({"error": "ESR not activated. Call esr_update_plan(action='set_goal', goal='...', success_criteria=[...]) first to initialize execution state."})

    action = args.get("action", "")

    if action == "apply":
        from .profiles import apply_profile

        profile = args.get("profile", "")
        result = apply_profile(state, profile)
        if not result:
            return json.dumps({"error": f"Unknown profile: {profile}"})
        record_event(
            state,
            "policy_applied",
            source=profile,
            fields_set={
                "enforce_plan": state.enforce_plan,
                "mandatory": state.mandatory,
                "blocked_tools": state.blocked_tools,
                "approval_required_tools": state.approval_required_tools,
            },
        )
        state.save()
        return json.dumps({
            "status": "ok",
            "profile": state.profile,
            "enforcement": {
                "enforce_plan": state.enforce_plan,
                "mandatory": state.mandatory,
                "blocked_tools": state.blocked_tools,
                "approval_required_tools": state.approval_required_tools,
            },
        })

    elif action == "list":
        from .profiles import list_profiles

        profiles = [
            {"name": name, "description": description}
            for name, description in list_profiles()
        ]
        return json.dumps({"profiles": profiles}, indent=2)

    elif action == "current":
        return json.dumps({
            "profile": state.profile,
            "enforcement": {
                "enforce_plan": state.enforce_plan,
                "mandatory": state.mandatory,
                "blocked_tools": state.blocked_tools,
                "approval_required_tools": state.approval_required_tools,
            },
        })

    else:
        return json.dumps({
            "error": f"Unknown action: {action}",
            "valid_actions": ["apply", "list", "current"],
        })
