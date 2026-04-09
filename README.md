# claude-telegram-remote

Control Claude Code from your phone via Telegram. Five pieces that turn a terminal-only AI into a mobile-first assistant.

![Hero](assets/hero.png)

## What This Is

A set of scripts and configurations that give you full remote control of Claude Code through Telegram. Built by someone who manages BPO operations for a living, not an engineer.

**[Read the full story on Clelp.ai](https://clelp.ai/blog/claude-telegram-remote-control)**

## The Five Pieces

| # | Piece | What It Does |
|---|-------|-------------|
| 1 | **Conversation Layer** | Anthropic's Telegram MCP plugin. Claude receives and sends messages via Telegram. |
| 2 | **Message Cache** | Hooks that log all messages per chat. Gives Claude thread context across sessions. |
| 3 | **Command Daemon** | Background service that watches for `!commands` and injects them into Claude Code's tmux session. |
| 4 | **Notification Fix** | Stop hook that ensures Claude always replies via Telegram, not just to the terminal. |
| 5 | **Proactive Messaging** | Shell scripts for cron notifications and interactive inline keyboard buttons. |

## Commands

| Command | What It Does |
|---------|-------------|
| `!status` | What Claude is working on right now |
| `!stop` | Send SIGINT to stop the current task |
| `!plan` | Switch to plan mode before acting |
| `!restart` | Restart the Claude Code session |
| `!mode` | Cycle permission modes (Shift+Tab) |
| `!opus` | Switch to Opus (1M context) |
| `!sonnet` | Switch to Sonnet (faster) |
| `!model` | Show current model |
| `!clear` | Clear conversation context |
| `!compact` | Compact the conversation |

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

The conversation bot token is configured in Claude Code's Telegram MCP plugin settings.

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

Edit `scripts/telegram-commander.py`:

- Set `YOUR_USER_ID` to your Telegram user ID
- Set `TMUX_SESSION` to your tmux session name

### Step 6: Install the Hooks

Copy the hook configurations into your Claude Code settings:

**Message Cache (UserPromptSubmit hook):**
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash /path/to/hooks/cache-telegram-inbound.sh",
            "timeout": 10,
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
            "command": "bash /path/to/hooks/cache-telegram-outbound.sh",
            "timeout": 10,
            "async": true
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Check if the model's LAST turn included a Telegram channel message. If it received a Telegram message but did NOT call the Telegram reply tool, output BLOCK. Otherwise output PASS.",
            "timeout": 15
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
python3 scripts/telegram-commander.py

# Run as a launchd service (macOS)
cp services/com.claude.telegram-commander.plist ~/Library/LaunchAgents/
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
    telegram-commander.py    # Command daemon
    tg-send.sh               # Proactive plain text messaging
    tg-buttons.sh            # Proactive inline keyboard buttons
  hooks/
    cache-telegram-inbound.sh   # Message cache (inbound)
    cache-telegram-outbound.sh  # Message cache (outbound)
  services/
    com.claude.telegram-commander.plist  # macOS launchd config
  examples/
    settings-hooks.json      # Example Claude Code hook configuration
  assets/
    hero.png                 # Project hero image
```

## How It Works

The command daemon is a Python process that long-polls the Telegram Bot API for messages from your command bot. When it sees a message starting with `!`, it maps it to an action:

- **Slash commands** (`!plan`, `!clear`, `!compact`): Injected as keystrokes into tmux via `tmux send-keys`
- **Raw keys** (`!mode`): Sent as special key names (e.g., `BTab` for Shift+Tab)
- **Process control** (`!stop`, `!restart`): Direct signal/subprocess calls

The message cache hooks fire on every prompt submission and every Telegram reply, logging both sides of the conversation to JSONL files organized by chat ID.

The Stop hook checks every time Claude finishes a response. If it received a Telegram message but only replied to the terminal (not via the Telegram tool), it blocks and forces a retry through Telegram.

## Customization

- **Add commands**: Edit the `COMMANDS` dict in `telegram-commander.py`
- **Change tmux session name**: Edit `TMUX_SESSION` variable
- **Linux**: Replace the launchd plist with a systemd service file
- **Multiple users**: Add user IDs to an allowlist in the commander

## Credits

Built by [Oscar Sterling](https://github.com/oscarsterling) (AI Chief of Staff) for [Jason Haugh](https://x.com/jason_haugh).

Story: [How I Control Claude Code From My Phone](https://clelp.ai/blog/claude-telegram-remote-control)

## License

MIT
