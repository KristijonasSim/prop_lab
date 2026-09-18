"""The page Kris watches. What is harvested, what is being tested, what it cost.

Kris, 2026-09-18: *"i also would want to have UI where i could see what is
happening what we are harvesting and testing etc etc"*.

FOUR THINGS, IN THIS ORDER, AND THE ORDER IS AN ARGUMENT

  1. **the budget** - trials charged and the luck bar they imply. First, because
     it governs everything under it. A page that shows results above their cost
     is how this project produced three headlines it had to withdraw.
  2. **the harvest** - every feed in the registry, cached or missing, with its
     honest lag and what it is for. This is the C-target: feeds are the unit of
     search, so the feed table IS the search space.
  3. **the bench** - recent trials, each with the number that killed it. The
     failures are the denominator and they are shown, not summarised away.
  4. **the funnel** - survivors against what chance alone would give. The H-035
     correction, on the page instead of in a lesson nobody re-reads.

NO AUTO-REFRESH. Kris removed it from the board on 2026-09-08 because it stole
focus and scroll position mid-read, and that instruction applies here for the
same reason. The build stamp in the header is how you tell which render you are
looking at. `--serve` gives a local HTTP server for anyone who would rather poll.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ledger import LEDGER, budget, read                    # noqa: E402
from core.searchcost import expected_max_z                      # noqa: E402
from research import vocab                                      # noqa: E402
from research.propose import (                                  # noqa: E402
    enumerate_space, unmechanised, untried)

OUT = ROOT / "backtests" / "research.html"
STATE = ROOT / "backtests" / "loop_state.json"

CSS = """
:root{--bg:#faf9f7;--surface:#fff;--ink:#16150f;--muted:#6b6862;--line:#e3e0d8;
 --good:#1a7f4b;--warn:#a8730a;--fail:#b3261e;--accent:#2b5fd9;
 --shadow:0 1px 2px rgba(0,0,0,.05);--mono:"JetBrains Mono",ui-monospace,
 SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --bg:#14140f;--surface:#1c1c17;--ink:#f0eee6;--muted:#96938b;--line:#2e2e27;
 --good:#4ec27f;--warn:#d99b25;--fail:#f0705f;--accent:#7aa2f7;
 --shadow:0 1px 2px rgba(0,0,0,.4)}}
:root[data-theme="dark"]{--bg:#14140f;--surface:#1c1c17;--ink:#f0eee6;
 --muted:#96938b;--line:#2e2e27;--good:#4ec27f;--warn:#d99b25;--fail:#f0705f;
 --accent:#7aa2f7;--shadow:0 1px 2px rgba(0,0,0,.4)}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;padding:0 16px 60px;
 font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1500px;margin:0 auto}
header{padding:28px 0 14px;border-bottom:1px solid var(--line);margin-bottom:8px}
h1{margin:0;font-size:20px;letter-spacing:-.01em}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.07em;
 color:var(--muted);margin:34px 0 10px;font-weight:600}
.sub{color:var(--muted);font-size:13px;margin-top:5px}
.built{color:var(--muted);font-size:11px;margin-top:7px;opacity:.75;
 font-family:var(--mono)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));
 gap:10px;margin:18px 0 4px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:7px;
 padding:13px 15px;box-shadow:var(--shadow)}
.card .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;
 color:var(--muted)}
.card .v{font-family:var(--mono);font-size:23px;margin-top:5px;
 letter-spacing:-.02em}
.card .n{font-size:11.5px;color:var(--muted);margin-top:4px;line-height:1.45}
.card.alarm{border-color:var(--fail)} .card.alarm .v{color:var(--fail)}
.card.ok .v{color:var(--good)}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--surface);
 border:1px solid var(--line);border-radius:7px;overflow:hidden}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
 color:var(--muted);padding:9px 11px;border-bottom:1px solid var(--line);
 font-weight:600;white-space:nowrap}
