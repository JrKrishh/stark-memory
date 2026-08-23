#!/usr/bin/env python3
"""Search, analyze, and grow learn-from-mistakes lessons logs.

Usage:
  python3 lessons.py search <keyword> [keyword...]     # match entries across both logs
  python3 lessons.py stats                             # counts, hot-spots, automation candidates
  python3 lessons.py preflight [file...]               # lessons relevant to files you're about to touch
                                                       #   (no args: uses git diff + staged changes)
  python3 lessons.py bootstrap [--apply] [--limit N]   # draft lessons from the repo's git history
   python3 lessons.py save <title-substring>            # record that a lesson just prevented a repeat (ROI)
   python3 lessons.py inbox [--all] [--clear]           # triage JARVIS-captured failures (mistakes.jsonl)
   python3 lessons.py recall <question>                 # federated: logs + session RAG + workspace corpus
   python3 lessons.py patterns                          # cluster entries into failure classes
   python3 lessons.py stale                             # flag lessons whose paths churned since their date
   python3 lessons.py graduate <title-substring>        # scaffold the guard for a lesson
   python3 lessons.py project                            # dossier: stack, git, recent prompts
   python3 lessons.py models                             # which model fails least per session
   python3 lessons.py copilot --suggest --prompt "<p>"   # Claude-Code-powered prompt improver
   python3 lessons.py env                               # print an environment fingerprint for Env: lines

Reads the project log (.claude/LESSONS.md, found by walking up from cwd) and the
global log (~/.claude/LESSONS.md). Only `save`, `bootstrap --apply`, and
`inbox --clear` write.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys
import time


def find_logs():
    logs = []
    d = os.getcwd()
    while True:
        p = os.path.join(d, ".claude", "LESSONS.md")
        if os.path.isfile(p):
            logs.append(("project", p))
            break
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    g = os.path.expanduser("~/.claude/LESSONS.md")
    if os.path.isfile(g) and all(os.path.abspath(g) != os.path.abspath(p) for _, p in logs):
        logs.append(("global", g))
    return logs


def project_log_path():
    for scope, p in find_logs():
        if scope == "project":
            return p
    return os.path.join(os.getcwd(), ".claude", "LESSONS.md")


def parse_entries(path):
    """Return dicts: {title, date, category, body} for each '### [date] title' block."""
    entries = []
    category = None
    current = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                category = line[3:].strip()
            m = re.match(r"^### \[([^\]]*)\]\s*(.*)", line)
            if m:
                current = {"date": m.group(1), "title": m.group(2).strip(),
                           "category": category or "Uncategorized", "body": ""}
                entries.append(current)
            elif current is not None and not line.startswith("## "):
                current["body"] += line
    return entries


def field(entry, name):
    m = re.search(r"\*\*%s:\*\*\s*(.*)" % re.escape(name), entry["body"], re.IGNORECASE)
    return m.group(1).strip() if m else ""


def print_entry(scope, e):
    print(f"--- [{scope}] {e['category']} — [{e['date']}] {e['title']}")
    print(e["body"].rstrip() + "\n")


def git(args, check=True):
    p = subprocess.run(["git"] + args, capture_output=True, text=True)
    if check and p.returncode != 0:
        return None
    return p.stdout


# ---------- search ----------

def cmd_search(terms):
    logs = find_logs()
    if not logs:
        print("No lessons logs found (.claude/LESSONS.md or ~/.claude/LESSONS.md).")
        return 1
    terms = [t.lower() for t in terms]
    hits = 0
    for scope, path in logs:
        for e in parse_entries(path):
            text = (e["title"] + " " + e["body"]).lower()
            if all(t in text for t in terms):
                hits += 1
                print_entry(scope, e)
    if not hits:
        print(f"No entries matching: {' '.join(terms)}")
    return 0


# ---------- stats ----------

def cmd_stats():
    logs = find_logs()
    if not logs:
        print("No lessons logs found (.claude/LESSONS.md or ~/.claude/LESSONS.md).")
        return 1
    for scope, path in logs:
        entries = parse_entries(path)
        print(f"== {scope} log: {path} — {len(entries)} entries")
        by_cat, by_sev = {}, {}
        candidates, earners, dead = [], [], []
        for e in entries:
            by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
            sev = field(e, "Severity") or "unspecified"
            by_sev[sev] = by_sev.get(sev, 0) + 1
            automation = field(e, "Automation")
            recur_count = len(re.findall(r"\d{4}-\d{2}-\d{2}", field(e, "Recurred")))
            saves = int(re.search(r"\d+", field(e, "Saves")).group()) if re.search(r"\d+", field(e, "Saves") or "") else 0
            if (recur_count >= 1 or sev.lower().startswith("high")) and not automation:
                candidates.append((e, recur_count, sev))
            if saves >= 3:
                earners.append((e, saves))
            if saves == 0 and recur_count == 0 and not field(e, "Saves"):
                dead.append(e)
        for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
            print(f"   {n:3d}  {cat}")
        print("   severity: " + ", ".join(f"{k}={v}" for k, v in sorted(by_sev.items())))
        if candidates:
            print("   AUTOMATION CANDIDATES (recurring or high-severity, no guard yet):")
            for e, rc, sev in candidates:
                print(f"     -> [{e['date']}] {e['title']} (recurrences: {rc}, severity: {sev})")
            print("   Graduate these up the ladder — see references/automation-ladder.md")
        if earners:
            print("   TOP EARNERS (3+ saves — strong graduation candidates):")
            for e, s in sorted(earners, key=lambda x: -x[1]):
                print(f"     -> [{e['date']}] {e['title']} (saves: {s})")
        if len(dead) > 3:
            print(f"   {len(dead)} entries with no recorded saves or recurrences — pruning candidates if old.")
        print()
    return 0


# ---------- preflight ----------

def changed_files():
    files = set()
    for args in (["diff", "--name-only"], ["diff", "--name-only", "--cached"]):
        out = git(args)
        if out:
            files.update(l.strip() for l in out.splitlines() if l.strip())
    return sorted(files)


def entry_matches_files(e, files):
    """Match via the entry's Paths: globs, or filenames mentioned in its text."""
    reasons = []
    pats = [p.strip() for p in re.split(r"[,\s]+", field(e, "Paths")) if p.strip()]
    for f in files:
        for pat in pats:
            if fnmatch.fnmatch(f, pat) or fnmatch.fnmatch(f, pat.rstrip("/") + "/*"):
                reasons.append(f"{f} matches Paths glob '{pat}'")
        base = os.path.basename(f)
        if len(base) > 3 and base in (e["title"] + e["body"]):
            reasons.append(f"{base} is mentioned in the entry")
    return reasons


