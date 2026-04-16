# Custom Patches

Our fork's patch layer. When syncing to a new upstream base, cherry-pick commits
from this list in order (bottom-to-top = oldest-to-newest).

Last updated: 2026-04-16
Base: `custom` branch, tip `f130b675`
Upstream divergence point: 273 commits behind `upstream/main`

---

## Status Legend

- ✅ **KEEP** — custom functionality not in upstream
- ⚠️ **REVIEW** — may overlap with upstream; check before cherry-picking
- ❌ **DROP** — upstream provides this natively or commit is stale
- 🔀 **SKIP** — already cherry-picked upstream (git will auto-skip)

---

## Patches (oldest first)

### Infrastructure / Repo Tooling

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 44 | `c9b44899` | ✅ KEEP | docs: genericize browser tool description away from Browserbase-only language | `tools/browser_tool.py` |
| 43 | `7c4b7db1` | ✅ KEEP | docs(skill): native-mcp — prefer /reload-mcp over full restart | skill docs |
| 42 | `f9b3f361` | ❌ DROP | chore: regenerate package-lock.json for current dependency tree | `package-lock.json` — always regenerate fresh |
| 41 | `0e16c1ba` | ✅ KEEP | chore: add commit-msg hook enforcing structured commit messages | `.githooks/` |
| 40 | `1bfb34dd` | ⚠️ REVIEW | feat(cli): add 'hermes update-custom' command for fork rebase workflow | `hermes_cli/` — may need rework for new workflow |

### Copilot / Vision / Auxiliary

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 39 | `42b5058f` | ✅ KEEP | feat(auxiliary): Copilot vision routing + vision backend fallback on quota errors | `agent/auxiliary_client.py` |
| 17 | `f9874d1f` | ✅ KEEP | fix(vision): add Copilot-Vision-Request header for copilot vision backend | `agent/auxiliary_client.py` |
| 10 | `4d78ee8e` | ✅ KEEP | fix(copilot): preserve base URL and gpt-5-mini routing | `run_agent.py` |
| 20 | `abc4b1d4` | ✅ KEEP | fix(copilot): silence spurious token validation warning | `agent/` |
| 5 | `bbdc2f88` | ✅ KEEP | fix(vision): default copilot vision to gpt-5-mini, remove dead header injection | `agent/auxiliary_client.py`, tests |

### Compaction / Context

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 38 | `5a074f54` | ⚠️ REVIEW | feat(compaction): Codex-style user message preservation + handoff framing | `agent/context_compressor.py` — upstream overhauled compressor |
| 37 | `7587579d` | ⚠️ REVIEW | fix(compaction): use identity-preserving prefix instead of 'another language model' | `agent/context_compressor.py` — check if upstream changed wording |
| 36 | `eeb81e8e` | ✅ KEEP | debug(compaction): add [DEBUG] logs for compaction output | `agent/context_compressor.py` |

### Auxiliary / Runtime Plumbing

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 32 | `d755400c` | ⚠️ REVIEW | fix(auxiliary_client): add missing api_mode param to resolve_provider_client signature | `agent/auxiliary_client.py` — may be fixed upstream |
| 31 | `38140cd6` | ⚠️ REVIEW | fix(auxiliary): reconcile main_runtime plumbing with upstream and restore compaction behavior | `agent/auxiliary_client.py`, tests — heavy overlap risk |

### Config / CLI Features

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 35 | `1e68bd46` | ✅ KEEP | feat: add `hermes config sync` and `/config-sync` command | `gateway/run.py`, `hermes_cli/` |
| 25 | `3f37769c` | ✅ KEEP | fix(cli): avoid heavy import in recent session display | `hermes_cli/` |
| 15 | `040c22de` | ✅ KEEP | feat: add `hermes update-skills` — pull only built-in skills from upstream | `hermes_cli/` |
| 14 | `3bca7e1c` | ✅ KEEP | feat: nightly skill & memory review cron job | config/cron |
| 13 | `398f96c5` | ✅ KEEP | Merge branch 'feature/update-skills-cmd' into custom | merge commit — may need to flatten |

### Discord Platform

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 34 | `c2a7387e` | ✅ KEEP | fix: expand supported document types and text injection for inbound file uploads | gateway |
| 33 | `d4f73ac5` | ✅ KEEP | fix(discord): preserve more reasoning detail and fail fast on oversize edits | `gateway/platforms/discord.py` |
| 29 | `e878da90` | ✅ KEEP | fix(discord): use get_partial_message for edits to avoid 503s | `gateway/platforms/discord.py` |
| 16 | `9467f5ad` | ✅ KEEP | revert(discord): restore edit_message truncation instead of fail-fast | `gateway/platforms/discord.py` |
| 12 | `fcd2587c` | 🔀 SKIP | feat(discord): extract reply text from message references | already upstream |
| 11 | `afd2e51c` | 🔀 SKIP | fix: guard reply_to_text against DeletedReferencedMessage | already upstream |
| 8 | `ed78e870` | ✅ KEEP | fix(discord): remove latency-inducing defaults | `gateway/platforms/discord.py` |

