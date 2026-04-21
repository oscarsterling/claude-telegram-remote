#!/usr/bin/env python3
"""Restore a saved session context brief."""
import os, sys

SAVE_DIR = os.path.expanduser("~/claude-telegram-remote/saved-contexts")


def main():
    if len(sys.argv) < 2:
        print("Usage: session-restore.py <label>")
        sys.exit(1)

    label = sys.argv[1].strip().replace(" ", "-").lower()
    save_path = os.path.join(SAVE_DIR, f"{label}.md")

    if not os.path.exists(save_path):
        # Try partial match
        if not os.path.isdir(SAVE_DIR):
            print(f"No saved context found for '{label}'")
            sys.exit(1)
        matches = [f for f in os.listdir(SAVE_DIR) if label in f and f.endswith(".md")]
        if len(matches) == 1:
            save_path = os.path.join(SAVE_DIR, matches[0])
        elif len(matches) > 1:
            print(f"Multiple matches: {', '.join(m.replace('.md','') for m in matches)}")
            sys.exit(1)
        else:
            print(f"No saved context found for '{label}'")
            sys.exit(1)

    with open(save_path) as f:
        content = f.read()

    # Output the brief for injection
    print(content)


if __name__ == "__main__":
    main()
