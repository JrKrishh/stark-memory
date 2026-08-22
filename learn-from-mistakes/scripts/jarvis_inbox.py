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
DEDUP_SECS = 120  # same failure signature within this window -> skip

EXIT_RE = re.compile(r"^Exit code (\d+)")


def signature(entry):
    """What makes two failures 'the same retry loop': project, command, exit
    code, and the first line of output. A flaky command failing differently on
    the retry is a distinct signal, not a duplicate."""
    first = next(iter(str(entry.get("error") or "").splitlines()), "")
    return (entry.get("project"), entry.get("cmd"), entry.get("exit_code"), first[:200])


def _acquire_lock(deadline_s=5.0):
    """Atomic-on-every-OS lock (directory creation). Returns False on timeout;
    callers then fail OPEN so telemetry capture can never stall a session."""
    lock = str(INBOX) + ".lock"
    deadline = time.time() + deadline_s
    while True:
        try:
            os.mkdir(lock)
            return True
        except FileExistsError:
            try:  # a crashed writer left the lock behind -> claim it
                if time.time() - os.stat(lock).st_mtime > 15:
                    os.rmdir(lock)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                return False
            time.sleep(0.02)


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
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    have_lock = _acquire_lock()
    try:
        lines = INBOX.read_text(encoding="utf-8").splitlines() if INBOX.exists() else []
        sig = signature(entry)
        for line in reversed(lines):
            try:
                prev = json.loads(line)
            except ValueError:
                continue
            if signature(prev) == sig:
                if abs(entry["ts"] - prev.get("ts", 0)) < DEDUP_SECS:
                    return  # retry loop of the same failure; one record is enough
                break
        keep = None
        if len(lines) + 1 >= MAX_LINES:
            keep = (lines[-(KEEP_LINES - 1):] + [json.dumps(entry, ensure_ascii=False)])
        if keep is not None:  # trim: rewrite through a temp file
            tmp = str(INBOX) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(keep[-KEEP_LINES:]) + "\n")
            os.replace(tmp, INBOX)
        else:                 # normal path: plain append under the lock
            with open(INBOX, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    finally:
        if have_lock:
            try:
                os.rmdir(str(INBOX) + ".lock")
            except OSError:
                pass


def main():
    try:
        # Claude Code sends UTF-8 JSON; decode explicitly so locale codepages
        # (cp1252 etc.) can't mojibake non-ASCII output before we ever see it.
        data = sys.stdin.buffer.read().decode("utf-8", "replace")
        capture(json.loads(data or "{}"))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
