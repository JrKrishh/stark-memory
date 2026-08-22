# projektkode

Home of the **learn-from-mistakes** skill for Claude Code — a self-improvement memory
inspired by Tony Stark: every failure gets logged with its root cause and fix, the
next time the same problem appears the known solution is applied immediately, and
lessons that keep mattering get built into the suit as automated guards.

## What it does

- **Consults** the project log (`.claude/LESSONS.md`) and the global cross-project
  log (`~/.claude/LESSONS.md`) before non-trivial or failure-prone work, and follows
  the prevention rules it finds there.
- **Recognizes** recurring errors and applies the logged fix in one step, tracking
  recurrences on the entry.
- **Logs** each new mistake after its fix is verified — and near-misses and user
  corrections too, via an end-of-task debrief — with severity, trigger, root cause,
  fix, and a prevention rule.
- **Graduates** recurring or high-severity lessons up the automation ladder: from a
  logged note, to a validator/test/source-fix, to a Claude Code hook or CI gate that
  makes the mistake impossible.
- **Maintains** the logs — merging duplicates, promoting portable lessons to the
  global log, pruning obsolete entries.

### SWE power features

- **Git-history bootstrap** — `lessons.py bootstrap` mines the repo's fix/revert
  commits and drafts path-tagged starter lessons, so the skill knows a mature
  repo's scars on day one.
- **Pre-flight checks** — lessons carry `Paths:` globs; `lessons.py preflight`
  surfaces the lessons relevant to the exact files about to change (defaults to
  the current git diff).
- **Flaky-test memory** — a dedicated category for flake signatures, workarounds,
  and root-cause status: "known flake, re-run once" vs "new real failure" without
  re-debugging.
- **Team sharing** — the project log lives at a committable path; commit it and
  every teammate's Claude inherits every teammate's lessons.
- **ROI tracking** — `lessons.py save` bumps a per-entry Saves counter; `stats`
  shows top earners (graduate them to guards) and dead weight (prune it).
- **Environment fingerprints** — `Env:` lines (via `lessons.py env`) keep
  version-specific lessons from misfiring on other machines.

## Install

Copy the skill folder into your project (or user) skills directory:

```bash
# Project-level
mkdir -p .claude/skills
cp -r learn-from-mistakes .claude/skills/

# Or user-level, available in every project
mkdir -p ~/.claude/skills
cp -r learn-from-mistakes ~/.claude/skills/
```

Claude Code picks it up automatically; you can also invoke it explicitly with
`/learn-from-mistakes`. For automatic lesson loading at the start of every session,
see `learn-from-mistakes/references/session-start-hook.md`.

## Layout

```
learn-from-mistakes/
├── SKILL.md                          # the skill itself
├── scripts/
│   └── lessons.py                    # search + stats over the lessons logs
└── references/
    ├── log-template.md               # initial LESSONS.md structure & categories
    ├── automation-ladder.md          # recipes for turning lessons into guards
    └── session-start-hook.md         # auto-load lessons into every session
```
