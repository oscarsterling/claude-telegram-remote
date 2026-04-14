# Changelog

## v2.2.0 — 2026-04-14

### Added
- **`!context`** command. Scrapes model and context % from the tmux pane status line. No Claude turn is burned. Works at 0% (immediately after /reset) by falling back to the window size embedded in the model name (e.g., "Opus 4.6 (1M context)").
- **Telegram slash-command menu registration.** On startup the daemon calls `setMyCommands` so all `!` commands also appear in Telegram's in-chat `/` picker. `/ping`, `/context`, etc. are normalized to `!ping`, `!context` server-side.

## v2.1.0 — 2026-04-14

### Added
- **Wake-ping pattern for `!restart`.** Manual-flag stub in `cmd_restart` and README section documenting how to have the freshly restarted Claude announce itself in Telegram. Nightly/scheduled restarts skip the flag and stay silent.

## v2.0.0 — 2026-04-14

### Added
- **Typing indicator pinger** (`hooks/typing-indicator-pinger.py`, `hooks/start-typing-pinger.sh`, `hooks/stop-typing-pinger.sh`). Telegram now shows "Claude is typing..." for the entire duration of the response. Single-instance per chat_id, hard 10-minute ceiling, killed on reply.
- **Deterministic Stop hook** (`hooks/check-tg-reply-completeness.py`). Replaces the LLM-judge prompt-style Stop hook with a Python script that walks the JSONL transcript. Catches both "missing TG reply" AND "trailing terminal text after the reply" by cross-referencing the persisted transcript with the in-flight `last_assistant_message` payload.
- **`!ping`** command. Returns "Pong" for daemon health checks.
- **`!reset`** command. Alias for `!restart`.
- **`!effort [max|high|medium|auto]`** command. Sets thinking effort. With no argument, sends an inline keyboard button picker; the daemon handles the callback_query.
- **`!health`** command. Runs an optional user-configured health check script (`HEALTH_SCRIPT` config var).
- **`!cost`** command. Sends `/cost` to the tmux session.
- **Inline-button callback handler** in the daemon. The commander bot can now send and respond to `inline_keyboard` button taps, not just text replies.
- **Optional `RESTART_SCRIPT` and `HEALTH_SCRIPT`** config vars. Both default to empty (the corresponding commands no-op gracefully if not set).

### Changed
- Configuration block at the top of `telegram-commander.py` is now explicitly marked `=== CONFIGURE THESE ===` with sensible defaults and inline guidance.
- `/command` syntax is now normalized to `!command` server-side, so both work from Telegram.
- "No tmux session" error messages are now generated from the configured `TMUX_SESSION` value rather than hardcoded.
- The Stop hook example in the README is now a `command` type (deterministic Python) rather than a `prompt` type (LLM-judge).

### Fixed
- Removed a duplicate `cmd_cost` definition that was shadowing the first.
- The daemon now refuses to start if `YOUR_USER_ID` is unset, with a clear error.
- Log directory is auto-created on daemon start.

## v1.0.0 — 2026-04-09

Initial release: command daemon, message cache hooks, LLM-judge Stop hook, proactive messaging scripts.
