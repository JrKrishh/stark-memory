# projektkode

Home of the **learn-from-mistakes** skill for Claude Code — a self-improvement memory
inspired by Tony Stark: every failure gets logged with its root cause and fix, and the
next time the same problem appears, the known solution is applied immediately instead
of being debugged from scratch.

## What it does

- **Consults** a per-project `.claude/LESSONS.md` log before non-trivial or
  failure-prone work, and follows the prevention rules it finds there.
- **Recognizes** recurring errors and applies the logged fix in one step.
- **Logs** each new mistake after its fix is verified: trigger, what happened,
  root cause, fix, and a prevention rule.
- **Maintains** the log — merging duplicates and pruning obsolete entries so it
  stays scannable.

## Install

Copy the skill folder into your project (or user) skills directory:

```bash
# Project-level (recommended — the lessons log is per-project anyway)
mkdir -p .claude/skills
cp -r learn-from-mistakes .claude/skills/

# Or user-level, available in every project
mkdir -p ~/.claude/skills
cp -r learn-from-mistakes ~/.claude/skills/
```

Claude Code picks it up automatically; you can also invoke it explicitly with
`/learn-from-mistakes`.

## Layout

```
learn-from-mistakes/
├── SKILL.md                     # the skill itself
└── references/
    └── log-template.md          # initial LESSONS.md structure & categories
```
