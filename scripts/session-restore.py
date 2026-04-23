#!/usr/bin/env python3
"""Restore a saved session context brief."""
import os, re, sys

SAVE_DIR = os.path.expanduser("~/claude-telegram-remote/saved-contexts")

# Labels are exact-or-substring matched against filenames in SAVE_DIR.
# Restrict to plain alnum + underscore + hyphen so a caller cannot pass
# `../somewhere` or `.hidden` and reach outside SAVE_DIR.
LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def main():
    if len(sys.argv) < 2:
        print("Usage: session-restore.py <label>")
        sys.exit(1)

    label = sys.argv[1].strip().replace(" ", "-").lower()
    if not LABEL_RE.match(label):
        print(f"ERROR: invalid label {label!r}. Use [a-z0-9_-] only, no path separators.")
        sys.exit(2)
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
