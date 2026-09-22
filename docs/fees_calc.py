"""Round-trip cost in bps at a fixed clip. All inputs are sourced; see docs/FEES.md."""
GOLD, EUR, ES = 4353.0, 1.08, 6900.0

def bps(dollars, notional): return dollars / notional * 1e4

rows = []
def add(cls, venue, instr, notional, spread_usd, comm_rt_usd, note=""):
    rows.append((cls, venue, instr, notional,
                 bps(spread_usd, notional), bps(comm_rt_usd, notional),
                 bps(spread_usd + comm_rt_usd, notional), note))

CLIP = 50_000

# --- GOLD -------------------------------------------------------------------
# futures: contract notional is what it is; you cannot trade half a contract
mgc = 10 * GOLD                      # micro gold, 10 oz
gc  = 100 * GOLD                     # full gold, 100 oz
add("commodity", "Topstep / Apex (futures prop)", "MGC", mgc, 1.00, 1.92, "1 tick = $1.00; comm from Topstep fee table")
add("commodity", "Interactive Brokers", "MGC", mgc, 1.00, 1.90, "$0.25 comm + ~$0.70 exch/clear per side")
add("commodity", "Topstep / Apex (futures prop)", "GC", gc, 10.00, 4.32, "needs $435k notional")
add("commodity", "Interactive Brokers", "GC", gc, 10.00, 4.30, "needs $435k notional")
# CFD: spread in dollars per ounce x ounces in the clip
oz = CLIP / GOLD
add("commodity", "Dukascopy CFD (our data)", "XAUUSD", CLIP, 0.714*oz, 0.0, "1.64 bps MEASURED mean, all hours, commission NOT included")
add("commodity", "CFD prop firm, raw, liquid hours", "XAUUSD", CLIP, 0.20*oz, 0.14/1e4*CLIP, "advertised 10-30c; 20c used")
add("commodity", "CFD prop firm, standard acct", "XAUUSD", CLIP, 0.40*oz, 0.0, "advertised 20-50c; 40c used")

# --- FX ---------------------------------------------------------------------
pip = 0.0001 / EUR * 1e4             # one pip of EURUSD in bps = 0.926
def fx(venue, all_in_pips, note=""):
    rows.append(("fx", venue, "EURUSD", CLIP, float('nan'), float('nan'),
                 all_in_pips * pip, note))
fx("Interactive Brokers (>= $100k clip)", 0.10 + 0.40/pip*0, "0.2bp/side comm + ~0.1 pip spread")
rows[-1] = ("fx", "Interactive Brokers (clip >= $100k)", "EURUSD", 100_000,
            0.10*pip, 0.40, 0.10*pip + 0.40, "0.20 bps/side commission, $2 min/order")
rows.append(("fx", "Interactive Brokers (clip $50k)", "EURUSD", CLIP,
             0.10*pip, bps(4.0, CLIP), 0.10*pip + bps(4.0, CLIP), "$2/side MINIMUM bites below $100k"))
fx("Dukascopy (our data, spread only)", 0.29, "0.27 bps MEASURED; commission NOT included")
fx("IC Markets Raw / cTrader", 0.62, "all-in, published")
fx("Pepperstone Razor", 0.80, "all-in, published")

# --- CRYPTO -----------------------------------------------------------------
def cr(venue, taker_pct_side, spread_bps, note=""):
    c = 2 * taker_pct_side * 100      # % per side -> bps round trip
    rows.append(("crypto", venue, "BTC perp", CLIP, spread_bps, c, spread_bps + c, note))
cr("Binance futures", 0.05, 1.0, "standard tier")
cr("OKX futures", 0.05, 1.0, "standard tier")
cr("Bybit futures", 0.055, 1.0, "standard tier")
cr("Binance futures, VIP+BNB", 0.0375, 1.0, "requires volume/holdings")
cr("Binance SPOT", 0.075, 1.0, "with BNB discount")
cr("Binance SPOT, no discount", 0.10, 1.0, "")

# --- EQUITIES ---------------------------------------------------------------
def eq(venue, px, spread_usd, per_share, min_order, note=""):
    sh = CLIP / px
    comm = max(per_share * sh, min_order) * 2
    rows.append(("stocks", venue, f"${px:.0f} share", CLIP, bps(spread_usd*sh, CLIP),
                 bps(comm, CLIP), bps(spread_usd*sh + comm, CLIP), note))
eq("Interactive Brokers tiered", 700, 0.01, 0.0035, 0.35, "SPY-like: high price, 1c spread")
eq("Interactive Brokers tiered", 200, 0.01, 0.0035, 0.35, "mega-cap")
eq("Interactive Brokers tiered", 20, 0.01, 0.0035, 0.35, "cheap share = many shares = expensive")

# --- INDEX FUTURES ----------------------------------------------------------
mes, es = 5 * ES, 50 * ES
add("index", "Topstep / IBKR", "MES", mes, 1.25, 1.00, "1 tick = $1.25")
add("index", "Topstep / IBKR", "ES", es, 12.50, 4.30, "needs $345k notional")

print(f"{'class':10}{'venue':40}{'instr':14}{'notional':>11}{'spread':>9}{'comm':>8}{'TOTAL':>9}  note")
print("-"*140)
for r in sorted(rows, key=lambda r: r[6]):
    cls, v, i, n, s, c, t, note = r
    ss = f"{s:9.2f}" if s == s else "        -"
    cc = f"{c:8.2f}" if c == c else "       -"
    print(f"{cls:10}{v:40}{i:14}{n:>11,.0f}{ss}{cc}{t:>9.2f}  {note}")