def cmd_preflight(files):
    if not files:
        files = changed_files()
        if not files:
            print("No files given and no uncommitted git changes found. Usage: lessons.py preflight [file...]")
            return 1
    logs = find_logs()
    if not logs:
        print("No lessons logs found — nothing to check against.")
        return 0
    print(f"Pre-flight check for {len(files)} file(s): {', '.join(files[:8])}{' ...' if len(files) > 8 else ''}\n")
    hits = 0
    for scope, path in logs:
        for e in parse_entries(path):
            reasons = entry_matches_files(e, files)
            if reasons:
                hits += 1
                print(f"!! [{scope}] [{e['date']}] {e['title']}")
                print(f"   why: {reasons[0]}")
                prev = field(e, "Prevention")
                if prev:
                    print(f"   PREVENTION: {prev}")
                print()
    if hits:
        print(f"{hits} relevant lesson(s). Follow the prevention lines; run "
              "`lessons.py save \"<title>\"` for any that saves you from a repeat.")
    else:
        print("No logged lessons touch these files.")
    return 0


# ---------- bootstrap ----------

FIX_RE = re.compile(r"\b(fix|fixes|fixed|bugfix|hotfix|revert|regression|broke|broken|crash|oops)\b", re.I)

def cmd_bootstrap(apply=False, limit=300):
    out = git(["log", "--format=%h|%ad|%s", "--date=short", f"-n{limit}"])
    if out is None:
        print("Not a git repository (or git unavailable) — bootstrap needs history to mine.")
        return 1
    fixes = []
    for line in out.splitlines():
        sha, date, subject = line.split("|", 2)
        if FIX_RE.search(subject):
            names = git(["show", "--name-only", "--format=", sha]) or ""
            files = [f for f in names.splitlines() if f.strip()]
            fixes.append({"sha": sha, "date": date, "subject": subject, "files": files})
    if not fixes:
        print(f"No fix/revert-style commits found in the last {limit} commits.")
        return 0
    # Cluster by the directory each fix touched most, to surface repeat offenders.
    clusters = {}
    for fx in fixes:
        dirs = [os.path.dirname(f) or "." for f in fx["files"]] or ["."]
        key = max(set(dirs), key=dirs.count)
        clusters.setdefault(key, []).append(fx)
    drafts = []
    for path, fxs in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        glob = (path + "/**") if path != "." else "**"
        commits = ", ".join(f"{f['sha']} ({f['subject'][:60]})" for f in fxs[:4])
        more = f" and {len(fxs)-4} more" if len(fxs) > 4 else ""
        drafts.append(
            f"### [{fxs[0]['date']}] DRAFT: repeated fixes under {path or 'repo root'}\n"
            f"- **Severity:** {'high' if len(fxs) >= 3 else 'medium'}\n"
            f"- **Paths:** {glob}\n"
            f"- **Trigger:** changing code under `{path or '.'}`\n"
            f"- **What happened:** {len(fxs)} fix/revert commit(s) here: {commits}{more}\n"
            f"- **Root cause:** UNVERIFIED — mined from git history; read the commits and fill this in\n"
            f"- **Fix:** see the commits above\n"
            f"- **Prevention:** UNVERIFIED — extra care and testing when touching this area until a real prevention rule is written\n"
        )
    header = ("## Bootstrapped From Git History (unverified drafts)\n\n"
              "Mined by `lessons.py bootstrap`. Each draft needs a human/Claude pass: read the\n"
              "commits, replace UNVERIFIED lines, then move the entry to a real category — or\n"
              "delete drafts that carry no reusable insight.\n\n")
    text = header + "\n".join(drafts)
    if not apply:
        print(text)
        print(f"\n({len(fixes)} fix-commits -> {len(drafts)} draft lesson(s). Re-run with --apply to append to the project log.)")
        return 0
    logp = project_log_path()
    os.makedirs(os.path.dirname(logp), exist_ok=True)
    existing = open(logp, encoding="utf-8").read() if os.path.isfile(logp) else "# Lessons Learned\n\n"
    if "Bootstrapped From Git History" in existing:
        print("Log already has a bootstrapped section — review/clean that first, then re-run.")
        return 1
    with open(logp, "w", encoding="utf-8") as f:
        f.write(existing.rstrip() + "\n\n" + text)
    print(f"Appended {len(drafts)} draft lesson(s) to {logp}. Verify them before trusting them.")
    return 0


