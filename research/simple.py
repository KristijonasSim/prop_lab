"""The simple board. Four numbers, one chart, what passed, what nearly did.

Kris, 2026-09-18: *"super super simple ... how many we test per 1h, how many
researched, tested, waiting ... i dont want to see all strategies that failed
only those that passed minimum bar and those that are close to bar ... maybe
some graph ... and also button to refresh."*

WHY A SERVER AND NOT A FILE. A refresh button on a `file://` page can only
reload what was written the last time something rebuilt it, so the button would
lie. This serves the page and recomputes the numbers on every press.

    python -m research.simple            # serves on 8899 and prints the link
    python -m research.simple --once     # write the html and exit

WHAT IS DELIBERATELY NOT ON IT. The failures. 400-odd of them, all dead for
stated reasons, and Kris does not want to scroll past them - they stay in
`backtests/research.html`, which is the full board. What is here is the two
lists that can change a decision: what cleared the bar, and what came close
enough to be worth a second feed.

THE ONE NUMBER THAT MUST NOT BE READ AS GOOD NEWS. "Passed" is not "works". The
screen is a cheap filter; a pass earns a walk-forward. The page says so under
the number, every render, because a bare count in a big font is exactly how a
loop like this gets misread.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ledger import read                                    # noqa: E402
from research import naming, tradestats, vocab                  # noqa: E402
from research.propose import enumerate_space, untried           # noqa: E402

OUT = ROOT / "backtests" / "simple.html"
STATE = ROOT / "backtests" / "loop_state.json"
PORT = 8899

#: A candidate is "close" if it died on the LAST two checks only — the shape of
#: its response or its own shuffle — while clearing events, cost and the median.
#: Those are the two a bigger sample can move. Dying under the cost bar is not
#: close: no amount of data makes a 0.6 bps effect pay a 2.13 bps round trip.
NEAR_RHO = 0.55          # monotone-ish: |rho| here or above, but under 0.80
NEAR_P = 0.25            # lost to its shuffle, but not badly


def _params(t) -> dict:
    if not t.params:
        return {}
    try:
        return json.loads(t.params)
    except ValueError:
        return {}


def _cadence(feed: str) -> str:
    spec = vocab.FEEDS.get(feed)
    return spec.cadence if spec else "1d"


_STATS_CACHE: dict[str, dict] = {}


def _trade_stats(arm: str) -> dict:
    """tpd / PF / DD / win / Sharpe for one arm, cached for the session.

    Returns empty rather than raising: a board that 500s because one feed's
    cache moved is worse than a board with one row missing its numbers.
    """
    if arm in _STATS_CACHE:
        return _STATS_CACHE[arm]
    out: dict = {}
    try:
        from research.propose import Candidate
        from research.run import build_signal
        from research.tradestats import compute
        feed, rest = arm.split(".", 1)
        tr_w, mkt, hold = rest.split(".")
        transform = "".join(ch for ch in tr_w if not ch.isdigit())
        window = int("".join(ch for ch in tr_w if ch.isdigit()) or 0)
        spec = vocab.FEEDS[feed]
        c = Candidate(feed=feed, transform=transform, window=window, lag=spec.lag_floor,
                      market=mkt, hold=int(hold.lstrip("h")),
                      direction=spec.prior_sign or 1, mechanism="x" * 50)
        sig, fwd, rt, _fires = build_signal(c)
        st = compute(sig, fwd, rt, c.hold, spec.cadence)
        out = st.as_dict()
        out["cadence"] = spec.cadence
    except Exception:                                    # noqa: BLE001
        out = {}
    _STATS_CACHE[arm] = out
    return out


def collect() -> dict:
    trials = read()
    loop = [(t, _params(t)) for t in trials if _params(t).get("candidate_key")]

    # The ledger is append-only, so a retraction is a NEW row, not an edit -
    # that is what makes the trial count trustworthy. The board therefore has to
    # honour it: any candidate with a later WITHDRAWN row is gone from the
    # lists, while both of its rows stay charged against the search.
    withdrawn = {p["candidate_key"] for t, p in loop if t.verdict == "WITHDRAWN"}

    now = datetime.now(timezone.utc)

    def ts(t):
        try:
            return datetime.fromisoformat(t.ts)
        except ValueError:
            return None

    stamped = [(t, p, ts(t)) for t, p in loop]
    stamped = [(t, p, d) for t, p, d in stamped if d]

    # tests per hour over the last 24h of ACTIVE hours, not wall-clock: the loop
    # sleeps between cycles and a mean over idle hours understates it badly.
    buckets: Counter = Counter()
    for _t, _p, d in stamped:
        if now - d <= timedelta(hours=24):
            buckets[d.replace(minute=0, second=0, microsecond=0)] += 1
    per_hour = (sum(buckets.values()) / len(buckets)) if buckets else 0.0

    hours = [(now.replace(minute=0, second=0, microsecond=0)
              - timedelta(hours=h)) for h in range(23, -1, -1)]
    series = [{"h": x.strftime("%H"), "n": buckets.get(x, 0)} for x in hours]

    passed, near = [], []
    for t, p in loop:
        key = p.get("candidate_key", "")
        feed = key.split("|")[0] if key else ""
        row = {
            "name": naming.from_key(key, _cadence(feed)),
            "arm": t.arm,
            "market": t.market,
            "events": t.n_trades,
            "effect": p.get("effect_bps"),
            "bar": p.get("cost_bar_bps"),
            "rho": p.get("rho"),
            "p": p.get("p_null"),
            "note": t.note or "",
        }
        if key in withdrawn:
            continue
        if t.verdict == "PASS":
            passed.append(row)
            continue
        note = (t.note or "").lower()
        eff, bar = p.get("effect_bps"), p.get("cost_bar_bps")
        rho, pv = p.get("rho"), p.get("p_null")
        if not (isinstance(eff, (int, float)) and isinstance(bar, (int, float))):
            continue
        if abs(eff) < bar:                      # cost is not a near miss
            continue
        # Nor is running backwards. The direction is already applied to the
        # signal, so a negative effect means the response went OPPOSITE to the
        # mechanism - "buy Euro" next to -34.0 bps is not a near miss, it is a
        # wrong mechanism, and putting it on a page of near misses invites
        # exactly the flip that `vocab.prior_sign` exists to forbid.
        if eff < 0:
            continue
        if "monotone" in note and isinstance(rho, (int, float)) \
                and NEAR_RHO <= abs(rho) < 0.80:
            row["why"] = f"shape almost held (rho {abs(rho):.2f} of 0.80)"
            near.append(row)
        elif "shuffle" in note and isinstance(pv, (int, float)) \
                and 0.05 <= pv <= NEAR_P:
            row["why"] = f"lost to shuffled data, but only just (p {pv:.3f})"
            near.append(row)

    passed.sort(key=lambda r: -(abs(r["effect"] or 0) / (r["bar"] or 1)))
    near.sort(key=lambda r: -(abs(r["effect"] or 0) / (r["bar"] or 1)))
    near = near[:8]

    # The mandatory reporting fields (CLAUDE.md), computed only for the handful
    # shown. Rebuilding a signal costs a second, so doing it for all 400 dead
    # ones would make the refresh button useless for no gain.
    for r in passed + near:
        r.update(_trade_stats(r["arm"]))

    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except ValueError:
            pass

    ideas = len({r["name"] for _t, r in
                 [(t, {"name": naming.from_key(p.get("candidate_key", ""))})
                  for t, p in loop]})

    book_tpd = sum(r.get("trades_per_day", 0) or 0 for r in passed)
    solo = [r for r in passed
            if (r.get("trades_per_day", 0) or 0) >= tradestats.MIN_TPD]

    return {
        "book_tpd": round(book_tpd, 3),
        "min_tpd": tradestats.MIN_TPD,
        "solo": len(solo),
        "researched": len(enumerate_space()),
        "tested": len(loop),
        "waiting": len(untried()),
        "per_hour": round(per_hour, 1),
        "passed": passed,
        "near": near[:8],
        "series": series,
        "ideas": ideas,
        "status": state.get("status", "unknown"),
        "built": now.strftime("%H:%M:%S UTC"),
    }


CSS = """
:root{--bg:#faf9f7;--card:#fff;--ink:#16150f;--mut:#75726b;--line:#e5e2da;
 --good:#1a7f4b;--warn:#b07d10;--accent:#2b5fd9;--barfill:#c9d4f2;
 --mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --bg:#141410;--card:#1d1d18;--ink:#f1efe7;--mut:#9b978e;--line:#2f2f28;
 --good:#4ec27f;--warn:#dca62c;--accent:#7aa2f7;--barfill:#2f3f66}}
:root[data-theme="dark"]{--bg:#141410;--card:#1d1d18;--ink:#f1efe7;--mut:#9b978e;
 --line:#2f2f28;--good:#4ec27f;--warn:#dca62c;--accent:#7aa2f7;--barfill:#2f3f66}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;font-size:16px;line-height:1.5;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding-inline:18px;padding-block:30px 70px}
.top{display:flex;justify-content:space-between;align-items:center;gap:14px;
 flex-wrap:wrap;margin-bottom:22px}
h1{font-size:21px;margin:0;letter-spacing:-.01em}
.sub{color:var(--mut);font-size:12.5px;font-family:var(--mono);margin-top:3px}
button{background:var(--accent);color:#fff;border:0;border-radius:7px;
 padding:11px 20px;font-size:15px;font-weight:600;cursor:pointer;
 font-family:inherit}
button:hover{filter:brightness(1.08)}
button:active{transform:translateY(1px)}
button[disabled]{opacity:.55;cursor:default}
.nums{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:26px}
.n{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:16px 15px}
.n .v{font-family:var(--mono);font-size:29px;letter-spacing:-.03em;
 font-variant-numeric:tabular-nums}
.n .k{font-size:12px;color:var(--mut);margin-top:5px;line-height:1.35}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);
 margin:30px 0 11px;font-weight:700}
