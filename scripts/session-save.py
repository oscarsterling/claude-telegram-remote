#!/usr/bin/env python3
"""Save a compressed context brief of the current Claude Code session."""
import json, os, sys, glob, subprocess, datetime, re

# === CONFIGURE THESE ===
# Auto-detect the Claude projects directory. Override if your layout differs.
PROJECTS_DIR = ""  # Leave empty for auto-detect, or set to your .claude/projects/... path
SAVE_DIR = os.path.expanduser("~/claude-telegram-remote/saved-contexts")
# =======================

SESSIONS_DIR = os.path.expanduser("~/.claude/sessions")


def _detect_projects_dir():
    """Auto-detect the Claude Code projects directory for the current working directory."""
    if PROJECTS_DIR:
        return PROJECTS_DIR
    # Claude Code stores session JSONL files under ~/.claude/projects/-<escaped-path>/
    cwd = os.getcwd()
    escaped = cwd.replace("/", "-")
    candidate = os.path.expanduser(f"~/.claude/projects/{escaped}")
    if os.path.isdir(candidate):
        return candidate
    # Fallback: find the most recently modified projects subdirectory
    projects_base = os.path.expanduser("~/.claude/projects")
    if os.path.isdir(projects_base):
        subdirs = [os.path.join(projects_base, d) for d in os.listdir(projects_base)
                    if os.path.isdir(os.path.join(projects_base, d))]
        if subdirs:
            return max(subdirs, key=os.path.getmtime)
    return ""


def get_active_session_id():
    """Find the most recent session ID from ~/.claude/sessions/."""
    files = sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.json")),
                   key=os.path.getmtime, reverse=True)
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
                if data.get("sessionId"):
                    return data["sessionId"]
        except Exception:
            continue
    return None


