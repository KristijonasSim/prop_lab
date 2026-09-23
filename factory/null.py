"""STEP 5 — THE LUCK CHECK. How many survivors does a market with NO EDGE give?

    docs/WORKFLOW.drawio   the picture
    docs/STEP5.md          the design, and what it does that step 3 does not

WHAT KRIS ASKED, 2026-09-23: *"should we keep step 5? it seems like similar
things are done in step 3."* He is right that they overlap and wrong that they
are the same, and the difference is the whole reason this file exists.

    STEP 3 GATE 4 asks:  did this rule pick better bars than random bars,
                         on ONE cell?
    STEP 5 asks:         the factory takes the best of ~30 tries per idea
                         (24 cells, then up to 12 repairs on one of them).
                         How good does BEST-OF-30 look when there is nothing
                         to find?

Nothing upstream prices that. Gate 4 is applied per cell and never to the
maximum over the cells, and step 4 then hands the same idea another twelve
draws. This repo's own history is what makes the gap expensive rather than
theoretical: on 2026-09-08 six information-free gates were walked forward on
gold and **the best-scoring arm of the entire day's work was one of them**;
on 2026-09-17 the fastest number the project had ever produced was withdrawn
because the paired null sped up MORE than the real data did.

HOW THE SCRAMBLE WORKS, and every choice in it is fixed here rather than tuned.

Bars are resampled in BLOCKS of one trading day, from the live bars only, and
re-chained:

  * **Per-bar factors, not prices.** Each live bar contributes
    `(open, high, low, close) / previous live close`. Re-chaining those
    reproduces the market's drift, its volatility clustering inside a block,
    its bar shapes and its weekend gaps, and destroys only the alignment
    between a rule's signal and what follows it. THE DRIFT MUST SURVIVE: gold
    rose 123% over the cached window, and a null that flattened it would be one
    every real idea beats for the wrong reason.
  * **The calendar is not touched.** Timestamps, the hour column and the volume
    column stay on the rows they belong to, so `trading_days`, the session
    repairs and the dead-bar rules all see what they normally see. An
    hour-concentrated effect is therefore compared against an hour-matched
    population - the exact defect `core/probe.py` was caught with on
    2026-09-13 and the reason this is done by row and not by shuffling time.
  * **Dead bars stay dead.** 21.5% of the gold series is padded weekend at a
    frozen price. Those rows are frozen again after re-chaining, so the null
    carries the same closed market the real data does.
  * **One block is one trading day.** Fixed before the first run. Shorter and
    the null keeps no intraday structure; longer and it starts copying whole
    stretches of the real market back in.

WHAT THE OUTPUT MEANS. A count, against a distribution of counts. If forty real
ideas produce one survivor and the scrambled markets produce one as often as
not, the pipeline has found nothing and the honest statement is "nothing above
what luck gives". That sentence has never been available in this repo.

    python -m factory.null -n 40 --seeds 10
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import cells, check, repair                             # noqa: E402
from factory.spec import Strategy                                    # noqa: E402

#: One block is one trading day of bars, per timeframe. Fixed 2026-09-23.
BLOCK_BARS = {"15m": 96, "1h": 24, "4h": 6, "1d": 5}
DEFAULT_BLOCK = 24
#: Prices are rebuilt by multiplying factors, so the level has to stay sane.
#: A factor outside this range is a data error, not a market move.
FACTOR_CLIP = (0.5, 2.0)


def _factors(px: np.ndarray) -> np.ndarray:
    """(n, 4) of open/high/low/close divided by the PREVIOUS close.

    Row 0 is dropped by the caller - it has no previous close to divide by.
    """
    prev = px[:-1, 3][:, None]
    return px[1:] / prev


def scramble(frame: pd.DataFrame, seed: int, block: int) -> pd.DataFrame:
    """The same market with its bar-to-bar ordering destroyed in blocks.

    Everything that is not a price is left exactly where it was: the index, the
    hour column, the volume column and therefore which bars are dead.
    """
    if len(frame) < 3 * block:
        return frame.iloc[0:0]
    out = frame.copy()
    live = (out["volume"].values > 0) if "volume" in out else np.ones(len(out), bool)
    if live.sum() < 3 * block:
        return frame.iloc[0:0]

    px = out.loc[live, ["open", "high", "low", "close"]].values.astype(float)
    fac = _factors(px)
    fac = np.clip(fac, *FACTOR_CLIP)
    n = len(fac)

    rng = np.random.default_rng(seed)
    starts = rng.integers(0, max(n - block, 1), size=n // block + 1)
    idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
    idx = np.clip(idx, 0, n - 1)
    drawn = fac[idx]

    # re-chain: each drawn bar is applied to the close we have arrived at
    c = np.empty(n + 1)
    c[0] = px[0, 3]
    rebuilt = np.empty((n + 1, 4))
    rebuilt[0] = px[0]
    for i in range(n):
        base = c[i]
        bar = drawn[i] * base
        # the drawn factors come from one real bar, so high >= max(open, close)
        # and low <= min(open, close) hold by construction; the clip above is
        # the only thing that could break it, so it is restored explicitly.
        bar[1] = max(bar[1], bar[0], bar[3])
        bar[2] = min(bar[2], bar[0], bar[3])
        rebuilt[i + 1] = bar
        c[i + 1] = bar[3]

    vals = out[["open", "high", "low", "close"]].values.astype(float)
    vals[live] = rebuilt
    # dead bars are frozen at the last live close, which is what the feed does.
    last = np.nan
    for i in range(len(vals)):
        if live[i]:
            last = vals[i, 3]
        elif last == last:
            vals[i] = last
    out[["open", "high", "low", "close"]] = vals
    return out


def loader(seed: int, block_bars: dict | None = None):
    """A drop-in for `cells.load` that serves scrambled markets.

    Cached per (sym, tf) within one seed, because `check_all` asks for the same
    cell twice - once for the gates and once for the trades/day denominator -
    and re-chaining a 145,000-bar series is the expensive part of this file.
    """
    bars = block_bars or BLOCK_BARS
    cache: dict[tuple[str, str], pd.DataFrame] = {}

    def load(sym: str, tf: str) -> pd.DataFrame:
        key = (sym, tf)
        if key not in cache:
            real = cells.load(sym, tf)
            cache[key] = (real.iloc[0:0] if not len(real) else
                          scramble(real, seed + hash(key) % 1000,
                                   bars.get(tf, DEFAULT_BLOCK)))
        return cache[key]

    return load


@dataclass
class Tally:
    """What one pass of the pipeline produced over a fixed idea list."""
    label: str
    ideas: int = 0
    passed_step3: int = 0
    repaired: int = 0
    survivor_names: list[str] = field(default_factory=list)

    @property
    def survivors(self) -> int:
        return self.passed_step3 + self.repaired

    def __str__(self) -> str:
        return (f"{self.label:18}{self.ideas:>7}{self.passed_step3:>10}"
                f"{self.repaired:>10}{self.survivors:>11}")


def run_pipeline(ideas: list[Strategy], *, label: str, loader_fn=None,
                 cell_list=None, control_seeds: int = check.CONTROL_SEEDS,
                 do_repair: bool = True) -> Tally:
    """Steps 3 and 4 over a fixed idea list. The same code on either market."""
    t = Tally(label=label, ideas=len(ideas))
    for s in ideas:
        checks = check.check_all(s, cell_list, control_seeds=control_seeds,
                                 loader=loader_fn)
        if any(c.verdict == "PASS" for c in checks):
            t.passed_step3 += 1
            t.survivor_names.append(s.label())
            continue
        if not do_repair:
            continue
        _, fixed = repair.repair(s, checks, control_seeds=control_seeds,
                                 loader=loader_fn)
        if fixed is not None:
            t.repaired += 1
            t.survivor_names.append(fixed.label())
    return t


def compare(ideas: list[Strategy], seeds: int = 10, **kw) -> dict:
    """The real pipeline against `seeds` scrambled ones, same ideas throughout.

    The p-value is the share of scrambled passes that matched or beat the real
    one. It is one-sided and it is deliberately crude: with ten seeds the
    smallest value it can report is 0.09, and quoting a smaller number than the
    seed count supports is how this repo has been wrong before.
    """
    real = run_pipeline(ideas, label="real market", **kw)
    nulls = [run_pipeline(ideas, label=f"scrambled #{i}",
                          loader_fn=loader(1000 * (i + 1)), **kw)
             for i in range(seeds)]
    counts = np.array([n.survivors for n in nulls], dtype=float)
    beat = int((counts >= real.survivors).sum())
    return {
        "real": real, "nulls": nulls,
        "real_survivors": real.survivors,
        "null_mean": float(counts.mean()) if len(counts) else float("nan"),
        "null_max": int(counts.max()) if len(counts) else 0,
        "seeds": seeds,
        "p_value": (beat + 1) / (seeds + 1),
    }


def _main(argv=None) -> int:
    """Run steps 3+4 on the real market and on scrambled copies of it."""
    import argparse

    from factory import queue

    ap = argparse.ArgumentParser(description=_main.__doc__)
    ap.add_argument("-n", "--count", type=int, default=20,
                    help="ideas to take off the queue")
    ap.add_argument("--seeds", type=int, default=10,
                    help="scrambled markets to run the same ideas through")
    ap.add_argument("--market", action="append")
    ap.add_argument("--tf", action="append")
    ap.add_argument("--control-seeds", type=int, default=check.CONTROL_SEEDS)
    a = ap.parse_args(argv)

    ideas = [s for s in (queue.take() for _ in range(a.count)) if s is not None]
    if not ideas:
        print("queue is empty - run `python -m factory.fill` first")
        return 1
    cell_list = cells.all_cells(a.market, tuple(a.tf) if a.tf else None)
    print(f"step 5: {len(ideas)} ideas x {len(cell_list)} cells, "
          f"{a.seeds} scrambled markets\n")

    res = compare(ideas, seeds=a.seeds, cell_list=cell_list,
                  control_seeds=a.control_seeds)
    head = f"{'market':18}{'ideas':>7}{'step 3':>10}{'repaired':>10}{'survivors':>11}"
    print(head); print("-" * len(head))
    print(res["real"])
    for n in res["nulls"]:
        print(n)
    print("-" * len(head))
    print(f"\nreal {res['real_survivors']}   "
          f"scrambled mean {res['null_mean']:.1f}, worst case {res['null_max']}"
          f"   p = {res['p_value']:.2f}")
    if res["p_value"] > 0.1:
        print("\nLUCK IS NOT EXCLUDED. A scrambled market with no information "
              "in it produced\nas many survivors as the real one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
