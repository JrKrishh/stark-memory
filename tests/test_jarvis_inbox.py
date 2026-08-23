"""jarvis_inbox.py — capture, dedup/trim/locking, reflex, and shield.

These run on every Bash command and every failure in a live session, and the
hook swallows its own errors by design, so regressions here are silent in
production. The false-positive strictness rules (MIN_HITS, failure-side text
only, severity and Paths gating) each get an explicit regression test.
"""
import json
import time

import pytest

import jarvis_inbox as ji
import lessons as L
from conftest import write_lessons

HIGH_SEV_LOG = """# Lessons Learned

## Destructive Operations

### [2026-01-05] dropdb wiped production data
- **Severity:** high
- **Trigger:** running dropdb against production
- **What happened:** dropdb production ran against the live cluster
- **Root cause:** stale DATABASE_URL in shell profile
- **Fix:** restore from snapshot
- **Prevention:** check DATABASE_URL before any dropdb
"""

BUILD_SH_LOG = """# Lessons Learned

## Build & Tooling

### [2026-01-08] bare build.sh corrupted artifacts
- **Severity:** medium
- **Trigger:** running ./build.sh directly
- **What happened:** artifacts corrupted because preconditions were skipped
- **Root cause:** the script assumes a clean dist directory
- **Fix:** use make target instead, it cleans dist first
- **Prevention:** always go through the make target, never bare build.sh
"""


@pytest.fixture
def inbox(tmp_path, monkeypatch):
    p = tmp_path / "inboxdir" / "mistakes.jsonl"
    monkeypatch.setattr(ji, "INBOX", p)
    monkeypatch.setattr(ji, "_toast", lambda *a, **k: None)
    return p


def read_events(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class TestTokens:
    def test_stopwords_and_short_chunks_dropped(self):
        toks = ji._tokens("python3 git push --all")
        assert "python3" not in toks and "git" not in toks
        assert "all" not in toks  # 3 chars after stripping the dashes
        assert "push" in toks

    def test_compound_chunk_survives_whole_and_split(self):
        toks = ji._tokens("./build.sh --verbose")
        assert "build.sh" in toks
        assert "build" in toks

    def test_empty_command(self):
        assert ji._tokens("") == set()


class TestFailureTextAndMatching:
    def test_failure_text_excludes_fix_and_prevention(self, project):
        write_lessons(project / ".claude" / "LESSONS.md", BUILD_SH_LOG)
        _, e = next(iter(list(ji_entries())))
        text = ji._failure_text(L, e).lower()
        assert "build.sh" in text
        assert "make" not in text  # the SAFE alternative must not be matchable

    def test_safe_alternative_does_not_trigger_match(self, project):
        # Regression: a lesson whose Fix says "use make target" must not make
        # the shield/reflex fire on the make command itself.
        write_lessons(project / ".claude" / "LESSONS.md", BUILD_SH_LOG)
        best, hits = ji._best_match(ji._tokens("make target"))
        assert best is None

    def test_failing_command_itself_does_match(self, project):
        write_lessons(project / ".claude" / "LESSONS.md", BUILD_SH_LOG)
        best, hits = ji._best_match(ji._tokens("./build.sh"))
        assert best is not None and best["title"].startswith("bare build.sh")
        assert hits >= ji.MIN_HITS

    def test_single_token_hit_is_not_enough(self, project):
        write_lessons(project / ".claude" / "LESSONS.md", HIGH_SEV_LOG)
        best, hits = ji._best_match(ji._tokens("dropdb"))
        assert best is None and hits == 0

    def test_two_token_hits_match(self, project):
        write_lessons(project / ".claude" / "LESSONS.md", HIGH_SEV_LOG)
        best, _ = ji._best_match(ji._tokens("dropdb production"))
        assert best is not None and "dropdb" in best["title"]


def ji_entries():
    for scope, path in L.find_logs():
        for e in L.parse_entries(path):
            yield scope, e


class TestStore:
    def entry(self, ts, cmd="pytest -x", code=1, err="Exit code 1\nboom"):
        return {"ts": ts, "project": "/p", "session": "s",
                "cmd": cmd, "exit_code": code, "error": err}

    def test_append_and_read_back(self, inbox):
        assert ji._store(self.entry(1000)) is True
        assert read_events(inbox)[0]["cmd"] == "pytest -x"

    def test_dedup_same_signature_within_window(self, inbox):
        assert ji._store(self.entry(1000)) is True
        assert ji._store(self.entry(1000 + ji.DEDUP_SECS - 1)) is False
        assert len(read_events(inbox)) == 1

    def test_same_signature_after_window_is_kept(self, inbox):
        ji._store(self.entry(1000))
        assert ji._store(self.entry(1000 + ji.DEDUP_SECS + 1)) is True
        assert len(read_events(inbox)) == 2

    def test_different_first_error_line_is_distinct(self, inbox):
        # the signature keys on the FIRST line of the error: a flaky command
        # failing differently on retry is a distinct signal, not a duplicate
        ji._store(self.entry(1000))
        assert ji._store(self.entry(1001, err="Exit code 1: connection refused\nboom")) is True
        assert len(read_events(inbox)) == 2

    def test_dedup_false_always_stores(self, inbox):
        ji._store(self.entry(1000))
        assert ji._store(self.entry(1001), dedup=False) is True

    def test_trims_to_keep_lines_when_over_cap(self, inbox):
        inbox.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(self.entry(i, cmd="cmd%d" % i)) for i in range(ji.MAX_LINES - 1)]
        inbox.write_text("\n".join(lines) + "\n", encoding="utf-8")
        newest = self.entry(999999, cmd="the-newest")
        assert ji._store(newest) is True
        events = read_events(inbox)
        assert len(events) == ji.KEEP_LINES
        assert events[-1]["cmd"] == "the-newest"


