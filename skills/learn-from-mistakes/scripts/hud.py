#!/usr/bin/env python3
"""stark-memory HUD v2 — full J.A.R.V.I.S. deck.

Reads telemetry inbox + lesson logs + Claude Code session transcripts and
renders ~/.claude/stark-hud.html from hud_template.html (same folder).

Usage:
  python hud.py                 # render once
  python hud.py --watch [secs]  # rebuild every N seconds (default 5)
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lessons as L  # noqa: E402

HERE = Path(__file__).resolve().parent
INBOX = Path(os.environ.get("JARVIS_INBOX") or Path.home() / ".claude" / "mistakes.jsonl")
OUT = Path(os.environ.get("STARK_HUD_OUT") or Path.home() / ".claude" / "stark-hud.html")
PROJECTS_DIR = Path.home() / ".claude" / "projects"
REFRESH = 5


# ---------------- data ----------------
def load_events():
    if not INBOX.exists():
        return []
    out = []
    for line in INBOX.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return sorted(out, key=lambda x: x.get("ts", 0))


def kind(e):
    return "shield" if e.get("shield") else ("reflex" if e.get("reflex") else "capture")


def load_lessons():
    out = []
    for scope, path in L.find_logs():
        for e in L.parse_entries(path):
            saves = re.search(r"\d+", L.field(e, "Saves") or "")
            out.append({"scope": scope, "date": e["date"], "title": e["title"],
                        "severity": (L.field(e, "Severity") or "-").lower(),
                        "saves": int(saves.group()) if saves else 0,
                        "automation": bool(L.field(e, "Automation"))})
    return out


def env_fingerprint():
    import platform
    import subprocess
    bits = {"os": f"{platform.system()} {platform.release()}"}
    for tool in ("python", "node", "git", "docker"):
        try:
            p = subprocess.run([tool, "--version"], capture_output=True,
                               timeout=4, text=True)
            v = (p.stdout + p.stderr).strip().splitlines()[0]
            bits[tool] = re.sub(r"^[^0-9]*", "", v).split()[0].rstrip(",;")
        except Exception:
            bits[tool] = "-"
    return bits


def plugin_version():
    base = Path.home() / ".claude" / "plugins" / "cache"
    for pj in base.glob("**/.claude-plugin/plugin.json"):
        try:
            d = json.loads(pj.read_text(encoding="utf-8"))
            if d.get("name") == "stark-memory":
                return d.get("version", "?")
        except Exception:
            continue
    return "-"


def pretty_slug(slug):
    m = re.match(r"^([A-Za-z])--(.*)$", slug)
    if m:
        return m.group(1) + ":\\" + m.group(2).replace("-", "\\")
    return slug


def load_transcripts(per_project=6, max_projects=14):
    """Newest Claude Code sessions from ~/.claude/projects/<slug>/<uuid>.jsonl"""
    if not PROJECTS_DIR.exists():
        return []
    out = []
    projs = sorted(PROJECTS_DIR.iterdir(),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:max_projects]
    for pd in projs:
        files = sorted(pd.glob("*.jsonl"),
                       key=lambda f: f.stat().st_mtime, reverse=True)[:per_project]
        for f in files:
            try:
                st = f.stat()
                cwd = ""
                with f.open(encoding="utf-8", errors="replace") as fh:
                    head = fh.readline()
                if head.strip():
                    cwd = json.loads(head).get("cwd", "")[:60]
                out.append({"sid": f.stem[:8], "slug": pd.name,
                            "project": pretty_slug(pd.name), "cwd": cwd,
                            "ts": int(st.st_mtime),
                            "size_kb": max(1, st.st_size // 1024)})
            except Exception:
                continue
    return out


def merge_sessions(events, transcripts):
    """Telemetry grouped per session-id, enriched by transcript metadata."""
    tel = {}
    order = {}
    for i, e in enumerate(events):
        sid = (e.get("session") or "????????")[:8]
        s = tel.setdefault(sid, {"sid": sid, "events": [], "shields": 0,
                                 "reflexes": 0, "captures": 0,
                                 "first": e.get("ts", 0), "last": e.get("ts", 0),
                                 "project": os.path.basename(e.get("project") or "?"),
                                 "cmds": []})
        s["events"].append(e)
        k = kind(e)
        key = {"shield": "shields", "reflex": "reflexes", "capture": "captures"}[k]
        s[key] += 1
        s["last"] = max(s["last"], e.get("ts", 0))
        label = e.get("cmd") or e.get("lesson") or "?"
        if len(s["cmds"]) < 8:
            s["cmds"].append({"k": k, "label": label[:90],
                              "t": time.strftime("%H:%M:%S", time.localtime(e.get("ts", 0)))})
        order.setdefault(sid, i)

    tr_by_sid = {t["sid"]: t for t in transcripts}
    sessions = list(tel.values())
    seen = set(tel.keys())
    for t in transcripts:
        if t["sid"] not in seen:
            sessions.append({"sid": t["sid"], "events": [], "shields": 0,
                             "reflexes": 0, "captures": 0, "first": t["ts"],
                             "last": t["ts"], "project": t["project"],
                             "cmds": [], **{k: 0 for k in ()}})
            sessions[-1]["transcript"] = t
    for s in sessions:
        t = tr_by_sid.get(s["sid"])
        if t:
            s["transcript"] = t
            if not s["cmds"]:
                s["project"] = t["project"]
    sessions.sort(key=lambda s: -s["last"])
    return sessions, tr_by_sid


def build_projects(events, transcripts):
    agg = {}
    for e in events:
        p = os.path.basename(e.get("project") or "?")
        a = agg.setdefault(p, {"name": p, "captures": 0, "shields": 0,
                               "reflexes": 0, "last": 0})
        a[{"shield": "shields", "reflex": "reflexes", "capture": "captures"}[kind(e)]] += 1
        a["last"] = max(a["last"], e.get("ts", 0))
    for t in transcripts:
        key = os.path.basename(t["project"]) or t["project"]
        a = agg.setdefault(key, {"name": os.path.basename(t["project"]),
                                 "captures": 0, "shields": 0, "reflexes": 0,
                                 "last": 0})
        a["last"] = max(a["last"], t["ts"])
        a.setdefault("path", t["project"])
    for a in agg.values():
        a["total"] = a["captures"] + a["shields"] + a["reflexes"]
    return sorted(agg.values(), key=lambda a: -a["last"])[:10]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def fmt_age(ts):
    if not ts:
        return "-"
    d = time.time() - ts
    if d < 90: return f"{int(d)}s"
    if d < 5400: return f"{int(d // 60)}m"
    if d < 172800: return f"{int(d // 3600)}h"
    return f"{int(d // 86400)}d"


# ---------------- render ----------------
def render():
    events = load_events()
    lessons = load_lessons()
    transcripts = load_transcripts()
    sessions, _ = merge_sessions(events, transcripts)
    projects = build_projects(events, transcripts)
    env = env_fingerprint()

    caps = sum(1 for e in events if kind(e) == "capture")
    n_sh = sum(1 for e in events if kind(e) == "shield")
    n_rf = sum(1 for e in events if kind(e) == "reflex")
    saves = sum(l["saves"] for l in lessons)
    high_open = sum(1 for l in lessons if l["severity"].startswith("high") and not l["automation"])

    if n_sh:
        posture, pcolor, sub = f"{n_sh} THREATS INTERCEPTED", "#ff6b5e", "the suit is holding the line"
    elif high_open:
        posture, pcolor, sub = "GUARDS PENDING", "#ffd166", f"{high_open} high-severity lesson(s) still advisory"
    else:
        posture, pcolor = ("QUIET SKIES", "#7de8ff") if not events else ("ALL SYSTEMS NOMINAL", "#9fe8b4")
        sub = "no hostile activity on record"

    rs = min(n_sh * 30, 340); rr = min(n_rf * 20, 340); rv = min(saves * 40, 340)

    proj_cards = []
    for p in projects:
        tot = max(p["total"], 1)
        dot = "g" if (time.time() - p["last"] < 86400 and p["last"]) else ("a" if p["last"] else "x")
        proj_cards.append(f"""