td{padding:8px 11px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
td.m,th.m{font-family:var(--mono);font-size:12px;white-space:nowrap}
td.r{text-align:right}
.pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;
 font-family:var(--mono);border:1px solid}
.pass{color:var(--good);border-color:var(--good)}
.fail{color:var(--fail);border-color:var(--fail)}
.miss{color:var(--warn);border-color:var(--warn)}
.why{color:var(--muted);font-size:12px}
.note{color:var(--muted);font-size:12.5px;line-height:1.6;margin:8px 0 2px;
 max-width:900px}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;
 margin-top:7px}
.bar i{display:block;height:100%;background:var(--accent)}
.bar i.over{background:var(--fail)}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);
 color:var(--muted);font-size:12px;line-height:1.6}
code{font-family:var(--mono);font-size:12px;background:var(--line);
 padding:1px 5px;border-radius:3px}
@media(max-width:700px){.card .v{font-size:19px}td,th{padding:7px 8px}}
"""


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


def _feed_stats() -> list[dict]:
    rows = []
    for f in sorted(vocab.FEEDS.values(), key=lambda x: (x.kind, x.name)):
        r = {"name": f.name, "kind": f.kind, "desc": f.desc,
             "cadence": f.cadence, "lag": f.lag_floor, "source": f.source,
             "note": f.notes[0] if f.notes else "",
             "markets": ", ".join(f.markets) if f.markets else "all",
             "rows": None, "first": "", "last": "", "ok": False}
        try:
            s = f.load()
            r.update(rows=len(s), ok=True,
                     first=str(s.index[0].date()), last=str(s.index[-1].date()))
        except Exception as exc:                          # noqa: BLE001
            r["note"] = f"NOT LOADABLE: {type(exc).__name__}"
        rows.append(r)
    return rows


def _trials(limit: int = 40) -> list[dict]:
    out = []
    for t in read():
        p = {}
        if t.params:
            try:
                p = json.loads(t.params)
            except ValueError:
                p = {}
        if not p.get("candidate_key"):
            continue                       # historical backfill has no detail
        out.append({
            "ts": t.ts[:16].replace("T", " "), "arm": t.arm,
            "market": t.market, "verdict": t.verdict, "note": t.note,
            "events": t.n_trades, "effect": p.get("effect_bps"),
            "median": p.get("median_bps"), "rho": p.get("rho"),
            "bar": p.get("cost_bar_bps"), "p": p.get("p_null"),
            "origin": p.get("origin", ""), "prereg": t.prereg,
        })
    return out[-limit:][::-1]


def _num(v, fmt="{:.1f}") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "<span class=why>—</span>"
    try:
        return fmt.format(float(v))
    except (TypeError, ValueError):
        return _esc(v)


def build() -> str:
    b = budget()
    feeds = _feed_stats()
    trials = _trials()
    space = enumerate_space()
    left = untried()
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except ValueError:
            state = {}

    screened = len(trials)
    survived = sum(1 for t in trials if t["verdict"] == "PASS")
    by_chance = screened * 0.05
    live = sum(1 for f in feeds if f["ok"])
    pct_spent = min(100.0, 100.0 * b.raw / max(1, b.affordable_5y))

    # ---- cards ----------------------------------------------------------
    cards = [
        ("trials charged", f"{b.raw:,}",
         f"{b.prereg} pre-registered. 3y of history buys "
         f"{b.affordable_3y}, 5y buys {b.affordable_5y}.",
         "alarm" if b.raw > b.affordable_5y else "ok"),
        ("luck bar", f"{b.bar_z:.2f}σ",
         f"what the best of {b.raw:,} tries reaches on noise alone. "
         f"A pre-registered single arm faces 0.00σ.", ""),
        ("feeds harvested", f"{live}/{len(feeds)}",
         "the search space is the feed table — a new feed resets it, "
         "a new parameter does not.", "ok" if live == len(feeds) else "alarm"),
        ("space left", f"{len(left):,}",
         f"of {len(space):,} expressible candidates.", ""),
        ("screened here", f"{screened:,}",
         f"{survived} survived; chance alone gives {by_chance:.1f}.",
         "ok" if survived > by_chance * 2 else ""),
    ]
    card_html = "".join(
        f'<div class="card {c}"><div class=k>{_esc(k)}</div>'
        f'<div class=v>{v}</div><div class=n>{_esc(n)}</div></div>'
        for k, v, n, c in cards)

    # ---- loop state -----------------------------------------------------
    if state:
        st = (f"<p class=note><b>Loop:</b> {_esc(state.get('status','idle'))} — "
              f"cycle {_esc(state.get('cycle','?'))}, last ran "
              f"{_esc(state.get('last_run','never'))}, mode "
              f"<code>{_esc(state.get('mode','library'))}</code>. "
              f"Next up: <code>{_esc(state.get('next','—'))}</code></p>")
    else:
        st = ("<p class=note><b>Loop:</b> never run. Start it with "
              "<code>python -m research.loop --cycles 1</code>.</p>")

    # ---- feed table -----------------------------------------------------
    frows = ""
    for f in feeds:
        pill = ('<span class="pill pass">cached</span>' if f["ok"]
                else '<span class="pill miss">missing</span>')
        rows = f"{f['rows']:,}" if f["rows"] else "—"
        span = f"{f['first']} → {f['last']}" if f["ok"] else ""
        frows += (
            f"<tr><td class=m>{_esc(f['name'])}</td>"
            f"<td>{_esc(f['kind'])}</td><td class=m>{_esc(f['cadence'])}</td>"
            f"<td class='m r'>{f['lag']}</td><td class='m r'>{rows}</td>"
            f"<td class=m>{_esc(span)}</td><td>{pill}</td>"
            f"<td class=m>{_esc(f['markets'])}</td>"
            f"<td class=why>{_esc(f['desc'])}"
            + (f"<br>{_esc(f['note'])}" if f["note"] else "") + "</td></tr>")

    # ---- trial table ----------------------------------------------------
    if trials:
        trows = ""
        for t in trials:
            cls = "pass" if t["verdict"] == "PASS" else "fail"
            pr = (f'<a href="../{_esc(t["prereg"])}">prereg</a>'
                  if t["prereg"] else "")
            trows += (
                f"<tr><td class=m>{_esc(t['ts'])}</td>"
                f"<td class=m>{_esc(t['arm'])}</td>"
                f"<td class=m>{_esc(t['market'])}</td>"
                f"<td class='m r'>{t['events']:,}</td>"
                f"<td class='m r'>{_num(t['effect'])}</td>"
                f"<td class='m r'>{_num(t['median'])}</td>"
                f"<td class='m r'>{_num(t['bar'])}</td>"
                f"<td class='m r'>{_num(t['rho'], '{:.2f}')}</td>"
                f"<td class='m r'>{_num(t['p'], '{:.3f}')}</td>"
                f"<td><span class='pill {cls}'>{_esc(t['verdict'])}</span></td>"
                f"<td class=why>{_esc(t['note'])} {pr}</td></tr>")
        trial_table = (
            "<table><tr><th>when</th><th>candidate</th><th>market</th>"
            "<th class=r>events</th><th class=r>effect</th><th class=r>median</th>"
            "<th class=r>bar</th><th class=r>rho</th><th class=r>p</th>"
            f"<th>verdict</th><th>why</th></tr>{trows}</table>")
    else:
        trial_table = ("<p class=note>Nothing screened yet. "
                       "<code>python -m research.run -n 5</code></p>")

    nm = unmechanised()
    nomech = (
        f'<p class=note><b>Harvested but not testable:</b> '
        f'<code>{", ".join(_esc(x) for x in nm)}</code>. A feed with no '
        f'declared direction has no written mechanism, and the proposer will '
        f'not emit it — testing a signal both ways is a free second attempt at '
        f'the same question, and one of the two always matches the data.</p>'
        if nm else
        '<p class=note>Every harvested feed has a declared direction and a '
        'written mechanism, so none is being tested both ways.</p>')

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    over = " over" if b.raw > b.affordable_5y else ""

    return f"""<!doctype html><meta charset="utf-8">
