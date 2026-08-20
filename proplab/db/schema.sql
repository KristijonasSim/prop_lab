-- proplab tracking database
-- Every hypothesis, variation and run is recorded permanently, pass or fail.
-- The failed rows are the point: they are the denominator for judging whether
-- a good-looking result is real or just the best of N tries.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS hypotheses (
    id           INTEGER PRIMARY KEY,
    slug         TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT,              -- the idea as given
    mechanism    TEXT,              -- why it should work
    research     TEXT,              -- how it is normally traded, sources
    asset_class  TEXT,
    symbol       TEXT,
    status       TEXT NOT NULL DEFAULT 'queued',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS variations (
    id            INTEGER PRIMARY KEY,
    hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    slug          TEXT UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    rationale     TEXT,             -- why THIS variation is worth a test
    details       TEXT,             -- concrete rule differences
    strategy_name TEXT,             -- registry slug once coded
    code_path     TEXT,
    code_hash     TEXT,
    params_json   TEXT,
    status        TEXT NOT NULL DEFAULT 'queued',
    verdict_note  TEXT,             -- why it was rejected / kept
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY,
    run_uuid       TEXT UNIQUE NOT NULL,
    variation_id   INTEGER REFERENCES variations(id) ON DELETE CASCADE,
    strategy_name  TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    timeframe      TEXT NOT NULL,
    higher_tfs     TEXT,
    period_start   TEXT,
    period_end     TEXT,
    split          TEXT NOT NULL DEFAULT 'full',   -- full | is | oos
    n_bars         INTEGER,
    data_hash      TEXT,
    code_hash      TEXT,
    core_hash      TEXT,
    config_json    TEXT,
    params_json    TEXT,
    metrics_json   TEXT,
    prop_json      TEXT,
    checks_json    TEXT,
    checks_passed  INTEGER,
    prop_passed    INTEGER,
    -- flattened headline numbers so the dashboard can sort without JSON parsing
    net_profit     REAL,
    total_return_pct REAL,
    cagr_pct       REAL,
    sharpe         REAL,
    sortino        REAL,
    max_dd_pct     REAL,
    n_trades       INTEGER,
    win_rate_pct   REAL,
    profit_factor  REAL,
    expectancy_r   REAL,
    t_stat         REAL,
    trades_per_week REAL,
    exposure_pct   REAL,
    first_breach_rule TEXT,
    notes          TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq         INTEGER,
    entry_time  TEXT, exit_time TEXT, side TEXT,
    qty REAL, entry_price REAL, exit_price REAL,
    gross_pnl REAL, fees REAL, funding REAL, net_pnl REAL,
    r_multiple REAL, bars_held INTEGER, exit_reason TEXT, tag TEXT,
    mae REAL, mfe REAL, equity_after REAL
);

CREATE TABLE IF NOT EXISTS equity_curve (
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    ts     TEXT NOT NULL,
    equity REAL NOT NULL,
    equity_low REAL,
    PRIMARY KEY (run_id, ts)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    entity      TEXT NOT NULL,     -- hypothesis | variation | run
    entity_id   INTEGER NOT NULL,
    event       TEXT NOT NULL,
    detail      TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_variation ON runs(variation_id);
CREATE INDEX IF NOT EXISTS idx_runs_created   ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_var_hyp        ON variations(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_trades_run     ON trades(run_id);
