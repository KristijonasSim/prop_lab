"""ENGINE 1 — what to test next, and why. Never how.

Kris chose this shape on 2026-09-18: *"C target with B machinery"* — hunt new
DATA FEEDS (the only family that has ever worked in two repos), with a model
driving the search (the only way the space does not run out at sixteen ideas).

WHAT THE MODEL IS AND IS NOT ALLOWED TO DO

    allowed      pick a feed, a transform, a window, a lag, a market, a hold,
                 a direction. Write the MECHANISM - why an edge should exist
                 and who is on the other side.
    forbidden    write code, touch the data, set the costs, choose the null,
                 move the gate, or see a price, a date or a recent return.

The second list is not a policy, it is the type system: a proposal is a set of
enum choices validated against `research/vocab.py`, so a look-ahead feature is
not something the model is asked to avoid - it is something it cannot express.
arXiv 2608.27734 planted an oracle with Sharpe 34.7 and deflation scored it a
perfect 1.00, so statistics are not the guard. The registry is.

**THE MODEL NEVER SEES THE CALENDAR.** Carried over from the sibling repo's
`brain.py`, which states the reason: a model asked about a past period already
knows how it ended, and Llama-2 volunteers Covid in over a quarter of
Sept-Nov 2019 prompts. No date, no price, no recent performance goes into the
prompt. It sees feed names, mechanism text, and what has already been tried.

THE ONE RULE THAT MAKES QUANTITY WORTH ANYTHING. A proposal already in the
ledger is refused, and so is anything on `CLAUDE.md`'s known-dead list. The bar
rises with the log of the trial count whether or not a trial was informative
(`core/searchcost.py`), so re-testing dead space costs exactly as much as
testing new space and buys nothing. This is AlphaMemo's finding and it is the
difference between a loop that compounds and a loop that spins.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ledger import read as read_ledger                    # noqa: E402
from core.universe import STANDARD                             # noqa: E402
from research import vocab                                     # noqa: E402

CLI_MODEL = "sonnet"
TIMEOUT = 300

#: Feed families this project has already killed, by name. A proposal naming one
#: is refused with the reason, so the model is told rather than silently ignored.
KNOWN_DEAD: dict[str, str] = {
    "COT": "H-030: eight CFTC positioning gates, every one slower than no gate "
           "(26.3-64.1 expected days against 21.7).",
    "NETFLOW": "H-035: on-chain exchange netflow alternates sign when the "
               "knowable lag moves one day. Also never honestly testable - "
               "every value is revised later.",
    "FUNDING": "H-004 / H-013 / H-036: funding as level and as event, both dead.",
    "BASIS": "H-034: the dated contract is a feed, never a trade - it turns "
             "over one thousandth of the perp.",
    "DEPTH": "H-024: real, monotone, beats its null, and 0 of 935 cells clear "
             "a 14bps taker round trip.",
}


@dataclass(frozen=True)
class Candidate:
    """One thing to test. Every field is an enum choice or a sentence."""
    feed: str
    transform: str
    window: int
    lag: int
    market: str
    hold: int
    direction: int          # +1 high values predict up, -1 predict down
    mechanism: str = ""
    origin: str = "library"

    @property
    def key(self) -> str:
        """Identity for duplicate detection. Mechanism text is NOT part of it -
        two different stories about the same test are the same test."""
        return (f"{self.feed}|{self.transform}|{self.window}|{self.lag}"
                f"|{self.market}|{self.hold}|{self.direction:+d}")

    @property
    def name(self) -> str:
        # `level` takes no window, so it gets no suffix - an earlier version
        # printed "level-" and it read like a typo on the page.
        w = f"{self.window}" if self.window else ""
        return f"{self.feed}.{self.transform}{w}.{self.market}.h{self.hold}"


class ProposalError(Exception):
    """Raised with a message meant for the MODEL, not for a human. Structured
    errors go back into the loop so the next attempt is corrected rather than
    discarded - the registry pattern's whole point."""


