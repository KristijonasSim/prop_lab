"""The page Kris watches. Visual, not prose.

Kris, 2026-09-18: *"make good UI super good everything must be clear, dont use
text too much no one reads it, i just want to see full workflow of what is
happening right now"*.

So the page answers four questions with numbers and shape, in this order:

    what is it doing RIGHT NOW      the live strip, top of page
    how much has been searched      four counters
    WHAT KIND of thing was tried    the baskets - the main event
    what is being killed, and why   the funnel and the tape

THE BASKETS ARE THE POINT. 55 hypotheses listed by H-number is a column of
numbers that says nothing about what was tried. Sorted into thirteen families it
becomes a map of the search: where the effort went, which directions are closed,
and which have never been touched. `research/families.py` holds the mapping.

NO AUTO-REFRESH. Kris removed it from the board on 2026-09-08 because it stole
focus and scroll position mid-read. The build stamp says which render this is.

WHAT THIS PAGE MUST NEVER IMPLY. A green basket is not a working strategy. The
loop runs the cheap screen only; a survivor has earned a walk-forward and
nothing else. The funnel's own caption carries that, because a page that shows
one survivor in a big colour is a page that will be misread.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ledger import LEDGER, budget, read                    # noqa: E402
from research import vocab                                      # noqa: E402
from research.families import BY_KEY, FAMILIES, classify        # noqa: E402
from research.propose import (                                  # noqa: E402
    enumerate_space, unmechanised, untried)

OUT = ROOT / "backtests" / "research.html"
STATE = ROOT / "backtests" / "loop_state.json"

KIND_LABEL = {"price": "Shapes in price",
              "data": "Outside information",
              "method": "How we measure, not what we trade"}


def _e(x) -> str:
    return html.escape(str(x), quote=True)


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def _gather() -> dict:
    trials = read()
    fam_trials: Counter = Counter()
    fam_pass: Counter = Counter()
    fam_names: dict[str, dict[str, dict]] = defaultdict(dict)

    for t in trials:
        key, name = classify(t.hypothesis)
        fam_trials[key] += 1
        rec = fam_names[key].setdefault(name, {"n": 0, "pass": 0})
        rec["n"] += 1
        if t.verdict == "PASS":
            fam_pass[key] += 1
            rec["pass"] += 1

    loop = [t for t in trials if t.params and "candidate_key" in t.params]
    gates: Counter = Counter()
    for t in loop:
        n = (t.note or "").lower()
        if "independent events" in n or "under 40" in n:
            gates["events"] += 1
        elif "under the" in n and "bar" in n:
            gates["cost"] += 1
        elif "disagree in sign" in n:
            gates["skew"] += 1
        elif "monotone" in n:
            gates["shape"] += 1
        elif "shuffle" in n:
            gates["null"] += 1
        elif t.verdict == "PASS":
            gates["live"] += 1
        else:
            gates["other"] += 1

    tape = []
    for t in loop[-14:][::-1]:
        try:
            p = json.loads(t.params)
        except ValueError:
            p = {}
        key, _ = classify(t.hypothesis)
        tape.append({"ts": t.ts[11:16], "arm": t.arm, "mkt": t.market,
                     "fam": BY_KEY[key].name, "verdict": t.verdict,
                     "note": t.note, "effect": p.get("effect_bps"),
                     "bar": p.get("cost_bar_bps")})

    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except ValueError:
            state = {}

    return {"trials": trials, "loop": loop, "fam_trials": fam_trials,
            "fam_pass": fam_pass, "fam_names": fam_names, "gates": gates,
            "tape": tape, "state": state, "budget": budget(trials)}


# ---------------------------------------------------------------------------
# pieces
# ---------------------------------------------------------------------------
def _live_strip(d: dict) -> str:
    st = d["state"]
    status = st.get("status", "not started")
    running = status not in ("stopped", "not started", "exhausted")
    label = {"harvesting": "Downloading feeds", "proposing": "Choosing what to test",
             "screening": "Testing", "publishing": "Writing results",
             "idle": "Waiting for next cycle", "exhausted": "Out of ideas",
             "stopped": "Stopped", "not started": "Not started"}.get(status, status)
    nxt = st.get("next", "—")
    cyc = st.get("cycle", "—")
    left = st.get("left")
    dot = "on" if running else "off"
    return f"""
<div class="live {dot}">
  <span class="dot"></span>
  <div class="lv">
    <b>{_e(label)}</b>
    <span class="sep">/</span>
    <span class="muted">cycle</span> <span class="mn">{_e(cyc)}</span>
    <span class="sep">/</span>
    <span class="muted">next</span> <span class="mn">{_e(nxt)}</span>
  </div>
  <div class="lr mn">{_e(f"{left:,} left") if left else ""}</div>
