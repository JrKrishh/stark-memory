#!/usr/bin/env python3
"""JARVIS inbox — PostToolUseFailure hook for learn-from-mistakes.

Two duties, one fast synchronous call:

1. CAPTURE — append shell failures (Bash/PowerShell) to ~/.claude/mistakes.jsonl:
       {"ts": ..., "project": cwd, "session": id, "tool": "Bash",
        "cmd": "...", "exit_code": N, "error": "first 500 chars"}
   The debrief triages this inbox into LESSONS.md (`lessons.py inbox`).

2. REFLEX — scan the lesson logs for a match to this exact failure; on a strong
   one, emit hookSpecificOutput.additionalContext so Claude sees the logged fix
   immediately instead of debugging from scratch. Strictness rules keep false
   positives near zero: at least two distinct command tokens must appear in the
   entry text, only the best entry fires, output is capped. Every firing is
   recorded as {"reflex": true, "lesson": ...} telemetry for tuning.

Contract notes (hooks reference): the failure detail is a single freeform
`error` string whose first line is conventionally "Exit code N" with stdout+
stderr interleaved below; there is no structured stderr/exit_code field.
Interrupted calls (user pressed Esc) are not mistakes and are skipped.

This script must never disturb the session: it swallows every error and
always exits 0. The inbox stays local; never commit it.
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
STOPWORDS = {"powershell", "bash", "pwsh", "python", "python3", "node",
             "npm", "npx", "git", "echo", "sudo", "cmd", "exit", "code"}
MIN_HITS = 2      # distinct command tokens that must appear in an entry to fire


def _tokens(cmd):
    """Meaningful tokens: whole chunks (build.sh survives as one token) plus
    their alphanumeric parts. Short flags (--all) are noise by design."""
    out = set()
    for chunk in re.split(r"\s+", cmd):
        c = chunk.strip("`'\"(),;|&").lstrip("./-").lower()
        if len(c) >= 4 and c not in STOPWORDS:
            out.add(c)
            for part in re.split(r"[^a-zA-Z0-9_]+", c):
                if len(part) >= 4 and part not in STOPWORDS:
                    out.add(part)
    return out


def _failure_text(L, e):
    """The failure-description side of an entry (title, trigger, what happened,
    root cause) — deliberately EXCLUDING Fix/Prevention, whose job is to name
    the SAFE alternative. Without this, 'never run bare build.sh - use make
    build' makes the shield block 'make build' itself."""
    t = " ".join([e["title"], L.field(e, "Trigger"), L.field(e, "What happened"),
                  L.field(e, "Root cause")]).strip()
    return t if len(t) >= 25 else e["title"] + " " + e["body"]


def _best_match(toks):
    """Best lesson whose failure-side text contains >=MIN_HITS command tokens.
    Returns (entry, hits) or (None, 0). Strict on purpose."""
    try:
        import lessons as L  # sibling module in scripts/
    except Exception:
        return None, 0
    try:
        best, best_hits = None, 0
        for scope, path in L.find_logs():
            for e in L.parse_entries(path):
                text = _failure_text(L, e).lower()
                hits = sum(1 for t in toks if t in text)
                if hits > best_hits:
                    best, best_hits = e, hits
        return (best, best_hits) if best and best_hits >= MIN_HITS else (None, 0)
    except Exception:
        return None, 0


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


def _store(entry, dedup=True):
    """Append one event line under the lock; trim when over cap.
    Returns False if a same-signature entry was recorded recently."""
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    have_lock = _acquire_lock()
    try:
        lines = INBOX.read_text(encoding="utf-8").splitlines() if INBOX.exists() else []
        if dedup:
            sig = signature(entry)
            for line in reversed(lines):
                try:
                    prev = json.loads(line)
                except ValueError:
                    continue
                if signature(prev) == sig:
                    if abs(entry["ts"] - prev.get("ts", 0)) < DEDUP_SECS:
                        return False  # retry loop of the same failure
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
        return True
    except OSError:
        return True
    finally:
        if have_lock:
            try:
                os.rmdir(str(INBOX) + ".lock")
            except OSError:
                pass


def capture(payload):
    """Store the failure. Returns (cmd, err) for the reflex stage."""
    if payload.get("is_interrupt"):
        return None, ""  # user aborted; not a mistake
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return None, ""  # non-shell failure or no command to learn from
    err = str(payload.get("error") or "")
    m = EXIT_RE.match(err)
    _store({
        "ts": int(time.time()),
        "project": payload.get("cwd") or os.getcwd(),
        "session": payload.get("session_id") or "",
        "cmd": cmd[:300],
        "exit_code": int(m.group(1)) if m else None,
        "error": err[:TAIL],
    })
    return cmd, err


