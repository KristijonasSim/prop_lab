# `research/` — the two engines

Built 2026-09-18, on Kris's pick: **hunt data feeds, with a model driving the
search, and a page to watch it.** Engine 1 proposes and registers. Engine 2
tests. Neither can reach into the other.

```
python -m research.harvest              # top up the feed cache
python -m research.propose -n 5         # what would be tested next, and why
python -m research.run -n 5             # screen them, charge them to the ledger
python -m research.loop --cycles 1      # all of the above, then publish
python -m research.dashboard            # rebuild backtests/research.html
python -m core.ledger                   # the bill
```

| engine | file | what it does | cost |
|---|---|---|---|
| **0 — harvest** | `harvest.py` | the only thing that touches the network | free |
| **1 — propose** | `vocab.py` | the feed registry. The action surface. | free |
| | `propose.py` | next untried candidate, refusing dead space | free |
| | `run.write_prereg` | the pre-registration, written before the test | free |
| **2 — test** | `run.py` | builds the signal, applies the lag, screens | free |
| | `core/screen.py` | five checks, cheapest kill first | free |
| | `core/searchcost.py` | what the search cost | free |
| **3 — show** | `dashboard.py` | `backtests/research.html` | free |
| | `loop.py` | unattended, cycle after cycle | free |

Outputs: `backtests/ledger.csv` (every trial), `docs/prereg/` (one file per
candidate, written first), `backtests/research.html` (the page),
`backtests/loop.log`, `backtests/loop_state.json`.

## Why feeds and not rules

Across this repo and `~/trading-bots`, **every leg that ever worked came from a
new data feed and none came from a new arrangement of price.** Twelve price
hypotheses and five feed hypotheses have died here; the five feed ones were
*real* and died to crypto's 14 bps round trip. Gold's round trip is 1.83 bps and
EURUSD's is 0.27.

So the unit of search is a row in `vocab.py`. A new feed opens space that was
never tested. A new parameter on an old feed does not, and costs exactly the
same.

## The four rules that make it safe

**1. A candidate never writes code.** It picks a feed, a transform, a window, a
lag, a market and a hold from enumerated sets. `run.build_signal` is the only
thing that touches a series. Look-ahead is not discouraged, it is
inexpressible — which matters because deflation does *not* catch leakage: arXiv
2608.27734 planted an oracle with Sharpe 34.7 and it scored a perfect 1.00.

**2. Every feed declares its knowable lag, with the reason.** The shift is
applied by the runner, from the registry, never by the proposal. A lag below the
floor is refused loudly rather than silently corrected — the first version
silently upgraded `lag: 0` to the floor, so an attempt to read same-day data
would never have been reported.

**3. Every feed declares ONE direction, and it comes from the mechanism.**
Testing a signal both ways doubles the trial count and guarantees that one of
the pair matches the data whatever the data says. A feed with no declared sign
has no written mechanism and is not a candidate. The first draft of the
enumerator emitted both directions; fixing it halved the space from 5,590 to
2,795.

**4. Every trial is charged, and nothing is proposed twice.** `core/ledger.py`
is the single entry point, so the count is complete by construction, and
`propose.tried_keys()` refuses anything already in it. The luck bar rises with
the log of the trial count whether or not a trial was informative, so re-testing
dead space costs full price and buys nothing.

## The arithmetic behind "quantity"

Kris: *"from quantity maybe we will get some quality."* The bar grows with
log(N), so volume is affordable — and where it is spent is not:

| trials | luck bar | annual Sharpe 3y can certify |
|---|---|---|
| 1 | 0.00σ | 0.00 |
| 264 | 2.86σ | ~1.63 |
| 10,000 | 3.86σ | 2.23 |
| 1,000,000 | 4.87σ | 2.81 |

**Going from 264 trials to a million costs about two sigma.** But at ten thousand
trials on three years of data, nothing below an annual Sharpe of 2.23 can be
certified however real it is. **Mass search and marginal edges are incompatible**,
so this loop screens for large effects and kills everything else for free.

For scale: H-027, the project's only survivor, has an annual Sharpe of 1.16.

## Throughput, honestly

The cheap screen is **seconds** — 30 candidates ran in about 2. A full
walk-forward is hours, so the real throughput of the whole pipeline is 5–20
studies a day. **This loop runs the screen only.** A `PASS` here means one thing:
the idea earned a real study with a walk-forward and honest fills. It is not a
result and it is not a strategy.

## Where it runs

Not on the VM. That box is **2 cores and 952 MB** and it is busy routing orders
hourly — it has been up 56 days doing exactly that and should keep doing it. The
desktop is **28 cores and 30 GB** and sits idle. Autonomous means unattended, not
remote.

```
python -m research.loop --forever --every 900 --mode llm
```

SIGINT and SIGTERM finish the current cycle and stop cleanly. A failed harvest,
a failed model call or a candidate that raises is recorded and the loop
continues — a loop that halts on a bad parse is not unattended.

## When it runs out

`propose` returns nothing and the loop reports `exhausted`. That is the honest
end of the current search space, and the fix is **a new feed in `vocab.py`, not
a new parameter**. The sibling repo's library ran out at 16 families and returned
0 of 19; expect the same shape here.

The next feed is already identified and is the largest untested input this
project has: **Dukascopy's hourly XAUUSD tick files carry ask volume and bid
volume**, and `core/fx_spread.py` has been downloading them all along while
discarding both fields on line 106. Two-sided volume, on the one market whose
round trip is 1.83 bps.

## Gotchas found the hard way

**FRED hangs on browser-like user agents.** Measured: the default urllib agent
and `curl/8.5.0` are served in 0.5s; `"prop_lab"` and a Mozilla string both time
out after 20s. It fails closed rather than with a 403, so it looks exactly like a
network outage. `harvest.AGENT` sets the agent per source.

**FRED revises.** The cache keeps only the latest vintage, so a result from these
feeds is an upper bound on what was tradeable. H-035 died on exactly this. Any
survivor must be re-checked against a point-in-time vintage (ALFRED).