<div class="pcard">
  <div class="prow"><span class="dot {dot}"></span>
    <b class="pname">{esc(p['name'][:24])}</b>
    <span class="page">{fmt_age(p['last'])}</span></div>
  {f"<div class='ppath'>{esc(p.get('path','')[:52])}</div>" if p.get('path') else ""}
  <div class="bars">
    <i class="b c" style="width:{p['captures'] / tot * 100:.0f}%"></i>
    <i class="b s" style="width:{p['shields'] / tot * 100:.0f}%"></i>
    <i class="b r" style="width:{p['reflexes'] / tot * 100:.0f}%"></i>
  </div>
  <div class="pnums"><span>{p['captures']} cap</span><span>{p['shields']} shd</span><span>{p['reflexes']} rfl</span></div>
</div>""")

    sess_cards = []
    for s in sessions[:16]:
        t = s.get("transcript") or {}
        chips = "".join(f"<span class='tag {k[0]}'>{k}</span>" for k in
                        ([ "shield"] * min(s["shields"], 3) + ["reflex"] * min(s["reflexes"], 3)))
        rows = "".join(f"<tr><td class='dim'>{c['t']}</td><td class='tag {c['k'][0]}'>{c['k']}</td>"
                       f"<td>{esc(c['label'])}</td></tr>" for c in s["cmds"])
        body = (f"<table>{rows}</table>" if rows else
                "<div class='dim' style='padding:6px'>no failures this session</div>")
        meta_bits = [f"failures {s['captures']}", f"shields {s['shields']}",
                     f"id {s['sid']}"]
        if t:
            meta_bits.append(f"{t['size_kb']} KB transcript")
        sess_cards.append(f"""