<title>Research loop</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- No auto-refresh, deliberately: Kris removed it from the board on
     2026-09-08 because it stole focus and scroll position mid-read. The build
     stamp below is how you tell which render this is. Reload by hand. -->
<style>{CSS}</style>
<div class=wrap>
<header>
  <h1>Research loop — feeds in, verdicts out</h1>
  <div class=sub>Engine 1 proposes a feed and writes the pre-registration.
    Engine 2 screens it cheapest-check-first and charges it to the ledger.
    Nothing here is a result; it is what has been spent and what survived.</div>
  <div class=built>built {stamp} · ledger {_esc(LEDGER.name)} ·
    reload by hand after a cycle</div>
</header>

<div class=cards>{card_html}</div>
<div class=bar><i class="{'over' if b.raw > b.affordable_5y else ''}"
  style="width:{pct_spent:.1f}%"></i></div>
<p class=note><b>Read the budget first.</b> The bar a result must clear rises
with the number of things tried — {b.raw:,} trials{over} the {b.affordable_5y}
that five years of history pays for, so the best thing this search can produce
reaches {b.bar_z:.2f}σ on luck alone. The same arm declared in advance faces
0.00σ. That is why every candidate here writes its pre-registration
<em>before</em> it runs.</p>
{st}

<h2>Harvest — the feed registry</h2>
<p class=note>The unit of search. Every leg that has ever worked in this project
or its predecessor came from a data feed, never from a new arrangement of price,
so a new row here opens space that was never tested while a new parameter on an
old row does not. <b>lag</b> is the earliest the value was readable, and it is
the field most likely to flatter a result if it is wrong.</p>
<table><tr><th>feed</th><th>kind</th><th>cadence</th><th class=r>lag</th>
<th class=r>rows</th><th>span</th><th>state</th><th>markets</th>
<th>what it is</th></tr>{frows}</table>
{nomech}

