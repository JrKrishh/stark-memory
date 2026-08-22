---
name: learn-from-mistakes
description: Self-improvement memory for Claude — learn from past errors like Tony Stark rebuilding his suit after every fight. Use this skill whenever an error, failed command, test failure, bug, wrong assumption, near-miss, or user correction happens during work, AND at the start of any non-trivial task to check whether a similar mistake was already made and solved before. It logs each mistake with its root cause and fix to a per-project LESSONS.md (plus a global cross-project log), applies the known solution immediately when a logged error recurs, and graduates recurring or dangerous lessons into automated guards (validators, tests, hooks) so they can't happen again. Trigger it even if the user doesn't mention "lessons" or "mistakes" — any moment where something went wrong, almost went wrong, or where past failures could inform current work, is a reason to use it. Also use it to bootstrap a lessons log from a repo's git fix/revert history, pre-flight a change against path-scoped lessons, and track flaky tests.
---

# Learn From Mistakes

Tony Stark never builds the same suit twice. Every time something breaks — icing at
altitude, a depleted arc reactor, a suit torn apart — the next version ships with a fix
for exactly that failure. That's the model here: **a mistake is only expensive the first
time. The second time, it should be free. The third time, it should be impossible.**

This skill maintains lessons logs so knowledge survives across sessions, and — the
Stark move — pushes the best lessons *out of memory and into the machine*: a lesson
that keeps mattering becomes a validator, a test, or a hook that enforces itself.

## The two logs

- **Project log — `.claude/LESSONS.md`** in the project root: lessons about *this*
  codebase (its quirks, its scripts, its data formats).