# ---------- save ----------

def cmd_save(term):
    logp = project_log_path()
    if not os.path.isfile(logp):
        print(f"No project log at {logp}.")
        return 1
    lines = open(logp, encoding="utf-8").read().splitlines(keepends=True)
    # Find the entry heading matching the term, then bump/insert its Saves line.
    idx = None
    for i, l in enumerate(lines):
        if l.startswith("### [") and term.lower() in l.lower():
            if idx is not None:
                print(f"'{term}' matches more than one entry — be more specific.")
                return 1
            idx = i
    if idx is None:
        print(f"No entry matching '{term}'.")
        return 1
    end = next((j for j in range(idx + 1, len(lines))
                if lines[j].startswith("### [") or lines[j].startswith("## ")), len(lines))
    for j in range(idx + 1, end):
        m = re.match(r"(- \*\*Saves:\*\*\s*)(\d+)", lines[j])
        if m:
            n = int(m.group(2)) + 1
            lines[j] = f"{m.group(1)}{n}\n"
            break
    else:
        n = 1
        insert = next((j for j in range(end, idx, -1) if lines[j - 1].strip().startswith("- ")), end)
        lines.insert(insert, "- **Saves:** 1\n")
    open(logp, "w", encoding="utf-8").writelines(lines)
    print(f"Recorded save #{n} on: {lines[idx].strip()[4:]}")
    if n >= 3:
        print("3+ saves — this lesson earns its keep; consider graduating it to an automated guard.")
    return 0


# ---------- env ----------

def cmd_env():
    import platform
    bits = [f"os={platform.system()}-{platform.release()}"]
    for tool, args in [("python3", ["--version"]), ("node", ["--version"]),
                       ("git", ["--version"]), ("docker", ["--version"])]:
        try:
            p = subprocess.run([tool] + args, capture_output=True, text=True, timeout=5)
            v = (p.stdout + p.stderr).strip().splitlines()[0]
            bits.append(f"{tool}={re.sub(r'^[^0-9]*', '', v).split()[0].rstrip(',;')}")
        except Exception:
            pass
    print("; ".join(bits))
    return 0