</div>"""


def _counters(d: dict) -> str:
    b = d["budget"]
    ideas = len({classify(t.hypothesis)[1] for t in d["trials"]})
    left = len(untried())

    # Loop survivors ONLY. Counting every PASS in the ledger gives 16, but 15 of
    # those are rows backfilled from STRATEGY_LOG.md where PASS meant "cleared
    # the gate that day" under a dozen different gates. Mixing them into one
    # number on the front of the page would overstate the loop by 16x.
    alive = sum(1 for t in d["loop"] if t.verdict == "PASS")
    cells = [
        ("Strategies researched", f"{ideas}", "distinct ideas, all time"),
        ("Tests run", f"{b.raw:,}", f"{b.prereg} declared in advance"),
        ("Queued to test", f"{left:,}", "combinations not yet tried"),
        ("Past the screen", f"{alive}", f"of {len(d['loop']):,} the loop ran — "
                                        "earned a real test, not a result"),
    ]
    return "".join(
        f'<div class="ct"><div class="ck">{_e(k)}</div>'
        f'<div class="cv mn">{v}</div><div class="cn">{_e(n)}</div></div>'
        for k, v, n in cells)


def _baskets(d: dict) -> str:
    out = []
    for kind in ("price", "data", "method"):
        fams = [f for f in FAMILIES if f.kind == kind]
        cards = ""
        for f in fams:
            n = d["fam_trials"].get(f.key, 0)
            p = d["fam_pass"].get(f.key, 0)
            if not n and f.key == "other":
                continue
            names = d["fam_names"].get(f.key, {})
            chips = "".join(
                f'<span class="chip{" hit" if v["pass"] else ""}">{_e(k)}'
                f'<i class="mn">{v["n"]}</i></span>'
                for k, v in sorted(names.items(), key=lambda x: -x[1]["n"])[:7])
            if len(names) > 7:
                chips += f'<span class="chip more">+{len(names) - 7}</span>'
            pct = (p / n * 100) if n else 0
            state = "hit" if p else ("dead" if n else "empty")
            bar = (f'<span class="seg dead" style="width:{100 - pct:.1f}%"></span>'
                   f'<span class="seg hit" style="width:{pct:.1f}%"></span>') if n else ""
            cards += f"""
  <div class="bk {state}">
    <div class="bh">
      <div><div class="bn">{_e(f.name)}</div>
           <div class="bb">{_e(f.blurb)}</div></div>
      <div class="bc mn">{n:,}</div>
    </div>
    <div class="bar">{bar}</div>
    <div class="chips">{chips or '<span class="chip empty">never tried</span>'}</div>
  </div>"""
        out.append(f'<div class="kl">{_e(KIND_LABEL[kind])}</div>'
                   f'<div class="bgrid">{cards}</div>')
    return "".join(out)


GATE_LABELS = [
    ("events", "Happened enough times?", "under 40 separate occasions"),
    ("cost", "Bigger than the cost?", "must beat 2x the spread"),
    ("skew", "Typical trade, not one lucky one?", "mean and median must agree"),
    ("shape", "More signal, more move?", "response must be monotone"),
    ("null", "Beats shuffled nonsense?", "200 scrambled reruns"),
]


def _funnel(d: dict) -> str:
    g = d["gates"]
    total = len(d["loop"])
    if not total:
        return '<p class="note">Nothing screened yet.</p>'
    rows, remaining = "", total
    for key, q, sub in GATE_LABELS:
        killed = g.get(key, 0)
        w = remaining / total * 100
        rows += f"""
  <div class="gt">
    <div class="gq">{_e(q)}<small>{_e(sub)}</small></div>
    <div class="gbar"><i style="width:{w:.1f}%"></i></div>
    <div class="gk mn">{remaining:,}<span> in</span></div>
    <div class="gd mn">−{killed:,}</div>
  </div>"""
        remaining -= killed
    rows += f"""
  <div class="gt out">
    <div class="gq">Survived<small>earned a real test, nothing more</small></div>
    <div class="gbar"><i class="ok" style="width:{max(remaining / total * 100, 0.6):.1f}%"></i></div>
    <div class="gk mn">{remaining:,}<span> left</span></div>
    <div class="gd mn"></div>
  </div>"""
    return rows


def _tape(d: dict) -> str:
    if not d["tape"]:
        return '<p class="note">Nothing yet.</p>'
    rows = ""
    for t in d["tape"]:
        ok = t["verdict"] == "PASS"
        eff = t["effect"]
        bar = t["bar"]
        ratio = ""
        if isinstance(eff, (int, float)) and isinstance(bar, (int, float)) and bar:
            ratio = f"{abs(eff) / bar:.1f}x"
        rows += (f'<tr class="{"ok" if ok else ""}">'
                 f'<td class="mn dim">{_e(t["ts"])}</td>'
                 f'<td><span class="fdot"></span>{_e(t["fam"])}</td>'
                 f'<td class="mn">{_e(t["arm"])}</td>'
                 f'<td class="mn num">{_e(ratio)}</td>'
                 f'<td class="why">{_e(t["note"])}</td></tr>')
    return (f'<table class="tape"><tr><th>time</th><th>basket</th>'
            f'<th>test</th><th class="num">vs cost</th><th>outcome</th></tr>'
            f'{rows}</table>')


# ---------------------------------------------------------------------------
CSS = """
:root{
 --bg:#faf9f7;--surface:#fff;--ink:#16150f;--muted:#6b6862;--line:#e3e0d8;
 --dim:#f3f1ec;--good:#1a7f4b;--warn:#a8730a;--fail:#b3261e;--accent:#2b5fd9;
 --deadbar:#ded9cf;
 --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
 --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --bg:#14140f;--surface:#1c1c17;--ink:#f0eee6;--muted:#96938b;--line:#2e2e27;
 --dim:#22221c;--good:#4ec27f;--warn:#d99b25;--fail:#f0705f;--accent:#7aa2f7;
 --deadbar:#33332b}}
:root[data-theme="dark"]{
 --bg:#14140f;--surface:#1c1c17;--ink:#f0eee6;--muted:#96938b;--line:#2e2e27;
 --dim:#22221c;--good:#4ec27f;--warn:#d99b25;--fail:#f0705f;--accent:#7aa2f7;
 --deadbar:#33332b}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);margin:0;
 font-size:15px;line-height:1.5}
.wrap{max-width:1180px;margin:0 auto;padding-inline:18px;padding-block:26px 70px}
.mn{font-family:var(--mono);font-variant-numeric:tabular-nums}
.muted{color:var(--muted)}
h1{font-size:19px;margin:0;letter-spacing:-.01em}
.stamp{color:var(--muted);font-size:11px;font-family:var(--mono);margin-top:3px}
h2{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);
 margin:40px 0 12px;font-weight:700}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}