def validate(d: dict) -> Candidate:
    """Turn a raw dict into a Candidate or raise with a correctable message."""
    def need(k):
        if k not in d:
            raise ProposalError(f"missing field '{k}'")
        return d[k]

    feed = str(need("feed"))
    if feed not in vocab.FEEDS:
        raise ProposalError(
            f"unknown feed '{feed}'. Choose one of: {sorted(vocab.FEEDS)}")
    for dead, why in KNOWN_DEAD.items():
        if dead in feed.upper():
            raise ProposalError(f"feed '{feed}' is known-dead. {why}")

    tr = str(need("transform"))
    if tr not in vocab.TRANSFORMS:
        raise ProposalError(
            f"unknown transform '{tr}'. Choose one of: {sorted(vocab.TRANSFORMS)}")

    needs_window = vocab.TRANSFORMS[tr][1]
    window = int(d.get("window") or 0)
    if needs_window and window not in vocab.WINDOWS:
        raise ProposalError(
            f"transform '{tr}' needs a window from {vocab.WINDOWS}, got {window}")
    if not needs_window:
        window = 0

    spec = vocab.FEEDS[feed]
    # `or` would be wrong here: lag=0 is falsy, so an explicit request for a
    # same-day (look-ahead) lag would be silently upgraded to the floor and the
    # attempt never reported. An omitted lag defaults; a supplied one is checked.
    raw_lag = d.get("lag")
    lag = spec.lag_floor if raw_lag is None else int(raw_lag)
    if lag < spec.lag_floor:
        raise ProposalError(
            f"lag {lag} is below the floor {spec.lag_floor} for '{feed}': "
            f"{spec.lag_reason}")

    market = str(need("market"))
    allowed = spec.markets or tuple(STANDARD)
    if market not in allowed:
        raise ProposalError(
            f"feed '{feed}' does not apply to '{market}'. Allowed: {list(allowed)}")

    hold = int(need("hold"))
    if hold not in vocab.HOLDS:
        raise ProposalError(f"hold must be one of {vocab.HOLDS}, got {hold}")

    direction = int(d.get("direction", spec.prior_sign or 1))
    if direction not in (1, -1):
        raise ProposalError("direction must be +1 or -1")
    if spec.prior_sign and direction != spec.prior_sign:
        raise ProposalError(
            f"feed '{feed}' has a declared prior sign of {spec.prior_sign:+d} "
            f"and you asked for {direction:+d}. {spec.sign_reason} "
            "Testing a feed both ways is a free second attempt at the same "
            "question - one of the two directions always matches the data. "
            "If the mechanism genuinely points the other way, the registry's "
            "sign is what has to change, in a commit, with the reason.")

    mech = str(d.get("mechanism", "")).strip()
    if len(mech) < 40:
        raise ProposalError(
            "mechanism must say why an edge should exist AND who is on the "
            "other side of the trade, in at least 40 characters")

    return Candidate(feed=feed, transform=tr, window=window, lag=lag,
                     market=market, hold=hold, direction=direction,
                     mechanism=mech, origin=str(d.get("origin", "library")))


# ---------------------------------------------------------------------------
# Memory — what has already been spent
# ---------------------------------------------------------------------------
def tried_keys() -> set[str]:
    """Candidate keys already in the ledger.

    Read from `params`, where `research/run.py` stores the key. Historical rows
    backfilled from `STRATEGY_LOG.md` have no key and are simply not matched -
    they still COUNT against the search budget, they just cannot be deduplicated.
    """
    out: set[str] = set()
    for t in read_ledger():
        if not t.params:
            continue
        try:
            p = json.loads(t.params)
        except (ValueError, TypeError):
            continue
        k = p.get("candidate_key")
        if k:
            out.add(k)
    return out