.chart{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:18px 16px 10px}
.bars{display:flex;align-items:flex-end;gap:3px;height:120px}
.bars div{flex:1;background:var(--barfill);border-radius:2px 2px 0 0;min-height:2px;
 position:relative}
.bars div.hi{background:var(--accent)}
.xax{display:flex;gap:3px;margin-top:6px}
.xax span{flex:1;text-align:center;font-size:9.5px;color:var(--mut);
 font-family:var(--mono)}
.item{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:14px 16px;margin-bottom:9px}
.item.ok{border-left:3px solid var(--good)}
.item.near{border-left:3px solid var(--warn)}
.item .t{font-size:15.5px;font-weight:600;letter-spacing:-.01em}
.item .d{color:var(--mut);font-size:13px;margin-top:5px}
.item .m{font-family:var(--mono);font-size:11.5px;color:var(--mut);margin-top:9px;
 font-variant-numeric:tabular-nums}
.stats{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:11px;
 padding-top:11px;border-top:1px solid var(--line)}
.stats span{display:flex;flex-direction:column;font-size:10.5px;color:var(--mut);
 line-height:1.3}
.stats b{font-family:var(--mono);font-size:16px;color:var(--ink);font-weight:600;
 font-variant-numeric:tabular-nums;letter-spacing:-.02em;margin-bottom:2px}
