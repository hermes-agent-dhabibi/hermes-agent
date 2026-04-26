# Custom Patches

Our fork's patch layer. Synced onto `my/v0.11.0` from `upstream/main` at tag `v2026.4.23` (release v0.11.0).

Last updated: 2026-04-23 (post v0.11.0 release)
Base: `my/v0.11.0`, tip `fa9f608d`
Upstream base tag: `v2026.4.23` (commit `bf196a3f`)

**Dropped this rebase:**
- `89cd6a11 fix(discord): bump sync timeout to 60s with 3 retries` — superseded by upstream `a1ff6b45 add safe startup slash sync policy` which adds policy controls (`safe`/`bulk`/`off`) plus its own timeout/retry handling and per-command reconciliation.

---

## Reapplied patch commits on `my/upstream-20260423`

Oldest to newest.

| Original SHA | New SHA | Description |
|---|---|---|
| `b1810b56` | `ba00b442` | docs(skill): native-mcp — prefer /reload-mcp over full restart |
| `995592c3` | `a22442dd` | chore: add commit-msg hook enforcing structured commit messages |
| `cfe22401` | `5f997819` | feat(auxiliary): Copilot vision routing + vision backend fallback on quota errors |
| `b0f174d3` | `b58c876a` | fix(vision): add Copilot-Vision-Request header for copilot vision backend |
| `dd1e40a9` | `729389ec` | fix(copilot): preserve base URL and gpt-5-mini routing |
| `f7a6b6b6` | `3a7625ea` | fix(copilot): silence spurious token validation warning |
| `f8699721` | `a502f396` | fix(vision): default copilot vision to gpt-5-mini, remove dead header injection |
| `ea751f39` | `be2e89b2` | feat(compaction): Codex-style user message preservation + handoff framing |
| `61eeb6b0` | `8edafa71` | fix(compaction): use identity-preserving prefix instead of 'another language model' |
| `60b16a3f` | `9e746f86` | debug(compaction): add [DEBUG] logs for compaction output |
| `08b1a862` | `8c656069` | fix(auxiliary_client): add missing api_mode param to resolve_provider_client signature |
| `97b92258` | `b3759660` | fix(auxiliary): reconcile main_runtime plumbing with upstream and restore compaction behavior |
| `8d1bfc6c` | `8646e60d` | feat: add `hermes config sync` and `/config-sync` command |
| `d5e09ed4` | `3ac1278a` | fix(cli): avoid heavy import in recent session display |
| `6697d0b8` | `7a35c8d2` | feat: add `hermes update-skills` — pull only built-in skills from upstream |
| `37627b09` | `6ef8bc53` | feat: nightly skill & memory review cron job |
| `5b6d9660` | `c897c8b1` | fix: expand supported document types and text injection for inbound file uploads |
| `25a11ff3` | `8846bb78` | fix(discord): use get_partial_message for edits to avoid 503s |
| `50785ae8` | `63734c12` | fix(discord): remove latency-inducing defaults |
| `5ad4681d` | `51d0ddda` | feat(web): add SearXNG search backend + split search/extract routing |
| `db062ea3` | `45ac09d0` | fix(media): reject non-path text after MEDIA: tag |
| `f61950ad` | `502388f0` | fix: extract_media() now accepts arbitrary file extensions |
| `c9e66790` | `5e177b95` | fix: load .env before flush_memories credential resolution |
| `95fba1ce` | `fc465075` | feat: add WorldSim OSINT-powered personality simulation skill (from PR #6243) |
| `0bfad059` | `60e5776c` | fix(tests): resolve stale test imports and missing module references |
| `a80463bb` | `b14127fb` | chore(tests): curate test suite - remove 39 low-value tests, clean up fixtures |
| `c85af849` | `70216829` | Fix test suite failures: isolate env vars, fix stale assertions |
| `3ff0393c` | `ab33a457` | Suppress noisy WARNING logs and deprecation warnings in test output |
| `b8a5fc33` | `c0289272` | fix(tests): update stale assertions for discord edit truncation and compress noop output |
| `f1baf63e` | `89cd6a11` | fix(discord): bump sync timeout to 60s with 3 retries |
| `7bc1dea8` | `9539bfd8` | feat(plugins): make pre_api_request hook mutable |
| `9fc6cc3b` | `378bcf8a` | feat(gateway): chronological thinking traces + block quote formatting |
| `06db25b5` | `7cc3027a` | fix(gateway): block-quote thinking text + smarter tool grouping |
| `02cf0f49` | `8271fda0` | fix(gateway): raise default tool preview cap from 40 to 200 chars |
| `f6afaf31` | `b3a7eee3` | Auto-register/unregister plugin toolsets in platform_toolsets on install/remove |
| `47c812b3` | `89f34a71` | feat: auto-background detection for long-running terminal commands |
| `0ecc7210` | `a39fcac3` | fix: review swarm findings — tighten patterns, drop load_config(), add tests |
| `6878ed0f` | `218cd801` | fix: add npx serve/http-server to auto-background patterns |
| `6c2ad31f` | `8e68e855` | fix: add ad-hoc HTTP servers (python -m http.server, php -S, etc.) to auto-background |
| `6b172954` | `2e20c56a` | fix(terminal): comprehensive auto-background detection rewrite |
| `8ab50be9` | `39a162b3` | fix(gateway): suppress user-facing notification when notify_on_complete=true |
| —          | `10f9a80f` | fix(discord): decouple free-response from auto-thread (revert upstream `93fe4b35` coupling) |

---

## Dropped during 2026-04-23 rebase

| Original SHA | Reason |
|---|---|
| `9223f943` | Upstream already merged PR #9169 for parallel cron due jobs. |
| `c65d0849` | Upstream commit `d7fb435e` already replaced `/skill` subcommand groups with autocomplete. |
| `bfc0e68f` | Upstream `d7fb435e` already includes prefix-based skill autocomplete behavior. |

## Skipped during cherry-pick

| Original SHA | Reason |
|---|---|
| `1dc0ac14` | Empty cherry-pick on top of current tree; behavior already present from prior conflict resolutions/upstream state. |