<details class="scard {'hot' if s['shields'] else ''}">
  <summary>
    <span class="sid">{s['sid']}</span>
    <span class="sproj">{esc(s['project'][:26])}</span>
    {chips}
    <span class="sage">{fmt_age(s['last'])} ago</span>
    <span class="smeta">{' · '.join(meta_bits)}</span>
  </summary>
  <div class="sbody">{body}</div>
</details>""")

    ev_rows = "".join(
        f"<tr><td class='dim'>{time.strftime('%H:%M:%S', time.localtime(e.get('ts',0)))}</td>"
        f"<td><span class='tag {kind(e)[0]}'>{kind(e)}</span></td>"
        f"<td>{esc((e.get('cmd') or e.get('lesson') or '?'))[:70]}</td>"
        f"<td class='dim'>{esc(os.path.basename(e.get('project') or ''))[:24]}</td></tr>"
        for e in sorted(events, key=lambda x: -x.get("ts", 0))[:16])

    les_rows = "".join(
        f"<tr><td class='sev {'hi' if l['severity'].startswith('high') else ''}'>{esc(l['severity'])}</td>"
        f"<td title='{esc(l['title'])}'>{esc(l['title'])[:56]}</td>"
        f"<td class='dim'>{l['scope']}</td><td class='gold'>{l['saves'] or ''}</td>"
        f"<td class='{'ok' if l['automation'] else 'dim'}'>{'GUARD' if l['automation'] else '—'}</td></tr>"
        for l in sorted(lessons, key=lambda x: (-x["saves"], x["date"]))[:16])

    diag = "".join(f"<div class='drow'><span>{k.upper()}</span><b>{esc(v)}</b></div>"
                   for k, v in [("os", env["os"]), ("python", env["python"]),
                                ("node", env["node"]), ("git", env["git"]),
                                ("docker", env["docker"]),
                                ("plugin", "v" + plugin_version()),
                                ("inbox", f"{len(events)} events"),
                                ("logs", f"{len(lessons)} entries")])

    # ---- copilot panel ----
    cop = L._load_cache("copilot.json") or {}
    sug_rows = "".join(
        f"<div class='sug'><div class='sgp'>{esc(s['prompt'][:80])}</div>"
        f"<div class='sgs'>&raquo; {esc(s['suggestion'][:170])}</div>"
        f"<div class='dim' style='font-size:10px'>{esc(s['ts'])} · {esc(s['project'])}</div></div>"
        for s in cop.get("suggestions", [])[-3:][::-1]) or "<div class='dim'>no suggestions yet — set STARK_COPILOT=1 and type a short prompt in Claude Code</div>"
    prompts = L._recent_prompts(os.getcwd(), 4)
    prom_rows = "".join(
        f"<div class='prom'><span class='dim'>[{i}]</span> {esc(p[:90])}</div>"
        for i, p in enumerate(prompts, 1)) or "<div class='dim'>no prompts recorded in this project yet</div>"

    # ---- dossier panel ----
    doss = L._project_digest(os.getcwd())
    doss_cards = f"""
<div class="dossier">
  <div class="drow"><span>PATH</span><b>{esc(doss['path'][:48])}</b></div>
  <div class="drow"><span>STACK</span><b>{' · '.join(doss['stack'])}</b></div>
  <div class="drow"><span>FILES</span><b>{doss['files']}</b></div>
  <div class="drow"><span>REMOTE</span><b>{esc((doss['git_remote'] or '-')[:40])}</b></div>
  <div class="drow"><span>COMMIT</span><b>{esc((doss['last_commit'] or '-')[:52])}</b></div>
  <div class="drow"><span>LESSONS</span><b>{len(lessons)} in range</b></div>
</div>"""

    tpl = Template((HERE / "hud_template.html").read_text(encoding="utf-8"))
    return tpl.substitute(
        refresh=REFRESH, posture=posture, pcolor=pcolor, sub=sub,
        core=caps, rs=rs, rr=rr, rv=rv, n_sh=n_sh, n_rf=n_rf, n_sv=saves,
        n_le=len(lessons), stamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        proj_cards="".join(proj_cards), sess_cards="".join(sess_cards),
        ev_rows=ev_rows or "<tr><td colspan=4 class='dim'>no events yet</td></tr>",
        les_rows=les_rows or "<tr><td colspan=5 class='dim'>empty</td></tr>",
        diag=diag, sug_rows=sug_rows, prom_rows=prom_rows, doss_cards=doss_cards)


def main():
    args = sys.argv[1:]
    watch = "--watch" in args
    secs = float(args[args.index("--watch") + 1]) if watch and len(args) > args.index("--watch") + 1 else REFRESH
    while True:
        try:
            OUT.write_text(render(), encoding="utf-8")
            print(f"[{time.strftime('%H:%M:%S')}] rendered {OUT}", flush=True)
        except Exception as ex:
            print(f"render error: {ex}", flush=True)
            if os.environ.get("HUD_DEBUG"):
                import traceback
                traceback.print_exc()
        if not watch:
            break
        time.sleep(secs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
