CREATE MACRO IF NOT EXISTS datetime(value, modifier := NULL) AS strftime(CAST(current_timestamp AS TIMESTAMP) + COALESCE(TRY_CAST(modifier AS INTERVAL), INTERVAL '0 second'), '%Y-%m-%d %H:%M:%S');
CREATE TABLE IF NOT EXISTS _qc_storage_meta(key VARCHAR PRIMARY KEY,value VARCHAR);
CREATE SEQUENCE IF NOT EXISTS backtest_queue_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS experiments_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS code_blobs_id_seq START 1;
-- Generic execution schema. Strategy-specific tables belong to their strategy.
CREATE TABLE IF NOT EXISTS backtest_queue (
        id             BIGINT PRIMARY KEY DEFAULT nextval('backtest_queue_id_seq'),
        name           TEXT NOT NULL UNIQUE,
        code           TEXT NOT NULL,
        description    TEXT,
        hypothesis     TEXT,
        based_on       TEXT,
        batch          TEXT,
        priority       INTEGER NOT NULL DEFAULT 5,
        status         TEXT NOT NULL DEFAULT 'queued',
        submitted_by   TEXT,
        submitted_at   VARCHAR DEFAULT (datetime('now')),
        started_at     VARCHAR,
        completed_at   VARCHAR,
        backtest_id    TEXT,
        compile_id     TEXT,
        retry_count    INTEGER DEFAULT 0,
        error_message  TEXT,
        result_json    TEXT
    , runtime_seconds DOUBLE, node_id TEXT, code_hash TEXT, project_id INTEGER, extra_files TEXT, requested_project_id INTEGER);

CREATE TABLE IF NOT EXISTS experiments (
        id                  BIGINT PRIMARY KEY DEFAULT nextval('experiments_id_seq'),

        -- Identity
        name                TEXT NOT NULL UNIQUE,
        backtest_id         TEXT,
        batch               TEXT,

        -- Execution status
        -- Values: success | running | push_failed | compile_error |
        --         runtime_error | zero_orders | no_stats | imported
        status              TEXT NOT NULL DEFAULT 'imported',
        error_message       TEXT,   -- error detail when status != success

        -- What changed and why
        description         TEXT,   -- WHAT: human-readable change vs baseline
        hypothesis          TEXT,   -- WHY: the idea/reason for this experiment
        based_on            TEXT,   -- PARENT: experiment name this was derived from (e.g. 'Exp312_gm_cap_baseline')

        -- Backtest date range (ISO date strings)
        start_date          TEXT,   -- e.g. '2009-08-01'
        end_date            TEXT,   -- e.g. '2026-05-01'

        -- Core performance metrics
        cagr                DOUBLE,
        dd                  DOUBLE,
        car_mdd             DOUBLE,
        sharpe              DOUBLE,
        sortino             DOUBLE,
        total_orders        INTEGER,
        win_rate            DOUBLE,   -- 0-100

        -- Risk / attribution stats
        alpha               DOUBLE,
        beta                DOUBLE,
        expectancy          DOUBLE,
        profit_loss_ratio   DOUBLE,
        annual_std_dev      DOUBLE,
        annual_variance     DOUBLE,
        information_ratio   DOUBLE,
        tracking_error      DOUBLE,
        treynor_ratio       DOUBLE,
        probabilistic_sharpe DOUBLE,  -- 0-100

        -- Financial stats
        net_profit_pct      DOUBLE,
        loss_rate           DOUBLE,   -- 0-100
        total_fees          DOUBLE,
        start_equity        DOUBLE,
        end_equity          DOUBLE,
        portfolio_turnover  DOUBLE,   -- 0-100
        drawdown_recovery   INTEGER, -- days
        estimated_capacity  DOUBLE,
        lowest_capacity_asset TEXT,
        avg_win             DOUBLE,   -- %
        avg_loss            DOUBLE,   -- %

        -- QC backtest run timestamps
        backtest_run_start  TEXT,   -- when QC started running the backtest
        backtest_run_end    TEXT,   -- when QC finished running the backtest

        -- Full raw QC statistics JSON
        created_at          VARCHAR DEFAULT (datetime('now')),
        notes               TEXT
    , code_hash TEXT, runtime_seconds DOUBLE, project_id INTEGER);

CREATE TABLE IF NOT EXISTS settings (
        category    TEXT NOT NULL,
        key         TEXT NOT NULL,
        value       TEXT,
        description TEXT,
        updated_at  VARCHAR DEFAULT (datetime('now')),
        PRIMARY KEY (category, key)
    );

CREATE TABLE IF NOT EXISTS code_blobs (
        id       BIGINT PRIMARY KEY DEFAULT nextval('code_blobs_id_seq'),
        hash     TEXT NOT NULL UNIQUE,
        code     TEXT NOT NULL,
        size     INTEGER
    );

CREATE INDEX IF NOT EXISTS idx_queue_status_priority ON backtest_queue(status, priority, id);