# ---------- inbox (JARVIS telemetry) ----------

def inbox_path():
    return os.environ.get("JARVIS_INBOX") or os.path.expanduser("~/.claude/mistakes.jsonl")


def _same_project(a, b):
    a = os.path.normcase(os.path.normpath(a or ""))
    b = os.path.normcase(os.path.normpath(b or ""))
    return bool(a) and bool(b) and (a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep))


def load_inbox():
    if not os.path.isfile(inbox_path()):
        return []
    out = []
    for line in open(inbox_path(), encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def cmd_inbox(all_projects=False, clear=False):
    events = load_inbox()
    if not events:
        print("JARVIS inbox is empty — nothing has fallen yet.")
        return 0
    cwd = os.getcwd()
    shown = [e for e in events if all_projects or _same_project(e.get("project"), cwd)]
    if not shown:
        print(f"{len(events)} event(s) in the inbox, none from this project. Re-run with --all to see everything.")
        return 0
    print(f"JARVIS inbox — {len(shown)} failure(s)"
          f"{f' (of {len(events)} total)' if all_projects else ' for this project'}\n")
    for i, e in enumerate(shown, 1):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.get("ts", 0)))
        code = e.get("exit_code")
        head = f"[{i}] {when}  exit {'?' if code is None else code}  {e.get('cmd', '')}"
        if not all_projects and not _same_project(e.get("project"), cwd):
            head += f"   ({e.get('project', '?')})"
        print(head)
        detail = next((l for l in str(e.get("error", "")).splitlines()
                       if l.strip() and not l.startswith("Exit code")), "")
        if detail:
            print(f"    {detail[:140]}")
    kept = [e for e in events if e not in shown] if clear else None
    if clear:
        with open(inbox_path(), "w", encoding="utf-8") as f:
            f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in kept)
        print(f"\nCleared {len(shown)} triaged event(s); {len(kept)} remain.")
    else:
        print("\nFor each distinct failure worth keeping: log it per the SKILL.md workflow"
              "\n(verified fix only), then re-run with --clear. Retry loops are one lesson, not N.")
    return 0


# ---------- recall (federated memory) ----------

SRAG = os.environ.get("STARK_SRAG") or os.path.expanduser("~/.claude/session-rag/srag.py")


def _run(args, timeout=60):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
        # child output is UTF-8 by convention; never let the locale codec eat it
        return p.stdout.decode("utf-8", "replace").strip() if p.returncode == 0 else None
    except Exception:
        return None


def _find_dr():
    d = os.getcwd()
    while True:
        p = os.path.join(d, "dynamo-rag", "dr.py")
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def cmd_recall(terms):
    """Federated query: lesson logs + project session RAG + workspace law decks.

    stark-memory owns no new storage — it routes one question to whichever
    sovereign memory systems exist near this project and labels the sources.
    Every component degrades gracefully when absent."""
    query = " ".join(terms)
    sections = 0

    logs = find_logs()
    hits = []
    for scope, path in logs:
        for e in parse_entries(path):
            text = (e["title"] + " " + e["body"]).lower()
            if all(t.lower() in text for t in terms):
                hits.append((scope, e))
    print(f"== lessons ({len(logs)} log(s))")
    if hits:
        for scope, e in hits[:6]:
            print_entry(scope, e)
        sections += 1
    else:
        print("   no matching entries\n")

    proj = os.path.basename(os.getcwd())
    if os.path.isfile(SRAG):
        out = _run([sys.executable, SRAG, "ask", query, "--project", proj, "--k", "5"])
        print(f"== sessions (srag, project ~ '{proj}')")
        if out:
            print(out + "\n")
            sections += 1
        else:
            print("   srag unavailable or returned nothing\n")
    else:
        print("== sessions (srag): not installed\n")

    dr = _find_dr()
    print("== workspace corpus (dr.py)" if dr else "== workspace corpus (dr.py): not found here")
    if dr:
        out = _run([sys.executable, dr, "ask", query, "--fast"])
        if out:
            print(out + "\n")
            sections += 1

    if not sections:
        print("No memory source answered. This is a cold-start project — "
              "log the next failure and recall gets smarter.")
    return 0


# ---------- patterns / stale / graduate ----------

