# Session-Start Auto-Consult

Consulting the log shouldn't depend on remembering to consult the log. A
`SessionStart` hook injects the lessons into context automatically at the start of
every Claude Code session, so every session boots already knowing the project's scars.

Offer this to the user once per project (don't install hooks silently — settings
changes should be theirs to approve). Add to the project's `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh -c 'for f in .claude/LESSONS.md \"$HOME/.claude/LESSONS.md\"; do [ -f \"$f\" ] && { echo \"=== Lessons log: $f ===\"; cat \"$f\"; }; done; true'"
          }
        ]
      }
    ]
  }
}
```

Notes:
- The hook's stdout is added to Claude's context at session start; both the project
  and global logs are included when present, and the command exits cleanly when
  neither exists.
- If the logs grow large, switch the `cat` to `head -c 4000` per file, or print only
  entry titles (`grep -h '^### '`) and let Claude fetch details with
  `scripts/lessons.py search` when a title looks relevant — context is a budget.
- User-level alternative: put the same hook in `~/.claude/settings.json` to get the
  global log in every project, even ones without a project log.