def find_session_jsonl(session_id, projects_dir):
    """Find the JSONL file for a given session ID."""
    path = os.path.join(projects_dir, f"{session_id}.jsonl")
    if os.path.exists(path):
        return path
    # Fallback: most recently modified JSONL
    files = sorted(glob.glob(os.path.join(projects_dir, "*.jsonl")),
                   key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def parse_session(jsonl_path, max_lines=800):
    """Parse session JSONL for meaningful context data."""
    with open(jsonl_path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        read_size = min(size, 3 * 1024 * 1024)
        f.seek(size - read_size)
        tail = f.read().decode("utf-8", errors="replace")

    lines = tail.strip().split("\n")
    if len(lines) > max_lines:
        lines = lines[-max_lines:]

    telegram_replies = []     # What the assistant said via Telegram
    user_requests = []        # What the user asked for
    files_modified = []       # Files written/edited
    git_commits = []          # Commit messages
    tools_used = set()        # Unique tool names
    topics = []               # Extracted topic keywords

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        entry_type = entry.get("type")

        # Extract Telegram replies (the actual conversation)
        if entry_type == "assistant":
            msg = entry.get("message", {})
            content_list = msg.get("content", [])
            if not isinstance(content_list, list):
                continue
            for block in content_list:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    if name == "mcp__plugin_telegram_telegram__reply":
                        text = inp.get("text", "")
                        if text and len(text) > 20:
                            telegram_replies.append(text[:400])
                    elif name in ("Write", "Edit"):
                        fp = inp.get("file_path", "")
                        if fp and fp not in files_modified:
                            files_modified.append(fp)
                    elif name == "Bash":
                        cmd = inp.get("command", "")
                        if "git commit" in cmd:
                            m = re.search(r'-m\s+"([^"]+)"', cmd)
                            if m:
                                git_commits.append(m.group(1)[:120])
                        tools_used.add("Bash")
                    elif name == "Agent":
                        desc = inp.get("description", "")
                        if desc:
                            tools_used.add(f"Agent({desc})")
                    elif name not in ("Read", "Glob", "Grep", "ToolSearch"):
                        tools_used.add(name)
                elif block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text and len(text) > 30 and not text.startswith("Waiting"):
                        topics.append(text[:200])

        # User messages (requests)
        if entry_type == "user":
            msg = entry.get("message", {})
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                tg_match = re.search(r'<channel[^>]*>(.*?)</channel>', content, re.DOTALL)
                if tg_match:
                    tg_text = tg_match.group(1).strip()
                    if tg_text and len(tg_text) > 5:
                        user_requests.append(tg_text[:300])
                elif not content.startswith("<") and not content.startswith("[{"):
                    if len(content) > 10:
                        user_requests.append(content[:300])

    return {
        "telegram_replies": telegram_replies[-30:],
        "user_requests": user_requests[-30:],
        "files_modified": files_modified,
        "git_commits": git_commits,
        "tools_used": sorted(tools_used)[:15],
        "topics": topics[-10:],
    }


def build_summary(parsed_data):
    """Build a structured summary from parsed session data."""
    sections = []

    # What we were working on
    sections.append("## What we worked on")
    work_items = set()
    for r in parsed_data["telegram_replies"]:
        if any(kw in r.lower() for kw in ["fixed", "built", "added", "created", "updated", "removed", "wired"]):
            first_sentence = r.split(".")[0].split("\n")[0]
            if len(first_sentence) > 15:
                work_items.add(first_sentence[:150])
    if work_items:
        for item in list(work_items)[-5:]:
            sections.append(f"- {item}")
    elif parsed_data["git_commits"]:
        for c in parsed_data["git_commits"][-3:]:
            sections.append(f"- {c}")
    else:
        sections.append("- (no clear work items extracted)")

    # Key exchanges
    sections.append("")
    sections.append("## Key exchanges")
    exchanges = []
    requests = parsed_data["user_requests"][-10:]
    for req in requests[-5:]:
        short = req.split("\n")[0][:120]
        if len(short) > 10:
            exchanges.append(f"- User: {short}")
    if exchanges:
        sections.extend(exchanges[-5:])
    else:
        sections.append("- (no exchanges captured)")

    # Files changed
    if parsed_data["files_modified"]:
        sections.append("")
        sections.append("## Files changed")
        home = os.path.expanduser("~")
        for f in parsed_data["files_modified"][:10]:
            short = f.replace(home, "~")
            sections.append(f"- {short}")

    # Git commits
    if parsed_data["git_commits"]:
        sections.append("")
        sections.append("## Commits")
        for c in parsed_data["git_commits"][-5:]:
            sections.append(f"- {c}")

    # Where we left off
    sections.append("")
    sections.append("## Where we left off")
    if parsed_data["user_requests"]:
        last = parsed_data["user_requests"][-1].split("\n")[0][:200]
        sections.append(f"Last from user: {last}")
    if parsed_data["telegram_replies"]:
        last = parsed_data["telegram_replies"][-1].split("\n")[0][:200]
        sections.append(f"Last from assistant: {last}")

    return "\n".join(sections)


def main():
    if len(sys.argv) < 2:
        print("Usage: session-save.py <label>")
        sys.exit(1)

    label = sys.argv[1].strip().replace(" ", "-").lower()
    os.makedirs(SAVE_DIR, exist_ok=True)

    projects_dir = _detect_projects_dir()
    if not projects_dir:
        print("ERROR: Could not detect Claude Code projects directory.")
        print("Set PROJECTS_DIR at the top of session-save.py.")
        sys.exit(1)

    # Use most recently modified JSONL as the active session
    jsonl_files = sorted(glob.glob(os.path.join(projects_dir, "*.jsonl")),
                         key=os.path.getmtime, reverse=True)
    if not jsonl_files:
        print("ERROR: No session JSONL files found")
        sys.exit(1)
    jsonl_path = jsonl_files[0]
    session_id = os.path.basename(jsonl_path).replace(".jsonl", "")

    parsed = parse_session(jsonl_path)
    summary = build_summary(parsed)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# Session Save: {label}\n**Saved:** {now} | **Session:** {session_id[:8]}\n\n"
    content = header + summary + "\n"

    save_path = os.path.join(SAVE_DIR, f"{label}.md")
    with open(save_path, "w") as f:
        f.write(content)

    print(f"Saved '{label}' ({len(content)} chars, {len(parsed['telegram_replies'])} TG replies, {len(parsed['files_modified'])} files)")


if __name__ == "__main__":
    main()
