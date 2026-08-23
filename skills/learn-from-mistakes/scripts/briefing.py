#!/usr/bin/env python3
"""JARVIS morning briefing — yesterday's sitrep in ~10 lines.

Runs from the plugin's SessionStart hook (after the lessons injection), so every
session opens already briefed: threats intercepted, failures captured, lessons
logged, top failure zone, top model, inbox backlog.

Read-only, fast, never blocks (pure local file reads + one stats scan).
"""
import collections
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lessons as L  # noqa: E402


def load_events():
    p = os.path.expanduser("~/.claude/mistakes.jsonl")
    if not os.path.isfile(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def main():
    try:
        events = load_events()
        day = [e for e in events if time.time() - e.get("ts", 0) < 86400]
        shields = sum(1 for e in day if e.get("shield"))
        reflexes = sum(1 for e in day if e.get("reflex"))
        captures = sum(1 for e in day if not e.get("shield") and not e.get("reflex"))
        zones = collections.Counter(os.path.basename(e.get("project") or "?")
                                    for e in day if not e.get("shield") and not e.get("reflex"))
        top_zone, top_n = zones.most_common(1)[0] if zones else ("-", 0)

        lessons = []
        for scope, path in L.find_logs():
            lessons.extend(L.parse_entries(path))
        saves = sum(int(__import__("re").search(r"\d+", L.field(e, "Saves")).group())
                    if __import__("re").search(r"\d+", L.field(e, "Saves") or "") else 0
                    for e in lessons)
        today = time.strftime("%Y-%m-%d")
        new_today = sum(1 for e in lessons if e["date"].strip().endswith(today)
                        or today in L.field(e, "Recurred"))

        models, best = L._model_stats()
        if best:
            rate = next((f"{m['rate']:.2f}/s" for m in models if m["model"] == best), "?")
            mline = f"{best} ({rate})"
        else:
            mline = "-"

        print("=== JARVIS BRIEFING · last 24h ===")
        print(f"  threats intercepted: {shields}   failures captured: {captures}   reflexes: {reflexes}")
        print(f"  lessons: {len(lessons)} on file · {new_today} touched today · {saves} lifetime saves")
        print(f"  top failure zone: {top_zone} ({top_n})   top model: {mline}")
        print(f"  inbox backlog: {len(events)} raw events (triage with lessons.py inbox)")
        if shields:
            print("  NOTE: review shield firings — every interception is a save waiting to be counted.")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