PATTERNS = [
    ("environment & tooling", "version environment environment installed missing module package "
     "dependency not recognized path python node docker cli binary executable"),
    ("config & schema placement", "config config schema key field table section placement root "
     "level header format syntax toml yaml json metadata label vocabulary naming snake_case"),
    ("wrong assumption about state", "assumed assumes assumed missing doesn't exist deleted renamed "
     "moved outdated stale changed refactor expected"),
    ("ordering, caching & timing", "order before after cache cached race async timeout retry wait "
     "timing sequence stale refresh"),
    ("destructive paths & data loss", "delete deletes wipe wiped rm remove overwrite destroyed wrong "
     "path directory data loss dangerous destructive"),
    ("network, auth & permissions", "auth token permission permission network connection ssh refused "
     "denied credentials firewall proxy certificate"),
]


def _all_entries():
    for scope, path in find_logs():
        for e in parse_entries(path):
            yield scope, e


def cmd_patterns():
    """Cluster entries by failure class — 'why does the same spot keep failing'."""
    entries = list(_all_entries())
    if not entries:
        print("No lessons logs found.")
        return 1
    buckets = {name: [] for name, _ in PATTERNS}
    unclassified = []
    for scope, e in entries:
        text = (e["title"] + " " + e["body"]).lower()
        placed = False
        for name, kws in PATTERNS:
            score = sum(1 for kw in kws.split() if kw in text)
            if score >= 2:
                buckets[name].append(e)
                placed = True
                break
        if not placed:
            unclassified.append(e)
    total = len(entries)
    print(f"Failure patterns across {total} entr"
          f"{'y' if total == 1 else 'ies'} ({len(find_logs())} log(s))\n")
    if total < 10:
        print(f"(thin data — {total}/10 entries; clusters sharpen as the logs grow)\n")
    ranked = sorted(((n, es) for n, es in buckets.items() if es),
                    key=lambda kv: -len(kv[1]))
    if ranked:
        top = ranked[0]
        print(f"TOP FAILURE CLASS: {top[0]} ({len(top[1])} of {total}) — fix the class, not the instance\n")
    for name, es in ranked:
        print(f"[{len(es)}] {name}")
        for e in es:
            print(f"      - [{e['date']}] {e['title']}")
    if unclassified:
        print(f"\n[{len(unclassified)}] unclassified (no keyword class fit twice):")
        for e in unclassified:
            print(f"      - [{e['date']}] {e['title']}")
    return 0


def cmd_stale(threshold=10):
    """Flag lessons whose Paths-globbed files churned heavily since their date."""
    import datetime
    if git(["rev-parse", "--show-toplevel"]) is None:
        print("Not a git repository — stale detection needs history to measure churn against.")
        return 1
    today = datetime.date.today().isoformat()
    flagged = checked = 0
    for scope, e in _all_entries():
        globs = [g.strip() for g in re.split(r"[,\s]+", field(e, "Paths")) if g.strip()]
        if not globs or not re.match(r"^\d{4}-\d{2}-\d{2}$", e["date"].strip()):
            continue
        checked += 1
        out = git(["log", "--since=" + e["date"].strip(), "--name-only", "--pretty=format:"])
        changed = {l.strip() for l in (out or "").splitlines() if l.strip()}
        churn = sum(1 for f in changed
                    if any(fnmatch.fnmatch(f, g) or fnmatch.fnmatch(f, g.rstrip("/") + "/*")
                           for g in globs))
        mark = ""
        if churn >= threshold:
            mark = f"  << STALE? {churn} matching changes since {e['date']} — verify or prune"
            flagged += 1
        elif churn:
            mark = f"  ({churn} matching changes since {e['date']})"
        else:
            mark = f"  (quiet since {e['date']})"
        print(f"- [{scope}] [{e['date']}] {e['title']}{mark}")
    print(f"\n{checked} dated entry(ies) with Paths checked against churn since {today[:4]}; "
          f"{flagged} stale candidate(s) at >= {threshold} changes. "
          "A lesson about code that no longer exists is folklore — verify or delete.")
    return 0


