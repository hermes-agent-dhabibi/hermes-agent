# Local Discord Gateway Layer for Smooth Upstream Tracking

### Problem Statement

Danny runs a customized Hermes hard fork where Discord is the primary interface, not an optional edge adapter. The fork has accumulated Discord, gateway, trace, terminal, media, and UX changes directly inside upstream-shaped modules. After each upstream rebase, these scattered edits create conflicts or worse: silent semantic regressions where the code applies cleanly but Discord behavior changes.

The most painful recent example is Discord thinking/tool traces. After rebasing, not every action, commentary message, and tool call appeared in Discord, making it difficult to debug live incidents such as unexpected gateway shutdown/restart behavior. The underlying issue is architectural: local Discord auditability and UX behavior are braided through generic gateway streaming, upstream adapter internals, and agent callback behavior.

Danny wants upstream tracking to become much smoother. He also expects to continue making custom changes, so the codebase needs a deliberate **Local Layer**: code that belongs to this fork, is allowed to diverge, and is kept out of upstream-shaped modules except through tiny hook points.

### Solution

Create a small **Local Layer** for gateway/Discord behavior that subclasses, wraps, or calls into upstream-shaped code rather than copying it wholesale. Upstream-shaped code should continue to own protocol/runtime mechanics: Discord connection lifecycle, event parsing, API send/edit plumbing, generic gateway dispatch, generic streaming, and generic agent/tool execution. Local code should own Danny-specific UX and behavior: Discord trace rendering, low-latency Discord defaults, no accidental mentions, thread/free-response decisions, attachment/text injection behavior, and fork-specific no-spam behavior.

The current codebase already has an important hook point: the gateway runner creates adapters through a dedicated adapter creation method. The implementation should use that existing hook point first instead of introducing a gateway runner subclass as the initial abstraction. New hook points should be added only when needed and should be tiny, stable, and behavior-free.

This is not a plugin architecture project and not a rewrite of the Discord adapter. It is a local-code extraction project: subclass where the code already has a method boundary, introduce small hook points where it does not, and use pure decision helpers and formatters for behavior that can be tested independently.

### User Stories

1. As Danny, I want upstream rebases to produce fewer conflicts, so that keeping the fork current is not a recurring time sink.

2. As Danny, I want local Discord behavior isolated from upstream-shaped internals, so that upstream changes do not silently break my Discord UX.

3. As Danny, I want Discord thinking traces to be durable and chronological, so that I can understand what the agent did during a live thread.

4. As Danny, I want every relevant tool action to be visible in Discord when audit mode is enabled, so that debugging does not depend on hidden logs.

5. As Danny, I want assistant commentary before tool calls to appear as Discord trace messages, so that I can see why the agent is taking actions.

6. As Danny, I want tool start events to include useful argument previews, so that I can spot wrong actions before they become confusing.

7. As Danny, I want tool completion and error events to be representable in the trace model, so that the trace can become forensic rather than merely decorative.

8. As Danny, I want gateway lifecycle events to be traceable, so that shutdown, drain, restart, and interrupt behavior can be inspected after incidents.

9. As Danny, I want Discord trace formatting to be owned by local code, so that upstream stream-consumer changes do not change how Discord traces look.

10. As Danny, I want thinking/commentary text rendered as clear block quotes, so that traces are readable in Discord threads.

11. As Danny, I want tool progress grouping to be explicit state rather than magic queue sentinels, so that trace behavior is understandable and testable.

12. As Danny, I want free-response channels and auto-threading to be independent decisions, so that a channel can accept free responses while still creating threads.

13. As Danny, I want Discord message edits to use the more reliable partial-message path where appropriate, so that Discord API 503s are less likely to break response delivery.

14. As Danny, I want Discord text batching defaults to prioritize low latency, so that Hermes feels responsive in chat.

15. As Danny, I want Discord streaming edit intervals to be tuned for Discord without changing global defaults for every platform, so that platform-specific UX does not leak into generic behavior.

16. As Danny, I want no accidental user, role, or everyone mentions from Hermes, so that LLM output cannot unexpectedly ping people.

