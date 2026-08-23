"""End-to-end hook contract: every hook script, run exactly as Claude Code
runs it (subprocess, JSON on stdin), must exit 0 and emit either nothing or
valid hookSpecificOutput JSON — on good input, garbage input, and empty input.

The scripts are designed to swallow their own errors, so these tests are the
only place a broken hook ever becomes visible.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "learn-from-mistakes" / "scripts"
HOOKS = ["jarvis_inbox.py", "session_consult.py", "briefing.py", "copilot_hook.py"]

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


@pytest.fixture
def hook_env(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["JARVIS_INBOX"] = str(tmp_path / "mistakes.jsonl")
    env["STARK_TOAST"] = "0"
    env.pop("STARK_COPILOT", None)
    env.pop("STARK_COPILOT_INNER", None)
    return {"env": env, "home": home, "inbox": tmp_path / "mistakes.jsonl",
            "cwd": tmp_path}


def run_hook(script, stdin=b"", ctx=None, extra_env=None):
    env = dict(ctx["env"])
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=stdin, capture_output=True, env=env, cwd=str(ctx["cwd"]), timeout=60)


@pytest.mark.parametrize("script", HOOKS)
def test_empty_stdin_never_breaks_a_session(script, hook_env):
    p = run_hook(script, b"", hook_env)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("script", HOOKS)
def test_garbage_stdin_never_breaks_a_session(script, hook_env):
    p = run_hook(script, b"{{{not json \xff\xfe", hook_env)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")


def test_pretooluse_harmless_command_is_silent(hook_env):
    payload = {"hook_event_name": "PreToolUse", "cwd": str(hook_env["cwd"]),
               "tool_input": {"command": "ls -la"}}
    p = run_hook("jarvis_inbox.py", json.dumps(payload).encode(), hook_env)
    assert p.returncode == 0
    assert p.stdout.strip() == b""


def test_pretooluse_shield_asks_on_high_severity_match(hook_env):
    (hook_env["home"] / ".claude" / "LESSONS.md").write_text(HIGH_SEV_LOG, encoding="utf-8")
    payload = {"hook_event_name": "PreToolUse", "cwd": str(hook_env["cwd"]),
               "tool_input": {"command": "dropdb production"}}
    p = run_hook("jarvis_inbox.py", json.dumps(payload).encode(), hook_env)
    assert p.returncode == 0
    out = json.loads(p.stdout.decode("utf-8"))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "ask"  # never "deny" — the human decides
    assert "dropdb wiped production data" in hso["permissionDecisionReason"]


def test_posttoolusefailure_captures_to_inbox(hook_env):
    payload = {"hook_event_name": "PostToolUseFailure", "cwd": str(hook_env["cwd"]),
               "session_id": "sess-1",
               "tool_input": {"command": "pytest -x"},
               "error": "Exit code 2\nassertion failed"}
    p = run_hook("jarvis_inbox.py", json.dumps(payload).encode(), hook_env)
    assert p.returncode == 0
    events = [json.loads(l) for l in
              hook_env["inbox"].read_text(encoding="utf-8").splitlines()]
    assert events[0]["cmd"] == "pytest -x"
    assert events[0]["exit_code"] == 2


def test_posttoolusefailure_reflex_injects_logged_fix(hook_env):
    (hook_env["home"] / ".claude" / "LESSONS.md").write_text(HIGH_SEV_LOG, encoding="utf-8")
    payload = {"hook_event_name": "PostToolUseFailure", "cwd": str(hook_env["cwd"]),
               "tool_input": {"command": "dropdb production"},
               "error": "Exit code 1\ncould not connect"}
    p = run_hook("jarvis_inbox.py", json.dumps(payload).encode(), hook_env)
    assert p.returncode == 0
    out = json.loads(p.stdout.decode("utf-8"))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PostToolUseFailure"
    assert "restore from snapshot" in hso["additionalContext"]


def test_session_consult_injects_global_log_without_project_log(hook_env):
    # Regression for the cold-start bug: global lessons must appear even when
    # the project has no .claude/LESSONS.md of its own.
    (hook_env["home"] / ".claude" / "LESSONS.md").write_text(
        "## Cat\n\n### [2026-01-01] global lesson café exists\n- **Severity:** low\n",
        encoding="utf-8")
    p = run_hook("session_consult.py", b"", hook_env)
    assert p.returncode == 0
    # strict decode: hooks must emit UTF-8 regardless of the locale codepage
    out = p.stdout.decode("utf-8")
    assert "Global lessons" in out
    assert "global lesson café exists" in out


def test_briefing_runs_on_empty_state(hook_env):
    p = run_hook("briefing.py", b"", hook_env)
    assert p.returncode == 0
    assert "JARVIS BRIEFING" in p.stdout.decode("utf-8")


def test_copilot_disabled_by_default_is_silent(hook_env):
    payload = {"prompt": "please refactor the parser module for clarity"}
    p = run_hook("copilot_hook.py", json.dumps(payload).encode(), hook_env)
    assert p.returncode == 0
    assert p.stdout.strip() == b""


def test_copilot_skips_short_and_long_prompts(hook_env):
    for prompt in ("hi", "x" * 400):
        p = run_hook("copilot_hook.py", json.dumps({"prompt": prompt}).encode(),
                     hook_env, extra_env={"STARK_COPILOT": "1"})
        assert p.returncode == 0
        assert p.stdout.strip() == b""


def test_copilot_recursion_guard(hook_env):
    payload = {"prompt": "please refactor the parser module for clarity"}
    p = run_hook("copilot_hook.py", json.dumps(payload).encode(), hook_env,
                 extra_env={"STARK_COPILOT": "1", "STARK_COPILOT_INNER": "1"})
    assert p.returncode == 0
    assert p.stdout.strip() == b""


def test_copilot_throttle_suppresses_suggestion(hook_env):
    # A fresh stamp file means the 90s throttle is active -> instant silent exit
    # (also keeps the test from spawning an inner `claude -p` call).
    stamp = hook_env["home"] / ".claude" / "stark-cache" / "copilot.throttle"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("now", encoding="utf-8")
    payload = {"prompt": "please refactor the parser module for clarity"}
    p = run_hook("copilot_hook.py", json.dumps(payload).encode(), hook_env,
                 extra_env={"STARK_COPILOT": "1"})
    assert p.returncode == 0
    assert p.stdout.strip() == b""


def test_non_ascii_payload_roundtrip(hook_env):
    payload = {"hook_event_name": "PostToolUseFailure", "cwd": str(hook_env["cwd"]),
               "tool_input": {"command": "grep café résumé.txt"},
               "error": "Exit code 1\nno match: café"}
    p = run_hook("jarvis_inbox.py", json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                 hook_env)
    assert p.returncode == 0
    events = [json.loads(l) for l in
              hook_env["inbox"].read_text(encoding="utf-8").splitlines()]
    assert "café" in events[0]["cmd"]
