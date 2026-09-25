# Wednesday after work

Written 2026-09-23. Notes to self for picking this up on the other PC.

---

## 1. Can I work from the other machine?

**Yes, but three things are NOT in the repo and have to be brought over by hand.**

Everything else travels: all the code, all the cached bars (the repo is 1.8 GB
because `data/` is committed on purpose), the Pine script, the queue, the idea
records and the archives. A clone reproduces the board exactly.

### What is missing from a fresh clone

| | where it is now | what to do |
|---|---|---|
| **the Python venv** | `.venv/`, gitignored | rebuild, see below |
| **the VM ssh key** | `~/trading-bots/bybit_bot/deploy/ssh/oracle_bots` — a **different repo**, not this one | copy it across on a USB stick or `scp`, then `chmod 600` |
| **the `claude` CLI login** | `~/.local/bin/claude`, logged in | install it and log in on the other box |

---

## 2. Setup on the other PC, in order

```bash
git clone git@github.com:KristijonasSim/prop_lab.git
cd prop_lab

python3.12 -m venv .venv                  # 3.12 exactly — 3.13 breaks numba
./.venv/bin/pip install -r requirements-lock.txt

# check it works — should be ~430 passed
./.venv/bin/python -m pytest tests/ -q
```

**The ssh key.** Copy `oracle_bots` from the old machine, then:

```bash
chmod 600 /path/to/oracle_bots
export PROP_LAB_VM_KEY=/path/to/oracle_bots     # put this in ~/.bashrc
ssh -i $PROP_LAB_VM_KEY ubuntu@89.168.78.138 'uptime'
```

`factory/deploy_vm.sh` reads `PROP_LAB_VM_KEY` and `PROP_LAB_VM_HOST`, so with
that variable set nothing else needs editing.

**The `claude` CLI.** Only step 1 needs it — proposing ideas and translating
Pine. Steps 2 to 7 are plain Python and run with no login at all. So the box
is useful immediately and only the idea sources wait on it.

---

## 3. Start the board

```bash
./.venv/bin/python -m factory.dashboard      # then open http://127.0.0.1:8765
```

Nothing on that page can start a run — it only watches. Runs are started by
hand:

```bash
# translate whatever Pine is in data/pine/ (needs claude CLI)
./.venv/bin/python -m factory.sources.tradingview --ai

# one full pass, steps 3 to 7
./.venv/bin/python -m factory.nightly --no-agent -n 1 --seeds 5

# clear the board but keep the dedupe
./.venv/bin/python -m factory.reset
```

---

## 4. Where we got to

**The whole line works end to end** — 7 steps, on a real script.

Boxes PRO went in as Pine and came out as
`long when wpr21 above -20 for 2 bars and wpr112 above -20 for 2 bars`.
The model had to be given two new grammar terms to express it: Williams %R,
and "this condition has held for N bars".

**Its result, on gold:**

| timeframe | trades/day | PF | R per trade | eval days | accounts |
|---|---|---|---|---|---|
| 15m | 1.59 | 0.99 | −0.004 | 7.5 | 3.76 |
| **1h** | **0.47** | **1.29** | **+0.155** | **18.1** | 3.62 |
| 4h | 0.16 | 1.80 | +0.359 | 37.7 | 2.35 |
| 1d | 0.04 | 3.23 | +0.705 | 71.2 | 1.78 |

It **stopped at step 6**: on 2021–2023, which we keep hidden, it makes −0.157 R
per trade while entering at *random moments* makes +0.097. Eight repairs were
tried and every one made it worse.

---

## 5. THE OPEN QUESTION — this one is mine to answer

I asked and did not answer it.

Boxes PRO works on 2023–2026 and not before. That can be two different things
and a backtest cannot tell them apart:

* the rule was **fitted** to the recent window (we do try 24 combinations and
  keep the best), or
* gold's behaviour **changed** and the rule genuinely started working.

**Only forward testing separates them** — paper trading from today, on bars
that do not exist yet.

**So: should "works recently, unproven forward" be its own outcome instead of
counting as a failure?** If yes, ideas like this get parked in a paper-trading
list rather than deleted, and earn their place over weeks.

---

## 6. Other things waiting on me

1. **`./factory/deploy_vm.sh`** has never been run. It installs the factory on
   the VM **stopped**; `--arm` starts it. The VM has no `claude` CLI, so it can
   only run steps 2–7 and takes ideas from the queue file.
2. **More Pine scripts.** One script is one data point. `data/pine/`, any
   filename, `--ai` reads them.
3. **TradingView bulk download** is a terms-of-service call. Not built.
4. **Quantpedia** — no reader exists, their library is paid, terms unchecked.

---

## 7. Things not to forget

* **Push before leaving either machine.** The board state lives in
  `backtests/factory/` and it is committed, so an uncommitted run on one PC is
  invisible on the other.
* **`data/feeds/*.parquet` show as modified** and always have — that is from
  before this work, left alone deliberately.
* The five-year caches are `{sym}_dukascopy5y_{tf}.parquet`, deliberately under
  their own name so no existing board number moves.
