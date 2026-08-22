#!/usr/bin/env python3
"""Search and analyze learn-from-mistakes lessons logs.

Usage:
  python3 lessons.py search <keyword> [keyword...]   # match entries across both logs
  python3 lessons.py stats                           # counts, hot-spots, automation candidates

Reads the project log (.claude/LESSONS.md, found by walking up from cwd) and the
global log (~/.claude/LESSONS.md). Read-only: never modifies the logs.
"""
import os
import re
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


def parse_entries(path):
    """Yield dicts: {title, date, category, body} for each '### [date] title' block."""
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
                print(f"--- [{scope}] {e['category']} — [{e['date']}] {e['title']}")
                print(e["body"].rstrip() + "\n")
    if not hits:
        print(f"No entries matching: {' '.join(terms)}")
    return 0


def cmd_stats():
    logs = find_logs()
    if not logs:
        print("No lessons logs found (.claude/LESSONS.md or ~/.claude/LESSONS.md).")
        return 1
    for scope, path in logs:
        entries = parse_entries(path)
        print(f"== {scope} log: {path} — {len(entries)} entries")
        by_cat, by_sev = {}, {}
        candidates = []
        for e in entries:
            by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
            sev = field(e, "Severity") or "unspecified"
            by_sev[sev] = by_sev.get(sev, 0) + 1
            recurred = field(e, "Recurred")
            automation = field(e, "Automation")
            recur_count = len(re.findall(r"\d{4}-\d{2}-\d{2}", recurred))
            if (recur_count >= 1 or sev.lower().startswith("high")) and not automation:
                candidates.append((e, recur_count, sev))
        for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
            print(f"   {n:3d}  {cat}")
        print("   severity: " + ", ".join(f"{k}={v}" for k, v in sorted(by_sev.items())))
        if candidates:
            print("   AUTOMATION CANDIDATES (recurring or high-severity, no guard yet):")
            for e, rc, sev in candidates:
                print(f"     -> [{e['date']}] {e['title']} (recurrences: {rc}, severity: {sev})")
            print("   Graduate these up the ladder — see references/automation-ladder.md")
        print()
    return 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "search":
        return cmd_search(sys.argv[2:])
    if len(sys.argv) == 2 and sys.argv[1] == "stats":
        return cmd_stats()
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