17. As Danny, I want Discord attachment handling to support code, config, data, and document uploads, so that files I attach are available to the agent as useful text/context.

18. As Danny, I want uploaded text files to be injected or summarized predictably, so that the agent does not claim it read a file it silently skipped.

19. As Danny, I want MEDIA attachment parsing to be robust, so that generated files are delivered natively without false-positive MEDIA tags polluting responses.

20. As Danny, I want background process completion notifications to avoid chat spam when the agent is already expected to consume them, so that Discord threads stay focused.

21. As Danny, I want long-running terminal command behavior to remain local code, so that server/background safety rules survive upstream changes.

22. As Danny, I want local behavior expressed through small classes and helpers, so that future custom changes have obvious homes.

23. As a future implementer, I want a local Discord adapter subclass rather than a copied adapter file, so that upstream Discord improvements still flow through by inheritance.

24. As a future implementer, I want to use the existing adapter creation hook point, so that Discord can resolve to a local adapter without subclassing the whole gateway runner.

25. As a future implementer, I want trace formatting extracted into a pure formatter, so that formatting can be tested without a live Discord client.

26. As a future implementer, I want trace grouping extracted into explicit state, so that grouping behavior can be tested independently of queue processing.

27. As a future implementer, I want Discord mention/thread decisions extracted into decision helpers, so that the message handler does not become the permanent home for every local rule.

28. As a future implementer, I want attachment behavior extracted only after the adapter and trace extraction are stable, so that the first slice stays small.

29. As a future implementer, I want MEDIA parsing behavior extracted only after the core local Discord layer is stable, so that the first slice does not become a grab bag.

30. As a future implementer, I want terminal auto-background decisions kept outside the Discord adapter, so that terminal safety remains isolated from gateway transport.

31. As a future implementer, I want tiny hook points with stable names, so that rebases are mostly about preserving hooks rather than re-resolving behavior.

32. As a future implementer, I want tests that fail when upstream changes break local invariants, so that regressions are caught before live deployment.

33. As a future implementer, I want local code to avoid plugin architecture complexity, so that the design stays understandable and direct.

34. As a future implementer, I want upstream accepted changes, such as Copilot vision routing, removed from the local inventory, so that the local layer stays smaller over time.

35. As a maintainer, I want custom patches grouped by ownership area, so that the branch history communicates why each patch exists.

36. As a maintainer, I want upstream-shaped code to contain hook points rather than local behavior, so that cherry-picking onto a new upstream base is mechanical.

37. As a maintainer, I want the local layer to be small enough to audit quickly, so that Danny can keep moving fast without losing control of behavior.

38. As a Discord user, I want Hermes responses and traces to remain readable on mobile, so that debugging and interaction work well from a phone.

39. As a Discord user, I want trace verbosity to be configurable, so that ordinary conversations are not overwhelmed while debug threads can be fully auditable.

40. As a Discord user, I want final answers not to be suppressed because trace/interim messages were emitted, so that preview/deduplication logic does not eat real replies.

41. As a Discord user, I want trace messages not to be silently suppressed by streaming delivery rules, so that auditability is independent from final response rendering.

42. As Danny, I want the fork to keep benefiting from upstream bug fixes, so that owning local UX does not mean freezing protocol code.

43. As Danny, I want implementation to be incremental, so that the bot is not destabilized by a giant extraction.

44. As Danny, I want no gateway restarts performed by the agent during this work, so that development does not interrupt live conversations.

45. As Danny, I want the end state to make upstream tracking boring, so that rebases become predictable maintenance instead of live-fire debugging.

### Implementation Decisions

- Use **Local Layer** and **local code** as the canonical terms for Danny/Habibi-specific behavior that is allowed to diverge from upstream.

- Treat large gateway and platform modules as **upstream-shaped code**: code we want to keep close to Nous upstream even if the current branch has local edits inside it.

- Build a local gateway/Discord layer rather than a new full Discord adapter.

- Do not copy the upstream Discord adapter wholesale. The local Discord adapter should subclass the upstream adapter and override only local behavior.

