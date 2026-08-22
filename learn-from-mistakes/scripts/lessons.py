#!/usr/bin/env python3
"""Search, analyze, and grow learn-from-mistakes lessons logs.

Usage:
  python3 lessons.py search <keyword> [keyword...]     # match entries across both logs
  python3 lessons.py stats                             # counts, hot-spots, automation candidates
  python3 lessons.py preflight [file...]               # lessons relevant to files you're about to touch
                                                       #   (no args: uses git diff + staged changes)
  python3 lessons.py bootstrap [--apply] [--limit N]   # draft lessons from the repo's git history
  python3 lessons.py save <title-substring>            # record that a lesson just prevented a repeat (ROI)
  python3 lessons.py env                               # print an environment fingerprint for Env: lines

Reads the project log (.claude/LESSONS.md, found by walking up from cwd) and the
global log (~/.claude/LESSONS.md). Only `save` and `bootstrap --apply` write, and
only to the project log.
"""
import fnmatch
import os
import re
import subprocess
import sys


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


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "search":
        return cmd_search(a[1:])
    if a == ["stats"]:
        return cmd_stats()
    if a and a[0] == "preflight":
        return cmd_preflight(a[1:])
    if a and a[0] == "bootstrap":
        limit = int(a[a.index("--limit") + 1]) if "--limit" in a else 300
        return cmd_bootstrap(apply="--apply" in a, limit=limit)
    if len(a) == 2 and a[0] == "save":
        return cmd_save(a[1])
    if a == ["env"]:
        return cmd_env()
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
