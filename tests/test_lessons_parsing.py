"""Parsing core of lessons.py: parse_entries, field, find_logs, glob matching.

Everything else in the plugin (every command, both hooks, the briefing)
consumes these functions, so this is the foundation of the suite.
"""
import lessons as L
from conftest import write_lessons

SAMPLE = """# Lessons Learned

## Build & Tooling

### [2026-01-01] pip install failed on café package
- **Severity:** medium
- **Paths:** src/**, docs/*.md
- **Trigger:** installing deps
- **What happened:** wheels missing for utils.py helpers
- **Root cause:** wrong index url
- **Fix:** use the internal index
- **Prevention:** pin the index-url in pip.conf
- **Saves:** 2

## Destructive Operations

### [2026-01-05] dropdb wiped production data
- **Severity:** high
- **Trigger:** running dropdb against production
- **What happened:** dropdb production ran against the live cluster
- **Root cause:** stale DATABASE_URL in shell profile
- **Fix:** restore from snapshot
- **Prevention:** check DATABASE_URL before any dropdb
"""


def _entries(tmp_path):
    p = tmp_path / "LESSONS.md"
    write_lessons(p, SAMPLE)
    return L.parse_entries(str(p))


class TestParseEntries:
    def test_finds_all_entries(self, tmp_path):
        entries = _entries(tmp_path)
        assert len(entries) == 2
        assert entries[0]["title"] == "pip install failed on café package"
        assert entries[1]["title"] == "dropdb wiped production data"

    def test_dates_and_categories(self, tmp_path):
        entries = _entries(tmp_path)
        assert entries[0]["date"] == "2026-01-01"
        assert entries[0]["category"] == "Build & Tooling"
        assert entries[1]["category"] == "Destructive Operations"

    def test_body_accumulates_until_next_heading(self, tmp_path):
        first, second = _entries(tmp_path)
        assert "**Saves:** 2" in first["body"]
        assert "dropdb" not in first["body"]
        # last entry runs to EOF
        assert "restore from snapshot" in second["body"]

    def test_entry_without_category_is_uncategorized(self, tmp_path):
        p = tmp_path / "LESSONS.md"
        write_lessons(p, "### [2026-02-02] orphan entry\n- **Severity:** low\n")
        entries = L.parse_entries(str(p))
        assert entries[0]["category"] == "Uncategorized"

    def test_empty_file(self, tmp_path):
        p = tmp_path / "LESSONS.md"
        write_lessons(p, "")
        assert L.parse_entries(str(p)) == []


class TestField:
    def test_extracts_value(self, tmp_path):
        e = _entries(tmp_path)[0]
        assert L.field(e, "Severity") == "medium"
        assert L.field(e, "Paths") == "src/**, docs/*.md"

    def test_case_insensitive(self, tmp_path):
        e = _entries(tmp_path)[0]
        assert L.field(e, "severity") == "medium"

    def test_missing_field_is_empty(self, tmp_path):
        e = _entries(tmp_path)[0]
        assert L.field(e, "Automation") == ""


class TestFindLogs:
    def test_project_and_global(self, project, fake_home):
        write_lessons(project / ".claude" / "LESSONS.md", SAMPLE)
        write_lessons(fake_home / ".claude" / "LESSONS.md", SAMPLE)
        logs = L.find_logs()
        assert [scope for scope, _ in logs] == ["project", "global"]

    def test_walks_up_from_nested_cwd(self, project, monkeypatch):
        write_lessons(project / ".claude" / "LESSONS.md", SAMPLE)
        nested = project / "src" / "deep"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        logs = L.find_logs()
        assert logs and logs[0][0] == "project"

    def test_global_not_duplicated_when_cwd_is_home(self, fake_home, monkeypatch):
        write_lessons(fake_home / ".claude" / "LESSONS.md", SAMPLE)
        monkeypatch.chdir(fake_home)
        logs = L.find_logs()
        assert len(logs) == 1  # same file must not appear as project AND global

    def test_no_logs_anywhere(self, project):
        assert L.find_logs() == []


class TestEntryMatchesFiles:
    def test_paths_glob_match(self, tmp_path):
        e = _entries(tmp_path)[0]
        reasons = L.entry_matches_files(e, ["src/app/main.py"])
        assert any("Paths glob" in r for r in reasons)

    def test_filename_mentioned_in_body(self, tmp_path):
        e = _entries(tmp_path)[0]  # body mentions utils.py
        reasons = L.entry_matches_files(e, ["lib/utils.py"])
        assert any("mentioned" in r for r in reasons)

    def test_no_match(self, tmp_path):
        e = _entries(tmp_path)[0]
        assert L.entry_matches_files(e, ["unrelated/thing.go"]) == []
