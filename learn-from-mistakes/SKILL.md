---
name: learn-from-mistakes
description: Self-improvement memory for Claude — learn from past errors like Tony Stark rebuilding his suit after every fight. Use this skill whenever an error, failed command, test failure, bug, wrong assumption, or user correction happens during work, AND at the start of any non-trivial task to check whether a similar mistake was already made and solved before. It logs each mistake with its root cause and fix to a LESSONS.md file in the project, and applies the known solution immediately when a logged error recurs. Trigger it even if the user doesn't mention "lessons" or "mistakes" — any moment where something went wrong, or where past failures could inform current work, is a reason to use it.
---

# Learn From Mistakes

Tony Stark never builds the same suit twice. Every time something breaks — icing at
altitude, a depleted arc reactor, a suit torn apart — the next version ships with a fix
for exactly that failure. That's the model here: **a mistake is only expensive the first
time. The second time, it should be free.**

This skill maintains a per-project lessons log so that knowledge survives across
sessions. Without it, every new conversation starts from zero and repeats the same
failed commands, wrong assumptions, and broken approaches. With it, past pain becomes
a checklist.

## The lessons log

The log lives at **`.claude/LESSONS.md`** in the project root. If it doesn't exist,
create it (with the header from `references/log-template.md`) the first time there is
something worth writing down — don't create an empty one preemptively.

## Workflow

### 1. Consult before you act

At the start of any non-trivial task — and before repeating a category of action that
is failure-prone (builds, deploys, migrations, test runs, tricky APIs) — read
`.claude/LESSONS.md` if it exists. Scan for entries whose **Trigger** matches what
you're about to do. If one matches, follow its **Prevention** line from the start
instead of rediscovering the problem. Mention briefly that you're applying a logged
lesson, so the user knows the log is paying off.

### 2. Recognize a recurring error

When an error occurs, check the log before debugging from scratch. If the error matches
a logged entry, apply the logged **Fix** immediately. This is the core payoff: known
problems get known solutions in one step, not another debugging session.

If the logged fix *doesn't* work this time, debug normally — then **update that entry**
rather than adding a duplicate. Lessons evolve; the log should hold the current best
answer, not a history of half-answers.

### 3. Log new mistakes — after they're fixed

When something goes wrong and you solve it, ask: *would a future session plausibly hit
this again?* If yes, append an entry to `.claude/LESSONS.md` using the format below.

Log it when:
- A command or build failed for a non-obvious reason and the fix took real effort
- You made a wrong assumption about the codebase, API, or environment
- The user corrected you — their correction is a lesson by definition
- A bug you introduced was caught by tests, review, or the user
- A tool, library, or config behaved differently than documented/expected

Don't log:
- One-off typos or transient network hiccups that carry no reusable insight
- Anything containing secrets, tokens, or private user data
- Duplicates — update the existing entry instead (bump its date, refine the fix)

Log the lesson **after the fix is verified**, not while guessing. An unverified fix in
the log is worse than no entry: it sends the next session down a wrong path with
confidence.

### 4. Maintain the log

The log is a working tool, not an archive. When touching it, keep it healthy:
- Merge near-duplicate entries into one stronger entry
- Delete entries made obsolete by codebase changes (the failing script was removed,
  the flaky dependency was replaced)
- Keep it scannable — if it grows past ~50 entries, consolidate the weakest ones.
  A log nobody can scan in 30 seconds stops being consulted.

## Entry format

Append entries under the matching category heading (create the heading if new).
Keep each entry short enough to scan — the *Prevention* line is the part future
sessions act on, so make it imperative and specific.

```markdown
### [2026-08-22] Vite build fails with ESM import error
- **Trigger:** running `npm run build` in this repo
- **What happened:** build failed: `require() of ES Module not supported` from config
- **Root cause:** `vite.config` uses ESM but `package.json` lacked `"type": "module"`
- **Fix:** added `"type": "module"` to package.json
- **Prevention:** don't remove `"type": "module"`; new config files must use ESM syntax
```

Another example — a wrong-assumption lesson:

```markdown
### [2026-08-22] Assumed API returns snake_case
- **Trigger:** writing client code against /api/v2 endpoints
- **What happened:** parsing silently produced undefined fields
- **Root cause:** /api/v2 returns camelCase, unlike /api/v1; assumption carried over
- **Fix:** switched field access to camelCase for all v2 calls
- **Prevention:** check one real response payload before writing parsing code for any endpoint
```

## The spirit of it

The goal is not bureaucracy — it's compounding. A project whose lessons log has 20 good
entries makes every future session faster and safer than the last. When in doubt about
whether to log something, ask the Stark question: *"if this exact thing bites me again
next month, will I be annoyed I didn't write it down?"* If yes, write it down.
