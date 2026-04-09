#!/usr/bin/env python3
"""Telegram Commander - Remote control Claude Code via ! commands from Telegram."""
import json, logging, os, signal, subprocess, sys, time, inspect
import urllib.error, urllib.request

# === CONFIGURE THESE ===
YOUR_USER_ID = 0  # Your Telegram user ID (get it from @userinfobot)
TMUX_SESSION = "claude"  # Your tmux session name
TMUX_PATH = "/opt/homebrew/bin/tmux"  # Path to tmux (run `which tmux` to find yours)
# =======================

PID_FILE = os.path.expanduser("~/claude-telegram-remote/commander.pid")
LOG_FILE = os.path.expanduser("~/claude-telegram-remote/commander.log")
POLL_TIMEOUT = 30
RETRY_DELAY = 30
running = True


def get_bot_token():
    """Read bot token from macOS Keychain."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-a", "clawdbot",
             "-s", "telegram-commander-bot-token", "-w"],
            capture_output=True, text=True, timeout=10)
        token = r.stdout.strip()
        if not token:
            logging.error("Bot token empty from Keychain")
            sys.exit(1)
        return token
    except Exception as e:
        logging.error("Failed to get bot token: %s", e)
        sys.exit(1)


def telegram_api(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        data = json.dumps(params).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=POLL_TIMEOUT + 10) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        logging.warning("Telegram API error (%s): %s", method, e)
        return None


def reply(token, chat_id, text):
    telegram_api(token, "sendMessage", {"chat_id": chat_id, "text": text})


def find_claude_pid():
    r = subprocess.run(["pgrep", "-f", "claude.*--channels"], capture_output=True, text=True)
    pids = r.stdout.strip().split("\n") if r.stdout.strip() else []
    return pids[0] if pids and pids[0] else None


def inject_slash_command(slash_cmd):
    """Inject a slash command into the running Claude Code tmux session."""
    check = subprocess.run([TMUX_PATH, "has-session", "-t", TMUX_SESSION],
                           capture_output=True, text=True)
    if check.returncode != 0:
        return "no_session"
    r = subprocess.run(
        [TMUX_PATH, "send-keys", "-t", TMUX_SESSION, slash_cmd, "Enter"],
        capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        return "sent"
    return f"error: {r.stderr.strip()}"


def inject_key(key_name):
    """Send a raw key (not text) into the tmux session."""
    check = subprocess.run([TMUX_PATH, "has-session", "-t", TMUX_SESSION],
                           capture_output=True, text=True)
    if check.returncode != 0:
        return "no_session"
    r = subprocess.run(
        [TMUX_PATH, "send-keys", "-t", TMUX_SESSION, key_name],
        capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        return "sent"
    return f"error: {r.stderr.strip()}"


def read_current_mode():
    """Read current permission mode from tmux pane status line."""
    try:
        r = subprocess.run(
            [TMUX_PATH, "capture-pane", "-t", TMUX_SESSION, "-p"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            for line in reversed(lines):
                low = line.lower()
                if "shift+tab to cycle" in low or "permissions" in low:
                    if "bypass" in low:
                        return "bypass permissions"
                    if "plan" in low:
                        return "plan mode"
                    if "auto" in low:
                        return "auto mode"
                    if "accept" in low:
                        return "accept edits"
            return "default mode"
        return "unknown"
    except Exception:
        return "unknown"


# === COMMANDS ===

def cmd_ping():
    return "Pong"


def cmd_status():
    pid = find_claude_pid()
    if not pid:
        return "Claude is NOT running."
    lines = [f"Claude is running (PID {pid})"]
    ps = subprocess.run(["ps", "-o", "etime=", "-p", pid], capture_output=True, text=True)
    if ps.stdout.strip():
        lines.append(f"Uptime: {ps.stdout.strip()}")
    return "\n".join(lines)


def cmd_stop():
    pid = find_claude_pid()
    if not pid:
        return "No Claude process found."
    try:
        os.kill(int(pid), signal.SIGINT)
        return f"Sent SIGINT to PID {pid}. Claude is waiting for input."
    except OSError as e:
        return f"Failed to stop PID {pid}: {e}"


def cmd_restart():
    """Restart Claude Code session. Customize the restart script path."""
    return "Restart not configured. Set RESTART_SCRIPT path in the config section."


def cmd_plan():
    result = inject_slash_command("/plan")
    if result == "sent":
        return "Sent /plan to tmux session."
    if result == "no_session":
        return f"No tmux session '{TMUX_SESSION}' found. Is Claude running in tmux?"
    return f"Failed: {result}"


def cmd_mode():
    result = inject_key("BTab")
    if result == "sent":
        time.sleep(0.5)
        mode = read_current_mode()
        return f"Cycled mode (Shift+Tab). Current: {mode}"
    if result == "no_session":
        return f"No tmux session '{TMUX_SESSION}' found. Is Claude running in tmux?"
    return f"Failed: {result}"


def cmd_compact():
    result = inject_slash_command("/compact")
    if result == "sent":
        return "Sent /compact to tmux session."
    if result == "no_session":
        return f"No tmux session '{TMUX_SESSION}' found."
    return f"Failed: {result}"


def cmd_clear():
    result = inject_slash_command("/clear")
    if result == "sent":
        return "Sent /clear to tmux session. Fresh conversation."
    if result == "no_session":
        return f"No tmux session '{TMUX_SESSION}' found."
    return f"Failed: {result}"


def cmd_model(args=""):
    model = args.strip() if args else ""
    if not model:
        try:
            r = subprocess.run(
                [TMUX_PATH, "capture-pane", "-t", TMUX_SESSION, "-p"],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                for line in reversed(r.stdout.strip().split("\n")):
                    low = line.lower()
                    if "opus" in low or "sonnet" in low or "haiku" in low:
                        return f"Current model: {line.strip()}"
        except Exception:
            pass
        return "Could not read current model."
    result = inject_slash_command(f"/model {model}")
    if result == "sent":
        return f"Switched to {model}."
    if result == "no_session":
        return f"No tmux session '{TMUX_SESSION}' found."
    return f"Failed: {result}"


def cmd_opus():
    result = inject_slash_command("/model default")
    if result == "sent":
        return "Switched to Opus (1M context)."
    if result == "no_session":
        return f"No tmux session '{TMUX_SESSION}' found."
    return f"Failed: {result}"


def cmd_sonnet():
    result = inject_slash_command("/model sonnet")
    if result == "sent":
        return "Switched to Sonnet."
    if result == "no_session":
        return f"No tmux session '{TMUX_SESSION}' found."
    return f"Failed: {result}"


COMMANDS = {
    "!ping": cmd_ping, "!status": cmd_status, "!stop": cmd_stop,
    "!restart": cmd_restart, "!reset": cmd_restart,
    "!plan": cmd_plan, "!mode": cmd_mode, "!compact": cmd_compact,
    "!clear": cmd_clear, "!model": cmd_model,
    "!opus": cmd_opus, "!sonnet": cmd_sonnet,
}


def handle_signal(signum, frame):
    global running
    logging.info("Received signal %d, shutting down", signum)
    running = False


def main():
    if YOUR_USER_ID == 0:
        print("ERROR: Set YOUR_USER_ID in the script before running.")
        print("Get your Telegram user ID from @userinfobot")
        sys.exit(1)

    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    logging.basicConfig(
        filename=LOG_FILE, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    logging.info("Telegram Commander starting")
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    token = get_bot_token()
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    logging.info("Daemon started, PID %d", os.getpid())
    last_update_id = 0

    try:
        while running:
            result = telegram_api(token, "getUpdates", {
                "offset": last_update_id + 1,
                "timeout": POLL_TIMEOUT,
                "allowed_updates": ["message"]
            })
            if result is None or not result.get("ok"):
                logging.warning("API issue, retrying in %ds: %s", RETRY_DELAY, result)
                time.sleep(RETRY_DELAY)
                continue

            for update in result.get("result", []):
                update_id = update["update_id"]
                last_update_id = max(last_update_id, update_id)
                msg = update.get("message")
                if not msg:
                    continue
                user_id = msg.get("from", {}).get("id")
                chat_id = msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip().lower()
                if user_id != YOUR_USER_ID or (not text.startswith("!") and not text.startswith("/")):
                    continue

                cmd_key = text.split()[0]
                if cmd_key.startswith("/"):
                    cmd_key = "!" + cmd_key[1:].split("@")[0]
                logging.info("Command: %s", cmd_key)
                handler = COMMANDS.get(cmd_key)
                if handler:
                    try:
                        args = text[len(cmd_key):].strip()
                        if inspect.signature(handler).parameters:
                            response = handler(args)
                        else:
                            response = handler()
                    except Exception as e:
                        response = f"Command failed: {e}"
                        logging.error("Command %s failed: %s", cmd_key, e)
                else:
                    available = ", ".join(sorted(COMMANDS.keys()))
                    response = f"Unknown command: {cmd_key}\nAvailable: {available}"
                reply(token, chat_id, response)
                logging.info("Replied to %s: %s", cmd_key, response[:80])
    finally:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        logging.info("Telegram Commander stopped")


if __name__ == "__main__":
    main()