### Web / Search

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 18 | `b84c7c70` | ✅ KEEP | feat(web): add SearXNG search backend + split search/extract routing | `tools/web_tools.py`, config |

### Media / Files

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 28 | `eea408d6` | ✅ KEEP | fix(media): reject non-path text after MEDIA: tag | media handling |
| 9 | `7865a3be` | ✅ KEEP | fix: extract_media() now accepts arbitrary file extensions | media handling |
| 30 | `3a5d738c` | ✅ KEEP | fix: load .env before flush_memories credential resolution | startup |

### Cron / Skills

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 27 | `44342c34` | ⚠️ REVIEW | fix(cron): run due jobs in parallel to prevent serial tick starvation | `cron/` — was upstream PR #9169, check if merged |
| 19 | `3352926e` | ✅ KEEP | feat: add WorldSim skill (from PR #6243) | skills |

### Plugin / Hook Plumbing (upstream now provides)

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 26 | `9a80fa52` | 🔀 SKIP | feat(plugins): let pre_tool_call hooks block tool execution | already upstream |
| 7 | `5582e732` | ❌ DROP | fix(core): pass session_id to pre_tool_call hooks in concurrent/sequential dispatch | upstream fixed natively |
| 6 | `fe81507b` | ❌ DROP | fix(core): pass session_id through registry.dispatch() to plugin tool handlers | upstream fixed natively |
| 4 | `e02650e2` | ❌ DROP | fix(core): propagate chat_id, thread_id, user_id to all plugin hooks | upstream has extra kwargs everywhere |
| 2 | `a9fb813f` | ❌ DROP | feat(core): on_session_end continuation directive for plugin-driven follow-up turns | upstream already consumes this shape |
| 1 | `f130b675` | ❌ DROP | fix(core): set chat_id/thread_id as attrs after AIAgent construction | upstream has this |

### Test Suite

| # | Hash | Status | Description | Files touched |
|---|------|--------|-------------|---------------|
| 24 | `63da34ce` | ⚠️ REVIEW | fix(tests): resolve stale test imports and missing module references | multiple test files — may not apply cleanly |
| 23 | `cd452875` | ⚠️ REVIEW | chore(tests): curate test suite — remove 39 low-value tests | test deletions — re-evaluate against upstream's current tests |
| 22 | `39daadc7` | ❌ DROP | docs: add test suite curation report | stale doc |
| 21 | `be106ea4` | ⚠️ REVIEW | Fix test suite failures: isolate env vars, fix stale assertions | may not apply to upstream's current tests |
| 3 | `eada28ff` | ✅ KEEP | Suppress noisy WARNING logs and deprecation warnings in test output | `conftest.py` / pytest config |

---

## Summary

| Status | Count |
|--------|-------|
| ✅ KEEP | 24 |
| ⚠️ REVIEW | 9 |
| ❌ DROP | 8 |
| 🔀 SKIP | 3 |
| **Total** | **44** |

## Cherry-pick order for new base

When creating a new patch branch, cherry-pick in this order:

1. Infrastructure (`c9b44899`, `7c4b7db1`, `0e16c1ba`)
2. Copilot/Vision (`42b5058f`, `f9874d1f`, `4d78ee8e`, `abc4b1d4`, `bbdc2f88`)
3. Compaction (`5a074f54`, `7587579d`, `eeb81e8e`) — review against new upstream compressor first
4. Auxiliary plumbing (`d755400c`, `38140cd6`) — review against upstream changes first
5. Config/CLI (`1e68bd46`, `3f37769c`, `040c22de`, `3bca7e1c`)
6. Discord (`c2a7387e`, `d4f73ac5`, `e878da90`, `9467f5ad`, `ed78e870`)
7. Web/Search (`b84c7c70`)
8. Media/Files (`eea408d6`, `7865a3be`, `3a5d738c`)
9. Cron (`44342c34`)
10. Tests (`63da34ce`, `cd452875`, `be106ea4`, `eada28ff`) — review all against upstream's current test state
11. Skills/Misc (`3352926e`)

Skip: `f9b3f361` (lockfile), `39daadc7` (stale doc), `398f96c5` (merge commit — flatten)
Skip (already upstream): `9a80fa52`, `fcd2587c`, `afd2e51c`
Drop (upstream provides): `5582e732`, `fe81507b`, `e02650e2`, `a9fb813f`, `f130b675`
