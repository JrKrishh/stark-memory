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
            "async": true,
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
- **`async: true`** logs in the background so the agentic loop never waits on it.
- The matcher limits capture to shell tools; Edit/Write failures are left out on purpose.

## What gets recorded

One JSON line per failure: timestamp, project cwd, session id, command, exit code
(parsed from the `Exit code N` first line of the error string), and the first 500
characters of output. Interrupted calls (Esc), non-shell tools, and retries of the
same failing command within 2 minutes are skipped. The file self-trims past 400 lines.
Override its location with the `JARVIS_INBOX` env var (useful for tests).

## Notes

- The inbox is raw telemetry and stays local — it can contain command output, so
  never commit it. Lessons enter `LESSONS.md` only through triage, which is where the
  skill's no-secrets rule is enforced.
- The receiver never crashes the session: any internal error exits 0 silently.