def enumerate_space(markets: tuple[str, ...] = tuple(STANDARD)) -> list[Candidate]:
    """Every candidate the registry can express. Deterministic order.

    **ONE DIRECTION PER FEED, the one its mechanism claims.** The first draft
    emitted both, which halves nothing and doubles the trial count while
    guaranteeing that one of the pair matches the data whatever the data says.
    A feed with `prior_sign = 0` is skipped entirely: no declared sign means no
    written mechanism, and an unmechanised feed is not a candidate.
    """
    out: list[Candidate] = []
    for fname in sorted(vocab.FEEDS):
        spec = vocab.FEEDS[fname]
        if not spec.prior_sign:
            continue
        mk = spec.markets or markets
        for tr in sorted(vocab.TRANSFORMS):
            wins = vocab.WINDOWS if vocab.TRANSFORMS[tr][1] else (0,)
            for w in wins:
                for m in mk:
                    for h in vocab.HOLDS:
                        out.append(Candidate(
                            feed=fname, transform=tr, window=w,
                            lag=spec.lag_floor, market=m, hold=h,
                            direction=spec.prior_sign,
                            mechanism=f"{spec.desc}. {spec.sign_reason}",
                            origin="library"))
    return out


def unmechanised() -> list[str]:
    """Feeds in the registry with no declared sign — harvested but not testable
    until somebody writes the mechanism. Shown on the dashboard on purpose."""
    return sorted(f.name for f in vocab.FEEDS.values() if not f.prior_sign)


def untried(markets: tuple[str, ...] = tuple(STANDARD)) -> list[Candidate]:
    done = tried_keys()
    return [c for c in enumerate_space(markets) if c.key not in done]


# ---------------------------------------------------------------------------
# The two proposers
# ---------------------------------------------------------------------------
def propose_library(n: int = 1,
                    markets: tuple[str, ...] = tuple(STANDARD)) -> list[Candidate]:
    """Deterministic fallback: walk the space breadth-first across feeds.

    Breadth-first ON PURPOSE. Depth-first would spend the whole budget tuning
    windows on one feed, which is the pattern that closed eight axes of H-027
    and produced nothing. One candidate per feed, then the next transform.
    """
    pool = untried(markets)
    if not pool:
        return []
    by_feed: dict[str, list[Candidate]] = {}
    for c in pool:
        by_feed.setdefault(c.feed, []).append(c)
    out: list[Candidate] = []
    while len(out) < n and by_feed:
        for f in sorted(by_feed):
            if by_feed[f]:
                out.append(by_feed[f].pop(0))
            if not by_feed[f]:
                del by_feed[f]
            if len(out) >= n:
                break
    return out[:n]


SYSTEM = """You choose what a systematic trading research loop tests next.

WHAT YOU ARE DOING
This project hunts DATA FEEDS, not price patterns. Across two repositories
every edge that ever survived came from a new data feed; twelve price-pattern
hypotheses and five feed hypotheses have died. Your job is to pick the next
feed/transform/market combination worth a test, and to state the MECHANISM.

A MECHANISM NAMES THE LOSER. "Gold rises when real yields fall" is a
correlation. "Gold pays no coupon, so when the real yield falls the opportunity
cost of holding it falls, and the marginal seller is a real-money allocator
rebalancing against TIPS" is a mechanism. If you cannot name who is on the
other side, say so in the mechanism field rather than inventing one.

HARD CONSTRAINTS
- You may ONLY use the feeds, transforms, windows and holds listed below.
- You may not write code, choose costs, choose the null, or move any gate.
- You will not be shown prices, dates, or any result's recent performance.
- A combination already tried is refused. Do not propose one.

OUTPUT
A JSON array, one object per candidate, no prose around it:
[{"feed": "...", "transform": "...", "window": 20, "lag": 1,
  "market": "XAUUSD", "hold": 5, "direction": 1, "mechanism": "..."}]
direction is +1 if HIGH values of the transformed feed predict the market UP,
-1 if they predict it DOWN."""


