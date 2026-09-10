"""THE STRATEGY KRIS TRADES. One place, read by the board and by the indicator.

Chosen 2026-09-09 after the exit study and the top-N study:

    XAUUSD 1h, wide stop, five settings in parallel, 2% risk per trade
    59.8% of accounts pass, 21.7 expected days to a funded account

WHY THIS ONE AND NOT THE FASTEST. `top 1` at 4% risk reaches 60.1% pass in 18.3
days - three days quicker - and it takes 0.15 trades a day, which is two or three
trades inside a whole evaluation. An account that resolves on two trades resolves
on luck, whichever way it goes. Five settings give the same pass rate on six
times the trades, and blow up less often (33.9% against 39.6%).

WHY IT IS PINNED HERE RATHER THAN DERIVED FROM THE BOARD. The blind selector
ranks configurations on profit factor, and profit factor is maximised by a very
tight stop that wins 5% of the time and pays hugely when it does. That is the
opposite of what a prop evaluation rewards. Until the selector's objective is
fixed - the open TASK - the board's own pick is not the thing to trade, so the
choice is stated here explicitly, with the numbers it was made on, rather than
inferred from a pipeline that is aiming at something else.

EVERY NUMBER BELOW IS OUT OF SAMPLE, from the blind quarterly walk-forward in
`strategies/vwapbreak/research/exits.py` + the top-N run (`backtests/vwapbreak/
topn.json`). None of it is a promise: the band on 21.7 days is 16.8-31.4, which
overlaps the measured luck zone, and the strategy has never traded a live bar.

THE SETTINGS EXPIRE. They were ranked on the twelve months ending 2026-08-30 and
are traded unchanged for one quarter. Re-rank on 2026-12-01: same procedure, new
twelve months, swap the five, do not touch them in between.
"""
from __future__ import annotations

#: The five configurations traded in parallel, each at a fifth of the risk.
#: Ranked by profit factor at double cost on the training window below - the
#: same rule the walk-forward applies inside every fold.
SETTINGS = [
    {"thr": 1.00, "stop_sig": 3.0, "max_hold": 384, "hour_lo": 0, "hour_hi": 0,
     "min_rvol": 0.0},
    {"thr": 1.50, "stop_sig": 4.0, "max_hold": 384, "hour_lo": 0, "hour_hi": 0,
     "min_rvol": 1.0},
    {"thr": 0.50, "stop_sig": 3.0, "max_hold": 384, "hour_lo": 0, "hour_hi": 0,
     "min_rvol": 1.0},
    {"thr": 0.75, "stop_sig": 4.0, "max_hold": 384, "hour_lo": 7, "hour_hi": 16,
     "min_rvol": 1.0},
    {"thr": 1.50, "stop_sig": 4.0, "max_hold": 384, "hour_lo": 0, "hour_hi": 0,
     "min_rvol": 0.0},
]