- Keep upstream-shaped code responsible for Discord connection lifecycle, event ingestion, REST plumbing, slash command machinery, rate limits, generic gateway dispatch, generic streaming, and generic tool execution.

- Move local Discord UX and behavior into local classes and helpers.

- Use the existing adapter creation method as the first hook point for selecting a local Discord adapter.

- Do not introduce a gateway runner subclass as the first implementation step. The gateway runner is very large, and subclassing it early risks copying large methods and recreating the rebase problem.

- Add new hook points to upstream-shaped modules only when no useful method boundary exists.

- Prefer method extraction hook points over inline local conditionals.

- Introduce a local Discord adapter subclass responsible for Discord-specific transport overrides and integration with local decision helpers.

- Introduce a Discord trace formatter responsible for converting structured trace events into Discord-friendly text.

- Introduce explicit trace grouping state responsible for when commentary should split subsequent tool progress into a new group.

- Represent trace activity as structured events rather than formatting strings directly inside gateway orchestration.

- Trace events should be able to represent assistant commentary, tool started, tool completed, tool error, gateway lifecycle events, approval requests, interrupts, and suppression decisions.

- Preserve existing compact behavior as one trace mode, but design the model so an audit mode can show more complete lifecycle information.

- Move Discord low-latency defaults into the local Discord adapter rather than changing generic stream consumer defaults globally.

- Move the partial-message edit behavior into the local Discord adapter.

- Move free-response versus auto-thread behavior into local Discord decision helpers or narrow adapter overrides.

- Move no-mention behavior into the local Discord adapter or a local Discord send-options helper.

- Move attachment text/document behavior into local code after the initial adapter/trace extraction is stable.

- Move MEDIA tag parsing behavior into local code after the initial gateway/Discord extraction is stable.

- Keep Copilot vision routing out of this local-layer work because the relevant change has been accepted upstream.

- Keep terminal auto-background detection out of the Discord adapter; it belongs near the terminal tool or in local terminal decision code.

- Keep web backend routing, compaction behavior, config sync, skills sync, and plugin system changes outside the Discord local adapter.

- The first implementation pass should create local modules and wire Discord adapter selection with no behavior change, then move one behavior at a time.

- The first behavior to move should be an isolated one, such as partial-message editing, to prove local adapter selection works.

- Trace formatting should be extracted before replacing trace grouping internals.

- Trace grouping state should replace magic queue sentinels only after output parity is established.

- Attachment and media behavior should be deferred until the core local Discord layer is working and tested.

- Configuration should not turn this into a general plugin architecture.

- Local modules should avoid hard dependencies on live Discord clients where pure formatting or decision tests are enough.

- The end state should make the custom patch inventory read as local modules plus a small list of hook points in upstream-shaped code.

### Codebase Comparison Notes

- The repository currently has no domain context map, no root context document, and no ADR directory for this area. The domain language should therefore be introduced explicitly as decisions crystallize.

- The gateway runner already has a dedicated adapter creation method. This is the first hook point to use for resolving Discord to a local adapter.

- The gateway runner is a very large controller containing adapter lifecycle, message handling, agent execution, stream setup, and progress callback construction. Overriding it wholesale would be fragile.

- The current Discord adapter already contains local behavior inline, including partial-message edits, low-latency text batching defaults, free-response channel logic, and auto-thread decisions.

- The current tool progress and interim assistant behavior lives inline in the gateway agent execution path. This is the main extraction target for trace behavior.

- Existing tests already encode important domain language around Discord: `free_response_channels` controls the mention gate; `auto_thread` controls thread creation; `no_thread_channels` opt channels out of thread creation.

- Existing stream consumer tests are useful prior art for message cleaning, progressive edits, final response behavior, and media directive stripping.

### Testing Decisions

- Tests should validate external behavior and local invariants, not implementation details such as exact private helper names.

- The local Discord adapter should have tests proving that message edits use the desired edit behavior through observable mocked Discord calls.

- The local Discord adapter should have tests proving low-latency defaults are applied only for the local Discord path and not globally.

