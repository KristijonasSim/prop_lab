# Step 7 — run the evaluation. Design, 2026-09-23

Settled with Kris 2026-09-21: **two numbers, pass % and days to pass.**

`factory/evaluate.py`, `tests/test_factory_steps567.py`.

---

## 1. Why those two and not the usual ones

**Not profit factor.** It is highest for a tight stop that wins one time in
twenty and pays huge — the worst possible shape to carry into a 3% daily cap.
A rule can have a fine PF and blow every account before it passes.

**Not trades per day.** That was measured to be actively misleading on
2026-09-17: `expected_days = median_days / pass_rate` treats a blown account as
free, so any lever that raises trade frequency buys apparent speed. On BTCUSDT
every cell **lost money** (PF@2x 0.44–0.80) and the wide configuration still
"resolved" an evaluation in 14.5 days against 28.2.

---

## 2. Accounts consumed — the debt this step pays

`1 / pass_rate` is how many evaluations are bought per funded seat. At €40–100
each it is a real cost the board has never shown.

| gold, like for like | pass % | accounts per funded seat |
|---|---|---|
| the shipped rule | 39.3 | **2.5** |
| the withdrawn wide one | 33.9 | **3.0** |

It is printed in its own column beside expected days, on every rung. The
standing rule from the same day still holds: **never compare expected days
across configurations with different trade frequencies without a null** — which
is step 5, upstream.

---

## 3. A candidate has a curve, not a score

Risk per trade trades the two numbers against each other: bigger size is fewer
days **and** a lower pass rate. So the whole ladder is printed and no rung is
picked — the choice is Kris's, and `NEXT.md` parks "where on the curve do we
sit" until a real candidate produces one.

**The ladder is the one thing in this repo not subject to the noise floor.**
Re-simulating a fixed trade series at another position size selects nothing and
searches nothing. It is arithmetic.

Every rung still carries its **band** (`core/noiseband.py`), because the
2026-09-08 floor governs everything else: six information-free gates scored
between 13.3 and 26.5 expected days, so a days figure without its band is not
evidence.

---

## 4. The spec

`core.prop_rules.HOUSE` — **8% target, 3% daily, 6% max**, set by Kris
2026-09-15. Deliberately harsher than anything we would buy (FundingPips Flex
is 10/4/12), so every number reads as a floor rather than a best case.

Fixed risk per trade, real breaches, a fresh account every trading day, no
budget-shrinking risk manager. If it fails, it fails.

---

## 5. What it reads

```
python -m factory.evaluate
```

Columns: `risk`, `pass %`, `median` days to pass, `expected` days, the
expected-days **band**, `accounts` consumed, peak drawdown at that risk, and the
two breach rates. Then one line saying where the fastest allowed rung sits
against the 5–14 day pace target, or `TOO SLOW` past 50.

Scored over everything the candidate has been tested on — the holdout plus the
step-3 window — because a pass rate is a count of simulated accounts and more
history is more accounts. `--three-year` scores the step-3 window alone.

---

## 6. What it is not

It is a prop simulation on one cell's trade series, **not a walk-forward**.
Nothing is fitted here because nothing in a factory idea is fittable — the stop,
target and hold are fixed at generation. What protects the number is step 5's
null and step 6's holdout, both upstream. Step 7 only prices what they let
through.
