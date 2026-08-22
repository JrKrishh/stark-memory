#!/usr/bin/env python3
"""JARVIS inbox — PostToolUseFailure hook for learn-from-mistakes.

Claude Code fires this on every failed tool call. We append shell failures
(Bash/PowerShell) to ~/.claude/mistakes.jsonl as one JSON line per event:

    {"ts": ..., "project": cwd, "session": id, "tool": "Bash",
     "cmd": "...", "exit_code": N, "error": "first 500 chars"}

The debrief then triages this inbox into LESSONS.md entries
(`lessons.py inbox`) instead of relying on memory.

Contract notes (hooks reference): the failure detail is a single freeform
`error` string whose first line is conventionally "Exit code N" with stdout+
stderr interleaved below; there is no structured stderr/exit_code field.
Interrupted calls (user pressed Esc) are not mistakes and are skipped.

This script must never disturb the session: it swallows every error and
always exits 0, silently. The inbox stays local; never commit it (it may
contain command output).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

INBOX = Path(os.environ.get("JARVIS_INBOX") or Path.home() / ".claude" / "mistakes.jsonl")
MAX_LINES = 400   # when exceeded ...
KEEP_LINES = 200  # ... keep only this many newest
TAIL = 500        # chars of the error string kept per entry
DEDUP_SECS = 120  # same project+cmd+exit within this window -> skip

EXIT_RE = re.compile(r"^Exit code (\d+)")


def capture(payload):
    if payload.get("is_interrupt"):
        return  # user aborted; not a mistake
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return  # non-shell failure or no command to learn from
    err = str(payload.get("error") or "")
    m = EXIT_RE.match(err)
    entry = {
        "ts": int(time.time()),
        "project": payload.get("cwd") or os.getcwd(),
        "session": payload.get("session_id") or "",
        "cmd": cmd[:300],
        "exit_code": int(m.group(1)) if m else None,
        "error": err[:TAIL],
    }
    lines = INBOX.read_text(encoding="utf-8").splitlines() if INBOX.exists() else []
    for line in reversed(lines):
        try:
            prev = json.loads(line)
        except ValueError:
            continue
        if prev.get("project") == entry["project"] and prev.get("cmd") == entry["cmd"]:
            if abs(entry["ts"] - prev.get("ts", 0)) < DEDUP_SECS:
                return  # retry loop of the same failure; one record is enough
            break
    lines.append(json.dumps(entry, ensure_ascii=False))
    if len(lines) >= MAX_LINES:
        lines = lines[-KEEP_LINES:]
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    INBOX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    try:
        capture(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