def cmd_graduate(term):
    """Scaffold the actual guard for a lesson: hook JSON + validator + CI step."""
    target = None
    for scope, e in _all_entries():
        if term.lower() in e["title"].lower():
            if target is not None:
                print(f"'{term}' matches more than one entry — be more specific.")
                return 1
            target = (scope, e)
    if not target:
        print(f"No entry matching '{term}'.")
        return 1
    scope, e = target
    prevention = field(e, "Prevention") or "TODO: derive the check from the prevention rule"
    print(f"Graduating: [{e['date']}] {e['title']}  ({scope} log)\n")
    print("1 · Claude Code hooks (merge into settings.json; already wired if you use JARVIS):")
    print(json.dumps({"hooks": {
        "PreToolUse": [{"matcher": "Bash|PowerShell", "hooks": [
            {"type": "command", "command": "python",
             "args": ["<abs path>/learn-from-mistakes/scripts/jarvis_inbox.py"],
             "timeout": 10, "statusMessage": "stark-memory shield"}]}],
        "PostToolUseFailure": [{"matcher": "Bash|PowerShell", "hooks": [
            {"type": "command", "command": "python",
             "args": ["<abs path>/learn-from-mistakes/scripts/jarvis_inbox.py"],
             "timeout": 10, "statusMessage": "JARVIS logging failure"}]}]}}, indent=2))
    globs = [g.strip() for g in re.split(r"[,\s]+", field(e, "Paths")) if g.strip()]
    watch = ", ".join(globs) or "**"
    testname = re.sub(r"[^a-z0-9]+", "_", e["title"].lower()).strip("_")[:40]
    print("\n2 · Validator stub — tests/test_" + testname + ".py:")
    print(f'"""Guard graduated from lesson [{e["date"]}]: {e["title"]}"""')
    print("import pathlib\n"
          "\n"
          f"# Prevention: {prevention}\n"
          f"# Watched paths: {watch}\n"
          "def test_guard():\n"
          "    # TODO: assert the anti-pattern cannot recur.\n"
          f"    # e.g. scan {watch} for whatever the prevention rule forbids,\n"
          "    # and fail with this message when found:\n"
          f'    raise AssertionError("GUARD NOT BUILT YET — prevention: {prevention[:80]}")\n')
    print("3 · CI gate (GitHub Actions step):")
    print(f"      - run: python -m pytest tests/test_{testname}.py\n"
          "        name: guard — " + e["title"][:50])
    import datetime
    print("\nAfter wiring a guard, record it on the entry's **Automation:** line, e.g.:")
    print(f"      - **Automation:** Level 2/3 — <what was built> (graduated {datetime.date.today().isoformat()})")
    return 0


# ---------- project dossier & prompt copilot ----------

CACHE_DIR = os.path.expanduser("~/.claude/stark-cache")


def _slugify(p):
    # Claude Code's ~/.claude/projects dir naming: ':' -> '-', '\'|'/' -> '-'
    return p.replace("\\", "-").replace("/", "-").replace(":", "-")


def _transcript_dir(project_dir):
    return os.path.join(os.path.expanduser("~/.claude/projects"), _slugify(project_dir))


def _recent_prompts(project_dir, limit=10):
    """User prompts from this project's recent Claude Code transcripts."""
    d = _transcript_dir(project_dir)
    if not os.path.isdir(d):
        return []
    files = sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl")),
                   key=os.path.getmtime, reverse=True)
    prompts = []
    for fp in files:
        if len(prompts) >= limit:
            break
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    if o.get("type") != "user":
                        continue
                    msg = o.get("message") or {}
                    if msg.get("isMeta"):
                        continue
                    c = msg.get("content")
                    if isinstance(c, str):
                        text = c
                    elif isinstance(c, list):
                        text = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
                    else:
                        continue
                    text = text.strip()
                    if len(text) >= 10 and not text.startswith("<") and not text.startswith("Caveat:"):
                        prompts.append(text)
                        if len(prompts) >= limit:
                            break
        except OSError:
            continue
    return prompts


def _detect_stack(project_dir):
    stack = []
    names = os.listdir(project_dir) if os.path.isdir(project_dir) else []
    checks = [("package.json", "node"), ("pyproject.toml", "python"),
              ("requirements.txt", "python"), ("go.mod", "go"),
              ("Cargo.toml", "rust"), ("composer.json", "php"),
              ("pom.xml", "java"), ("Dockerfile", "docker"),
              (".csproj", "dotnet"), ("*.ts", "typescript")]
    for n, label in checks:
        if any(fnmatch.fnmatch(x, n) for x in names):
            stack.append(label)
    return sorted(set(stack)) or ["plain"]


