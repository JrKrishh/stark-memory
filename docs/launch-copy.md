# Launch copy

Ready-to-paste promotion posts for stark-memory. Attach `assets/demo.gif` to
every post that allows media — Reddit, Discord, and X all autoplay it inline.

General playbook: launch everything on the same day, answer every comment in
the first two hours, and post as a story ("I built this because...") rather
than an announcement.

---

## Reddit — r/ClaudeAI

**Title (pick one):**

> I got tired of Claude Code repeating the same mistakes, so I gave it scar tissue

> I made Claude Code remember its failures — and ask permission before repeating the dangerous ones

**Body:**

Every Claude Code session starts with amnesia. It re-debugs the failure it
solved last week, and nothing stops it from re-running the build script that
wiped my data directory last month. I was re-typing the same "don't do X in
this repo" warnings into every prompt.

So I built **stark-memory**, a plugin that gives Claude Code a persistent
memory of its own failures. Three mechanisms:

- **Memory** — failures get logged as lessons in plain markdown
  (`.claude/LESSONS.md` per project, plus a global one). Commit the project
  log and your teammates' Claude inherits the scars too.
- **Reflex** — the moment a *known* failure recurs, a hook injects the logged
  fix into context before Claude starts debugging from scratch. Failed with
  `ECONNREFUSED` on the test DB before? The fix is already in front of it.
- **Shield** — lessons marked high-severity become guards. If Claude is about
  to run a command matching one, a PreToolUse hook stops it and asks *you*
  first, quoting the lesson. It's "ask", never "deny" — fuzzy matching should
  never hard-block real work.

A JARVIS-style telemetry hook captures every shell failure automatically, and
there's a `bootstrap` command that mines your git history's fix/revert commits
into draft lessons so day one isn't a cold start.

Zero dependencies (stdlib Python), plain files you can read and grep, works on
Windows/macOS/Linux. Install:

```
/plugin marketplace add JrKrishh/stark-memory
/plugin install stark-memory@stark-memory
```

Repo (demo GIF in the README): https://github.com/JrKrishh/stark-memory

Would love feedback — especially on the shield's matching strictness. It
requires two distinct command tokens to match a lesson's *failure* text
(deliberately excluding the Fix line, so "use `make build` instead" can't make
it block `make build` itself), but I'm sure there are edge cases I haven't hit
yet.

**Tips:** attach the demo GIF directly to the post (Reddit autoplays it),
post on a weekday morning US time, reply to every comment in the first two
hours.

---

## Show HN

**Title (79 chars):**

> Show HN: Stark-memory – Claude Code that remembers failures and blocks repeats

**URL field:** https://github.com/JrKrishh/stark-memory

**Text field:**

Claude Code (like most coding agents) has no memory between sessions: it
re-solves failures it already solved, and it will happily re-run a destructive
command that burned you before. Stark-memory is a plugin that closes that loop
with three mechanisms built on Claude Code's hooks API:

1. Capture: a PostToolUseFailure hook appends every shell failure to a local
   JSONL inbox (deduped by failure signature within a window, self-trimming,
   lock-protected). You triage the inbox into lessons — plain markdown entries
   with severity, trigger, root cause, fix, and a machine-actionable
   "Prevention" line.

2. Reflex: when a failure recurs, the hook matches it against logged lessons
   and injects the known fix into the model's context at the moment of
   failure, before debugging starts.

3. Shield: a PreToolUse hook checks commands against high-severity lessons.
   On a match it returns permissionDecision "ask" — never "deny" — so the
   human confirms with the lesson in view, but fuzzy text matching can never
   hard-block legitimate work.

The interesting design problem was false positives. A lesson saying "never
run bare build.sh — use make build" must not cause the shield to block "make
build" itself, so matching runs only against the failure-side text of a
lesson (title, trigger, what happened, root cause), deliberately excluding
the Fix/Prevention lines, and requires at least two distinct command tokens
to hit. Lessons can also be scoped to path globs so they only fire in the
right part of the tree.