/* live strip */
.live{display:flex;align-items:center;gap:12px;background:var(--surface);
 border:1px solid var(--line);border-left:3px solid var(--muted);
 border-radius:8px;padding:12px 16px;margin:18px 0 22px}
.live.on{border-left-color:var(--good)}
.live .dot{width:8px;height:8px;border-radius:50%;background:var(--muted);
 flex:none}
.live.on .dot{background:var(--good);animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@media(prefers-reduced-motion:reduce){.live.on .dot{animation:none}}
.lv{flex:1;font-size:13.5px;display:flex;gap:7px;flex-wrap:wrap;align-items:baseline}
.lv .sep{color:var(--line)}
.lr{color:var(--muted);font-size:12px;white-space:nowrap}

/* counters */
.cts{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.ct{background:var(--surface);border:1px solid var(--line);border-radius:9px;
 padding:15px 16px}
.ck{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.cv{font-size:30px;line-height:1.1;margin:7px 0 4px;letter-spacing:-.03em}
.cn{font-size:11.5px;color:var(--muted);line-height:1.4}

/* baskets */
.kl{font-size:12px;font-weight:700;color:var(--ink);margin:22px 0 9px;
 letter-spacing:-.01em}
.kl:first-child{margin-top:0}
.bgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));
 gap:11px}
.bk{background:var(--surface);border:1px solid var(--line);border-radius:9px;
 padding:14px 15px}