def _project_digest(project_dir):
    """Bounded dossier: stack, file count, git remote + last commit, prompts."""
    info = {"path": project_dir, "stack": _detect_stack(project_dir),
            "files": 0, "git_remote": "", "last_commit": "", "prompts": []}
    if os.path.isdir(project_dir):
        n = 0
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__",
                                                    ".venv", "venv", "dist", "build", ".next")]
            n += len(files)
            if n > 4000:
                break
        info["files"] = n
    rem = git(["remote", "get-url", "origin"], check=False)
    if rem:
        info["git_remote"] = rem.strip().splitlines()[-1]
    last = git(["log", "-1", "--format=%h|%ad|%s", "--date=short"], check=False)
    if last:
        info["last_commit"] = last.strip().splitlines()[0]
    info["prompts"] = _recent_prompts(project_dir, 6)
    return info


def cmd_project():
    """Print this project's dossier (stack, git, recent prompts)."""
    d = _project_digest(os.getcwd())
    print(f"PROJECT DOSSIER — {d['path']}")
    print(f"  stack:    {', '.join(d['stack'])}")
    print(f"  files:    {d['files']} (bounded walk)")
    print(f"  remote:   {d['git_remote'] or '-'}")
    print(f"  commit:   {d['last_commit'] or '-'}")
    if d["prompts"]:
        print(f"\nRECENT PROMPTS ({len(d['prompts'])}):")
        for i, p in enumerate(d["prompts"], 1):
            print(f"  [{i}] {p[:110]}")
    else:
        print("\nno user prompts found in this project's transcripts yet")
    return 0


