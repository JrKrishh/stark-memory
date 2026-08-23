<div align="center">

<img src="assets/banner.svg" width="100%" alt="stark-memory — self-improving memory for Claude Code"/>

[![tests](https://github.com/JrKrishh/stark-memory/actions/workflows/tests.yml/badge.svg)](https://github.com/JrKrishh/stark-memory/actions/workflows/tests.yml) [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE) ![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![Deps](https://img.shields.io/badge/dependencies-zero-success) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

</div>

---

## The idea in 10 seconds

Tony Stark never builds the same suit twice. This skill gives every Claude Code session a
memory of past failures — **per project** (`.claude/LESSONS.md`) and **across all projects**
(`~/.claude/LESSONS.md`) — then wires that memory into the loop: a **shield** that questions
destructive commands before they run, a **reflex** that applies the logged fix the instant
a known failure reappears, and JARVIS telemetry that records every failure automatically.
Lessons compound instead of evaporating when the session ends.

<div align="center">
<img src="assets/demo.gif" width="100%" alt="Demo: the shield stopping a destructive command before it runs, then the reflex injecting a logged fix the moment a known failure recurs"/>
</div>

```mermaid
flowchart LR
    A["Command about<br>to run"] -->|"shield: high-severity match<br>asks BEFORE executing"| H{"Human<br>confirms"}
    B["Failure happens"] -->|"JARVIS hook<br>(automatic)"| I[("mistakes.jsonl<br/>inbox")]
    I -->|"reflex at failure time"| D2["Logged fix injected<br/>before debugging"]
    I -->|"debrief triage<br>(lessons.py inbox)"| C[("LESSONS.md<br/>project + global logs")]
    C -->|"consult · search · preflight"| D["Claude applies the<br/>logged fix instantly"]
    C -.->|"Severity: high lessons<br>become guards"| A
    D -->|"recurs twice"| E["Automated guard<br/>validator · test · hook · CI"]
    H -->|confirmed safe| F["runs"]
```

---

## When to reach for this — the use cases

| You are... | stark-memory gives you |
|---|---|
| A solo dev on a long-lived repo | Claude stops re-discovering the same fix: the reflex injects the logged solution the moment a known failure reappears |
| A team sharing one codebase | Commit `.claude/LESSONS.md` and every teammate's Claude inherits the scars — one person's outage becomes everyone's guard |
| Running risky ops (prod DBs, infra scripts, deploy tooling) | The shield asks for human confirmation *before* a command matching a high-severity lesson executes |
| Onboarding Claude to a legacy codebase | `bootstrap` mines your git history's fix/revert commits into draft lessons, so day one starts with years of context |
| Working in a monorepo | Logs and manifests resolve by walking up from cwd — sessions nested deep inside packages still see the workspace's lessons |
| Tired of writing the same "don't do X here" in every prompt | Log it once with a **Prevention** line; every future session is told automatically at start |

The common thread: anything you'd otherwise re-explain to Claude — or re-suffer —
every session, becomes a one-time log entry that enforces itself.

---

## Install

### Option A — Plugin (recommended: one command, hooks included)

In Claude Code:

```
/plugin marketplace add JrKrishh/stark-memory
/plugin install stark-memory@stark-memory
/reload-plugins
```

That's the whole install: the skill, **both JARVIS hooks (shield + reflex), and telemetry**
wire themselves automatically. Invoke explicitly with `/stark-memory:learn-from-mistakes`.

### Option B — Manual skill copy

**macOS / Linux**

```bash
git clone https://github.com/JrKrishh/stark-memory.git
mkdir -p ~/.claude/skills
cp -r stark-memory/skills/learn-from-mistakes ~/.claude/skills/
```

**Windows PowerShell**

```powershell
git clone https://github.com/JrKrishh/stark-memory.git
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse stark-memory\skills\learn-from-mistakes "$HOME\.claude\skills\"
```

> Prefer project-only? Copy into `<project>/.claude/skills/` instead.
> Claude Code picks the skill up automatically in every new session;
> invoke explicitly any time with `/learn-from-mistakes`.

### Step 2 — Manual hooks (skip if you installed via plugin)

Without this step the skill still works, but logging depends on Claude remembering to debrief.
With these two hooks, **failures are recorded as they happen, logged fixes are injected at
the moment of failure, and high-severity lessons demand confirmation before their commands run**.

Merge into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "python",
            "args": ["~/.claude/skills/learn-from-mistakes/scripts/jarvis_inbox.py"],
            "timeout": 10,
            "statusMessage": "stark-memory shield"
          }
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "python",
            "args": ["~/.claude/skills/learn-from-mistakes/scripts/jarvis_inbox.py"],
            "timeout": 10,
            "statusMessage": "JARVIS logging failure"
          }
        ]
      }
    ]
  }
}
```

- Replace `~` with an absolute path (`C:/Users/<you>/...` on Windows).
- Keep both hooks synchronous (no `"async"`): they don't just record failures —
  **the reflex** injects a logged fix into context the moment a command fails,
  and **the shield** asks for confirmation before a command matching a
  high-severity lesson even executes.
- Full walkthrough incl. Windows specifics: [`references/jarvis-hook.md`](skills/learn-from-mistakes/references/jarvis-hook.md).

### Step 3 — (Optional) Auto-load lessons at session start

A `SessionStart` hook can inject your lesson logs into context every session:
[`references/session-start-hook.md`](skills/learn-from-mistakes/references/session-start-hook.md).

---

## Set up a specific project (5 minutes)

Installing the plugin arms the machinery globally; this is how you point it at one
codebase. Run these from the project root (with the manual install the scripts live at
`~/.claude/skills/learn-from-mistakes/scripts/`; with the plugin install, just ask
Claude in a session — *"run lessons.py project-init"* — it knows where they are):

```bash
cd ~/code/my-api

