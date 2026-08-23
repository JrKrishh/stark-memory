"""briefing.py — the SessionStart sitrep: 24h windowing, event
classification (shield/reflex/capture), and resilience to corrupt telemetry.
"""
import json
import time

import briefing
from conftest import write_lessons


def write_events(fake_home, events, extra_raw=""):
    p = fake_home / ".claude" / "mistakes.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n" + extra_raw,
                 encoding="utf-8")
    return p


def test_classifies_last_24h_events(fake_home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    now = int(time.time())
    write_events(fake_home, [
        {"ts": now - 100, "project": "/w/alpha", "shield": True, "lesson": "L"},
        {"ts": now - 200, "project": "/w/alpha", "reflex": True, "lesson": "L"},
        {"ts": now - 300, "project": "/w/alpha", "cmd": "pytest", "exit_code": 1, "error": "Exit code 1"},
        {"ts": now - 90000, "project": "/w/alpha", "cmd": "old", "exit_code": 1, "error": "Exit code 1"},
    ])
    assert briefing.main() == 0
    out = capsys.readouterr().out
    assert "threats intercepted: 1" in out
    assert "failures captured: 1" in out  # the day-old capture is out of window
    assert "reflexes: 1" in out
    assert "top failure zone: alpha (1)" in out
    assert "inbox backlog: 4 raw events" in out  # backlog counts everything
    assert "review shield firings" in out


def test_corrupt_lines_are_skipped(fake_home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    now = int(time.time())
    write_events(fake_home,
                 [{"ts": now - 10, "project": "/w/beta", "cmd": "x",
                   "exit_code": 1, "error": "Exit code 1"}],
                 extra_raw="{not json at all\n")
    assert briefing.main() == 0
    assert "failures captured: 1" in capsys.readouterr().out


def test_counts_lessons_and_saves(project, capsys):
    write_lessons(project / ".claude" / "LESSONS.md",
                  "## Cat\n\n### [2026-01-01] a lesson\n- **Saves:** 4\n\n"
                  "### [2026-01-02] another lesson\n- **Severity:** low\n")
    assert briefing.main() == 0
    out = capsys.readouterr().out
    assert "lessons: 2 on file" in out
    assert "4 lifetime saves" in out


def test_empty_state_never_crashes(fake_home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert briefing.main() == 0
    out = capsys.readouterr().out
    assert "JARVIS BRIEFING" in out
    assert "none qualified" in out  # no model has flight hours yet


def test_mission_line_from_manifest(project, capsys):
    write_lessons(project / ".claude" / "stark-project.md",
                  "# proj — keep the lights on\n\n## Purpose\nUptime.\n")
    assert briefing.main() == 0
    assert "mission: proj — keep the lights on" in capsys.readouterr().out
