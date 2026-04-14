#!/usr/bin/env python3
"""
Stop hook: enforce Telegram reply completeness on the last turn.

Replaces the LLM-judge prompt-type Stop hook with a deterministic check:
- If the turn's user prompts contained a `<channel source="plugin:telegram:telegram"`
  tag AND no `mcp__plugin_telegram_telegram__reply` tool was called anywhere in
  the turn, BLOCK with "missing TG reply".
- If a reply tool was called AND there is trailing text after it, BLOCK with
  "trailing terminal text after TG reply". Trailing text is detected via two
  paths:
    1. stdin `last_assistant_message`: the in-flight final text, populated by
       Claude Code even BEFORE it is flushed to the JSONL transcript. If it
       doesn't match any already-persisted text block in this turn, it is
       post-reply trailing text.
    2. Persisted transcript scan (belt-and-braces): any non-empty text block
       positioned after the last reply tool use, either within the same
       assistant message or in a later one.
- Otherwise PASS.

Turn boundary: walks backwards to the most recent real user prompt (a user
message NOT consisting exclusively of tool_result blocks), then treats all
subsequent user/assistant messages as part of the turn. This correctly handles
multi-message flows where tool_result user messages separate assistant
messages within a single logical turn.

Why deterministic: an LLM-judge can stamp PASS based on an earlier reply-tool
call in the same turn, missing trailing terminal text. This hook does not.

Hook contract (Claude Code Stop hook, command type):
- stdin: JSON with `transcript_path` and optionally `last_assistant_message`
- exit 0: PASS (no objection to stopping)
- exit 2: BLOCK; stderr is surfaced to the model as a system reminder

Defaults to PASS on malformed input or missing transcript, to avoid breaking
the agent loop.
"""

import json
import sys
from pathlib import Path

REPLY_TOOL = "mcp__plugin_telegram_telegram__reply"
TG_CHANNEL_TAG = '<channel source="plugin:telegram:telegram"'


def load_transcript(path):
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    messages = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return messages


def extract_message(entry):
    if "role" in entry and "content" in entry:
        return entry["role"], entry["content"]
    msg = entry.get("message")
    if isinstance(msg, dict) and "role" in msg and "content" in msg:
        return msg["role"], msg["content"]
    return None, None


def content_blocks(content):
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def is_tool_result_only(content):
    blocks = content_blocks(content)
    if not blocks:
        return False
    return all(b.get("type") == "tool_result" for b in blocks)


def find_turn_boundary(messages):
    turn_start = None
    for i in range(len(messages) - 1, -1, -1):
        role, content = extract_message(messages[i])
        if role == "user" and not is_tool_result_only(content):
            turn_start = i
            break
    if turn_start is None:
        return [], []

    user_idxs = []
    assistant_idxs = []
    for k in range(turn_start, len(messages)):
        role, _ = extract_message(messages[k])
        if role == "user":
            user_idxs.append(k)
        elif role == "assistant":
            assistant_idxs.append(k)
    return user_idxs, assistant_idxs


def has_tg_channel_tag(messages, indices):
    for idx in indices:
        _, content = extract_message(messages[idx])
        for block in content_blocks(content):
            if block.get("type") == "text":
                if TG_CHANNEL_TAG in block.get("text", ""):
                    return True
            elif block.get("type") == "tool_result":
                inner = block.get("content", "")
                if isinstance(inner, str) and TG_CHANNEL_TAG in inner:
                    return True
    return False


def reply_tool_indices(content):
    out = []
    for i, block in enumerate(content_blocks(content)):
        if block.get("type") == "tool_use" and block.get("name") == REPLY_TOOL:
            out.append(i)
    return out


def has_trailing_text(content, after_idx):
    blocks = content_blocks(content)
    for i, block in enumerate(blocks):
        if i <= after_idx:
            continue
        if block.get("type") == "text":
            text = block.get("text", "")
            if text and text.strip():
                return True
    return False


BLOCK_NO_REPLY = (
    "BLOCKED: Telegram message received but no mcp__plugin_telegram_telegram__reply "
    "tool call in your response. Terminal output is invisible to the user. "
    "Resend your response via the Telegram reply tool, including chat_id and "
    "(optionally) reply_to from the inbound channel tag."
)

BLOCK_TRAILING_TEXT = (
    "BLOCKED: You wrote terminal text AFTER your final Telegram reply tool call. "
    "That text is invisible to the user. Either fold it into the Telegram reply itself, "
    "or end the turn after the reply call. Status updates between tool calls are fine; "
    "trailing text after the last reply is not."
)


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        sys.exit(0)

    transcript_path = input_data.get("transcript_path", "")
    messages = load_transcript(transcript_path)
    if not messages:
        sys.exit(0)

    turn_user_idxs, turn_assistant_idxs = find_turn_boundary(messages)
    if not turn_user_idxs:
        sys.exit(0)

    tg_arrived = has_tg_channel_tag(messages, turn_user_idxs)

    reply_positions = []
    last_reply_msg_idx = None
    last_reply_block_idx = None
    for a_idx in turn_assistant_idxs:
        _, content = extract_message(messages[a_idx])
        for b_idx in reply_tool_indices(content):
            reply_positions.append((a_idx, b_idx))
            last_reply_msg_idx = a_idx
            last_reply_block_idx = b_idx

    if tg_arrived and not reply_positions:
        print(BLOCK_NO_REPLY, file=sys.stderr)
        sys.exit(2)

    last_assistant_message = (input_data.get("last_assistant_message") or "").strip()
    if reply_positions and last_assistant_message:
        already_in_transcript = False
        for a_idx in turn_assistant_idxs:
            _, content = extract_message(messages[a_idx])
            for block in content_blocks(content):
                if block.get("type") == "text" and block.get("text", "").strip() == last_assistant_message:
                    already_in_transcript = True
                    break
            if already_in_transcript:
                break
        if not already_in_transcript:
            print(BLOCK_TRAILING_TEXT, file=sys.stderr)
            sys.exit(2)

    if reply_positions:
        for a_idx in turn_assistant_idxs:
            _, content = extract_message(messages[a_idx])
            if a_idx < last_reply_msg_idx:
                continue
            threshold = last_reply_block_idx if a_idx == last_reply_msg_idx else -1
            if has_trailing_text(content, threshold):
                print(BLOCK_TRAILING_TEXT, file=sys.stderr)
                sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