def _prompt(n: int, pool: list[Candidate]) -> str:
    feeds = "\n".join(
        f"  {f.name:16}{f.kind:12}{f.desc}"
        f"{'  [' + f.notes[0] + ']' if f.notes else ''}"
        for f in sorted(vocab.FEEDS.values(), key=lambda x: x.name))
    dead = "\n".join(f"  {k}: {v}" for k, v in KNOWN_DEAD.items())
    sample = sorted({c.key for c in pool})[:40]
    return f"""{SYSTEM}

FEEDS AVAILABLE
{feeds}

TRANSFORMS: {sorted(vocab.TRANSFORMS)}
WINDOWS:    {list(vocab.WINDOWS)}   (ignored by 'level')
HOLDS:      {list(vocab.HOLDS)}     (trading days)
MARKETS:    {STANDARD}

KNOWN DEAD - do not propose these feed families
{dead}

UNTRIED COMBINATIONS REMAIN: {len(pool)}. A sample of their keys, in the format
feed|transform|window|lag|market|hold|direction:
{chr(10).join('  ' + s for s in sample)}

Propose {n} candidate(s). JSON array only."""


def propose_llm(n: int = 1, markets: tuple[str, ...] = tuple(STANDARD),
                model: str = CLI_MODEL, timeout: int = TIMEOUT) -> list[Candidate]:
    """Ask the model to pick, then validate hard against the registry.

    Uses `claude -p` on the logged-in session so no API key is needed, run from
    a neutral working directory so this repo's own CLAUDE.md is not pulled into
    every call. Anything that fails validation is dropped with its reason
    recorded; the caller falls back to the library proposer rather than
    stopping, because an unattended loop that halts on a bad parse is not
    unattended.
    """
    pool = untried(markets)
    if not pool:
        return []
    done = {c.key for c in enumerate_space(markets)} - {c.key for c in pool}

    try:
        proc = subprocess.run(
            ["claude", "-p", _prompt(n, pool), "--model", model],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.expanduser("~"),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ProposalError(f"model call failed: {exc}") from exc
    if proc.returncode != 0:
        raise ProposalError(f"model exited {proc.returncode}: {proc.stderr[:300]}")

    text = proc.stdout.strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ProposalError(f"no JSON array in model output: {text[:300]}")
    try:
        raw = json.loads(text[start:end + 1])
    except ValueError as exc:
        raise ProposalError(f"bad JSON: {exc}") from exc

    out: list[Candidate] = []
    rejected: list[str] = []
    for item in raw:
        try:
            c = validate({**item, "origin": "llm"})
        except ProposalError as exc:
            rejected.append(f"{item.get('feed', '?')}: {exc}")
            continue
        if c.key in done:
            rejected.append(f"{c.name}: already in the ledger")
            continue
        if any(c.key == o.key for o in out):
            rejected.append(f"{c.name}: duplicate within this batch")
            continue
        out.append(c)

    # Reported, never swallowed. An unattended loop whose generator has started
    # emitting invalid proposals looks exactly like one that is working, and the
    # only difference visible from outside is this line.
    if rejected:
        print(f"[propose] model returned {len(raw)}, kept {len(out)}, "
              f"rejected {len(rejected)}:", file=sys.stderr)
        for r in rejected:
            print(f"  - {r}", file=sys.stderr)
    return out[:n]


def propose(n: int = 1, mode: str = "library",
            markets: tuple[str, ...] = tuple(STANDARD)) -> list[Candidate]:
    """The entry point. `mode` is 'library' or 'llm'; llm falls back on failure."""
    if mode == "llm":
        try:
            got = propose_llm(n, markets)
            if got:
                return got
        except ProposalError as exc:
            print(f"[propose] llm unavailable, falling back: {exc}",
                  file=sys.stderr)
    return propose_library(n, markets)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="what to test next")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--mode", choices=("library", "llm"), default="library")
    a = ap.parse_args(argv)

    space = enumerate_space()
    pool = untried()
    print(f"space {len(space):,} candidates, {len(pool):,} untried, "
          f"{len(space) - len(pool):,} already in the ledger")
    print()
    for c in propose(a.n, a.mode):
        print(f"  {c.name:38}{c.origin:9}dir {c.direction:+d}  lag {c.lag}")
        print(f"      {c.mechanism[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