CHOSEN = {
    "sid": "vwapbreak",
    "hid": "H-027",
    "name": "VWAP band breakout — gold 1h, five settings",
    "market": "XAUUSD",
    "tf": "1h",
    "rule": "floor 30 / top 5",
    "risk_pct": 2.0,                  # total account risk per trade
    "risk_each_pct": 0.4,             # 2.0 / 5, one fifth per setting
    "trained_to": "2026-08-30",
    "train_months": 12,
    "refresh_on": "2026-12-01",
    "settings": SETTINGS,

    # --- what the walk-forward measured, at 2% risk ------------------------ #
    "measured": {
        "pass_pct": 59.8,
        "days_to_pass": 21.7,
        "days_band": [16.8, 31.4],
        "pass_band": [42.9, 70.7],
        "median_days": 13,
        "blown_pct": 33.9,            # 30.0 max-loss + 3.9 daily
        "never_finished_pct": 6.3,
        "trades_per_day": 0.93,
        "trades": 591,
        "win_pct": 20.3,
        "avg_r": 0.319,
        "pf": 2.951,
        "curve_dd_pct": -39.16,
    },

    # --- the same rule at other sizes, so the trade-off is visible --------- #
    "alternatives": [
        {"what": "safest", "risk_pct": 1.00, "pass_pct": 69.1, "days": 32.6,
         "blown_pct": 23.2},
        {"what": "chosen", "risk_pct": 2.00, "pass_pct": 59.8, "days": 21.7,
         "blown_pct": 33.9},
        {"what": "fastest at 60%", "risk_pct": 4.00, "pass_pct": 45.9,
         "days": 17.4, "blown_pct": 51.0},
    ],

    # --- THE SAME STRATEGY ON ELEVEN YEARS INSTEAD OF THREE ---------------- #
    # Measured 2026-09-09 (`research/longhistory.py`, 40 quarters against 8).
    # This is the more reliable estimate and it is WORSE than the three-year one:
    # the band halves, and the headline moves outside the old band's middle.
    # `measured` above is left exactly as it was, because it is what the frozen
    # record was built on and rewriting history in place is how numbers stop
    # meaning anything.
    "long_history": {
        "years": 11, "quarters": 40, "trades": 3213,
        "pass_pct": 60.0, "days_to_pass": 20.0, "days_band": [18.2, 23.2],
        "blown_pct": 40.0, "pf": 1.41, "win_pct": 17.8,
        "trades_per_day": 0.88,
        "note": ("Three years said 14.5 expected days with a band of 12.4-19.7. "
                 "Eleven years says 20.0 with a band of 18.2-23.2 - just outside "
                 "the old band. The edge survives (60% of accounts still pass) "
                 "and the profit factor falls from 2.25 to 1.41. Read the "
                 "eleven-year number as the honest one."),
    },

    # --- POSITION SIZING, adopted 2026-09-10 ------------------------------ #
    # Kris: "take the sizing rule". This is an ACCOUNT-level overlay, not a
    # change to the signal - the kernel, the settings and every board number
    # above are untouched, and no second-engine check applies because no trade
    # decision moves. What changes is how large each trade is.
    #
    # THE RULE: size in proportion to the drawdown budget still available.
    #
    #     mult = clip((max_loss + drawdown) / max_loss, 0.25, 1.0)
    #     risk this trade = risk_pct x mult
    #
    # where `drawdown` is the account's current distance below its high-water
    # mark (negative), and `max_loss` is the firm's cap. At the high-water mark
    # mult is 1.0 and nothing changes; half way to the cap it is 0.5; it never
    # goes below a quarter, so the account can always recover.
    #
    # MEASURED on the same walk-forward, same PASS/FAIL simulation, real
    # breaches, at 2% base risk (`research/tier1.py`):
    #
    #     flat (before)          65.8% pass   29.5% blown   15.2 expected days
    #     budget-linear (this)   77.0% pass   16.9% blown   16.9 expected days
    #
    # Blown accounts fall 43%. It costs 1.7 expected days.
    #
    # WHY THIS IS NOT THE THING CLAUDE.md FORBIDS. The banned pattern is a risk
    # manager that shrinks size until the account can never breach, which
    # manufactures a 0% fail rate on a book that never resolves. The guard is
    # `still_open`, and it moves only 4.7% -> 6.2%. Accounts still fail here;
    # 16.9% of them do.
    "sizing": {
        "rule": "budget-linear",
        "floor_mult": 0.25,
        "measured": {"pass_pct": 77.0, "blown_pct": 16.9, "days": 16.9,
                     "still_open_pct": 6.2},
        "before": {"pass_pct": 65.8, "blown_pct": 29.5, "days": 15.2,
                   "still_open_pct": 4.7},
    },

    # --- THE SECOND SIGNAL, adopted 2026-09-10 ---------------------------- #
    # The Asian-range break: the 00:00-07:00 UTC high and low as a LEVEL, traded
    # during the European and US day. Same kernel, same grid, same stop shape -
    # only the band it measures from changes, from the session VWAP to the
    # overnight range.
    #
    # WHY IT IS IN. It is the only arm out of roughly fifty measured on
    # 2026-09-10 that held on BOTH timeframes with no sign flip, and the eleven
    # year run is what decided it:
    #
    #                      3 years            11 years
    #     PF@2x            1.747 / 2.215      1.273
    #     its paired null  0.504 / 0.459      -
    #     pass rate        75.1% / 76.6%      71.4%   (baseline 60.0%)
    #     expected days    18.6 / 19.6        22.4    (baseline 20.0)
    #     best quarter     -                  30.4%   (baseline 48.3%)
    #     best day         -                  23%     (baseline 36%)
    #
    # It is SLOWER than the baseline and outside its band on the slow side, so it
    # is not a speed lever. What it buys is robustness: the lowest quarter
    # concentration and the smallest single day of anything measured here, and a
    # daily-return correlation with the VWAP break of **0.114** - two genuinely
    # different trades on the same instrument.
    #
    # SECOND ENGINE: 10 of 10 configurations, every entry bar, every exit bar,
    # max |dR| 2.2e-16 (`strategies/vwapbreak/nautilus_check2.py`).
    #
    # THE BOOK. Run beside the VWAP break at half risk each, gold only:
    #     vwap 1h alone            11.8 days [9-14]   59.5% pass   37.8% blown
    #     vwap 1h + asia 1h        13.5 [10-17]       66.9%        28.9%
    #     vwap 1h + asia 1h + 4h   14.9 [11-19]       73.6%        22.6%
    "second_signal": {
        "name": "Asian range break",
        "market": "XAUUSD", "tfs": ["1h", "4h"],
        "window_utc": [0, 7],
        "settings": {"thr": 1.0, "stop_sig": 3.0, "max_hold": 384},
        "corr_with_baseline": 0.114,
        "measured_3y": {"pf_2x_1h": 1.747, "pf_2x_4h": 2.215,
                        "pass_pct_1h": 75.1, "pass_pct_4h": 76.6,
                        "days_1h": 18.6, "days_4h": 19.6},
        "measured_11y": {"pf_2x": 1.273, "pass_pct": 71.4, "days": 22.4,
                         "days_band": [21, 27], "best_q_share": 0.304,
                         "best_day_share": 0.23},
        "second_engine": "10/10 configurations, every bar",
    },

    "caveats": [
        "The 21.7-day band (16.8-31.4) overlaps the measured luck zone "
        "(13.3-26.5 expected days). The edge beats its null; the SPEED has not "
        "been shown to differ from noise.",
        "The eleven-year study says 20.0 expected days, not 21.7 measured on "
        "three - and its band (18.2-23.2) is half as wide. Read `long_history` "
        "as the honest number and `measured` as the record the settings were "
        "chosen on.",
        "A two-market book (this plus ETHUSDT 1h at half risk each) measured "
        "72.7% pass in 12.4 days against this leg's 61.9% in 17.8 - better on "
        "every axis, correlation -0.014. Not adopted; it changes the frozen "
        "strategy and is Kris's call.",
        "Position sizing is budget-linear as of 2026-09-10 (see `sizing`): "
        "blown accounts 29.5% -> 16.9% and pass 65.8% -> 77.0%, for 1.7 days. "
        "It is an account overlay, so the signal numbers above are unchanged.",
        "The Asian-range break is ADOPTED as a second signal (see "
        "`second_signal`): second-engine clean 10/10, and over eleven years it "
        "has the best pass rate (71.4% vs 60.0%), the lowest quarter "
        "concentration (30.4% vs 48.3%) and the smallest best day (23% vs 36%) "
        "of anything measured. It is SLOWER than the baseline, not faster.",
        "A partial exit at +2R was measured and REJECTED. Over three years it "
        "doubled the win rate (20.3% -> 41.9%) at the same pace; over ELEVEN "
        "years it is slower (22.5 vs 20.0 days), its profit factor falls to "
        "1.168, and its quarter concentration is WORSE than the baseline's "
        "(64.5% vs 48.3%). The three-year picture did not survive.",
        "The blind selector does not choose this stop width by itself - it was "
        "forced and then measured. Ranking on days instead of profit factor "
        "(`Pipeline.SELECT_ON = 'days'`) is measured and better on 4h; on 1h the "
        "difference is inside the band. Still open.",
    ],
}
