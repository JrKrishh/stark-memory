# LESSONS.md template

Use this as the initial content when creating a lessons log for the first time —
either the project log (`.claude/LESSONS.md`) or the global log (`~/.claude/LESSONS.md`).
Categories are created on demand — only add a heading when the first entry for it exists.

```markdown
# Lessons Learned

A log of past mistakes and their fixes, maintained by the learn-from-mistakes skill.
Consult before non-trivial tasks; apply logged fixes when a known error recurs;
graduate recurring or high-severity lessons into automated guards.
Newest entries go at the top of their category.

## Build & Tooling

## Environment & Setup

## Codebase Assumptions

## Testing

## User Corrections

## Near-Misses

## Other
```

Suggested categories (rename or add freely to fit the project):

| Category | Use for |
|---|---|
| Build & Tooling | compile/build/bundler/CLI failures |
| Environment & Setup | missing deps, versions, env vars, OS quirks |
| Codebase Assumptions | wrong beliefs about how the code/API works |
| Testing | flaky tests, test-runner quirks, coverage traps |
| User Corrections | things the user explicitly corrected |
| Near-Misses | almost-failures caught in time (severity = what would have happened) |
| Other | anything that fits nowhere else |

Entry fields: **Severity** (low / medium / high), **Trigger**, **What happened**,
**Root cause**, **Fix**, **Prevention** are the core; **Recurred** (dates the lesson
was applied again) and **Automation** (what guard was built, if any) are added when
they become relevant. See SKILL.md for a full example entry.
