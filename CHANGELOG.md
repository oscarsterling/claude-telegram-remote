# Changelog

## v3.3.0 - 2026-05-03

Bundled bug fix and robustness improvements to two of the most-used code paths: the `!context` parser and the slash-command injector that backs every other command.

### Fixed
- **`!context` mis-parses when the pane holds a model name above the live status line.** `cmd_context` was iterating the captured tmux pane top-to-bottom and breaking at the FIRST line matching `(Opus|Sonnet|Haiku) N.N`. If anything above CC's live status block contained a model name (an earlier script echo, a prose mention in the conversation, a previous `!context` reply still in scrollback), the parser locked onto that line and read the line directly below it as the percentage row. The auto-mode subline that sits beneath the input prompt then produced the message `Opus 4.7 ... | context line not parseable: ...`. Reversed the iteration so the parser scans bottom-up: the LAST `Opus N.N` occurrence in the pane is always CC's live status line, since nothing CC renders below it contains a model name. Mirrors the `grep ... | tail -1` approach proven in the standalone status-line check. Output format on success is unchanged.

### Improved
- **`inject_slash_command` now pre-clears CC's input box before sending.** Adds an Escape, 0.4s, Escape, 0.4s, Enter, 0.5s sequence in front of every slash command. Drops CC out of any open picker or popup before the slash text lands. The 0.4s gap between the two escapes matters because CC's Ink-based input has a render cycle and faster pairs landed on stale frames in testing.
- **Empty-input Rewind-dialog edge case handled.** When the input box is EMPTY at injection time, the Escape Escape pair opens CC's Rewind dialog (`Restore the code and/or conversation to the point before...`) instead of being a no-op. Without the new Enter step, the slash text would type into that dialog and a stray Enter could fire an actual rewind. With `(current)` highlighted by default, the new Enter exits the dialog without rewinding anything. If no Rewind dialog is open, Enter on an empty input is a no-op (CC ignores empty submits), so the step is safe in the text-was-in-box case too.
- **Slash text and Enter are now sent as two separate `send-keys` calls** with a 0.5s gap. The text send uses `tmux send-keys -l` to force literal-text mode, so tmux cannot parse any token in the payload as a key name (matters for `!refresh` and `!restore`, where the payload is a multi-line `<channel>` block that may contain words like `Tab`, `Enter`, or `Escape` in body text). The gap gives CC time to process large pastes before Enter arrives.

### Added
- **`pre_clear=False` opt-out on `inject_slash_command`** for callers that know the input is already clean. `cmd_refresh` uses this on its post-`/reset` restore inject (the new session has an empty input by definition), avoiding a visible Escape blip at the end of the refresh flow and sidestepping the empty-input Rewind-dialog case.

### Notes
The `!context` fix is a backwards-compatible bug fix: same output format on success, just no longer mis-parses when the pane holds a prior model-name match above the live status line.

The `inject_slash_command` change is a small behavior change but should be invisible in normal use of the built-in `!commands`. If you have custom commands that call `inject_slash_command` directly and rely on the prior single-`send-keys` behavior, pass `pre_clear=False` to skip the new pre-clear sequence and they will run the old fast path. Otherwise they pick up the new robustness for free.

## v3.2.3 - 2026-04-28

Follow-up to v3.2.2: the new defense-in-depth check itself had a bug. The substring match `"No saved context found" in brief` fired against a HEALTHY restore whose body legitimately quoted that string in commentary about a previously-fixed bug, injecting a false-positive `restore-mismatch` failure notice over real restored context.

### Fixed
- **`!refresh` false-positive on healthy save bodies.** Anchored the failure-string check in `cmd_refresh` to `brief.startswith(...)` instead of substring `in`. `session-restore.py` always prints these strings as the entire stdout before `sys.exit(1)`, so they appear at offset 0 on real failure - never mid-body. A successful restore that quotes the failure string in historical commentary no longer trips the check. (`Multiple matches:` already used `startswith`; only the `No saved context found` branch was leaky.)

## v3.2.2 - 2026-04-28

Critical fix: `!refresh` was silently failing on macOS launchd-managed installs because subprocess Python lookups via `PATH` resolved to Apple's Command Line Tools shim, which exits 0 with no output in non-interactive subprocess context. Save never ran. Restore never ran. The daemon logged "Refresh complete" while no save file ever landed on disk, and the new session got the failure stdout pasted in as if it were valid restored content.

### Fixed
- **`!refresh` ghost on launchd installs.** Migrated all 5 `subprocess.run(["python3", ...])` callsites in `telegram-commander.py` to `[sys.executable, ...]`. `sys.executable` is the absolute path of the daemon's own interpreter, bypassing PATH lookup entirely so the launchd shim can never intercept.
- **Save success without disk write.** `cmd_refresh` now verifies the save file exists on disk after the save subprocess returns rc=0, BEFORE firing /reset. If the file is missing, abort with a clear message and the running session is preserved. The previous behavior was to /reset anyway, destroying the session for nothing.

### Added
- **Failure-notice injection on post-/reset errors.** When restore fails after /reset has fired, `cmd_refresh` now injects a `<channel>` diagnostic block into the new session naming the failing step, save path, full stdout/stderr from save and restore, and the files to investigate. The fresh session boots aware that the round-trip failed and where to look.
- **Defense-in-depth on restore output.** If restore stdout matches a known failure string (e.g. "No saved context found") despite rc=0, treat as failure and inject the diagnostic. Prevents future regressions if returncode propagation ever breaks again.
- **Full subprocess stdout/stderr logging.** `cmd_refresh` now logs both streams at INFO/ERROR for save and restore, so commander.log preserves full diagnostic output instead of silently dropping it.
- **Startup interpreter diagnostic.** Daemon logs `sys.executable`, `sys.version`, `shutil.which('python3')`, and `PATH` at startup so any future PATH drift surfaces immediately on respawn.

### Changed
- **`session-restore.py` exact-match only.** Dropped the partial-substring fallback (`if label in f`). Previous behavior would silently load the wrong file if the caller passed a truncated or substring-matching label. Use `!contexts` to discover full labels. LABEL_RE validation unchanged.
- **`session-save.py` retention.** `refresh-*.md` files older than 14 days are pruned at the start of each save. Custom-labelled saves are never pruned. Self-maintaining, no new cron needed. The dir was unbounded before.

### Notes
The launchd PATH issue affects any install where `telegram-commander.py` is run by `launchd` (the documented production path on macOS). Interactive shell invocations were unaffected because the user's PATH includes `/opt/homebrew/bin` (Homebrew Python). If you've been running the commander manually in a tmux pane and only recently moved to launchd, this fix is the missing piece.

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