@media(max-width:620px){.stats{grid-template-columns:repeat(3,1fr)}}
.book{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:13px 16px;margin-bottom:11px;font-size:14px}
.book b{font-family:var(--mono);font-size:19px;letter-spacing:-.02em}
.book .ok{color:var(--good)} .book .no{color:var(--warn)}
.book .s{display:block;color:var(--mut);font-size:12px;margin-top:4px}
.empty{color:var(--mut);font-size:14px;background:var(--card);
 border:1px dashed var(--line);border-radius:10px;padding:16px}
.foot{color:var(--mut);font-size:12.5px;margin-top:34px;padding-top:14px;
 border-top:1px solid var(--line)}
@media(max-width:620px){.nums{grid-template-columns:1fr 1fr}.n .v{font-size:24px}}
"""

JS = """
function bars(s){
  const max = Math.max(1, ...s.map(x=>x.n));
  document.getElementById('bars').innerHTML =
    s.map(x=>`<div class="${x.n===max&&x.n>0?'hi':''}" style="height:${
      Math.round(x.n/max*100)}%" title="${x.n} at ${x.h}:00"></div>`).join('');
  document.getElementById('xax').innerHTML =
    s.map((x,i)=>`<span>${i%4===0?x.h:''}</span>`).join('');
}
function list(id, rows, cls, none){
  const el = document.getElementById(id);
  if(!rows.length){ el.innerHTML = `<div class="empty">${none}</div>`; return; }
  const pf = v => (v===null||v===undefined) ? '–' : (v>99 ? '99+' : Number(v).toFixed(2));
  el.innerHTML = rows.map(r=>`<div class="item ${cls}">
    <div class="t">${r.name}</div>
    <div class="d">${r.why ? r.why : 'cleared every check'}</div>
    <div class="stats">
      <span><b>${pf(r.pf_2x)}</b>profit factor</span>
      <span><b>${r.trades_per_day===undefined?'–':Number(r.trades_per_day).toFixed(2)}</b>trades/day</span>
      <span><b>${r.win_pct===undefined?'–':Math.round(r.win_pct)+'%'}</b>win rate</span>
      <span><b>${r.max_dd_bps===undefined?'–':Math.round(r.max_dd_bps)}</b>worst drop, bps</span>
      <span><b>${r.sharpe===undefined?'–':Number(r.sharpe).toFixed(2)}</b>sharpe</span>
      <span><b>${r.trades===undefined?'–':r.trades}</b>trades in 3y</span>
    </div>
    <div class="m">${Number(r.effect).toFixed(1)} bps vs ${Number(r.bar).toFixed(2)} cost bar ·
      ${(Math.abs(r.effect)/r.bar).toFixed(1)}x · ${r.events.toLocaleString()} events</div>
    </div>`).join('');
}
function paint(d){
  document.getElementById('researched').textContent = d.researched.toLocaleString();
  document.getElementById('tested').textContent     = d.tested.toLocaleString();
  document.getElementById('waiting').textContent    = d.waiting.toLocaleString();
  document.getElementById('rate').textContent       = d.per_hour;
  document.getElementById('built').textContent      = d.built + ' · loop ' + d.status;
  bars(d.series);
  const bk = document.getElementById('book');
  const ok = d.book_tpd >= d.min_tpd;
  bk.innerHTML = `<b class="${ok?'ok':'no'}">${d.book_tpd.toFixed(2)}</b>
    trades/day traded together · bar is ${d.min_tpd}
    <span class="s">${d.solo} of ${d.passed.length} could stand alone;
    the rest only count as part of a book.</span>`;
  list('passed', d.passed, 'ok', 'Nothing has cleared the bar yet.');
  list('near', d.near, 'near', 'Nothing close right now.');
}
async function refresh(){
  const b = document.getElementById('rf');
  b.disabled = true; b.textContent = 'Checking…';
  try { paint(await (await fetch('stats.json?t='+Date.now())).json()); }
  catch(e){ document.getElementById('built').textContent = 'could not reach the loop'; }
  b.disabled = false; b.textContent = 'Refresh';
}
document.getElementById('rf').addEventListener('click', refresh);
refresh();
"""


def page() -> str:
    return f"""<!doctype html><meta charset="utf-8">
