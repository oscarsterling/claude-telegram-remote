#!/usr/bin/env python3
"""Telegram Commander - Remote control Claude Code via ! commands from Telegram."""
import inspect
import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

# === CONFIGURE THESE ===
YOUR_USER_ID = 0  # Your Telegram user ID (get it from @userinfobot)
TMUX_SESSION = "claude"  # Your tmux session name where Claude Code runs
TMUX_PATH = "/opt/homebrew/bin/tmux"  # `which tmux` to find yours
RESTART_SCRIPT = ""  # Optional: absolute path to your restart script (leave "" to disable !restart)
HEALTH_SCRIPT = ""  # Optional: absolute path to a health-check script (leave "" to disable !health)
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


def send_buttons(token, chat_id, text, buttons_json):
    """Send a message with inline keyboard buttons via the Commander bot itself."""
    telegram_api(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"inline_keyboard": buttons_json}
    })


def find_claude_pid():
    r = subprocess.run(["pgrep", "-f", "claude.*--channels"], capture_output=True, text=True)
    pids = r.stdout.strip().split("\n") if r.stdout.strip() else []
    return pids[0] if pids and pids[0] else None


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
    """Restart Claude Code session via RESTART_SCRIPT.

    Advanced: for a wake-ping after manual !restart, have this function also
    write a "manual flag" file, and have your restart script check for it
    after verifying the new session is ready. If present, sleep ~10s, inject
    a wake-prompt into tmux, delete the flag. Nightly/scheduled restarts
    skip the flag write → they stay silent. See README "Advanced: Wake-Ping".
    """
    if not RESTART_SCRIPT:
        return "No RESTART_SCRIPT configured. Set RESTART_SCRIPT in telegram-commander.py."
    try:
        # Optional: mark this as a manual restart so the script can wake-ping.
        # manual_flag = os.path.expanduser("~/claude-telegram-remote/restart-manual-flag")
        # with open(manual_flag, "w") as f: f.write(str(time.time()))
        subprocess.Popen(["bash", RESTART_SCRIPT],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Session restarting. Give it 30 seconds."
    except Exception as e:
        return f"Restart failed: {e}"


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
            for line in reversed(r.stdout.strip().split("\n")):
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


def _no_session_msg():
    return f"No tmux session '{TMUX_SESSION}' found. Is Claude running in tmux?"


def cmd_plan():
    result = inject_slash_command("/plan")
    if result == "sent":
        return "Sent /plan."
    if result == "no_session":
        return _no_session_msg()
    return f"Failed: {result}"


def cmd_mode():
    result = inject_key("BTab")
    if result == "sent":
        time.sleep(0.5)
        mode = read_current_mode()
        return f"Cycled mode (Shift+Tab). Current: {mode}"
    if result == "no_session":
        return _no_session_msg()
    return f"Failed: {result}"


def cmd_compact():
    result = inject_slash_command("/compact")
    if result == "sent":
        return "Sent /compact."
    if result == "no_session":
        return _no_session_msg()
    return f"Failed: {result}"


def cmd_clear():
    result = inject_slash_command("/clear")
    if result == "sent":
        return "Sent /clear. Fresh conversation."
    if result == "no_session":
        return _no_session_msg()
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
        return _no_session_msg()
    return f"Failed: {result}"


def cmd_opus():
    result = inject_slash_command("/model default")
    if result == "sent":
        return "Switched to Opus (1M context)."
    if result == "no_session":
        return _no_session_msg()
    return f"Failed: {result}"


def cmd_sonnet():
    result = inject_slash_command("/model sonnet")
    if result == "sent":
        return "Switched to Sonnet."
    if result == "no_session":
        return _no_session_msg()
    return f"Failed: {result}"


def cmd_cost():
    result = inject_slash_command("/cost")
    if result == "sent":
        return "Sent /cost."
    if result == "no_session":
        return _no_session_msg()
    return f"Failed: {result}"


def cmd_context():
    """Scrape Claude Code status line from tmux pane. No Claude turn burned."""
    import re
    try:
        r = subprocess.run(
            [TMUX_PATH, "capture-pane", "-t", TMUX_SESSION, "-p"],
            capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return _no_session_msg()
        lines = r.stdout.split("\n")
        model_re = re.compile(r"(Opus|Sonnet|Haiku)\s+[\d.]+", re.IGNORECASE)
        pct_re = re.compile(r"(\d+)%\s*(\d+[KM])")
        model_line = ctx_line = ""
        for idx, line in enumerate(lines):
            if model_re.search(line):
                model_line = line.strip()
                if idx + 1 < len(lines):
                    ctx_line = lines[idx + 1].strip()
                break
        if not model_line:
            return "Status line not found in pane. Is Claude CLI running?"
        model_m = model_re.search(model_line)
        model = model_line[model_m.start():].split("|")[0].strip()
        model = re.sub(r"[^\w\s().]", "", model).strip()
        pct_m = pct_re.search(ctx_line)
        if pct_m:
            pct, window = pct_m.group(1), pct_m.group(2)
            return f"{model} | {pct}% of {window} context used"
        window_m = re.search(r"\((\d+[KM])\s*context\)", model)
        window = window_m.group(1) if window_m else "?"
        return f"{model} | 0% of {window} context used"
    except subprocess.TimeoutExpired:
        return "tmux capture-pane timed out."
    except Exception as e:
        return f"Context check failed: {e}"


def cmd_effort(args=""):
    level = args.strip().lower() if args else ""
    valid_levels = {"max", "high", "medium", "auto"}
    if level in valid_levels:
        result = inject_slash_command(f"/effort {level}")
        if result == "sent":
            return f"Set effort to {level}."
        if result == "no_session":
            return _no_session_msg()
        return f"Failed: {result}"
    return "picker"


def cmd_health():
    if not HEALTH_SCRIPT:
        return "No HEALTH_SCRIPT configured. Set HEALTH_SCRIPT in telegram-commander.py."
    try:
        r = subprocess.run(
            ["bash", HEALTH_SCRIPT, "check", "--quiet"],
            capture_output=True, text=True, timeout=30)
        output = r.stdout.strip()
        if not output:
            return "All systems healthy."
        return output
    except subprocess.TimeoutExpired:
        return "Health check timed out."
    except Exception as e:
        return f"Health check failed: {e}"


COMMANDS = {
    "!ping": cmd_ping, "!status": cmd_status, "!stop": cmd_stop,
    "!restart": cmd_restart, "!reset": cmd_restart,
    "!plan": cmd_plan, "!mode": cmd_mode, "!compact": cmd_compact,
    "!clear": cmd_clear, "!model": cmd_model,
    "!opus": cmd_opus, "!sonnet": cmd_sonnet,
    "!effort": cmd_effort, "!health": cmd_health, "!cost": cmd_cost,
    "!context": cmd_context,
}


# Descriptions for Telegram's in-chat command menu (the "/" picker).
# Telegram requires a leading "/" not "!", so we register the ! aliases
# by stripping the prefix. Stored via setMyCommands.
COMMAND_DESCRIPTIONS = [
    ("ping", "Liveness check"),
    ("context", "Show model + context % used (no turn burned)"),
    ("restart", "Restart Claude Code session"),
    ("health", "System health check"),
    ("cost", "Show session cost"),
    ("mode", "Cycle permission mode"),
    ("effort", "Pick reasoning effort"),
    ("model", "Switch model"),
    ("opus", "Switch to Opus"),
    ("sonnet", "Switch to Sonnet"),
    ("plan", "Enter plan mode"),
    ("compact", "Compact the conversation"),
    ("clear", "Clear the conversation"),
    ("status", "Daemon status"),
    ("stop", "Stop the daemon"),
]


def register_bot_commands(token):
    """Register slash-commands in Telegram's UI picker via setMyCommands."""
    try:
        commands = [{"command": c, "description": d} for c, d in COMMAND_DESCRIPTIONS]
        result = telegram_api(token, "setMyCommands", {"commands": commands})
        if result and result.get("ok"):
            logging.info("Registered %d slash-commands in Telegram UI", len(commands))
        else:
            logging.warning("setMyCommands failed: %s", result)
    except Exception as e:
        logging.warning("setMyCommands exception: %s", e)


def handle_signal(signum, frame):
    global running
    logging.info("Received signal %d, shutting down", signum)
    running = False


def main():
    if YOUR_USER_ID == 0:
        sys.stderr.write("ERROR: Set YOUR_USER_ID at the top of telegram-commander.py.\n")
        sys.exit(1)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    logging.info("Telegram Commander starting")
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    token = get_bot_token()
    register_bot_commands(token)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    logging.info("Daemon started, PID %d", os.getpid())
    last_update_id = 0

    try:
        while running:
            result = telegram_api(token, "getUpdates", {
                "offset": last_update_id + 1,
                "timeout": POLL_TIMEOUT,
                "allowed_updates": ["message", "callback_query"]
            })
            if result is None or not result.get("ok"):
                logging.warning("API issue, retrying in %ds: %s", RETRY_DELAY, result)
                time.sleep(RETRY_DELAY)
                continue

            for update in result.get("result", []):
                update_id = update["update_id"]
                last_update_id = max(last_update_id, update_id)

                cb = update.get("callback_query")
                if cb:
                    cb_id = cb["id"]
                    data = cb.get("data", "")
                    cb_chat_id = cb.get("message", {}).get("chat", {}).get("id", 0)
                    cb_msg_id = cb.get("message", {}).get("message_id", 0)
                    cb_user_id = cb.get("from", {}).get("id", 0)
                    if cb_user_id == YOUR_USER_ID and data.startswith("effort:"):
                        level = data.split(":", 1)[1]
                        tmux_result = inject_slash_command(f"/effort {level}")
                        if tmux_result == "sent":
                            telegram_api(token, "answerCallbackQuery", {
                                "callback_query_id": cb_id,
                                "text": f"Effort set to {level}"
                            })
                            telegram_api(token, "editMessageText", {
                                "chat_id": cb_chat_id,
                                "message_id": cb_msg_id,
                                "text": f"Effort: {level}"
                            })
                        else:
                            telegram_api(token, "answerCallbackQuery", {
                                "callback_query_id": cb_id,
                                "text": f"Failed: {tmux_result}"
                            })
                        logging.info("Callback effort:%s -> %s", level, tmux_result)
                    else:
                        telegram_api(token, "answerCallbackQuery", {"callback_query_id": cb_id})
                    continue

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

                if response == "picker":
                    try:
                        send_buttons(token, chat_id, "Set effort level:", [
                            [{"text": "Max", "callback_data": "effort:max"},
                             {"text": "High", "callback_data": "effort:high"}],
                            [{"text": "Medium", "callback_data": "effort:medium"},
                             {"text": "Auto", "callback_data": "effort:auto"}]
                        ])
                    except Exception as e:
                        reply(token, chat_id, f"Button send failed: {e}")
                else:
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
