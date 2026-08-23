"""Command-level tests for lessons.py: save (the only LESSONS.md mutator),
search, stats, preflight, and bootstrap against a fixture git repo.
"""
import shutil
import subprocess

import pytest

import lessons as L
from conftest import write_lessons

LOG = """# Lessons Learned

## Cat

### [2026-01-01] first lesson about widgets
- **Severity:** low
- **Fix:** do X

### [2026-01-02] second lesson about gadgets
- **Severity:** high
- **Recurred:** 2026-01-10
- **Saves:** 2
"""


@pytest.fixture
def logfile(project):
    p = project / ".claude" / "LESSONS.md"
    write_lessons(p, LOG)
    return p


class TestSave:
    def test_inserts_saves_line_when_absent(self, logfile, capsys):
        assert L.cmd_save("widgets") == 0
        text = logfile.read_text(encoding="utf-8")
        first_block = text.split("### [2026-01-02]")[0]
        assert "- **Saves:** 1" in first_block
        assert "Recorded save #1" in capsys.readouterr().out

    def test_bumps_existing_saves_line(self, logfile, capsys):
        assert L.cmd_save("gadgets") == 0
        assert "- **Saves:** 3" in logfile.read_text(encoding="utf-8")
        out = capsys.readouterr().out
        assert "save #3" in out
        assert "graduating" in out  # 3+ saves suggests graduation

    def test_ambiguous_match_changes_nothing(self, logfile, capsys):
        before = logfile.read_text(encoding="utf-8")
        assert L.cmd_save("lesson") == 1
        assert logfile.read_text(encoding="utf-8") == before
        assert "more than one" in capsys.readouterr().out

    def test_no_match(self, logfile, capsys):
        assert L.cmd_save("nonexistent") == 1

    def test_no_project_log(self, project, capsys):
        assert L.cmd_save("anything") == 1


class TestSearch:
    def test_finds_matching_entry(self, logfile, capsys):
        assert L.cmd_search(["widgets"]) == 0
        assert "first lesson about widgets" in capsys.readouterr().out

    def test_all_terms_must_match(self, logfile, capsys):
        L.cmd_search(["widgets", "gadgets"])
        assert "No entries matching" in capsys.readouterr().out

    def test_no_logs_at_all(self, project, capsys):
        assert L.cmd_search(["anything"]) == 1


class TestStats:
    def test_counts_and_automation_candidates(self, logfile, capsys):
        assert L.cmd_stats() == 0
        out = capsys.readouterr().out
        assert "2 entries" in out
        # high-severity + recurred entry with no Automation line must be flagged
        assert "AUTOMATION CANDIDATES" in out
        assert "second lesson about gadgets" in out


class TestPreflight:
    def test_hits_on_explicit_files(self, project, capsys):
        write_lessons(project / ".claude" / "LESSONS.md",
                      "## Cat\n\n### [2026-01-01] migrations bite\n"
                      "- **Paths:** db/migrations/**\n"
                      "- **Prevention:** always run migrate --dry-run first\n")
        assert L.cmd_preflight(["db/migrations/0042_add_index.sql"]) == 0
        out = capsys.readouterr().out
        assert "migrations bite" in out
        assert "PREVENTION: always run migrate --dry-run first" in out

    def test_no_files_and_no_git_changes(self, project, capsys):
        assert L.cmd_preflight([]) == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestBootstrap:
    @pytest.fixture
    def repo(self, project):
        def git(*args):
            subprocess.run(
                ["git", "-c", "user.email=t@example.com", "-c", "user.name=T"] + list(args),
                cwd=str(project), check=True, capture_output=True)
        git("init")
        (project / "parser.py").write_text("x = 1\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "add parser")
        (project / "parser.py").write_text("x = 2\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "fix crash in parser")
        return project

    def test_dry_run_prints_drafts(self, repo, capsys):
        assert L.cmd_bootstrap(apply=False) == 0
        out = capsys.readouterr().out
        assert "DRAFT: repeated fixes" in out
        assert "Re-run with --apply" in out
        assert not (repo / ".claude" / "LESSONS.md").exists()

    def test_apply_writes_log_once(self, repo, capsys):
        assert L.cmd_bootstrap(apply=True) == 0
        text = (repo / ".claude" / "LESSONS.md").read_text(encoding="utf-8")
        assert "Bootstrapped From Git History" in text
        # a second --apply must refuse instead of appending duplicates
        assert L.cmd_bootstrap(apply=True) == 1

    def test_no_fix_commits(self, project, capsys):
        subprocess.run(["git", "init"], cwd=str(project), check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=T",
                        "commit", "--allow-empty", "-m", "add feature"],
                       cwd=str(project), check=True, capture_output=True)
        assert L.cmd_bootstrap(apply=False) == 0
        assert "No fix/revert-style commits" in capsys.readouterr().out