.bk.hit{border-color:var(--good)}
.bk.empty{opacity:.55;border-style:dashed}
.bh{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.bn{font-size:14.5px;font-weight:650;letter-spacing:-.01em}
.bb{font-size:11.5px;color:var(--muted);margin-top:2px}
.bc{font-size:19px;letter-spacing:-.02em;color:var(--muted)}
.bk.hit .bc{color:var(--good)}
.bar{display:flex;height:5px;border-radius:3px;overflow:hidden;
 background:var(--dim);margin:11px 0 10px}
.seg{display:block;height:100%}
.seg.dead{background:var(--deadbar)}
.seg.hit{background:var(--good)}
.chips{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-size:11.5px;background:var(--dim);border-radius:4px;padding:2px 6px;
 color:var(--muted);display:inline-flex;gap:5px;align-items:baseline}
.chip i{font-style:normal;opacity:.6;font-size:10.5px}
.chip.hit{background:transparent;border:1px solid var(--good);color:var(--good)}
.chip.more,.chip.empty{opacity:.6}

/* funnel */
.gt{display:grid;grid-template-columns:1fr 150px 92px 62px;gap:14px;
 align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}
.gt:last-child{border-bottom:none}
.gq{font-size:14px}
.gq small{display:block;color:var(--muted);font-size:11.5px;margin-top:1px}
.gbar{height:8px;background:var(--dim);border-radius:4px;overflow:hidden}
.gbar i{display:block;height:100%;background:var(--accent);opacity:.75}
.gbar i.ok{background:var(--good);opacity:1}
.gk{font-size:14px;text-align:right}
.gk span{color:var(--muted);font-size:11px}
.gd{font-size:13px;text-align:right;color:var(--fail)}
.gt.out .gk{color:var(--good)}

/* tape */
.tw{overflow-x:auto}
table.tape{border-collapse:collapse;width:100%;font-size:12.5px;min-width:620px}
table.tape th{text-align:left;font-size:10.5px;text-transform:uppercase;
 letter-spacing:.06em;color:var(--muted);padding:7px 10px 7px 0;
 border-bottom:1px solid var(--line);font-weight:700}
table.tape td{padding:7px 10px 7px 0;border-bottom:1px solid var(--line)}
table.tape tr:last-child td{border-bottom:none}
td.dim{color:var(--muted)}
td.num,th.num{text-align:right;padding-right:0}
td.why{color:var(--muted)}
.fdot{display:inline-block;width:6px;height:6px;border-radius:50%;
 background:var(--deadbar);margin-right:7px;vertical-align:middle}
tr.ok .fdot{background:var(--good)}
tr.ok td{color:var(--good)}
footer{margin-top:46px;padding-top:15px;border-top:1px solid var(--line);
 color:var(--muted);font-size:12px}
@media(max-width:860px){.cts{grid-template-columns:1fr 1fr}
 .gt{grid-template-columns:1fr 70px 56px;gap:10px}
 .gt .gbar{display:none}}
"""


def build() -> str:
    d = _gather()
    b = d["budget"]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    feeds_ok = sum(1 for f in vocab.FEEDS.values() if f.available())
    nm = unmechanised()
    passed = sum(1 for t in d["loop"] if t.verdict == "PASS")
    chance = len(d["loop"]) * 0.05

    return f"""<!doctype html><meta charset="utf-8">
<title>Research loop</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- No auto-refresh: removed from the board 2026-09-08 because it stole focus
     and scroll position mid-read. The stamp says which render this is. -->
<style>{CSS}</style>
<div class="wrap">

<h1>Research loop</h1>
<div class="stamp">{stamp} · {feeds_ok}/{len(vocab.FEEDS)} feeds live ·
 {len(enumerate_space()):,} combinations expressible · reload to refresh</div>

{_live_strip(d)}

<div class="cts">{_counters(d)}</div>

<h2>What kind of strategy — every idea ever tried here</h2>
{_baskets(d)}

<h2>What the loop kills, and where</h2>
{_funnel(d)}
<p class="note">{len(d['loop']):,} screened · {passed} survived ·
 chance alone gives {chance:.1f} · a survivor has earned a walk-forward,
 not a place in the book.</p>

<h2>Live tape</h2>
<div class="tw">{_tape(d)}</div>

<h2>Cost of the search</h2>
<div class="cts">
  <div class="ct"><div class="ck">Bar to beat</div>
    <div class="cv mn">{b.bar_z:.2f}σ</div>
    <div class="cn">what the best of {b.raw:,} tries reaches on luck alone</div></div>
  <div class="ct"><div class="ck">Declared first</div>
    <div class="cv mn">{b.prereg}</div>
    <div class="cn">those face a bar of 0.00σ</div></div>
  <div class="ct"><div class="ck">Budget</div>
    <div class="cv mn">{b.affordable_5y}</div>
    <div class="cn">tests 5 years of history pays for</div></div>
  <div class="ct"><div class="ck">Feeds without a mechanism</div>
    <div class="cv mn">{len(nm)}</div>
    <div class="cn">{_e(", ".join(nm)) if nm else "all have one — none tested both ways"}</div></div>
</div>

<footer>
Ledger <span class="mn">{_e(LEDGER.name)}</span> ·
baskets <span class="mn">research/families.py</span> ·
screen <span class="mn">core/screen.py</span>.
Nothing on this page is a trading result.
</footer>
</div>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build the research dashboard")
    ap.add_argument("--serve", type=int, metavar="PORT", default=0)
    a = ap.parse_args(argv)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    print(f"wrote {OUT.relative_to(ROOT)}")
    if a.serve:
        import functools
        import http.server
        import socketserver
        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                    directory=str(ROOT))
        print(f"http://127.0.0.1:{a.serve}/backtests/research.html")
        with socketserver.TCPServer(("127.0.0.1", a.serve), handler) as sv:
            sv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