<title>Loop Board</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style>
<div class="wrap">
  <div class="top">
    <div><h1>Research loop</h1><div class="sub" id="built">loading…</div></div>
    <button id="rf">Refresh</button>
  </div>

  <div class="nums">
    <div class="n"><div class="v" id="rate">–</div>
      <div class="k">tested per hour<br>while running</div></div>
    <div class="n"><div class="v" id="researched">–</div>
      <div class="k">strategies in the<br>search space</div></div>
    <div class="n"><div class="v" id="tested">–</div>
      <div class="k">tested<br>so far</div></div>
    <div class="n"><div class="v" id="waiting">–</div>
      <div class="k">waiting<br>to be tested</div></div>
  </div>

  <h2>Tests per hour — last 24 hours</h2>
  <div class="chart"><div class="bars" id="bars"></div>
    <div class="xax" id="xax"></div></div>

  <h2>Passed the bar</h2>
  <div class="book" id="book"></div>
  <div id="passed"></div>

  <h2>Close to the bar</h2>
  <div id="near"></div>

  <div class="foot">All numbers are the last <b>3 years</b>, costs charged at
  <b>2x</b>. Passing means one thing: it earned a proper test. It is not a
  result and not a strategy. No stop is applied, so there is deliberately no R
  and no "days to pass" — those need a stop, and picking one is a decision, not
  a calculation. Failures are not listed here; they are on the full board.</div>
</div>
<script>{JS}</script>"""


class Handler:
    """Defined inside `serve` so the stdlib import stays local to the command."""


def serve(port: int = PORT) -> None:
    import http.server
    import socketserver

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):        # quiet: this runs in a terminal
            pass

        def do_GET(self):                 # noqa: N802
            if self.path.startswith("/stats.json"):
                body = json.dumps(collect()).encode()
                ctype = "application/json"
            else:
                body = page().encode()
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), H) as srv:
        print(f"\n  http://127.0.0.1:{port}\n\n  ctrl-c to stop\n")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("stopped")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true",
                    help="write the html and a stats.json, then exit")
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args(argv)

    if a.once:
        OUT.write_text(page())
        (OUT.parent / "stats.json").write_text(json.dumps(collect(), indent=1))
        d = collect()
        print(f"wrote {OUT.relative_to(ROOT)}")
        print(f"  {d['per_hour']}/h · {d['tested']} tested · "
              f"{d['waiting']} waiting · {len(d['passed'])} passed · "
              f"{len(d['near'])} close")
        return 0
    serve(a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
