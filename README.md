# claude-telegram-remote

**v3.2** (April 22, 2026). Control Claude Code from your phone via Telegram. 23 commands, interactive checkpoint rollback, session save/restore/refresh, a typing indicator, a deterministic Stop-hook, and inline button pickers.

![Hero](assets/hero.png)

## What This Is

A set of scripts and configurations that give you full remote control of Claude Code through Telegram. Built by someone who manages BPO operations for a living, not an engineer.

**[Read the full story on Clelp.ai](https://clelp.ai/blog/claude-telegram-remote-control)**

## Version History

### v3.2

- **Full-fidelity session save/restore.** `session-save.py` no longer slices individual messages at character caps, uses `git log --since=<session-start>` instead of heredoc-breaking regex for commit extraction, and leads the output with the last full exchange so fresh sessions pick up exactly where the previous one left off. Restore payloads from prior saves are filtered out of the parse to stop recursive echo across save/restore cycles.
- **Optional reply-context patch for the Telegram MCP plugin.** Under `advanced/reply-context-patch/`, an idempotent script that patches `telegram@claude-plugins-official`'s `server.ts` to surface Telegram's "reply to this message" gesture to Claude. Without the patch, the swipe-reply is invisible. Ships with `--check` and `--dry-run` modes for safe re-runs after plugin auto-upgrades.

### v3.1

- **`!refresh` command.** Save, reset, restore in one shot. Captures context, resets the session, and injects the brief into the fresh session automatically. If any step fails, tells you exactly where it stopped and how to recover manually.
- **Channel-tag injection for restore/refresh.** `!restore` and `!refresh` now wrap the injected brief in Telegram channel tags so Claude treats it as a real Telegram message and responds in Telegram, not the terminal.

### v3.0

- **Interactive /rewind with Telegram buttons.** Opens the Claude Code checkpoint picker, parses it from tmux, and sends tappable buttons. Pick a checkpoint or cancel, all from your phone. Cooldown guard prevents duplicate execution.
- **Session save/restore.** `!save` captures a compressed brief of what you were working on (exchanges, files changed, commits, where you left off). `!restore` injects a saved brief into a fresh session. `!contexts` lists everything you have saved.
- **Seven new commands.** `!rewind`, `!save`, `!restore`, `!contexts`, `!fast`, `!resume`, `!init`.
- **Removed terminal-only commands.** `!review`, `!doctor`, and `!memory` produced output that only made sense in a terminal, not in Telegram.
- **Fixed dict-slice crash.** The logging line now handles dict responses without raising TypeError (this was causing a launchd respawn loop).

### v2.0

- **Typing indicator pinger.** Telegram now shows "Claude is typing..." the entire time he is working, just like a real chat. Spawns on inbound, dies on reply, hard 10-min ceiling.
- **Deterministic Stop hook.** Replaces the old LLM-judge with a Python script that walks the actual transcript. Catches both "missing TG reply" AND "trailing terminal text after the reply" (the silent killer).
- **Five new commands.** `!ping`, `!reset`, `!effort`, `!health`, `!cost`.
- **Inline button picker.** `!effort` with no argument pops up a Max/High/Medium/Auto button picker via callback queries.
- **Optional health check hook.** Wire your own health-check script into `!health`.

## The Six Pieces

| # | Piece | What It Does |
|---|-------|-------------|
| 1 | **Conversation Layer** | Anthropic's Telegram MCP plugin. Claude receives and sends messages via Telegram. |
| 2 | **Message Cache** | Hooks that log all messages per chat. Gives Claude thread context across sessions. |
| 3 | **Command Daemon** | Background service that watches for `!commands` and injects them into Claude Code's tmux session. Handles inline-button callbacks for effort and rewind pickers. |
| 4 | **Stop Hook** | Deterministic Python check. Blocks if Claude got a TG message and didn't reply, OR if he wrote terminal text after the final reply. |
| 5 | **Typing Pinger** | Spawns a `sendChatAction(typing)` loop on inbound, killed on reply. Single-instance per chat. |
| 6 | **Proactive Messaging** | Shell scripts for cron notifications and interactive inline keyboard buttons. |

## Commands

| Command | What It Does |
|---------|-------------|
| `!ping` | Health check, replies "Pong" |
| `!status` | What Claude is working on right now (PID + uptime) |
| `!stop` | Send SIGINT to interrupt the current task |
| `!plan` | Switch to plan mode before acting |
| `!restart` / `!reset` | Restart the Claude Code session (requires `RESTART_SCRIPT` config, supports wake-ping, see Advanced) |
| `!mode` | Cycle permission modes (Shift+Tab) and report the current one |
| `!opus` | Switch to Opus (1M context) |
| `!sonnet` | Switch to Sonnet (faster) |
| `!model [name]` | Show current model, or switch to a specific one |
| `!clear` | Clear conversation context |
| `!compact` | Compact the conversation |
| `!cost` | Show current session cost |
| `!effort [max\|high\|medium\|auto]` | Set thinking effort level (no arg = button picker) |
| `!health` | Run your custom health check script (requires `HEALTH_SCRIPT` config) |
| `!context` | Show model + context % used (no Claude turn burned) |
| `!rewind` | Roll back to a prior checkpoint (interactive button picker) |
| `!fast` | Toggle fast output mode (same model, faster output) |
| `!resume [query]` | Resume a previous conversation |
| `!init` | Initialize CLAUDE.md for current project |
| `!refresh` | Save context, reset session, restore context in one shot |
| `!save [label]` | Save a compressed context brief of the current session |
| `!restore <label>` | Restore a saved session context into Claude Code |
| `!contexts` | List all saved session context briefs |

Both `!command` and `/command` syntax work, since some Telegram clients auto-complete `/`.

## Prerequisites

- macOS (launchd for the daemon; Linux users swap for systemd)
- Claude Code installed and running in a tmux session
- Two Telegram bots (one for conversation, one for commands)
- tmux
- Python 3.10+

## Setup

### Step 1: Create Two Telegram Bots

You need two bots because the command daemon polls for messages, and you don't want that polling noise in your main conversation.

1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Create bot #1: your conversation bot (e.g., "MyClaudeBot")
3. Create bot #2: your command bot (e.g., "MyClaudeCommander")
4. Save both tokens

### Step 2: Store Tokens

On macOS, store the command bot token in Keychain:

```bash
security add-generic-password -a clawdbot -s telegram-commander-bot-token -w "YOUR_COMMAND_BOT_TOKEN"
```

Store the conversation bot token where the typing pinger can read it:

```bash
mkdir -p ~/.claude/channels/telegram
echo 'TELEGRAM_BOT_TOKEN=YOUR_CONVERSATION_BOT_TOKEN' > ~/.claude/channels/telegram/.env
chmod 600 ~/.claude/channels/telegram/.env
```

The conversation bot token is also configured in Claude Code's Telegram MCP plugin settings.

### Step 3: Get Your Telegram User ID

Send a message to [@userinfobot](https://t.me/userinfobot) on Telegram. It will reply with your user ID. You'll need this to restrict commands to only you.

### Step 4: Install the Telegram MCP Plugin

In Claude Code, enable the Telegram plugin:

```json
{
  "enabledPlugins": {
    "telegram@claude-plugins-official": true
  }
}
```

### Step 5: Configure the Command Daemon

Edit `scripts/telegram-commander.py` and set the values in the `=== CONFIGURE THESE ===` block:

- `YOUR_USER_ID` - your Telegram user ID
- `TMUX_SESSION` - your tmux session name (default: `claude`)
- `TMUX_PATH` - output of `which tmux`
- `RESTART_SCRIPT` - optional, absolute path to your restart script (or leave `""` to disable `!restart`)
- `HEALTH_SCRIPT` - optional, absolute path to your health check script (or leave `""` to disable `!health`)
- `REPO_DIR` - where you cloned this repo (default: `~/claude-telegram-remote`)

### Step 6: Install the Hooks

Copy this repo to `~/claude-telegram-remote/` (the hook scripts assume that path):

```bash
git clone https://github.com/oscarsterling/claude-telegram-remote ~/claude-telegram-remote
chmod +x ~/claude-telegram-remote/hooks/*.sh
chmod +x ~/claude-telegram-remote/hooks/*.py
```

Then add the hook configuration to your Claude Code `settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/claude-telegram-remote/hooks/cache-telegram-inbound.sh",
            "timeout": 10,
            "async": true
          },
          {
            "type": "command",
            "command": "bash ~/claude-telegram-remote/hooks/start-typing-pinger.sh",
            "timeout": 5,
            "async": true
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "mcp__plugin_telegram_telegram__reply",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/claude-telegram-remote/hooks/cache-telegram-outbound.sh",
            "timeout": 10,
            "async": true
          },
          {
            "type": "command",
            "command": "bash ~/claude-telegram-remote/hooks/stop-typing-pinger.sh",
            "timeout": 5,
            "async": true
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/claude-telegram-remote/hooks/check-tg-reply-completeness.py",
            "timeout": 10
          },
          {
            "type": "command",
            "command": "bash ~/claude-telegram-remote/hooks/stop-typing-pinger.sh",
            "timeout": 5,
            "async": true
          }
        ]
      }
    ]
  }
}
```

### Step 7: Start the Daemon

```bash
# Test it first
python3 ~/claude-telegram-remote/scripts/telegram-commander.py

# Run as a launchd service (macOS)
cp ~/claude-telegram-remote/services/com.claude.telegram-commander.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.claude.telegram-commander.plist
```

### Step 8: Start Claude Code in tmux

```bash
tmux new-session -d -s claude
tmux send-keys -t claude 'claude' Enter
```

Send `!ping` from your command bot. If you get `Pong`, you're live.

## File Structure

```
claude-telegram-remote/
  scripts/
    telegram-commander.py            # Command daemon (23 commands + button callbacks)
    session-save.py                  # Save session context briefs
    session-restore.py               # Restore saved context briefs
    session-list.py                  # List saved context briefs
    tg-send.sh                       # Proactive plain text messaging
    tg-buttons.sh                    # Proactive inline keyboard buttons
  hooks/
    cache-telegram-inbound.sh        # Message cache (inbound)
    cache-telegram-outbound.sh       # Message cache (outbound)
    start-typing-pinger.sh           # Spawns the typing pinger on inbound TG
    stop-typing-pinger.sh            # Kills any running typing pingers
    typing-indicator-pinger.py       # Loops sendChatAction(typing) until killed
    check-tg-reply-completeness.py   # Deterministic Stop hook
  services/
    com.claude.telegram-commander.plist  # macOS launchd config
  saved-contexts/                    # Session context briefs (created by !save)
  advanced/
    reply-context-patch/             # Optional patch for the Telegram MCP plugin
      apply.py                       # Idempotent patch applier with --check / --dry-run
      README.md                      # What it does, how to install, rot guard
  assets/
    hero.png                         # Project hero image
```

## How It Works

**Command daemon.** A Python process long-polls the Telegram Bot API for messages from your command bot. When it sees a message starting with `!` or `/`, it maps it to an action:
- Slash commands (`!plan`, `!clear`, `!compact`, `!cost`): injected as keystrokes into tmux via `tmux send-keys`
- Raw keys (`!mode`): sent as special key names (e.g., `BTab` for Shift+Tab)
- Process control (`!stop`, `!restart`): direct signal/subprocess calls
- Inline pickers (`!effort` with no arg, `!rewind`): sends inline keyboard buttons; the daemon handles the callback_query taps
- Session management (`!save`, `!restore`, `!contexts`): runs helper scripts that parse and store session JSONL data

**Message cache hooks.** Fire on every prompt submission and every Telegram reply, logging both sides of the conversation to JSONL files organized by chat ID.

**Typing pinger.** When a Telegram message arrives, `start-typing-pinger.sh` extracts the chat_id from the inbound channel tag and spawns `typing-indicator-pinger.py` as a detached process. The pinger loops `sendChatAction(typing)` every 4 seconds (Telegram clears typing after ~5s, so this keeps it lit). It dies in three ways: PostToolUse on the reply tool, the Stop hook backstop, or the hard 10-minute ceiling.

**Stop hook.** A deterministic Python script that walks the JSONL transcript backwards to the most recent real user prompt, then checks two conditions:
1. If a Telegram channel tag was in the prompt and no `mcp__plugin_telegram_telegram__reply` tool was called, BLOCK with "missing TG reply"
2. If a reply was called AND there is text either after it in the transcript OR in the in-flight `last_assistant_message` payload, BLOCK with "trailing terminal text after TG reply"

The trailing-text check uses both the persisted transcript AND the stdin payload because the Stop hook fires before the final assistant text is flushed to JSONL. Without that cross-check, trailing text after the final reply slips through invisible.

**Session save/restore/refresh.** `!save` runs `session-save.py`, which reads the tail of the active session JSONL, extracts Telegram replies, user requests, file modifications, and git commits, then compresses them into a structured markdown brief. `!restore` reads that brief back and injects it into the tmux session wrapped in Telegram channel tags, so Claude treats it as a real message and responds in Telegram. `!refresh` chains save, `/reset`, and restore into a single command for mid-session resets without losing context.

## Customization

- **Add commands**: Edit the `COMMANDS` dict in `telegram-commander.py`
- **Change tmux session name**: Edit `TMUX_SESSION` in the config block
- **Linux**: Replace the launchd plist with a systemd service file
- **Multiple users**: Add user IDs to an allowlist in the commander
- **Custom button pickers**: Add new `callback_data` prefixes in the `callback_query` handler
- **Session save location**: Edit `SAVE_DIR` in `session-save.py` and `session-restore.py`

## Advanced: Wake-Ping After `!restart`

When you `!restart` from your phone, tmux comes back fast but Claude takes a beat to fully reset. The daemon tells you "restarting, give it 30 seconds" but you have no proof the new session is actually awake before you send your next message.

Fix: have the new Claude announce itself in Telegram once `/reset` has processed.

Pattern:

1. `cmd_restart()` writes two files: the restart trigger **and** a "manual flag" file (e.g. `restart-manual-flag`).
2. Your restart script runs its normal steps, verifies the new session is ready, then checks for the manual flag.
3. If the flag exists, sleep ~10 seconds (buffer so `/reset` finishes), then `tmux send-keys` a short wake prompt. Example:
   ```bash
   WAKE_PROMPT='You just rebooted via manual /reset. Reply in DM: "Awake. Session ready." with current time. Nothing else.'
   tmux send-keys -t "$TMUX_SESSION" "$WAKE_PROMPT" Enter
   ```
4. Delete the flag.

**Customize the ping.** The wake prompt is just a string in your restart script, so you can make it anything: have Claude report system health, read the last few inbox items, sanity-check a cron, or just say hi with a specific tone. Keep it short (one to two sentences) so the first turn doesn't eat context.

Nightly cron restarts never create the flag, so scheduled resets stay silent. Only `!restart` (manual) triggers the ping.

See `cmd_restart()` in `scripts/telegram-commander.py` for the skeleton.

## Credits

Built by [Oscar Sterling](https://github.com/oscarsterling) (AI Chief of Staff) for [Jason Haugh](https://x.com/jason_haugh).

Story: [How I Control Claude Code From My Phone](https://clelp.ai/blog/claude-telegram-remote-control)

## License

MIT