<h2>Bench — what has been tested</h2>
<p class=note>Effect and bar are basis points between the top and bottom bucket
of the signal; a candidate must clear <b>2×</b> the round trip to survive. The
checks run cheapest-first, so the <b>why</b> column names the first one that
killed it — most never reach the shuffle.</p>
{trial_table}

<h2>Funnel</h2>
<p class=note>{screened:,} screened, <b>{survived}</b> survived. At a 5%
threshold chance alone gives <b>{by_chance:.1f}</b>.
{'<b>Indistinguishable from chance.</b>' if survived <= by_chance * 2
 else 'More than chance would give — which earns a real study, and nothing more.'}
</p>

<footer>
Built by <code>research/dashboard.py</code>. Feeds: <code>research/vocab.py</code>.
Proposer: <code>research/propose.py</code>. Screen: <code>core/screen.py</code>.
Budget: <code>core/searchcost.py</code>. Ledger: <code>backtests/ledger.csv</code>.<br>
A verdict of PASS here means one thing only: the idea earned a real study with a
walk-forward and honest fills. It is not a result and it is not a strategy.
</footer>
</div>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build the research dashboard")
    ap.add_argument("--serve", type=int, metavar="PORT", default=0,
                    help="serve backtests/ over HTTP on this port")
    a = ap.parse_args(argv)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    print(f"wrote {OUT.relative_to(ROOT)}")
    if a.serve:
        import http.server
        import socketserver
        import functools
        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                    directory=str(ROOT))
        print(f"http://127.0.0.1:{a.serve}/backtests/research.html")
        with socketserver.TCPServer(("127.0.0.1", a.serve), handler) as sv:
            sv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
