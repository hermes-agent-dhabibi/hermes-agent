# Fork shrink audit — 2026-04-26

## Scope

Audit target: current branch against its upstream merge-base.

Commands used:

```bash
cd ~/.hermes/hermes-agent
MB=$(git merge-base HEAD upstream/main)
git diff --stat "$MB" HEAD
git diff --name-status "$MB" HEAD
```

Observed merge-base: `0e2a53eab2ac7a937b2ce2a089b07c18f8e30bcf`.

Raw delta after adding the first `tests/fork/` slice:

```text
123 files changed, 14651 insertions(+), 7352 deletions(-)
```

The headline is misleading: most of the size is optional WorldSim content, one annotated gateway scratch file, and test-suite curation/deletion churn. The load-bearing fork behavior is much smaller and concentrated in Discord, terminal safety, provider routing, gateway process notifications, config sync, SearXNG/Firecrawl routing, and plugin/skill plumbing.

## Big-picture recommendations

1. **Make `tests/fork/` the rebase alarm bell.** Keep it small and opinionated. It should pin local semantics, not duplicate upstream's full test suite.
2. **Stop carrying broad test deletions as fork behavior.** The largest risky bucket is deleted upstream tests. Treat that as branch hygiene debt; restore/drop deliberately on the next fresh patch branch rather than reviewing all upstream commits by hand.
3. **Move bulky optional content out of the in-tree patch layer where possible.** WorldSim is ~8k lines. If it can live as an external skill bundle/plugin artifact, it should not be cherry-picked into every code rebase.
4. **Prefer hooks/config gates over adapter edits.** Discord and gateway changes are the highest rebase-conflict areas; every new local opinion should either become a tiny upstream hook or a local invariant-backed config default.
5. **Firewall default-on upstream features.** Adopt upstream code, but locally default-disable features that spend, spawn, mutate, create cron/ticker behavior, change Discord UX, or add sidecar state.

## Fork invariant status

Added first `tests/fork/` skeleton:

- `tests/fork/test_discord_invariants.py`
  - pins that `free_response_channels` does **not** suppress `auto_thread`;
  - pins that Discord quote-reply messages do not auto-thread.
- `tests/fork/test_terminal_invariants.py`
  - pins auto-background detection for known hang-prone commands such as `python -m http.server`, `npx serve`, `npm run dev`, `uvicorn`, and `journalctl -f`;
  - pins finite commands that should remain foreground.
- `tests/fork/test_gateway_invariants.py`
  - re-exports existing notify-on-complete invariants so fork checks have a stable entrypoint.

Discord auto-thread behavior was already restored before this slice:

```python
gateway/platforms/discord.py:3256
skip_thread = bool(channel_ids & no_thread_channels)
```

The old upstream coupling from `93fe4b35` (`... or is_free_channel`) is not present.

## Changed-file classification

