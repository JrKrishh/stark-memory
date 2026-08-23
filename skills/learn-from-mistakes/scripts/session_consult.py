#!/usr/bin/env python3
"""Session consult — inject project knowledge at session start.

Walks UP from cwd to find the nearest .claude/LESSONS.md and
.claude/stark-project.md (so sessions nested inside monorepos still see the
workspace's scars and scope), then the global log. Each source capped at 4000
chars — context is a budget; deeper queries go through lessons.py search/recall.
"""
import os
import sys
from pathlib import Path


def find_up(name):
    d = Path.cwd().resolve()
    while True:
        p = d / ".claude" / name
        if p.is_file():
            return p
        if d.parent == d:
            return None
        d = d.parent


def emit(label, path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return
    print(f"=== {label}: {path} ===")
    print(text)


def main():
    try:
        emit("Lessons log", find_up("LESSONS.md"))
        emit("Project manifest", find_up("stark-project.md"))
        g = Path.home() / ".claude" / "LESSONS.md"
        if g.is_file():
            emit("Global lessons", g)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
