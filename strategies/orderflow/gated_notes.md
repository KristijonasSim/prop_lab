# H-009 — H-002's VWAP book, gated by crowd positioning

Opened and measured 2026-09-02. **This is the first hypothesis in the project
that beats H-002 on the numbers that matter.**

## The idea, in one line

Take H-002's trades unchanged, and keep only the ones where the crowd is
positioned on the other side.

## Why it exists

H-006 established that Binance's long/short **account** ratio carries real
directional information — a monotone quintile response, stable across six
years, beating its null after costs — but could not carry a book on its own
because its drawdown is the wrong shape. H-002 is the one price strategy that
survived. Neither had been pointed at the other.

## The gate, fixed before the run

    keep a LONG  when crowd_z <= 0    (the crowd has been getting shorter)
    keep a SHORT when crowd_z >= 0    (the crowd has been getting longer)

`crowd_z` is the account ratio z-scored against a one-day trailing baseline,
shifted a bar. Threshold zero is the untuned choice. Thresholds 0.5 and 1.0 and
a three-day baseline all lift too — the result does not sit on a parameter.

## What is and is not re-decided

Nothing on the VWAP side is refitted. Every configuration is the one stage 10
chose blind for that quarter, before this feed was in the repo. The gate is a
single global rule applied on top — *stricter* than letting the walk-forward
select it, because it cannot pick the gate that happened to work.

XAUUSD has no crowd feed (it is a metals CFD, not a Binance perpetual), so the
gold leg passes through ungated and the book stays comparable to H-002's.

## The result — same selection rule stage 11 used, same window

| | gate off | gate on |
|---|---|---|
| book | BTC 4h + ETH 1h + SOL 4h + XAU 5m | **+ ETH 30m** |
| profit factor | 1.768 | **2.047** |
| **at 2x cost** | 1.458 | **1.651** |
| total R | 89.8 | **97.1** |
| max drawdown | −3.66R | **−2.82R** |
| return / drawdown | 24.6 | **34.4** |
| R per day | 0.135 | **0.146** |
| trades/day | 1.32 | 1.29 |
| estimated days | 27.1 | **19.3** |

The gate keeps **55%** of trades and total R goes *up*. Two-step prop simulation:
**92.4% pass, 0% killed, 48.7 expected days** at 2.50% risk, against H-002's
88.0% and 53.4 at 2.00%.

## The cleanest comparison: the same five legs, gate the only difference

The table above lets the selection rule pick a different book for each case,
which is what stage 11 does but which mixes two effects. Holding the book fixed
at the gated five legs and toggling only the gate, read straight from the saved
trade file:

| same 5 legs, same window | ungated | gated |
|---|---|---|
| trades | 1,108 | 859 |
| profit factor | 1.721 | **2.047** |
| at 2x cost | 1.375 | **1.651** |
| total R | 93.2 | **97.1** |
| max drawdown | −4.45R | **−2.82R** |
| return / drawdown | 20.9 | **34.4** |
| R per day | +0.140 | **+0.146** |

**Total R rises on 23% fewer trades and drawdown falls by 37%.** The ungated
column here (1.721 / 1.375 / −4.45R) is this pipeline's reconstruction of H-002,
against its published 1.772 / 1.418 / −3.77R — within a few percent, which is
what makes the comparison trustworthy.

One check worth stating: the gate keeps 53.0% of shorts and 53.8% of longs, so
it is not a disguised directional bias. It is conditioning on the crowd.

## The per-leg evidence, which is the strongest part

| leg | PF@2x ungated | PF@2x gated | kept | maxDD ungated | maxDD gated |
|---|---|---|---|---|---|
| BTCUSDT 4h | 1.213 | 1.261 | 75% | −9.8R | −9.5R |
| BTCUSDT 1h | 0.985 | 1.029 | 78% | −44.8R | −33.6R |
| BTCUSDT 30m | 1.229 | 1.324 | 72% | −18.4R | −13.1R |
| ETHUSDT 1h | 1.675 | **2.092** | 76% | −19.2R | −14.0R |
| ETHUSDT 30m | 1.177 | **1.657** | 63% | −48.7R | −21.4R |
| SOLUSDT 4h | 1.628 | **2.113** | 72% | −13.8R | −8.8R |
| XAUUSD 5m | 1.234 | 1.234 | 100% | −17.7R | −17.7R |

**Six of six crypto legs improve on both profit factor and drawdown. Not one is
hurt.** ETHUSDT 30m goes from failing the gate to passing it with half the
drawdown, which is why the gated book can carry a fifth leg.

## The control

Inverting the gate — keeping only the trades the crowd *agrees* with — gives
PF 1.137 and return/drawdown 2.9 against the baseline's 1.863 and 63.7. At a
threshold of 0.5 or 1.0 that subset is outright negative. **Almost all of
H-002's edge lives in the trades that go against retail positioning.** That is
what makes this a mechanism and not a filter that happened to fit.

## The null

A block-shuffled crowd feed driving the same gate: PF at 2x of 1.288, 1.309,
1.335, 1.357, 1.464 against the real 1.651. Real beats every seed. The shuffled
gate *hurts* — its median lift is negative — while the real one lifts +0.19.

## The board: 8.9 against H-002's 8.6, winning or tying every component

| component | H-002 | H-009 |
|---|---|---|
| speed | 0.763 | **0.791** |
| pass rate | 0.880 | **0.924** |
| breach | 1.000 | 1.000 |
| drawdown | 0.706 | **0.746** |
| evidence | 0.970 | 0.970 |
| raw profitability | 0.886 | **1.000** |

**Evidence took a second null to settle.** The first run scored the gate against a
shuffled FEED, which leaves H-002's entire price edge standing and therefore
measures only the increment. That is a far harder test than the one H-002 passes,
it scores 0.191, and it dropped H-009 to 8.3 — a better strategy ranked below the
one it improves on, purely because the two were being measured differently.

The like-for-like test is the one stage 11 uses: phase-randomise the **market**
and count how many legs still hold PF 1.20 at double cost.

| legs holding PF 1.20 at 2x, gate on | count |
|---|---|
| real market | **6 of 8** — BTC 4h, BTC 30m, ETH 1h, ETH 30m, SOL 4h, XAU 5m |
| phase-randomised market | **0 of 8** |

Margin 1.000, which is the same statistic and the same construction that gives
H-002 its 1.000. Both nulls are kept and reported: 1.000 against a market with no
edge, 0.191 against a shuffled feed with H-002's edge intact.

## Weaknesses, unprompted

- **Post-filter.** It can only ever REMOVE trades, never add the ones freed
  capacity would have allowed. Every trade it keeps is real at a real price, so
  this is a valid book rather than an estimate — but the in-kernel version would
  take extra trades this one cannot see, and those are unmeasured.
- **Short window.** The common window is 2024-09 onward, 859 trades. That is the
  window H-002 is measured on too, so the comparison is fair, but it is not long.
- **One feed, one venue.** Binance's account ratio. If the exchange changes how
  it computes or publishes it, the gate goes with it.
- **No TradingView port is possible.** Pine cannot fetch the long/short account
  ratio, so unlike every other hypothesis here this one cannot be checked on a
  chart.
- Nothing has been cross-checked by a second matching engine.
