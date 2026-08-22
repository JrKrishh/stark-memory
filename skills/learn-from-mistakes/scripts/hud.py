#!/usr/bin/env python3
"""stark-memory HUD — JARVIS-style live dashboard over your memory systems.

Watches (with --watch) and renders to a self-refreshing HTML page:
  ~/.claude/stark-hud.html

Usage:
  python hud.py                 # render once, print path
  python hud.py --watch [secs]  # rebuild every N seconds (default 5)

Everything is local: reads ~/.claude/mistakes.jsonl plus the lesson logs.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lessons as L  # noqa: E402

INBOX = Path(os.environ.get("JARVIS_INBOX") or Path.home() / ".claude" / "mistakes.jsonl")
OUT = Path(os.environ.get("STARK_HUD_OUT") or Path.home() / ".claude" / "stark-hud.html")
REFRESH = 5


def load_events():
    if not INBOX.exists():
        return []
    out = []
    for line in INBOX.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def load_lessons():
    out = []
    for scope, path in L.find_logs():
        for e in L.parse_entries(path):
            out.append({
                "scope": scope,
                "date": e["date"],
                "title": e["title"],
                "severity": L.field(e, "Severity") or "-",
                "saves": int(m.group()) if (m := re.search(r"\d+", L.field(e, "Saves") or "")) else 0,
                "automation": bool(L.field(e, "Automation")),
            })
    return out


def fmt_age(ts):
    d = time.time() - ts
    if d < 90: return f"{int(d)}s ago"
    if d < 5400: return f"{int(d // 60)}m ago"
    if d < 172800: return f"{int(d // 3600)}h ago"
    return f"{int(d // 86400)}d ago"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build(events, lessons):
    now = int(time.time())
    caps = [e for e in events if not e.get("shield") and not e.get("reflex")]
    shields = [e for e in events if e.get("shield")]
    reflx = [e for e in events if e.get("reflex")]
    projects = {}
    for e in caps:
        projects[e.get("project", "?")] = projects.get(e.get("project", "?"), 0) + 1
    total_saves = sum(l["saves"] for l in lessons)
    high_unguarded = sum(1 for l in lessons if l["severity"].startswith("high") and not l["automation"])
    last_ts = max((e.get("ts", 0) for e in events), default=0)
    quiet = (now - last_ts > 172800) if last_ts else True

    # threat posture
    if shields:
        posture, pcolor = f"{len(shields)} THREATS INTERCEPTED", "#ff6b5e"
        sub = "the suit is holding the line"
    elif high_unguarded:
        posture, pcolor = "GUARDS PENDING", "#ffd166"
        sub = f"{high_unguarded} high-severity lesson(s) still advisory"
    else:
        posture, pcolor = ("QUIET SKIES", "#7de8ff") if quiet else ("ALL SYSTEMS NOMINAL", "#9fe8b4")
        sub = "no hostile activity on record"

    core_num = len(caps)
    ring_shield = min(len(shields) * 30, 340)
    ring_reflex = min(len(reflx) * 20, 340)
    ring_save = min(total_saves * 40, 340)

    ev_rows = "".join(
        f"<tr><td class='t'>{time.strftime('%H:%M:%S', time.localtime(e.get('ts', 0)))}</td>"
        f"<td><span class='tag {'s' if e.get('shield') else 'r' if e.get('reflex') else 'c'}'>"
        f"{'SHIELD' if e.get('shield') else 'REFLEX' if e.get('reflex') else 'CAPTURE'}</span></td>"
        f"<td>{esc((e.get('cmd') or e.get('lesson') or '?'))[:64]}</td>"
        f"<td class='dim'>{esc(os.path.basename(e.get('project') or ''))[:22]}</td></tr>"
        for e in sorted(events, key=lambda x: -x.get("ts", 0))[:14])

    les_rows = "".join(
        f"<tr><td class='sev {'hi' if l['severity'].startswith('high') else ''}'>{esc(l['severity'])}</td>"
        f"<td>{esc(l['title'])[:58]}</td><td class='dim'>{l['scope']}</td>"
        f"<td class='gold'>{l['saves'] or ''}</td>"
        f"<td class='{'ok' if l['automation'] else 'dim'}'>{'GUARD' if l['automation'] else '—'}</td></tr>"
        for l in sorted(lessons, key=lambda x: (-x['saves'], x['date']))[:14])

    proj_chips = "".join(
        f"<span class='chip'>{esc(os.path.basename(p)[:18])}<b>{n}</b></span>"
        for p, n in sorted(projects.items(), key=lambda kv: -kv[1])[:8])

    return HTML.format(
        refresh=REFRESH, posture=posture, pcolor=pcolor, sub=sub, core=core_num,
        rs=ring_shield, rr=ring_reflex, rv=ring_save,
        n_sh=len(shields), n_rf=len(reflx), n_sv=total_saves,
        n_le=len(lessons), ev_rows=ev_rows or "<tr><td colspan=4 class='dim'>no events yet — go fly</td></tr>",
        les_rows=les_rows or "<tr><td colspan=5 class='dim'>logs empty</td></tr>",
        chips=proj_chips or "<span class='chip'>no projects yet</span>",
        stamp=time.strftime("%Y-%m-%d %H:%M:%S"), gen=int(now))


HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>stark-memory · JARVIS HUD</title>
<style>
:root{{--cy:#7de8ff;--gd:#ffd166;--rd:#ff6b5e;--gn:#9fe8b4;--dim:#4a6a86;--bg:#04080f}}
*{{box-sizing:border-box;margin:0}}
body{{background:radial-gradient(1200px 600px at 50% -10%,#0a1a2b 0%,var(--bg) 60%);
 font-family:Consolas,'Courier New',monospace;color:#cfe6f5;min-height:100vh;padding:18px}}
body::after{{content:'';position:fixed;inset:0;pointer-events:none;
 background:repeating-linear-gradient(0deg,transparent 0 2px,rgba(125,232,255,.02) 2px 4px)}}
header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
h1{{font-size:15px;letter-spacing:6px;color:var(--cy);font-weight:600}}
.posture{{text-align:right}}
.posture b{{font-size:19px;letter-spacing:3px;color:{pcolor}}}
.posture span{{font-size:11px;color:var(--dim);letter-spacing:2px}}
.grid{{display:grid;grid-template-columns:300px 1fr 380px;gap:14px}}
.panel{{border:1px solid #16344e;background:rgba(10,25,40,.55);border-radius:12px;padding:12px}}
.panel h2{{font-size:11px;letter-spacing:4px;color:var(--dim);margin-bottom:8px}}
.center{{text-align:center}}
.reactor{{width:290px;height:290px;margin:6px auto 0}}
.ring{{transform-origin:145px 145px;animation:spin 24s linear infinite}}
.ring.rev{{animation-direction:reverse;animation-duration:36s}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.core{{animation:pulse 2.6s ease-in-out infinite;transform-origin:145px 145px}}
@keyframes pulse{{0%,100%{{opacity:.85}}50%{{opacity:1}}}}
.corenum{{font-size:34px;font-weight:700;fill:#eafcff}}
.rlabel{{font-size:11px;fill:var(--dim);letter-spacing:2px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
td{{padding:3px 6px;border-bottom:1px solid rgba(125,232,255,.07);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.t{{color:var(--dim)}}
.dim{{color:var(--dim)}} .gold{{color:var(--gd)}} .ok{{color:var(--gn)}}
.sev.hi{{color:var(--rd);font-weight:700}}
.tag{{padding:1px 7px;border-radius:9px;font-size:10px;letter-spacing:1px}}
.tag.s{{background:#2a1114;color:var(--rd)}} .tag.r{{background:#241d0d;color:var(--gd)}} .tag.c{{background:#0e2434;color:var(--cy)}}
.chips{{margin-top:10px}} .chip{{display:inline-block;border:1px solid #1d3a55;color:#9fc2dd;border-radius:10px;
 padding:3px 10px;margin:2px;font-size:11px}} .chip b{{color:var(--cy);margin-left:6px}}
footer{{text-align:center;color:var(--dim);font-size:10px;letter-spacing:2px;margin-top:10px}}
</style></head>
<body>
<header><h1>STARK-MEMORY // JARVIS HUD</h1>
<div class="posture"><b style="color:{pcolor}">{posture}</b><br><span>{sub}</span></div></header>

<div class="grid">
<div class="panel center"><h2>REACTOR CORE</h2>
<svg class="reactor" viewBox="0 0 290 290">
 <circle cx="145" cy="145" r="132" fill="none" stroke="#16344e" stroke-width="1"/>
 <g class="ring"><circle cx="145" cy="145" r="122" fill="none" stroke="#2a4d70" stroke-width="8"
   stroke-dasharray="30 16" stroke-linecap="round"/></g>
 <circle cx="145" cy="145" r="104" fill="none" stroke="#16344e" stroke-width="26"
   stroke-dasharray="{rs} 400" transform="rotate(-90 145 145)" stroke-linecap="butt" style="stroke:#ff6b5e"/>
 <g class="ring rev"><circle cx="145" cy="145" r="88" fill="none" stroke="#2a4d70" stroke-width="6"
   stroke-dasharray="18 12"/></g>
 <circle cx="145" cy="145" r="88" fill="none" stroke="#ffd166" stroke-width="6"
   stroke-dasharray="{rr} 400" transform="rotate(-90 145 145)"/>
 <circle cx="145" cy="145" r="70" fill="none" stroke="#9fe8b4" stroke-width="8"
   stroke-dasharray="{rv} 400" transform="rotate(-90 145 145)"/>
 <g class="core">
  <circle cx="145" cy="145" r="52" fill="#0a1c2c" stroke="#2a4d70"/>
  <circle cx="145" cy="145" r="46" fill="none" stroke="#7de8ff" stroke-width="2" opacity=".6"/>
  <text class="corenum" x="145" y="156" text-anchor="middle">{core}</text>
  <text class="rlabel" x="145" y="174" text-anchor="middle">CAPTURES</text>
 </g>
</svg>
<div class="chips">{chips}</div>
</div>

<div class="panel"><h2>EVENT STREAM</h2>
<table><tr><td class="rlabel">TIME</td><td class="rlabel">CLASS</td><td class="rlabel">COMMAND / LESSON</td><td class="rlabel">PROJECT</td></tr>
{ev_rows}</table></div>

<div class="panel"><h2>LESSON LEDGER ({n_le})</h2>
<table><tr><td class="rlabel">SEV</td><td class="rlabel">TITLE</td><td class="rlabel">LOG</td><td class="rlabel">SAVES</td><td class="rlabel">STATE</td></tr>
{les_rows}</table>
<p style="margin-top:10px;font-size:11px;color:var(--dim)">
shields fired: <b style="color:var(--rd)">{n_sh}</b> ·
reflexes: <b style="color:var(--gd)">{n_rf}</b> ·
total saves: <b style="color:var(--gn)">{n_sv}</b></p>
</div>
</div>

<footer>GENERATED {stamp} · REFRESH {refresh}s · ALL TELEMETRY LOCAL</footer>
</body></html>"""


def main():
    args = sys.argv[1:]
    watch = "--watch" in args
    secs = float(args[args.index("--watch") + 1]) if "--watch" in args and len(args) > args.index("--watch") + 1 else REFRESH
    while True:
        try:
            html = build(load_events(), load_lessons())
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(html, encoding="utf-8")
            print(f"[{time.strftime('%H:%M:%S')}] rendered {OUT}", flush=True)
        except Exception as ex:
            print(f"render error: {ex}", flush=True)
        if not watch:
            break
        time.sleep(secs)
    print(f"open in browser:  start {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
