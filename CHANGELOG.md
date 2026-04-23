# Changelog

## v3.2.1 - 2026-04-22

Security hardening pass. No functional changes; all fixes are defense-in-depth after a Shield security review of v3.2.0.

### Security
- **Write-time channel-tag neutralization in `session-save.py`.** Captured Telegram content is now sanitized before being written to a brief: control characters stripped, literal `<channel` and `</channel>` tokens rewritten to `<_channel` / `</_channel>` so they cannot forge an inbound frame with a different `user_id` when the brief is later wrapped and restored. Prior on-disk briefs remain readable (the sanitizer is also applied on read in `telegram-commander.py` for defense in depth).
- **Read-time sanitization in `telegram-commander.py`.** `cmd_restore` and `cmd_refresh` now run the restored brief through the same neutralizer before wrapping it in a `<channel>` tag and pasting into tmux, so older unsanitized briefs on disk cannot bypass the fix.
- **Label validation.** `session-save.py` and `session-restore.py` now reject labels not matching `^[a-z0-9][a-z0-9_-]*$`. Closes a path-traversal vector where a label like `../../foo` could escape `SAVE_DIR` on save or partial-match a file outside `SAVE_DIR` on restore.
- **`saved-contexts/` added to `.gitignore`.** A careless `git add .` on a live install cannot accidentally push session briefs to the public repo.
- **Security Model section added to README.** Documents the trust boundary (allowlisted Telegram user ID is the only authentication), blast radius when that allowlist is breached, existing hardening, hardening the user can add, and what the project does NOT protect against.

## v3.2.0 - 2026-04-22

### Added
- **`advanced/reply-context-patch/`** — optional local patch to `telegram@claude-plugins-official` that surfaces Telegram's "reply to this message" gesture into Claude's inbound channel payload. Adds `reply_to_message_id` meta + prepends a 500-char quote of the replied-to body so Claude sees what you were replying to, even across session resets. Idempotent apply script with `--check` and `--dry-run` modes, anchor-based injection so it refuses to produce partial patches if upstream source shape changes. See `advanced/reply-context-patch/README.md`.

### Changed
- **`session-save.py` rewrite: full-fidelity round-trip, no more truncation.** Three compounding bugs were quietly lossy:
  - Per-message char caps (user 300, assistant 400) sliced individual messages mid-sentence. Replaced with per-section budgets — single messages now restore in full.
  - Commit extraction regex `-m\s+"([^"]+)"` matched `$(cat <<'EOF'...` heredoc preambles instead of the actual commit body, because `[^"]` matches newlines and the closing quote was many lines later. Replaced with `git log --since=<session-start>` using the JSONL's first timestamp as cutoff. No more bash-history archaeology.
  - Output structure now leads with the full last exchange (both sides), then paired earlier exchanges, then files/commits/tools. Fresh sessions read it top-to-bottom and know exactly where the last turn left off.
- Restore payloads auto-prefixed with `Context restore from` are now filtered out of the user-request parse so repeated save/restore cycles don't recursively echo old briefs.

## v3.1.0 - 2026-04-21

### Added
- **`!refresh`** command. Save, reset, restore in one shot. Captures a context brief, sends `/reset` to Claude Code, waits for the fresh session, then injects the brief back in. If any step fails, tells you exactly where it stopped and gives you the label to `!restore` manually.

### Changed
- **`!restore` now injects via channel tags.** The restored brief is wrapped in Telegram `<channel>` tags with your user ID, so Claude treats it as a real Telegram message and responds in Telegram instead of the terminal. `!refresh` uses the same injection method.
- Command count increased from 22 to 23.
- `COMMAND_DESCRIPTIONS` updated with `!refresh` for Telegram's `/` picker menu.

## v3.0.0 - 2026-04-21

### Added
- **Interactive `!rewind`** with Telegram inline button picker. Opens Claude Code's `/rewind` checkpoint list, parses the tmux pane, and sends up to 5 checkpoints as tappable buttons. Cancel button closes the picker cleanly. Cooldown guard prevents duplicate execution within 20 seconds.
- **`!save [label]`** command. Saves a compressed context brief of the current session (work items, key exchanges, files changed, commits, where you left off). Auto-generates a timestamped label if none provided. Briefs are stored in `saved-contexts/`.
- **`!restore <label>`** command. Loads a saved context brief and injects it into the running Claude Code session as a user message. Supports partial label matching.
- **`!contexts`** command. Lists all saved session context briefs with timestamps, sizes, and previews.
- **`!fast`** command. Toggles fast output mode (same model, faster output).
- **`!resume`** command. Resumes a previous Claude Code conversation.
- **`!init`** command. Initializes CLAUDE.md for the current project.
- **Rewind callback handler** in the daemon. Navigates the /rewind picker via Up-arrow keystrokes and Enter, or sends Escape on cancel.
- **`session-save.py`** script. Parses session JSONL, extracts Telegram replies, user requests, file changes, and git commits into a structured markdown brief.
- **`session-restore.py`** script. Reads a saved brief by label (exact or partial match) and outputs it for injection.
- **`session-list.py`** script. Lists all saved contexts with metadata and preview lines.
- **`saved-contexts/`** directory for session context briefs.
- **Self-review step** added to the recommended git workflow (best practice, not a code change).

### Changed
- Command count increased from 15 to 22 Telegram-ready commands.
- `REPO_DIR` config variable added for cleaner path references (replaces scattered `~/claude-telegram-remote` literals).
- `COMMAND_DESCRIPTIONS` updated with all new commands for Telegram's `/` picker menu.

### Removed
- **`!review`** command. Terminal-only output, does not translate to Telegram.
- **`!doctor`** command. Terminal-only output, does not translate to Telegram.
- **`!memory`** command. Terminal-only output, does not translate to Telegram.

### Fixed
- **Dict-slice crash** on the logging line. `response[:80]` now uses `str(response)[:80]` to handle dict responses (like the rewind picker) without raising TypeError. This was causing a launchd respawn loop.
- **None return handling** from cooldown guard. The main loop now checks for `None` responses and issues `continue` instead of trying to reply with `None`.

## v2.2.0 - 2026-04-14

### Added
- **`!context`** command. Scrapes model and context % from the tmux pane status line. No Claude turn is burned. Works at 0% (immediately after /reset) by falling back to the window size embedded in the model name (e.g., "Opus 4.6 (1M context)").
- **Telegram slash-command menu registration.** On startup the daemon calls `setMyCommands` so all `!` commands also appear in Telegram's in-chat `/` picker. `/ping`, `/context`, etc. are normalized to `!ping`, `!context` server-side.

## v2.1.0 - 2026-04-14

### Added
- **Wake-ping pattern for `!restart`.** Manual-flag stub in `cmd_restart` and README section documenting how to have the freshly restarted Claude announce itself in Telegram. Nightly/scheduled restarts skip the flag and stay silent.

## v2.0.0 - 2026-04-14

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

## v1.0.0 - 2026-04-09

Initial release: command daemon, message cache hooks, LLM-judge Stop hook, proactive messaging scripts.