- The free-response/threading decision helpers should have tests covering free-response channels, no-thread channels, DMs, existing threads, replies, voice-linked channels, and normal channel messages.

- Allowed-mentions behavior should have tests proving user, role, everyone, and replied-user mention behavior cannot accidentally ping by default.

- The trace formatter should have pure unit tests for assistant commentary formatting, block quotes, tool-start rendering, preview truncation, tool completion rendering, tool error rendering, and lifecycle event rendering.

- Trace grouping state should have pure unit tests for grouping behavior: thinking marks the next tool group as fresh, tool consumption clears the flag, and repeated tools do not create unnecessary groups.

- Gateway callback wiring should have tests proving that local trace-capable paths receive structured trace events and generic paths keep upstream-shaped behavior.

- Streaming/final-response tests should ensure trace/interim messages do not suppress the final assistant response.

- Regression tests should model assistant commentary followed by tool calls and assert chronological Discord-visible output.

- Regression tests should model multiple tool calls in one turn and assert every action can be visible in audit mode.

- Regression tests should model interrupts/stale runs and assert intentional suppression is explicit rather than silent when audit mode is enabled.

- Background process notification tests should verify that notify-on-complete does not create unwanted user-facing Discord spam when the agent is expected to consume the completion.

- Attachment behavior tests should use representative code, config, data, document, binary, and unknown extensions.

- MEDIA parsing tests should cover quoted paths, backticked paths, absolute paths, home-relative paths, arbitrary extensions, and false-positive placeholders.

- Terminal behavior tests should remain separate from Discord tests and verify command classification behavior without launching long-lived foreground servers.

- Prior art exists in gateway, stream consumer, platform adapter, media extraction, and terminal tool tests; new local-layer tests should follow those patterns but focus on externally visible behavior.

- Post-rebase verification should include the local invariant test subset before broader gateway tests.

### Out of Scope

- Rewriting the full Discord adapter from scratch.

- Building a general plugin architecture for Discord behavior.

- Restarting or deploying the live gateway as part of PRD creation.

- Reintroducing forked Copilot vision routing that has already been accepted upstream.

- Solving every custom patch in the fork at once.

- Refactoring unrelated web backend routing, compaction behavior, skills sync, config sync, or plugin management as part of the initial Discord local-layer extraction.

- Changing public upstream behavior for non-Discord platforms unless required for a tiny hook point.

- Adding new product features beyond preserving and isolating existing local behavior.

- Creating GitHub issues or commits automatically.

### Further Notes

The purpose of this work is to make upstream tracking smoother while preserving Danny’s ability to customize aggressively. The fork is expected to remain opinionated. The improvement is that opinions should live in local files with small, stable interfaces rather than being woven into upstream-shaped modules.

The safest implementation path is incremental: create empty local modules, wire the existing adapter creation hook point, move one isolated behavior, test it, then continue. Any point where an override requires copying a large upstream-shaped method should be treated as a design smell and should trigger extraction of a smaller hook point instead.

The long-term success metric is that a future upstream rebase requires checking a small number of hook points and running local invariant tests, not rediscovering scattered behavior across large gateway, platform, stream, and agent files.

---

## 2026-04-29 Unified Implementation Option: Local Discord Trace Adapter + Tiny Gateway Trace Hooks

### Updated Goal

Implement the real Discord thinking/tool trace fix inside the PRD’s **Local Layer** architecture:

- Do **not** prepend final reasoning to the final assistant answer.
- Show reasoning only from live reasoning deltas while the model is actually reasoning.
- Render Discord thinking traces and tool calls through Discord Components V2 where possible.
- Keep final assistant answers as normal Discord messages.
- Keep local Discord UX in local code, not scattered through upstream-shaped `gateway/run.py`, `gateway/stream_consumer.py`, or `gateway/platforms/discord.py`.

### Reconciled Architecture

The approved implementation should **not** start with a `LocalGatewayRunner` subclass. That contradicts the earlier decision in this PRD to use the existing adapter creation hook first. The unified architecture is:

```text
gateway/run.py                         upstream-shaped code
  └─ tiny hook points only
      ├─ _create_adapter()             existing seam
      ├─ _create_turn_trace_sink()      new tiny seam
      └─ callback wiring calls sink     new tiny seam

gateway/local/discord_adapter.py       local code
  └─ LocalDiscordAdapter(DiscordAdapter)

gateway/local/discord_components.py    local code
  └─ Components V2 payload builder

gateway/local/discord_trace.py         local code
  └─ DiscordTraceSink / DiscordTraceState / TraceEvent
```

The local layer owns Discord trace UX. Upstream-shaped code continues to own generic gateway lifecycle, adapter lifecycle, agent execution, generic streaming, and non-Discord behavior.

### Discord Components V2 Requirements

Discord Components V2 requires the message flag:

```text
IS_COMPONENTS_V2 = 1 << 15 = 32768
```

Important constraints from Discord docs:

- Once the `IS_COMPONENTS_V2` flag is set on a message, it cannot be removed from that message.
- With Components V2, message `content` and `embeds` no longer work; use `Text Display` and `Container` instead.
- Attachments do not show by default unless exposed through components.
- Messages allow up to 40 total components.
- Useful component types for the first implementation:
  - `10` Text Display
  - `14` Separator
  - `17` Container

The first implementation should be passive Components V2 only: Container, Text Display, Separator. Interactive buttons such as “Hide trace” or “Expand trace” are deferred because they require interaction routing and state.

### Target User-Visible Behavior

For Discord turns:

1. If live reasoning deltas arrive, create/update one trace component message with a `💭 Thinking` section.
2. If tools are called, update the same trace component message with a `🛠 Tools` section.
3. Send the final assistant answer as a separate normal Discord message.
4. Never prepend final reasoning to the final answer.
5. If the provider only supplies final `last_reasoning` and no live deltas, do not display it. Store/preserve it internally if needed, but do not render it as a post-hoc trace.
6. Leave the trace component visible after the answer, but compact/cap its content for mobile readability.

### First-Pass Component Shape

A trace message should be built roughly as:

```json
{
  "flags": 32768,
  "components": [
    {
      "type": 17,
      "accent_color": 5793266,
      "components": [
        {
          "type": 10,
          "content": "### 💭 Thinking\n<live reasoning summary>"
        },
        {
          "type": 14,
          "divider": true,
          "spacing": 1
        },
        {
          "type": 10,
          "content": "### 🛠 Tools\n🔎 `search_files`: `pattern...`\n📖 `read_file`: `/path/...`"
        }
      ]
    }
  ]
}
```

Rendering rules:

- Never include `reasoning.encrypted_content`.
- Cap reasoning and tool previews for mobile.
- Preserve chronological order.
- Deduplicate provider replay of reasoning summaries.
- Respect existing display config: `show_reasoning`, `tool_progress`, `interim_assistant_messages`, and `tool_preview_length`.

### Local Code Responsibilities

#### `gateway/local/discord_adapter.py`

Create `LocalDiscordAdapter(DiscordAdapter)`.

Responsibilities:

- Provide `create_trace_sink(...)` for Discord turns.
- Send/edit trace messages as Components V2 payloads.
- Fall back to plain text trace rendering if raw Components V2 send/edit fails.
- Inherit upstream Discord connection/event/slash-command behavior.
- Later home for no-mention policy, partial-message edit policy, Discord low-latency defaults, and Discord-specific batching decisions.

#### `gateway/local/discord_components.py`

Pure formatter/payload builder.

Responsibilities:

- Convert `DiscordTraceState` into Components V2 payloads.
- Convert `DiscordTraceState` into plain-text fallback trace.
- Enforce component count and content caps.
- Unit-test without a live Discord client.

#### `gateway/local/discord_trace.py`

Structured trace state and sink.

Responsibilities:

- Represent trace events: reasoning deltas, assistant commentary, tool started/completed/failed, gateway lifecycle, approvals, interrupts, and suppression decisions.
- Coalesce/throttle live reasoning deltas.
- Deduplicate replayed reasoning summaries.
- Track explicit grouping state instead of magic queue sentinels.
- Flush updates through `LocalDiscordAdapter.send_trace` / `edit_trace`.
- Never render final-only reasoning.