| Path / bucket | Delta | Category | Why it exists / suspected origin | Recommendation | Action |
|---|---:|---|---|---|---|
| `.githooks/commit-msg` | +141 / -0 | Intentional fork behavior | Local structured commit hook, including co-author policy. | Keep in fork; low conflict. | Keep; document in `CUSTOM_PATCHES.md`. |
| `CUSTOM_PATCHES.md` | +152 / -0 | Intentional fork behavior | Manual patch ledger for cherry-pick workflow. | Keep but update after every new fork commit. | Keep; update before promotion/merge. |
| `agent/auxiliary_client.py` | +27 / -11 | Intentional fork behavior / needs upstream hook | Copilot vision routing and `Copilot-Vision-Request` header plumbing are recurring local needs. | Keep short-term; propose upstream provider hook or provider-specific request-header extension. | Keep + test. |
| `run_agent.py` | +19 / -1 | Intentional fork behavior / needs upstream hook | Provider/model routing around Copilot and fallback semantics. | Keep only if covered by provider tests; otherwise push toward provider adapter config. | Keep + test. |
| `agent/context_compressor.py` | +4 / -0 | Intentional fork behavior | Identity-preserving compaction/handoff wording. | Keep if Danny still values exact wording; cheap invariant test would be enough. | Keep; add future fork test. |
| `gateway/platforms/discord.py` | +20 / -6 | Intentional fork behavior / needs upstream hook | Primary platform UX: allowed mentions/edit behavior/free-response/thread semantics. | Keep minimal. Prefer upstream hook/config for future Discord UX deviations. | Keep + fork invariant. |
| `gateway/run.py` | +60 / -7 | Intentional fork behavior / feature firewall | Background-process notification routing and `/config-sync` gateway command. | Keep notify-on-complete behavior. Consider extracting config-sync command registration to plugin/hook if upstream gateway command hooks mature. | Keep + fork invariant. |
| `gateway/platforms/base.py` | +88 / -1 | Needs upstream hook / extractable | Base adapter metadata/media behavior needed by Discord/gateway custom handling. | Identify exact call surface and upstream as small generic capability. | Keep short-term; shrink later. |
| `gateway/stream_consumer.py` | +1 / -1 | Intentional fork behavior | Message grouping / thinking text ordering. | Keep only with focused test because small changes can cause Discord UX regressions. | Keep + future fork test. |
| `gateway/builtin_cron.py` | +93 / -0 | Upstream feature adoption / feature firewall | Built-in cron behavior may create autonomous/ticker actions. | Default-disable unless explicitly configured. Audit for background spending/mutation before enabling. | Firewall. |
| `gateway/run_annotated_part3.py` | +2028 / -0 | Rebase/cherry-pick noise | Looks like an annotated scratch/copy file, not a runtime module. | Remove from patch layer unless a human confirms it is used. | Revert/drop candidate. |
| `hermes_cli/config_sync.py` | +494 / -0 | Intentional fork behavior / extractable | Local config sync command. | Keep, but isolate as CLI plugin or standalone command module to avoid `main.py` churn. | Keep; extraction candidate. |
| `hermes_cli/main.py` | +541 / -1 | Extractable to plugin/hook | Large CLI command insertion for config sync/update flows. | Shrink by moving command implementation/registration out of monolithic main if upstream command registry supports it. | Extract later. |
| `hermes_cli/commands.py` | +6 / -1 | Intentional fork behavior | Adds local slash/CLI command registry entry. | Keep tiny registry diff; good hook point. | Keep. |
| `hermes_cli/config.py` | +30 / -1 | Intentional fork behavior | Config defaults/loader support for local features. | Keep if covered by config-sync tests. | Keep + test. |
| `hermes_cli/plugins_cmd.py` | +81 / -0 | Intentional fork behavior / extractable | Local plugin command enhancements. | Keep if still needed; otherwise upstream plugin CLI may absorb. | Review next sync. |
| `cli.py` | +18 / -2 | Intentional fork behavior | Local CLI behavior around recent sessions/provider/runtime UX. | Keep only if no better command-registry hook exists. | Review; maybe extract. |
| `tools/terminal_tool.py` | +296 / -0 | Intentional fork behavior | Critical safety invariant: foreground long-lived processes must auto-background. | Keep. This is high-value fork behavior and should stay heavily tested. | Keep + fork invariant. |
| `tools/web_tools.py` | +93 / -5 | Intentional fork behavior / extractable | Local three-tier web stack: SearXNG search + Firecrawl extract + Camofox browser. | Keep. Prefer backend config abstraction upstream rather than hard fork. | Keep + future fork test. |
| `tools/skills_sync.py` | +10 / -3 | Intentional fork behavior | Symlinked skill category discovery. | Keep until upstream supports symlink traversal safely. | Keep + future fork test if simple surface remains. |
| `plugins/execution_state_runtime/*` | +889 / -0 | Extractable to plugin/hook | ESR is already plugin-shaped and mostly isolated. | Keep as plugin, but consider managing as external plugin repo/submodule rather than core cherry-pick. | Extractable/keep. |
| `optional-skills/worldsim/*` | +7969 / -0 | Extractable to skill bundle | Large optional skill + scripts + docs, not core runtime behavior. | Move to external optional skill bundle if feasible. Avoid carrying through every code rebase. | Extract/drop from core patch layer. |
| `skills/mcp/native-mcp/SKILL.md` | +7 / -3 | Intentional fork behavior | Local skill doc preference: use `/reload-mcp` over restart. | Prefer user skill override outside repo; no runtime need. | Move to local skill memory if possible. |
| `pyproject.toml` | +5 / -0 | Intentional fork behavior | Extra dev/runtime deps for local features/tests. | Keep only deps required by retained code. | Review after dropping noise. |
| `tests/fork/*` | +3 files | Intentional fork behavior | New invariant suite for rebase-sensitive local behavior. | Keep small; add one test per painful local invariant. | Keep. |
| Existing focused tests: `tests/gateway/test_discord_free_response.py`, `tests/tools/test_auto_background_detection.py`, `tests/gateway/test_background_process_notifications.py`, `tests/hermes_cli/test_config_sync.py` | mixed additions | Intentional fork behavior | Tests for local behavior. | Keep if tied to retained code. Cross-link important ones from `tests/fork/`. | Keep. |
| Broad deleted tests under `tests/` | ~39 deleted files / ~7k removed lines | Rebase/cherry-pick noise | Prior test-suite curation carried across upstream. This dominates risk and makes diff hard to reason about. | Do not treat deletion as product behavior. On next fresh branch, avoid cherry-picking deletions unless a test is provably obsolete/flaky and documented. | Restore/drop deliberately next sync. |
| Modified test import/expectation churn outside retained features | many small edits | Rebase/cherry-pick noise / unclear | Likely stale import fixes from older branch plus adaptation to local patches. | Re-evaluate after restoring upstream tests; keep only focused invariants. | Review. |