# 1 · Teach sessions what this project IS
python ~/.claude/skills/learn-from-mistakes/scripts/lessons.py project-init
#   -> scaffolds .claude/stark-project.md; fill in Purpose / Structure /
#      Workflow / Failure shapes. Injected into every session at start.

# 2 · Seed the lessons log from git history (optional but a great day-one)
python ~/.claude/skills/learn-from-mistakes/scripts/lessons.py bootstrap          # preview drafts
python ~/.claude/skills/learn-from-mistakes/scripts/lessons.py bootstrap --apply  # append to .claude/LESSONS.md
#   -> mines fix/revert commits into draft lessons; review them, replace the
#      UNVERIFIED lines, delete drafts with no reusable insight.
#      (No history worth mining? Start empty from references/log-template.md.)

# 3 · Commit the project's memory so teammates inherit it
git add .claude/LESSONS.md .claude/stark-project.md
git commit -m "add stark-memory project brain"
```

From then on the loop runs itself: failures in this project are captured to the
JARVIS inbox as they happen, the reflex injects logged fixes when a known failure
recurs, and `Severity: high` lessons shield their commands. Your only recurring
job is triage at a natural stopping point:

```bash
python ~/.claude/skills/learn-from-mistakes/scripts/lessons.py inbox          # what failed lately?
# log the keepers (or ask Claude to debrief), then:
python ~/.claude/skills/learn-from-mistakes/scripts/lessons.py inbox --clear
```

Two rules of thumb that keep the log sharp:

- **Write the Prevention line for a stranger.** "Be careful with build.sh" prevents
  nothing; "never run ./build.sh — always `make build`" is enforceable.
- **Scope with Paths globs.** `- **Paths:** db/migrations/**` is what lets
  `preflight` and the shield fire in the right neighborhood and stay silent elsewhere.

---

## How to use

Mostly, you don't — the skill runs itself inside sessions:

| Moment | What Claude does |
|---|---|
| Before a high-severity command runs | **The shield** asks for confirmation, quoting the logged lesson |
| Before non-trivial work | Consults both logs; follows any matching **Prevention** rule |
| Before touching unfamiliar files | Runs `preflight` — surfaces lessons scoped to those exact paths |
| A logged error reappears | **The reflex** injects the known fix before debugging starts |
| After fixing something new | Logs it (severity, trigger, root cause, fix, prevention) |
| End of a big task | Debriefs: triages the JARVIS inbox, catches near-misses |

Your part is two commands at a natural stopping point:

```bash
python ~/.claude/skills/learn-from-mistakes/scripts/lessons.py inbox          # what failed lately?
python ~/.claude/skills/learn-from-mistakes/scripts/lessons.py inbox --clear  # after logging the keepers
```

### CLI cheat sheet — `lessons.py`

| Command | What it does |
|---|---|
| `search <keywords>` | Find entries across both logs |
| `preflight [files...]` | Lessons matching files about to change (defaults to `git diff`) |
| `inbox [--all] [--clear]` | Triage JARVIS-captured failures (this project by default) |
| `recall <question>` | Federated query: lesson logs + session RAG + workspace corpora, sources labeled |
| `patterns` | Cluster entries into failure classes — "fix the class, not the instance" |
| `stale` | Flag lessons whose watched paths churned in git since their date |
| `graduate "<title>"` | Scaffold the guard: hook JSON + validator stub + CI step |
| `bootstrap [--apply]` | Mine fix/revert commits into draft lessons |
| `save "<title>"` | Bump a lesson's Saves counter — its ROI ledger |
| `stats` | Categories, hot-spots, graduation candidates, pruning candidates |
| `env` | Print an environment fingerprint for `Env:` lines |

### What a lesson looks like

```markdown
### [2026-08-22] build.sh deletes the data/ directory
- **Severity:** high
- **Paths:** scripts/**
- **Trigger:** building the project
- **What happened:** ./build.sh wiped data/ and the build then failed
- **Root cause:** cleanup line `rm -rf $OUT data` removes data/ — wrong path
- **Fix:** restored data/ from backup; built with `make build` instead
- **Prevention:** never run ./build.sh — always `make build`
```

The **Prevention** line is the payload — it's what future sessions act on.
**Paths:** globs make `preflight` fire before the right files change.

---

## From memory to machine

A lesson that keeps mattering shouldn't stay a note. The automation ladder:

| Level | Meaning | Enforced by |
|---|---|---|
| 0 | Logged | exists in LESSONS.md |
| 1 | Habit | consulted before matching work |
| 2 | Guard | validator / test / fixed at the source |
| 3 | Impossible | PreToolUse hook or CI gate |

Graduate when a lesson **recurs a second time**, or immediately if severity is high.
Recipes: [`references/automation-ladder.md`](skills/learn-from-mistakes/references/automation-ladder.md).

---

## Tracking without a dashboard

stark-memory reports *to you* instead of waiting to be watched:

- **JARVIS briefing** — every session opens with a 10-line sitrep: threats
  intercepted, failures captured, top failure zone, top model by
  failures-per-100-commands, inbox backlog.
- **Shield toasts** — a destructive command blocked mid-flight pops a system
  notification instantly.
- **CLI deep-dives** — `lessons.py stats | models | inbox` whenever you want the
  full ledger.

## Per-project manifests — the skill learns each project's mission

One file teaches every session what a project IS: `.claude/stark-project.md`
(Purpose, Structure, Workflow, Failure shapes). It is injected at session start
via walk-up — so even sessions nested deep inside a monorepo see the workspace's
manifest and lessons — the briefing opens with the mission line, and the prompt
copilot uses it as context when improving requests.

```bash
python skills/learn-from-mistakes/scripts/lessons.py project-init   # scaffold in cwd
# then fill in the four sections; everything else is automatic
```

---

## Where everything lives

| File | Scope | Commit it? |
|---|---|---|
| `<project>/.claude/LESSONS.md` | this codebase's quirks | yes — teammates' Claude inherits the scars |
| `~/.claude/LESSONS.md` | portable, cross-project lessons | local only |
| `~/.claude/mistakes.jsonl` | raw JARVIS telemetry | **never** — may contain command output |

Privacy notes: the inbox stays local and self-trims past 400 lines; entries carry no secrets
by policy (`Env:` fingerprints hold versions, not tokens); lessons enter `LESSONS.md` only
through human-reviewed triage.

---

## Layout

```
.claude-plugin/
├── plugin.json                        # plugin manifest (hooks bundled via ${CLAUDE_PLUGIN_ROOT})
└── marketplace.json                   # installable as a Claude Code marketplace
assets/
└── logo.svg                          # the arc-reactor memory core
skills/
└── learn-from-mistakes/
    ├── SKILL.md                      # the skill itself
    ├── scripts/
    │   ├── lessons.py                # search · preflight · inbox · recall · patterns · stale · graduate · project · models · copilot
    │   ├── jarvis_inbox.py           # shield (PreToolUse) + capture & reflex (PostToolUseFailure) + toasts
    │   ├── copilot_hook.py           # UserPromptSubmit: Claude-Code-powered prompt improver
    │   ├── briefing.py               # session-start sitrep
    │   └── toast.ps1                 # Windows notification helper
    └── references/
        ├── log-template.md           # initial LESSONS.md structure & categories
        ├── automation-ladder.md      # recipes for turning lessons into guards
        ├── jarvis-hook.md            # hook install walkthrough (manual route)
        └── session-start-hook.md     # auto-load lessons into every session
```

## Requirements

Python 3.8+ (standard library only) · Claude Code · git (for `preflight`/`bootstrap`)

## Development

The test suite lives in `tests/` and needs only `pytest` (the plugin itself stays
zero-dependency):

```bash
python -m pip install pytest
python -m pytest
```

It covers the lessons-log parsing core, the `save`/`bootstrap` log mutations, the
JARVIS shield/reflex/capture logic (including the false-positive strictness rules),
and an end-to-end hook contract: every hook script must exit 0 and emit valid JSON —
or nothing — on good, empty, and garbage input, so a regression can never break a
user's session. CI runs the suite on Linux, Windows, and macOS against Python 3.8
and 3.12.

## License

[MIT](LICENSE) © Boopathi Raja