- **Global log — `~/.claude/LESSONS.md`**: lessons about tools, languages, and
  environments in general — things that would bite in *any* project ("Python's `json`
  rejects trailing commas", "this CLI's `--force` flag also deletes remotes").

When logging, ask: *is this about this project, or about the world?* Project-specific →
project log. Portable → global log. If unsure, project log (it can be promoted later).
Create a log (with the header from `references/log-template.md`) the first time there
is something worth writing — don't create empty logs preemptively.

## Workflow

### 1. Consult before you act

At the start of any non-trivial task — and before a failure-prone category of action
(builds, deploys, migrations, destructive commands, tricky APIs) — read both logs if
they exist. `scripts/lessons.py search <keywords>` finds matching entries across both
in one step, and `scripts/lessons.py preflight` matches the files you're about to
touch (or the current git diff) against entries' **Paths** globs — run it before
editing code in an area you don't fully know. If an entry's **Trigger** matches what
you're about to do, follow its **Prevention** line from the start, and say briefly
that you're applying a logged lesson so the user sees the log paying off.

When a lesson actually saves you — prevents a repeat, or supplies the fix in one
step — record it: `scripts/lessons.py save "<entry title>"`. The **Saves** count is
the log's ROI ledger: it justifies each entry's existence, drives pruning (no saves,
no recurrences, old → delete), and 3+ saves marks a lesson that has earned a real
guard. In a big log, consult selectively — preflight + search surface the few
relevant entries instead of re-reading everything; context is a budget.

Tip: the consult step shouldn't depend on discipline. Offer the user the session-start
hook from `references/session-start-hook.md` once — it injects the logs into context
automatically at the start of every session.

### 2. Recognize a recurring error

When an error occurs, check the logs before debugging from scratch. If the JARVIS
hook is installed this happens automatically — on a match it injects the logged fix
into context at the moment of failure (a "reflex"; firings are recorded in the inbox
as `reflex: true` telemetry — bump `Saves` for the ones that helped, sharpen entries
whose matches felt noisy). Otherwise, check the logs yourself. On a match, apply the
logged **Fix** immediately. Then update the entry: append today's date to its
**Recurred** line (add the line if missing) — and leave the heading's original date
alone. The heading date records the first occurrence; **Recurred** records the
history, and that trail is what triggers graduation. A recurrence is a signal, not
just a save — see step 5.

If the logged fix *doesn't* work, debug normally, then update that entry with the
better answer rather than adding a duplicate. The log holds the current best answer,
not a history of half-answers.

### 3. Log new mistakes — and near-misses

When something goes wrong and you solve it, ask: *would a future session plausibly hit
this again?* If yes, append an entry (format below) to the right log.

Log it when:
- A command, build, or test failed for a non-obvious reason and the fix took real effort
- You made a wrong assumption about the codebase, API, or environment
- **The user corrected you** — their correction is a lesson by definition
- A bug you introduced was caught by tests, review, or the user
- **A near-miss**: something *almost* went wrong — you caught a destructive command
  before running it, noticed a wrong assumption just in time, or wasted more than a
  few minutes on a confusion that better notes would have prevented. Near-misses are
  the cheapest lessons you'll ever get; don't wait for the crash version.

Don't log: one-off typos, transient network blips, secrets/tokens/private data, or
duplicates (update the existing entry instead). Log **after the fix is verified** —
an unverified fix sends the next session down a wrong path with confidence.

### 4. Debrief at the end of significant tasks

Before closing out a substantial piece of work, run a 30-second after-action review:
*What surprised me? What did the user correct? What almost went wrong?* Log anything
that qualifies under step 3. This is where near-misses and corrections get captured —
they rarely announce themselves with a stack trace.

If the JARVIS hook (`scripts/jarvis_inbox.py`) is installed, every failed shell command
was already captured during the session — no memory required. Run
`scripts/lessons.py inbox` at debrief time and triage: cluster retry loops into one
lesson, keep only failures whose fix took real effort, log them per step 3, then clear
with `--clear`. The inbox is raw telemetry, not a log — an entry earns its place only
after the triage question (*would a future session plausibly hit this again?*).

### 5. Graduate lessons up the automation ladder

A lesson in a log is memory. Memory can be missed. The endgame for an important
lesson is to stop being advice and become a mechanism:

- **Level 0 — Logged**: it's in the log. (Every lesson starts here.)
- **Level 1 — Habit**: its Prevention line is consulted before matching work.
- **Level 2 — Guard in the code**: a validator script, lint rule, or test catches the
  mistake automatically — or the root cause is simply *fixed at the source* (the
  buggy script repaired, the trap deleted). Fixing the source beats guarding it.
- **Level 3 — Enforced**: a Claude Code hook or CI gate makes the mistake impossible
  to commit or even to attempt. The JARVIS shield is the fastest route: any
  `Severity: high` lesson automatically becomes a PreToolUse confirmation gate
  (see `references/jarvis-hook.md`), and a CI step or validator can finish the job.

Graduate a lesson when it **recurs a second time**, or immediately when its
**Severity is high** (data loss, destructive commands, security). Propose the guard to
the user, and record what was built on the entry's **Automation** line.
`scripts/lessons.py stats` flags graduation candidates — recurring entries that still
have no automation. See `references/automation-ladder.md` for concrete recipes
(hooks, validators, CI steps) with copy-paste examples.

### 6. Maintain the logs

The log is a working tool, not an archive. When touching it: merge near-duplicates,
delete entries made obsolete by codebase changes, promote project entries that turn
out to be universal into the global log, and keep it scannable — past ~50 entries,
consolidate the weakest. A log nobody can scan in 30 seconds stops being consulted.

## Entry format

Append under the matching category heading (create it if new). The **Prevention** line
is what future sessions act on — make it imperative and specific. **Severity**:
`low` (annoyance), `medium` (broken build/wrong results), `high` (data loss,
destructive, security). Optional fields, added when relevant:

- **Paths:** glob(s) the lesson is scoped to (`src/payments/**`) — this is what makes
  `preflight` fire when those files are about to change. Add it whenever a lesson is
  about a specific area of the codebase.
- **Recurred:** / **Automation:** — the recurrence trail and the guard built (step 5).
- **Saves:** how many times this lesson prevented a repeat (bumped by `lessons.py save`).
- **Env:** environment fingerprint (`lessons.py env` prints one) for lessons that only
  hold on specific tool versions or platforms — stops a node-22 lesson misfiring on a
  node-18 machine.

```markdown
### [2026-08-22] build.sh deletes the data/ directory
- **Severity:** high
- **Trigger:** building the project
- **What happened:** `./build.sh` wiped data/ and the build then failed
- **Root cause:** cleanup line `rm -rf $OUT data` removes data/ — wrong path
- **Fix:** restored data/ from backup; built with `make build` instead
- **Prevention:** never run `./build.sh` — always `make build`
- **Recurred:** 2026-08-25
- **Automation:** Level 2 — removed the bad rm path from build.sh; PreToolUse hook blocks `./build.sh`
```

A near-miss entry looks the same — note in **What happened** that it was caught in
time; severity reflects what *would* have happened.

## SWE power moves

**Bootstrap from git history.** A repo's history is a pre-existing mistake database:
every `fix:`, `revert:`, and hotfix commit is a lesson nobody wrote down. In a repo
whose log is empty (or thin), offer to run `scripts/lessons.py bootstrap` — it mines
fix-commits, clusters them by the area they touched, and drafts path-tagged entries
(dry-run by default; `--apply` appends them under a clearly-marked unverified
section). Drafts are leads, not lessons: read the underlying commits, replace the
UNVERIFIED lines with real root causes and prevention rules, and delete drafts with
no reusable insight. Never treat an unverified draft as an established lesson.

**Flaky tests.** Track flaky tests as first-class lessons under a `Flaky Tests`
category: the failing test's name in the title, its failure signature in **What
happened**, the workaround and root-cause status in **Fix**/**Prevention**, dates in
**Recurred**. Then a familiar failure is answered from the log — "known flake,
re-run once" vs "new real failure" — instead of being re-debugged. A flake that
keeps recurring graduates like any lesson: fix the root cause, or quarantine it
*visibly* with the team's consent (never silently skip a test).

**Team sharing.** The project log lives at `.claude/LESSONS.md` — a committable
path. Suggest committing it (and any guards) to the repo once it has real entries:
then every teammate's Claude inherits every teammate's scars, and lessons survive
machine changes. Keep entries merge-friendly: append within categories, stable
titles, one entry per lesson. Portable, non-project-specific lessons still belong in
the global log, not the repo.

## Bundled tools

- `scripts/lessons.py` — `search <keywords>` (both logs) · `preflight [files]`
  (lessons matching the files about to change; defaults to the git diff) ·
  `bootstrap [--apply]` (draft lessons from git history) · `save "<title>"` (bump a
  lesson's ROI counter) · `inbox [--all] [--clear]` (triage the JARVIS failure inbox) ·
  `recall <question>` (federated: logs + project session RAG + workspace corpora,
  each source labeled, graceful when absent) ·
  `patterns` (cluster entries into failure classes — fix the class, not the instance) ·
  `stale` (flag lessons whose Paths churned heavily in git since their date) ·
  `graduate "<title>"` (scaffold the guard: hook JSON + validator stub + CI step) ·
  `stats` (hot-spots, automation candidates, top earners, pruning candidates) ·
  `env` (fingerprint for Env: lines). Run it instead of re-implementing log searches
  by hand.
- `scripts/jarvis_inbox.py` — JARVIS telemetry + reflex: a synchronous
  PostToolUseFailure hook that appends every failed shell command to
  `~/.claude/mistakes.jsonl` as it happens (capture never depends on memory) and,
  when the failure matches a logged lesson, injects the known fix into context
  immediately. Install once per machine via `references/jarvis-hook.md`; triage
  with `lessons.py inbox`.
- `references/automation-ladder.md` — recipes for graduating lessons into guards.
- `references/session-start-hook.md` — auto-load the logs into every session.
- `references/log-template.md` — initial log structure and categories.

## The spirit of it

The goal is compounding. A project whose log has 20 good entries makes every session
faster and safer than the last; a lesson graduated into a hook protects even sessions
that never read the log. When in doubt about logging, ask the Stark question: *"if
this bites me again next month, will I be annoyed I didn't write it down?"* And when a
lesson keeps earning its keep, ask the better one: *"why is this still a note, and not
part of the suit?"*