## Suggested shrink roadmap

### Safe now / first slice

- Keep restored Discord behavior.
- Add `tests/fork/` as the invariant entrypoint.
- Document the feature firewall policy.
- Do not refactor Discord/terminal/gateway in this slice.

### Next patch branch

- Start from a fresh upstream base.
- Cherry-pick intentional behavior commits only.
- Do **not** cherry-pick broad test deletions by default.
- Re-run `tests/fork` first, then targeted suites for touched areas.

### Extraction candidates

1. `optional-skills/worldsim/*` → external optional skill bundle.
2. `plugins/execution_state_runtime/*` → external plugin package/submodule if plugin loader supports local plugin paths cleanly.
3. `hermes_cli/config_sync.py` + `hermes_cli/main.py` additions → command plugin or command-registry-only hook.
4. `tools/web_tools.py` backend selection → upstreamable search/extract backend abstraction.
5. `gateway/platforms/base.py` and `gateway/platforms/discord.py` UX customizations → upstream hooks/config flags instead of direct edits.

### Invariants still worth adding later

- Copilot vision requests include `Copilot-Vision-Request: true` and preserve the intended model/base URL.
- Terminal auto-background upgrades foreground calls to background execution in the actual tool path, not only detector unit tests.
- SearXNG search and Firecrawl extract config split remains intact.
- Symlinked skill category directories are discovered.
- Discord outbound messages never introduce user/role/everyone mentions unexpectedly.
- Curator or any similar background reviewer is disabled by default locally.

## Test results

Verification run on 2026-04-26 from `/home/hermes/.hermes/hermes-agent`:

```bash
source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || true
python3 -m pytest tests/fork -q
python3 -m pytest \
  tests/gateway/test_discord_free_response.py::test_discord_free_channel_independent_of_auto_thread \
  tests/gateway/test_discord_free_response.py::test_discord_reply_message_skips_auto_thread -q
python3 -m pytest tests/tools/test_auto_background_detection.py -q
python3 -m pytest \
  tests/gateway/test_background_process_notifications.py::test_agent_notify_suppresses_user_facing_text_notification \
  tests/gateway/test_background_process_notifications.py::test_agent_notify_skips_completely_when_already_consumed -q
```

Results after realigning the dev branch to the current live patch base (`49e8c242`) and applying review-swarm fixes:

```text
13 passed in 4.21s
21 passed in 1.95s
311 passed in 2.30s
2 passed in 3.43s
```

During verification, the Discord fake message helper was updated to include `message.guild` and guild IDs because current `DiscordAdapter._handle_message()` now reads `message.guild.id`. This was test-fixture drift, not a production behavior change.
