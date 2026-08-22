# The Automation Ladder

A lesson in a log is memory; memory can be missed. When a lesson recurs, or when its
severity is high (data loss, destructive commands, security), graduate it into a
mechanism the machine enforces. Always propose the guard to the user before wiring it
in, and record what was built on the entry's **Automation** line.

Prefer the lowest level that fully kills the failure mode — and remember that
**fixing the root cause at the source beats any guard**: repairing the buggy script
is better than a hook that blocks it.

## Level 2 — Guards in the project

**Fix the source.** If the lesson exists because a script/config is broken, fix or
delete the trap itself. Example: `build.sh` wipes `data/` → remove the bad `rm` line
(or delete `build.sh` and keep only `make build`).

**Validator script.** For "this file keeps getting corrupted by hand-edits" lessons:

```bash
# validate.sh — run after editing configs
python3 -m json.tool settings.json > /dev/null || { echo "settings.json invalid"; exit 1; }
```

**Regression test.** For "this bug came back" lessons, add a test that reproduces the
original failure. The lessons entry then points at the test name.

**Lint rule / pre-commit.** For style- or pattern-shaped mistakes, encode the rule in
the linter config or a pre-commit hook so it's caught before commit.

## Level 3 — Claude Code hooks and CI gates

**PreToolUse hook** — block a known-dangerous command before it runs. In the project's
`.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"import json,sys; d=json.load(sys.stdin); cmd=d.get('tool_input',{}).get('command',''); sys.exit(2 if './build.sh' in cmd else 0)\""
          }
        ]
      }
    ]
  }
}
```

Exit code 2 blocks the tool call and shows the hook's stderr to Claude — print the
lesson's Prevention line there so the block explains itself.

**PostToolUse hook** — validate right after a risky edit (e.g. run the JSON validator
whenever a `.json` file is written).

**CI gate** — add the validator/test to the repository's CI workflow so the mistake
cannot merge, even from contributors who never see the lessons log.

## Choosing a level

| Situation | Graduate to |
|---|---|
| Buggy script/config caused it | Fix the source (best) |
| Mistake corrupts a specific file type | Validator + PostToolUse hook |
| A specific command is destructive | PreToolUse hook blocking it |
| A code bug that regressed once | Regression test |
| Must hold for all contributors | CI gate |

After building a guard, keep the log entry (it explains *why* the guard exists) and
set its **Automation** line, e.g. `Level 3 — PreToolUse hook blocks ./build.sh`.