def reflex(cmd, project_dir):
    """Match this failure against the lesson logs; return injection text or None."""
    best, hits = _best_match(_tokens(cmd))
    if not best:
        return None
    try:
        import lessons as L
        parts = [f"stark-memory reflex — this failure matches logged lesson [{best['date']}] {best['title']}"]
        prevention = L.field(best, "Prevention")
        fix = L.field(best, "Fix")
        if fix:
            parts.append(f"Known fix: {fix[:300]}")
        if prevention:
            parts.append(f"Prevention rule: {prevention[:300]}")
        _store({"ts": int(time.time()), "project": project_dir,
                "reflex": True, "lesson": best["title"], "hits": hits}, dedup=False)
        return "\n".join(parts)[:800]
    except Exception:
        return None


def _paths_in_scope(globs):
    """True when at least one FILE under cwd matches the entry's Paths globs.
    (py3.8 quirk: 'dir/**' also yields the bare directory, so match files only.)
    Bounded walk; fail-open on glob trouble so unverifiable scope keeps old
    behavior."""
    import glob as gmod
    import itertools
    for pat in globs:
        try:
            for hit in itertools.islice(gmod.iglob(pat, recursive=True), 50):
                if os.path.isfile(hit):
                    return True
        except Exception:
            return True
    return False


def _toast(title, msg):
    """Fire-and-forget OS toast on critical events (Windows only). Never blocks
    the hook: detached spawn, no wait, all failures swallowed."""
    if os.name != "nt" or os.environ.get("STARK_TOAST") == "0":
        return
    try:
        import subprocess
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "toast.ps1")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-File", script, title, msg[:220]],
            creationflags=0x00000008)  # DETACHED_PROCESS
    except Exception:
        pass


AUTO_MODES = {"auto", "dontAsk", "bypassPermissions"}


def shield(cmd, project_dir, mode="default"):
    """Pre-execution guard over Severity:high lessons. Returns decision text or None.

    Interactive modes -> 'ask' (human confirms with the lesson in view).
    Auto modes (auto/dontAsk/bypassPermissions) -> 'deny' automatically: there is
    no human to confirm, so the suit refuses and hands Claude the prevention rule
    to reroute with — autonomous AND safe. STARK_SHIELD_AUTO=allow stands the
    guard down in auto modes (still logged + toasted)."""
    try:
        import lessons as L
    except Exception:
        return None
    best, hits = _best_match(_tokens(cmd))
    if not best:
        return None
    try:
        if not L.field(best, "Severity").lower().startswith("high"):
            return None  # medium/low stay advisory territory (reflex handles them)
        globs = [g.strip() for g in re.split(r"[,\s]+", L.field(best, "Paths")) if g.strip()]
        if globs and not _paths_in_scope(globs):
            return None  # scoped lesson, wrong neighborhood: shape match alone isn't enough
        auto = mode in AUTO_MODES
        if auto and os.environ.get("STARK_SHIELD_AUTO", "deny") == "allow":
            _store({"ts": int(time.time()), "project": project_dir, "shield": True,
                    "lesson": best["title"], "hits": hits, "mode": mode,
                    "decision": "allowed"})
            _toast("stark-memory shield (allowed)", f"{cmd[:90]}\n{best['title']}")
            return None  # stand-down mode: logged and toasted, but not blocked
        if auto:
            head = ("stark-memory shield — BLOCKED automatically (auto mode, no human "
                    "to confirm). This command matches HIGH severity lesson "
                    f"[{best['date']}] {best['title']}.")
            tail = (" Do NOT retry the same command. Follow the prevention above or "
                    "propose a safer alternative.")
            decision = "deny"
        else:
            head = (f"stark-memory shield — this command matches HIGH severity lesson "
                    f"[{best['date']}] {best['title']}.")
            tail = " Confirm only if this is intentional."
            decision = "ask"
        prevention = L.field(best, "Prevention")[:250] or "see lesson"
        reason = f"{head} Prevention: {prevention}.{tail}"
        _store({"ts": int(time.time()), "project": project_dir, "shield": True,
                "lesson": best["title"], "hits": hits, "mode": mode,
                "decision": decision}, dedup=False)
        _toast("stark-memory shield",
               f"{decision}: {cmd[:80]}\n{best['title']}")
        return json.dumps({"decision": decision, "reason": reason[:600]})
    except Exception:
        return None


def main():
    try:
        # Claude Code sends UTF-8 JSON; decode explicitly so locale codepages
        # (cp1252 etc.) can't mojibake non-ASCII output before we ever see it.
        data = sys.stdin.buffer.read().decode("utf-8", "replace")
        payload = json.loads(data or "{}")
        cwd = payload.get("cwd")
        if cwd and os.path.isdir(cwd):
            try:
                os.chdir(cwd)  # lesson logs resolve relative to the session project
            except OSError:
                pass
        if payload.get("hook_event_name") == "PreToolUse":
            cmd = (payload.get("tool_input") or {}).get("command") or ""
            res = shield(cmd, cwd, payload.get("permission_mode") or "default") if cmd else None
            if res:
                d = json.loads(res)
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": d["decision"],
                    "permissionDecisionReason": d["reason"]}}))
            return 0
        cmd, _err = capture(payload)
        msg = reflex(cmd, cwd) if cmd else None
        if msg:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUseFailure",
                "additionalContext": msg}}))
    except Exception:
        if os.environ.get("JARVIS_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