class TestLock:
    def test_acquire_and_release(self, inbox):
        inbox.parent.mkdir(parents=True, exist_ok=True)
        assert ji._acquire_lock(deadline_s=1) is True
        lock = inbox.parent / (inbox.name + ".lock")
        assert lock.is_dir()
        lock.rmdir()

    def test_fresh_lock_times_out(self, inbox):
        inbox.parent.mkdir(parents=True, exist_ok=True)
        lock = inbox.parent / (inbox.name + ".lock")
        lock.mkdir()
        assert ji._acquire_lock(deadline_s=0.2) is False

    def test_stale_lock_is_reclaimed(self, inbox):
        import os
        inbox.parent.mkdir(parents=True, exist_ok=True)
        lock = inbox.parent / (inbox.name + ".lock")
        lock.mkdir()
        old = time.time() - 60  # older than the 15s staleness cutoff
        os.utime(str(lock), (old, old))
        assert ji._acquire_lock(deadline_s=2) is True
        lock.rmdir()

    def test_store_fails_open_without_lock(self, inbox):
        # capture must never stall or lose the event just because the lock is held
        inbox.parent.mkdir(parents=True, exist_ok=True)
        (inbox.parent / (inbox.name + ".lock")).mkdir()
        ji_orig = ji._acquire_lock
        try:
            ji._acquire_lock = lambda deadline_s=5.0: ji_orig(deadline_s=0.1)
            assert ji._store({"ts": 1, "project": "/p", "cmd": "x",
                              "exit_code": 1, "error": "Exit code 1"}) is True
        finally:
            ji._acquire_lock = ji_orig
        assert len(read_events(inbox)) == 1


class TestCapture:
    def test_normal_failure_is_stored(self, inbox, project):
        cmd, err = ji.capture({"tool_input": {"command": "pytest -x"},
                               "error": "Exit code 2\nassertion failed",
                               "cwd": str(project), "session_id": "abc"})
        assert cmd == "pytest -x"
        e = read_events(inbox)[0]
        assert e["exit_code"] == 2
        assert e["session"] == "abc"

    def test_interrupt_is_not_a_mistake(self, inbox):
        cmd, err = ji.capture({"is_interrupt": True,
                               "tool_input": {"command": "sleep 100"}})
        assert cmd is None
        assert not inbox.exists()

    def test_no_command_no_event(self, inbox):
        cmd, _ = ji.capture({"tool_input": {}, "error": "Exit code 1"})
        assert cmd is None
        assert not inbox.exists()

    def test_error_truncated_to_tail(self, inbox, project):
        ji.capture({"tool_input": {"command": "x" * 500},
                    "error": "Exit code 1\n" + "y" * 2000, "cwd": str(project)})
        e = read_events(inbox)[0]
        assert len(e["error"]) == ji.TAIL
        assert len(e["cmd"]) == 300

    def test_missing_exit_code_line(self, inbox, project):
        ji.capture({"tool_input": {"command": "run thing"},
                    "error": "something exploded", "cwd": str(project)})
        assert read_events(inbox)[0]["exit_code"] is None


class TestReflex:
    def test_injects_logged_fix_on_match(self, inbox, project):
        write_lessons(project / ".claude" / "LESSONS.md", BUILD_SH_LOG)
        msg = ji.reflex("./build.sh", str(project))
        assert msg is not None
        assert "bare build.sh corrupted artifacts" in msg
        assert "Known fix:" in msg
        assert "Prevention rule:" in msg
        # every firing is recorded as telemetry
        assert any(e.get("reflex") for e in read_events(inbox))

    def test_no_match_no_injection(self, inbox, project):
        write_lessons(project / ".claude" / "LESSONS.md", BUILD_SH_LOG)
        assert ji.reflex("kubectl get pods", str(project)) is None
        assert not inbox.exists()


class TestShield:
    def test_fires_on_high_severity_match(self, inbox, project):
        write_lessons(project / ".claude" / "LESSONS.md", HIGH_SEV_LOG)
        reason = ji.shield("dropdb production", str(project))
        assert reason is not None
        assert "HIGH severity" in reason
        assert "check DATABASE_URL" in reason
        assert any(e.get("shield") for e in read_events(inbox))

    def test_medium_severity_stays_advisory(self, inbox, project):
        write_lessons(project / ".claude" / "LESSONS.md", BUILD_SH_LOG)
        assert ji.shield("./build.sh", str(project)) is None

    def test_paths_scoping_blocks_wrong_neighborhood(self, inbox, project):
        scoped = HIGH_SEV_LOG.replace("- **Severity:** high",
                                      "- **Severity:** high\n- **Paths:** src/**")
        write_lessons(project / ".claude" / "LESSONS.md", scoped)
        # no src/ files here -> shape match alone must not fire
        assert ji.shield("dropdb production", str(project)) is None
        # once the neighborhood exists, it fires
        (project / "src").mkdir()
        (project / "src" / "db.py").write_text("x\n", encoding="utf-8")
        assert ji.shield("dropdb production", str(project)) is not None

    def test_no_lessons_no_shield(self, inbox, project):
        assert ji.shield("dropdb production", str(project)) is None