### Upstream-Shaped Hook Points

#### Existing hook: `_create_adapter()`

Use the existing adapter creation method as the first seam. For Discord, resolve to `LocalDiscordAdapter` if available; otherwise fall back to upstream `DiscordAdapter`.

This keeps the existing PRD decision intact: no runner subclass as the first abstraction.

#### New hook: `_create_turn_trace_sink(...)`

Add a small method in `GatewayRunner` that asks the adapter whether it can create a trace sink:

```python
def _create_turn_trace_sink(self, *, adapter, source, metadata, display_config, progress_mode):
    if hasattr(adapter, "create_trace_sink"):
        return adapter.create_trace_sink(...)
    return None
```

The generic path remains unchanged when no sink exists.

#### Callback wiring

When a trace sink exists:

- `reasoning_callback` routes live reasoning deltas into the sink.
- `tool_progress_callback` routes tool lifecycle events into the sink.
- interim assistant commentary can route into the sink when enabled.
- generic text progress queues remain for non-Discord adapters.

Do not copy `_run_agent()` into a subclass. If the existing method lacks a boundary, extract the smallest stable hook needed.

### Testing Plan

Add local-layer tests:

```text
tests/gateway/local/test_discord_components.py
tests/gateway/local/test_discord_trace.py
tests/gateway/local/test_discord_adapter.py
tests/gateway/local/test_trace_wiring.py
```

Required assertions:

- Components V2 payload has `flags == 32768`.
- Payload uses Container/Text Display/Separator.
- Payload has no top-level `content` or `embeds`.
- Payload stays under 40 components.
- Encrypted reasoning is not rendered.
- Long reasoning/tool previews are capped.
- Provider replay is deduped.
- `show_reasoning=false` emits no reasoning trace.
- `tool_progress=off` emits no tool trace.
- Final `last_reasoning` alone emits no user-visible trace.
- Final answer is never prefixed with reasoning.
- Trace/interim messages do not suppress the final answer.
- Non-Discord adapters retain generic behavior.

### Incremental Commit Plan

1. `refactor(discord): add local adapter layer`
   - Create `gateway/local/` package.
   - Add `LocalDiscordAdapter` subclass.
   - Wire existing `_create_adapter()` seam to prefer the local adapter for Discord.
   - No user-visible behavior change.

2. `feat(discord): add trace components renderer`
   - Add Components V2 payload builder and plain-text fallback renderer.
   - Add pure unit tests.

3. `feat(discord): add structured trace sink`
   - Add trace event/state/sink model.
   - Add coalescing/dedupe/capping behavior.
   - Add pure unit tests.

4. `refactor(gateway): add trace sink hook point`
   - Add tiny hook in `GatewayRunner` to create a trace sink from trace-capable adapters.
   - Route reasoning/tool callbacks to trace sink for Discord only.
   - Preserve generic behavior for other platforms.

5. `feat(discord): render live traces as components`
   - Send/edit live Discord trace panel during turns.
   - Move reasoning/tool display into components.
   - Keep final assistant answer clean.

6. `refactor(discord): remove generic reasoning prepend path`
   - Delete final-response reasoning prepend.
   - Move Discord-specific trace formatting/dedupe out of generic stream consumer if no longer needed.
   - Keep upstream-shaped code lean.

### Deferred Work

Defer until the trace layer is stable:

- Discord attachment text/document extraction.
- MEDIA parsing extraction.
- Terminal auto-background behavior.
- Free-response versus auto-thread decision extraction.
- No-mention policy extraction.
- Background process notification cleanup.
- Full lifecycle trace events.
- Interactive trace buttons.

### Approved Defaults

- Final-only reasoning: do not display.
- Trace component after answer: leave visible but capped/compact.
- One trace message per turn: yes.
- Buttons: defer.
- Runner subclass: no, not initially.
- Existing adapter creation hook first: yes.