def _save_cache(name, obj):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def _load_cache(name):
    try:
        with open(os.path.join(CACHE_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def cmd_copilot(args):
    """Copilot: --suggest <prompt> uses Claude Code itself (inner claude -p,
    recursion-guarded) to improve a prompt for THIS project. --history prints
    recent prompts. --cache prints the suggestion cache."""
    if "--history" in args:
        for i, p in enumerate(_recent_prompts(os.getcwd(), 10), 1):
            print(f"[{i}] {p}")
        return 0
    if "--cache" in args:
        c = _load_cache("copilot.json") or {"suggestions": []}
        for s in c["suggestions"][-5:]:
            print(f"— {s['ts']} | {s['prompt'][:60]}\n  -> {s['suggestion'][:160]}\n")
        return 0
    prompt = ""
    if "--prompt" in args:
        i = args.index("--prompt")
        prompt = args[i + 1] if i + 1 < len(args) else ""
    if not prompt:
        print("usage: lessons.py copilot --suggest --prompt \"<the prompt>\" [--json]")
        return 2
    d = _project_digest(os.getcwd())
    context = (
        f"Project: {os.path.basename(os.getcwd())}\n"
        f"Stack: {', '.join(d['stack'])}\n"
        f"Files: {d['files']}\n"
        f"Last commit: {d['last_commit'] or '-'}\n"
        f"Recent user prompts:\n" + "\n".join(f"- {p}" for p in d["prompts"][:6]) +
        "\n\n"
        f"The user just typed this prompt into Claude Code in THIS project:\n"
        f"\"{prompt}\"\n\n"
        "Rewrite it into ONE stronger prompt. Keep the same intent and language. "
        "Make it specific to this project: reference real files, stack, or past "
        "work when relevant. Do not add features they didn't ask for. "
        "Output ONLY the improved prompt text, nothing else."
    )
    env = dict(os.environ, STARK_COPILOT_INNER="1")
    import shutil
    exe = shutil.which("claude.cmd") or shutil.which("claude.exe") or shutil.which("claude") or "claude"
    try:
        p = subprocess.run([exe, "-p", context, "--max-turns", "1"],
                           capture_output=True, timeout=50, env=env)
        suggestion = (p.stdout or b"").decode("utf-8", "replace").strip() \
            or (p.stderr or b"").decode("utf-8", "replace").strip()
    except Exception:
        suggestion = ""
    if not suggestion:
        print("copilot: inner Claude Code call failed")
        return 1
    c = _load_cache("copilot.json") or {"suggestions": []}
    c["suggestions"] = (c["suggestions"][-20:]) + [{
        "ts": time.strftime("%m-%d %H:%M"), "prompt": prompt,
        "suggestion": suggestion[:600], "project": os.path.basename(os.getcwd())}]
    _save_cache("copilot.json", c)
    if "--json" in args:
        print(json.dumps({"suggestion": suggestion[:600]}))
    else:
        print("IMPROVED PROMPT:\n\n" + suggestion[:600])
    return 0


# ---------- model efficacy ----------

def _scan_models(max_projects=14, per=6):
    """(session_id, model) for recent transcripts across all projects."""
    base = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(base):
        return []
    out = []
    dirs = sorted((os.path.join(base, p) for p in os.listdir(base)),
                  key=os.path.getmtime, reverse=True)
    for pd in dirs:
        if not os.path.isdir(pd):
            continue
        files = sorted((os.path.join(pd, x) for x in os.listdir(pd) if x.endswith(".jsonl")),
                       key=os.path.getmtime, reverse=True)[:per]
        for fp in files:
            model = None
            try:
                with open(fp, encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f):
                        if i > 150:
                            break
                        try:
                            o = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(o.get("message"), dict):
                            model = o["message"].get("model")
                        elif o.get("model"):
                            model = o["model"]
                        if model:
                            break
            except OSError:
                continue
            out.append({"sid": os.path.basename(fp)[:-6], "model": model or "unknown",
                        "ts": int(os.path.getmtime(fp))})
            if len(out) >= max_projects * per:
                return out
    return out


def _model_stats():
    """Aggregate failures (captures) and shields per model, all projects.
    Returns (rows, best_model) where rows is a list of dicts."""
    import collections
    inbox = os.path.expanduser("~/.claude/mistakes.jsonl")
    caps, shds = collections.defaultdict(int), collections.defaultdict(int)
    if os.path.isfile(inbox):
        for line in open(inbox, encoding="utf-8"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            sid = (e.get("session") or "")[:36]
            if e.get("shield"):
                shds[sid] += 1
            elif not e.get("reflex"):
                caps[sid] += 1
    agg = collections.defaultdict(lambda: {"sessions": 0, "captures": 0, "shields": 0})
    for s in _scan_models():
        a = agg[s["model"]]
        a["sessions"] += 1
        a["captures"] += caps.get(s["sid"], 0)
        a["shields"] += shds.get(s["sid"], 0)
    rows = []
    for m, a in agg.items():
        rows.append({"model": m, "sessions": a["sessions"], "captures": a["captures"],
                     "shields": a["shields"],
                     "rate": a["captures"] / a["sessions"] if a["sessions"] else 0})
    rows.sort(key=lambda r: -r["sessions"])
    cand = [r for r in rows if r["sessions"] >= 2]
    best = min(cand, key=lambda r: r["rate"])["model"] if cand else None
    return rows, best


def cmd_models():
    """Which model performs cleanest — failures per session, all projects."""
    rows, best = _model_stats()
    if not rows:
        print("no transcripts found yet")
        return 0
    print("MODEL EFFICACY — captured failures per session (recent ~84 sessions)")
    print(f"{'MODEL':<30} {'SESS':>5} {'FAILS':>6} {'RATE':>6} {'SHIELDS':>8}")
    for r in rows:
        mark = "  << top performer" if r["model"] == best else ""
        print(f"{r['model']:<30} {r['sessions']:>5} {r['captures']:>6} "
              f"{r['rate']:>6.2f} {r['shields']:>8}{mark}")
    return 0


def main():
    # never let a locale codepage break printing non-ASCII lessons or telemetry
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "search":
        return cmd_search(a[1:])
    if len(a) >= 2 and a[0] == "recall":
        return cmd_recall(a[1:])
    if a == ["stats"]:
        return cmd_stats()
    if a and a[0] == "preflight":
        return cmd_preflight(a[1:])
    if a and a[0] == "bootstrap":
        limit = int(a[a.index("--limit") + 1]) if "--limit" in a else 300
        return cmd_bootstrap(apply="--apply" in a, limit=limit)
    if a == ["project"]:
        return cmd_project()
    if a == ["models"]:
        return cmd_models()
    if a and a[0] == "copilot":
        return cmd_copilot(a[1:])
    if len(a) == 2 and a[0] == "save":
        return cmd_save(a[1])
    if a and a[0] == "inbox":
        return cmd_inbox(all_projects="--all" in a, clear="--clear" in a)
    if a == ["patterns"]:
        return cmd_patterns()
    if a == ["stale"]:
        return cmd_stale()
    if len(a) == 2 and a[0] == "graduate":
        return cmd_graduate(a[1])
    if a == ["env"]:
        return cmd_env()
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
