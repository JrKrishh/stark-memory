#!/usr/bin/env python3
"""Prompt copilot — UserPromptSubmit hook for stark-memory.

OFF by default: only activates when STARK_COPILOT=1 is set in the environment
(each firing spends one inner Claude Code call — deliberately opt-in).

When a user submits a prompt, this:
  1. bails instantly if disabled, or if WE are the inner call (recursion guard),
  2. throttles itself to one suggestion per 90s (stamp file),
  3. skips long prompts (>=300 chars are already thoughtful),
  4. spawns `lessons.py copilot --suggest` -> inner `claude -p` (no external
     APIs, pure Claude Code), and
  5. returns additionalContext so the user sees the improved prompt BEFORE
     Claude answers.

Never blocks: every failure exits 0 silently.
"""
import json
import os
import subprocess
import sys
import time

THROTTLE = os.path.expanduser("~/.claude/stark-cache/copilot.throttle")
MIN_CHARS = 10
MAX_CHARS = 300
THROTTLE_SECS = 90


def main():
    if not os.environ.get("STARK_COPILOT"):
        return 0  # opt-in feature; zero cost when off
    if os.environ.get("STARK_COPILOT_INNER"):
        return 0  # the inner claude -p must never suggest recursively
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    except Exception:
        return 0
    prompt = (payload.get("prompt") or "").strip()
    if not (MIN_CHARS <= len(prompt) <= MAX_CHARS):
        return 0
    try:
        if time.time() - os.stat(THROTTLE).st_mtime < THROTTLE_SECS:
            return 0
    except OSError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        p = subprocess.run(
            [sys.executable, os.path.join(here, "lessons.py"), "copilot",
             "--suggest", "--prompt", prompt, "--json"],
            capture_output=True, timeout=55)
        out = p.stdout.decode("utf-8", "replace")
        suggestion = json.loads(out).get("suggestion", "")
    except Exception:
        return 0
    if not suggestion:
        return 0
    try:
        os.makedirs(os.path.dirname(THROTTLE), exist_ok=True)
        with open(THROTTLE, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except OSError:
        pass
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "stark-memory copilot — a stronger phrasing of your "
                             "request for THIS project:\n\n" + suggestion[:600]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
