"""session_consult.py — the SessionStart injection.

Includes the regression test for the bug where a missing project log
(emit called with None) silently aborted the remaining emits, so the global
~/.claude/LESSONS.md was never injected in cold-start projects.
"""
import session_consult as sc
from conftest import write_lessons

GLOBAL = "# Lessons Learned\n\n## Cat\n\n### [2026-01-01] global lesson exists\n- **Severity:** high\n"
PROJECT = "# Lessons Learned\n\n## Cat\n\n### [2026-01-02] project lesson exists\n- **Severity:** low\n"


def test_emit_none_is_noop(capsys):
    sc.emit("Lessons log", None)
    assert capsys.readouterr().out == ""


def test_global_only_is_still_injected(fake_home, tmp_path, monkeypatch, capsys):
    # Regression: no project log anywhere, but a global log exists.
    bare = tmp_path / "bare-project"
    bare.mkdir()
    monkeypatch.chdir(bare)
    write_lessons(fake_home / ".claude" / "LESSONS.md", GLOBAL)
    assert sc.main() == 0
    out = capsys.readouterr().out
    assert "Global lessons" in out
    assert "global lesson exists" in out


def test_project_and_global_both_injected(project, fake_home, capsys):
    write_lessons(project / ".claude" / "LESSONS.md", PROJECT)
    write_lessons(fake_home / ".claude" / "LESSONS.md", GLOBAL)
    assert sc.main() == 0
    out = capsys.readouterr().out
    assert "project lesson exists" in out
    assert "global lesson exists" in out
    assert out.index("Lessons log") < out.index("Global lessons")


def test_manifest_injected(project, capsys):
    write_lessons(project / ".claude" / "stark-project.md", "# proj — mission\n\n## Purpose\nShip it.\n")
    assert sc.main() == 0
    out = capsys.readouterr().out
    assert "Project manifest" in out
    assert "Ship it." in out


def test_find_up_from_nested_dir(project, monkeypatch):
    write_lessons(project / ".claude" / "LESSONS.md", PROJECT)
    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    found = sc.find_up("LESSONS.md")
    assert found is not None and found.read_text(encoding="utf-8") == PROJECT


def test_each_source_capped_at_4000_chars(project, capsys):
    write_lessons(project / ".claude" / "LESSONS.md", "x" * 10000)
    sc.main()
    out = capsys.readouterr().out
    assert out.count("x") == 4000


def test_nothing_anywhere_is_quiet_success(fake_home, tmp_path, monkeypatch, capsys):
    bare = tmp_path / "empty-project"
    bare.mkdir()
    monkeypatch.chdir(bare)
    assert sc.main() == 0
    assert capsys.readouterr().out == ""
