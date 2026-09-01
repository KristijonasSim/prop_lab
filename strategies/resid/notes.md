# H-008 — Beta-residual reversion

**Status: rejected at stage 1.** The real data reverts *less* than shuffled noise.
This is the H-005 failure repeated, and it was predicted in the kernel docstring
before the run.

## Mechanism (stated before the results)

BTC is the liquidity centre of crypto and the alts trade mostly as a beta to it.
Strip the BTC factor out and what remains — the residual — is the coin-specific
part of the move. The claim: a large short-horizon residual is a *liquidity*
event, not information. Someone had to exit an illiquid book right now and paid
whatever the book charged. Nothing about the coin changed, so once the pressure
stops, makers refill and the residual reverts. On the other side: the trader who
could not wait, and the maker who wants paying for unwanted inventory.

**Why it should have beaten H-002.** VWAP mean reversion fades an asset from its
own volume-weighted average and cannot tell a liquidity move from an informed
one — if BTC drops 3% and ETH follows, VWAP sees an ETH overshoot and fades a
move that had a perfectly good reason to happen. Removing the market factor
first is a better-conditioned version of the same instinct: fade only the part
with no reason to persist. Four alts throwing signals is also more R per day than
five single-asset legs, and `days = maxDD_in_R / R_per_day`.

## What was run

1,152 configurations: 4 timeframes (15m/30m/1h/4h) × 3 beta windows (50/100/200)
× 4 residual lookbacks (2/4/8/16) × 4 z thresholds (1.5/2.0/2.5/3.0) × 3 holds
× hedged/naked, each at 0x/1x/2x/3x cost, on ETH, SOL, BNB and XRP against BTC,
2020-08 → 2026-08. Every configuration re-run on 5 paired-shuffle null panels.

Exit is **fixed-hold only** — no stop, no target. Both would need an intrabar
"which touched first" assumption, and this repo has already been burned once by a
fill assumption (the VWAP std-band result that backtested at PF 3.0 and traded at
0.7). A fixed hold has no fill ambiguity. It understates the strategy; that is
the right direction to be wrong in.

## Result

| | real | paired null |
|---|---|---|
| configs clearing PF 1.20 at 2x | **0** of 1152 | 2 / 0 / 0 / 0 / 0 |
| best config PF at 2x | 0.940 | **1.496** |
| median PF before costs (0x) | 1.002 | **1.005** |
| configs beating PF 1.0 at 0x | 51.6% | **55.4%** |
| median PF at 1x | 0.565 | **0.693** |

## Reading

**The residual does not revert.** Median profit factor before any costs is 1.002
and 51.6% of configurations beat 1.0 — a coin flip. Nothing here is cost-limited;
there is no edge to protect.

**The null is better than the real data on every single cut.** More configs
profitable before costs, higher median, higher best, more gate-clearing cells.
This is precisely the H-005 result: a fade rule is *easier* to satisfy on
phase-randomised data, because shuffled series revert around their extremes more
readily than real trending ones. The kernel docstring named this as the main risk
before the run; it is what happened.

**The decisive diagnostic is the z-response, and it is flat.** Median PF before
costs by entry threshold: z≥1.5 → 1.000, z≥2.0 → 0.997, z≥2.5 → 1.006, z≥3.0 →
1.013. If the mechanism were real, a three-sigma residual would revert far harder
than a 1.5-sigma one. It does not move. The size of the deviation carries no
information about what happens next, which is as clean a refutation as this
project has produced.

**The hedge does isolate something, and it is not enough.** Hedged median PF
before costs is 1.021 against naked 0.985 — so removing BTC genuinely does leave
a marginally more mean-reverting series. But it is a 2% effect, and hedging
crosses two spreads instead of one, so after costs the hedged variant is the
worse of the two (median PF at 2x: 0.142 hedged vs 0.482 naked). Both are far
under 1.0.

## What this closes off, taken with H-007

H-007 ranked the majors and traded the spread; H-008 hedged out the factor and
faded the residual. Continuation and reversion, on the same relative structure,
in opposite directions. H-007 found a real but tiny edge (~10% on PF, beaten by a
14bps round trip). H-008 found nothing at all.

**Together they say the relative structure of the crypto majors is not tradeable
at retail cost.** That is a family, not a hypothesis, and it should not be
reopened without either a much wider universe or a much cheaper venue.

## Methodology note

The naked variant is sized on the coin's **total** volatility, not the residual's.
A naked trade keeps the whole BTC beta, so residual-vol sizing would divide its
losses by less risk than it actually ran and flatter it against the hedged
variant. The first run of this grid had that bug; it was fixed before the numbers
above, and correcting it moved essentially nothing (0 of 1152 either way).
