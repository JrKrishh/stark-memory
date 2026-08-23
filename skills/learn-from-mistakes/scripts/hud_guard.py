#!/usr/bin/env python3
"""HUD guard — ensures each user's private stark-memory HUD artifact is up.

Called from the plugin's SessionStart hook on every Claude Code session:
  1. computes the per-user port from the username (two users on one machine
     get two independent artifacts),
  2. checks /api/health; if the server is already up, does nothing,
  3. otherwise launches `hud.py --serve` detached, so it survives this
     session and keeps serving until it goes idle (self-exits).

Zero-cost when up; one small python process when down. Never blocks.
"""
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def user_port():
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    return 8787 + (sum(ord(c) for c in user) % 200)


def is_up(port, timeout=1.5):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",
                                    timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def launch(port):
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    kwargs = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  stdin=subprocess.DEVNULL, close_fds=True, cwd=HERE)
    if flags:
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, os.path.join(HERE, "hud.py"),
                      "--serve", "--port", str(port)], **kwargs)


def main():
    port = int(os.environ.get("STARK_HUD_PORT") or user_port())
    if not is_up(port):
        launch(port)
        for _ in range(20):
            time.sleep(0.5)
            if is_up(port, timeout=1.2):
                print(f"stark-hud artifact up at http://127.0.0.1:{port}", flush=True)
                return 0
        print("stark-hud did not come up; next session will retry", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
