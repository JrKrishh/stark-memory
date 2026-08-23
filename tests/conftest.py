"""Shared fixtures for the stark-memory test suite.

The scripts under test live in skills/learn-from-mistakes/scripts/ and are
plain modules (no package), so the scripts directory is put on sys.path here.
Every test runs against a throwaway HOME so nothing ever touches the real
~/.claude of whoever runs the suite.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "learn-from-mistakes" / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Isolated HOME with an empty ~/.claude; works on POSIX and Windows."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("JARVIS_INBOX", raising=False)
    monkeypatch.delenv("STARK_COPILOT", raising=False)
    monkeypatch.delenv("STARK_COPILOT_INNER", raising=False)
    return home


@pytest.fixture
def project(tmp_path, monkeypatch, fake_home):
    """A project directory with a .claude/ dir, chdir'd into."""
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    monkeypatch.chdir(proj)
    return proj


def write_lessons(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
