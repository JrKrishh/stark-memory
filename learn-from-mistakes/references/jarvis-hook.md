# JARVIS hook — auto-capture every failure

The debrief (SKILL.md step 4) only works if failures are remembered. This hook makes
capture automatic: Claude Code fires `PostToolUseFailure` on every failed tool call,
and the receiver appends shell failures to `~/.claude/mistakes.jsonl`. At debrief
time, run `scripts/lessons.py inbox` to triage.

## Install — add to `~/.claude/settings.json`

Merge this group into the existing `"hooks"` object (don't replace other hooks):

```json
{
  "hooks": {
    "PostToolUseFailure": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "python",
            "args": ["~/.claude/skills/learn-from-mistakes/scripts/jarvis_inbox.py"],
            "timeout": 10,
            "statusMessage": "JARVIS logging failure"
          }
        ]
      }
    ]
  }
}
```

- **Exec form** (`command` + `args`) spawns Python directly, no shell quoting issues.
  On Windows, `command` must resolve to a real `.exe` — `python` does. Replace `~`
  with the absolute path (`C:/Users/<you>/...`) since exec form does not expand it.
- **Keep the hook synchronous** (no `"async": true`): decision-control output
  (`additionalContext`, i.e. the reflex) only reaches Claude from a synchronous
  handler. The script is bounded to stay fast — small log scans, no network,
  no LLM calls in the hot path.
- The matcher limits capture to shell tools; Edit/Write failures are left out on purpose.

## Reflex — the suit corrects mid-fight

On every failed shell command the receiver also scans both lesson logs. When at
least **two distinct meaningful tokens** of the failed command appear in an
entry's title/body, the best-matching lesson is injected into Claude's context:

```
stark-memory reflex — this failure matches logged lesson [2026-08-01] gizmo-deploy wipes ...
Known fix: restored from origin; deployed with --no-purge
Prevention rule: never run bare `gizmo deploy` - always pass --no-purge
```

- Strictness is deliberate: single-token overlaps stay silent. Expect matches on
  the command shape rather than the exact failure mode — that is prevention
  (warn before the destructive run succeeds), not diagnosis.
- Every firing is recorded in the inbox as `{"reflex": true, "lesson": ..., "hits": N}`
  telemetry. Triage reviews these: hits that helped bump the lesson's Saves
  counter; noisy ones tell you to sharpen the entry's wording or add Paths globs.
- No match → silent, exit 0. The hook never blocks longer than its scan.

## What gets recorded

One JSON line per failure: timestamp, project cwd, session id, command, exit code
(parsed from the `Exit code N` first line of the error string), and the first 500
characters of output. Interrupted calls (Esc) and non-shell tools are skipped.
Retries of the *same failure* within 2 minutes are deduplicated (signature:
project + command + exit code + first output line); a retry that fails differently
is kept as a distinct signal. The file self-trims past 400 lines; concurrent
sessions append atomically. Override its location with the `JARVIS_INBOX` env var
(useful for tests).

## Notes

- The inbox is raw telemetry and stays local — it can contain command output, so
  never commit it. Lessons enter `LESSONS.md` only through triage, which is where the
  skill's no-secrets rule is enforced.
- The receiver never crashes the session: any internal error exits 0 silently.
