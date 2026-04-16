# Stale Tests on `my/upstream-20260416`

32 failures + 10 errors from full pytest run (11829 passed, 32 skipped).
None are runtime regressions — all are test expectations that haven't caught up to upstream refactors.

Generated: 2026-04-16

---

## Copilot Auth Refactor (7 failures)
Upstream changed copilot credential resolution (now uses `COPILOT_GITHUB_TOKEN` env, different base URLs).

- `tests/agent/test_credential_pool.py::test_load_pool_seeds_copilot_via_gh_auth_token`
- `tests/agent/test_credential_pool.py::test_load_pool_does_not_seed_copilot_when_no_token`
- `tests/hermes_cli/test_api_key_providers.py::TestApiKeyProviderStatus::test_copilot_status_uses_gh_cli_token`
- `tests/hermes_cli/test_api_key_providers.py::TestResolveApiKeyProviderCredentials::test_resolve_copilot_with_github_token`
- `tests/hermes_cli/test_api_key_providers.py::TestResolveApiKeyProviderCredentials::test_resolve_copilot_with_gh_cli_fallback`
- `tests/hermes_cli/test_api_key_providers.py::TestRuntimeProviderResolution::test_runtime_copilot_uses_gh_cli_token`
- `tests/tools/test_delegate.py::TestDelegateTask::test_child_inherits_runtime_credentials`

## Discord Adapter Changes (3 failures + 10 errors)
Edit truncation behavior changed; slash command auto-registration API changed; discord.py lib version mismatch on `DMChannel`.

- `tests/gateway/test_discord_send.py::test_edit_message_rejects_oversized_content`
- `tests/gateway/test_discord_slash_commands.py::test_auto_registers_missing_gateway_commands`
- `tests/gateway/test_discord_slash_commands.py::test_auto_registered_command_dispatches_correctly`
- `tests/gateway/test_discord_slash_commands.py::test_auto_registered_command_with_args`

- `tests/gateway/test_discord_reply_mode.py::TestReplyToText::test_no_reference_both_none` (ERROR)
- `tests/gateway/test_discord_reply_mode.py::TestReplyToText::test_reference_without_resolved` (ERROR)
- `tests/gateway/test_discord_reply_mode.py::TestReplyToText::test_reference_with_resolved_content` (ERROR)
- `tests/gateway/test_discord_reply_mode.py::TestReplyToText::test_reference_with_empty_resolved_content` (ERROR)
- `tests/gateway/test_discord_reply_mode.py::TestReplyToText::test_reference_with_deleted_message` (ERROR)

## DM Topics / Skill Binding (4 failures)
Upstream changed topic→skill mapping interface; tests expect old return values.

- `tests/gateway/test_dm_topics.py::test_group_topic_skill_binding`
- `tests/gateway/test_dm_topics.py::test_group_topic_skill_binding_second_topic`
- `tests/gateway/test_dm_topics.py::test_group_topic_no_skill_binding`
- `tests/gateway/test_dm_topics.py::test_group_topic_chat_id_int_string_coercion`

## Model Detection Refactor (2 failures)
Provider slug resolution changed (`openrouter` → `ai-gateway`, bare names no longer get openrouter prefix).

- `tests/hermes_cli/test_models.py::TestDetectProviderForModel::test_openrouter_slug_match`
- `tests/hermes_cli/test_models.py::TestDetectProviderForModel::test_bare_name_gets_openrouter_slug`

## Telegram Network (2 failures)
IP validation logging format changed; tests assert old log strings.

- `tests/gateway/test_telegram_network.py::TestParseFallbackIpEnv::test_filters_invalid_and_ipv6`
- `tests/gateway/test_telegram_network.py::TestParseFallbackIpEnv::test_rejects_leading_zeros`

## Browser Console (3 failures)
Test mocks don't match new console tool signatures.

- `tests/tools/test_browser_console.py::TestBrowserConsole::test_returns_console_messages_and_errors`
- `tests/tools/test_browser_console.py::TestBrowserConsole::test_passes_clear_flag`
- `tests/tools/test_browser_console.py::TestBrowserConsole::test_no_clear_by_default`

## Web Tools Config (3 failures)
Backend key detection and tavily dispatch paths changed.

- `tests/tools/test_web_tools_config.py::TestCheckWebApiKey::test_no_keys_returns_false`
- `tests/tools/test_web_tools_config.py::TestCheckWebApiKey::test_configured_backend_must_match_available_provider`
- `tests/tools/test_web_tools_tavily.py::TestWebSearchTavily::test_search_dispatches_to_tavily`

## Misc (8 failures)

- `tests/cli/test_quick_commands.py::TestCLIQuickCommands::test_alias_command_passes_args` — CLI missing `session_id` attr in test setup (flaky)
- `tests/hermes_cli/test_runtime_provider_resolution.py::test_named_custom_provider_uses_providers_dict_when_list_missing` — provider resolution path changed
- `tests/run_agent/test_run_agent.py::TestMemoryNudgeCounterPersistence::test_counters_initialized_in_init` — missing counter init in `__init__` (harmless, defaults on access)
- `tests/run_agent/test_context_token_tracking.py::test_openai_prompt_tokens_unchanged` — token count constant shifted
- `tests/test_hermes_logging.py::TestAddRotatingHandler::test_no_session_filter_on_handler` — handler filter structure changed
- `tests/test_plugin_skills.py::TestSkillViewPluginGuards::test_injection_logged_but_served` — skill plugin guard behavior changed
- `tests/gateway/test_internal_event_bypass_pairing.py::test_non_internal_event_without_user_triggers_pairing` — event pairing logic changed
- `tests/gateway/test_compress_command.py::test_compress_command_reports_noop_without_success_banner` — ✅ ALREADY FIXED
