# LESSONS.md template

Use this as the initial content when creating `.claude/LESSONS.md` in a project for
the first time. Categories are created on demand — only add a heading when the first
entry for it exists.

```markdown
# Lessons Learned

A log of past mistakes and their fixes, maintained by the learn-from-mistakes skill.
Consult before non-trivial tasks; apply logged fixes when a known error recurs.
Newest entries go at the top of their category.

## Build & Tooling

## Environment & Setup

## Codebase Assumptions

## Testing

## User Corrections

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
| Other | anything that fits nowhere else |