Everything is plain files you can read, grep, and commit — project lessons
live in `.claude/LESSONS.md`, so a team shares scar tissue through git. Zero
runtime dependencies (Python stdlib), tested on Linux/Windows/macOS. There's
also a `bootstrap` command that mines fix/revert commits from git history
into draft lessons.

What it doesn't do: no embeddings, no vector store, no cloud — matching is
deliberately dumb (token overlap) because a guard that hallucinates matches
is worse than none. If a lesson keeps mattering, the intended path is
graduating it into a real validator/test/CI gate, and there's a scaffolding
command for that.

Repo: https://github.com/JrKrishh/stark-memory

Feedback welcome, especially from anyone who's tried to give agents
persistent memory — curious whether the "ask, never deny" tradeoff holds up
in other people's workflows.

**Tips:** post Tuesday–Thursday, ~8–10am ET. Stay in the thread — HN judges
Show HN by how the author handles hard questions; the "what it doesn't do"
paragraph pre-empts the "this is just grep" comment by owning it.

---

## Discord — Claude Developers #showcase

**Main version:**

**stark-memory** — self-improving memory for Claude Code 🧠

Claude Code forgets everything between sessions — it re-debugs failures it
already solved and will happily re-run the command that wiped your data last
month. This plugin closes the loop:

🛡️ **Shield** — commands matching a high-severity lesson get stopped *before*
they run; you confirm with the lesson in view
⚡ **Reflex** — a known failure recurs → the logged fix is injected into
context before Claude starts debugging
📋 **Memory** — failures auto-captured via hooks, triaged into plain markdown
lessons; commit `.claude/LESSONS.md` and your whole team's Claude inherits
the scars

Zero dependencies, plain files you can grep, Win/macOS/Linux, 89-test suite.

```
/plugin marketplace add JrKrishh/stark-memory
/plugin install stark-memory@stark-memory
```

🔗 https://github.com/JrKrishh/stark-memory — feedback very welcome,
especially on the shield's match strictness!

**Compact variant:**

Made Claude Code stop repeating its mistakes: failures get logged as lessons,
known failures get their fix injected instantly, and dangerous commands
matching a past incident need your confirmation before they run. Zero deps,
plain markdown, one-command install.
https://github.com/JrKrishh/stark-memory

**Tips:** attach the GIF directly (a repo link's embed preview won't
animate), post once in #showcase only, stick around for the first replies.

---

## X / Twitter

**Thread** (attach the GIF to tweet 1; post replies 2–5 immediately after):

**1/**

Your AI coding agent has no memory of the prod database it wiped last month.

Mine does — and it asks permission before trying again.

I built stark-memory: a Claude Code plugin that turns every failure into a
lesson that enforces itself 🧵

**2/**

Three mechanisms:

🛡️ Shield — a command matching a high-severity lesson stops BEFORE it runs;
you confirm with the lesson in view

⚡ Reflex — a known failure recurs → the logged fix lands in context before
debugging starts

📋 Memory — every shell failure auto-captured via hooks

**3/**

Lessons are plain markdown in .claude/LESSONS.md — commit the file and every
teammate's Claude inherits the scars. One person's outage becomes everyone's
guard.

Cold start? `bootstrap` mines your git history's fix/revert commits into
draft lessons on day one.

**4/**

The hard part was false positives.

The shield asks, never denies — fuzzy matching should never hard-block real
work. And it matches only a lesson's *failure* text, so "never run build.sh —
use make build" can't end up blocking make build itself.

**5/**

Zero dependencies. Plain files you can grep. Linux/macOS/Windows, 89-test CI.

Install:
/plugin marketplace add JrKrishh/stark-memory
/plugin install stark-memory@stark-memory

⭐ https://github.com/JrKrishh/stark-memory

**Single-tweet variant** (GIF attached):

Claude Code forgets everything between sessions — including the command that
wiped your data last month.

stark-memory fixes that: failures become lessons, known failures get their
fix injected instantly, dangerous repeats need your OK first.

https://github.com/JrKrishh/stark-memory

**Tips:** weekday 9–11am ET, pin tweet 1 for launch week, reply with the
Reddit/HN links once live, skip hashtags — dev audiences read them as spam.
