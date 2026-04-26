# Fork feature firewall

Upstream features are welcome in the Habibi/Hermes fork, but locally they must be opt-in or safely gated when they can change the live assistant's behavior without an explicit user action.

## Firewall trigger list

An upstream change must be default-disabled locally, config-gated, or covered by a fork invariant test if it can:

- spend model/API money in the background
- spawn auxiliary agents or long-running workers
- mutate files outside an explicit user action
- alter Discord/gateway UX
- create cron/ticker behavior
- change default tool availability
- move/archive/delete user-created artifacts
- add persistent sidecar state in `~/.hermes`
- change provider routing, headers, fallback behavior, or model-selection semantics
- change terminal execution safety for long-lived processes

## Preferred posture

For gated upstream features, prefer this order:

1. Keep upstream code available.
2. Default-disable locally if upstream enables by default.
3. Add a config flag or hook instead of deleting upstream code.
4. Add a small `tests/fork/` invariant for the local expectation.
5. Document the local decision in the fork audit or `CUSTOM_PATCHES.md`.

## What should not be firewalled

Do not block upstream changes just because they are large, unfamiliar, or internally refactored. The firewall is for user-visible side effects and operational risk, not general conservatism.

Safe-by-default changes can usually ride along with upstream:

- pure bug fixes
- docs-only changes
- tests-only changes
- new inactive modules
- features that require explicit user invocation and do not alter defaults

## Current example: Curator

Curator is tracked upstream at <https://github.com/NousResearch/hermes-agent/issues/16077>.

It may be useful and should not be hard-rejected. But it is dangerous as default-on because it can periodically spend auxiliary model calls, mutate skill directories by archiving content, and add sidecar telemetry/state.

Local expected posture:

- adopt when merged upstream,
- keep the code available,
- default-disable locally unless Danny explicitly enables it,
- add a fork invariant that proves it does not run background review/archive work by default.

## Current example: Discord auto-threading

`discord.free_response_channels` means "the bot may respond without @mention."

`discord.auto_thread` means "top-level channel messages spawn threads."

Those settings are orthogonal in this fork. A channel can be both free-response and auto-threaded. Inline free-response requires `DISCORD_NO_THREAD_CHANNELS` or `DISCORD_AUTO_THREAD=false` explicitly.

This is pinned by `tests/fork/test_discord_invariants.py`.
