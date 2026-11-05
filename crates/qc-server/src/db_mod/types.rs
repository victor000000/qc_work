//! Data structs for queue jobs and experiments.

#[derive(Debug, Clone)]
pub struct QueueJob {
    pub id: i64,
    pub name: String,
    pub code: String,
    /// Optional JSON object `{filename: content}` of EXTRA project files to
    /// upload alongside `main.py` (e.g. SML01's `bar_builder.py` / `ml_ext.py`).
    /// `None`/NULL for single-file strategies (s001/s002) — they upload only
    /// `main.py`, so their behaviour is byte-identical to before this column.
    pub extra_files: Option<String>,
    pub description: Option<String>,
    pub hypothesis: Option<String>,
    pub based_on: Option<String>,
    pub batch: Option<String>,
    /// Immutable submission constraint, separate from the assigned execution project.
    pub requested_project_id: Option<i64>,
    pub priority: i64,
    pub strategy: String,
}

/// The ordered column list for selecting a [`QueueJob`] — the single source of
/// truth shared by every `SELECT ... FROM backtest_queue` that builds one (the
/// claim transaction and crash recovery), so the column order and the
/// [`queue_job_from_row`] indices can never drift apart.
pub const QUEUEJOB_SELECT_COLUMNS: &str = "id, name, code, description, hypothesis, based_on, batch, priority, extra_files, requested_project_id";

/// Build a [`QueueJob`] from a row selected with [`QUEUEJOB_SELECT_COLUMNS`].
///
/// # Errors
/// Returns `Err` if any column fails to convert.
pub fn queue_job_from_row(row: &duckdb::Row, strategy: &str) -> duckdb::Result<QueueJob> {
    Ok(QueueJob {
        id: row.get(0)?,
        name: row.get(1)?,
        code: row.get(2)?,
        description: row.get(3)?,
        hypothesis: row.get(4)?,
        based_on: row.get(5)?,
        batch: row.get(6)?,
        priority: row.get(7)?,
        extra_files: row.get(8)?,
        requested_project_id: row.get(9)?,
        strategy: strategy.to_string(),
    })
}

#[derive(Debug, Clone, Default)]
pub struct Experiment {
    pub name: String,
    pub backtest_id: String,
    pub batch: Option<String>,
    pub status: String,
    pub description: Option<String>,
    pub hypothesis: Option<String>,
    pub based_on: Option<String>,
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub cagr: Option<f64>,
    pub dd: Option<f64>,
    pub car_mdd: Option<f64>,
    pub sharpe: Option<f64>,
    pub sortino: Option<f64>,
    pub total_orders: Option<i64>,
    pub win_rate: Option<f64>,
    pub alpha: Option<f64>,
    pub beta: Option<f64>,
    pub expectancy: Option<f64>,
    pub profit_loss_ratio: Option<f64>,
    pub annual_std_dev: Option<f64>,
    pub annual_variance: Option<f64>,
    pub information_ratio: Option<f64>,
    pub tracking_error: Option<f64>,
    pub treynor_ratio: Option<f64>,
    pub probabilistic_sharpe: Option<f64>,
    pub net_profit_pct: Option<f64>,
    pub loss_rate: Option<f64>,
    pub total_fees: Option<f64>,
    pub start_equity: Option<f64>,
    pub end_equity: Option<f64>,
    pub portfolio_turnover: Option<f64>,
    pub drawdown_recovery: Option<i64>,
    pub estimated_capacity: Option<f64>,
    pub lowest_capacity_asset: Option<String>,
    pub avg_win: Option<f64>,
    pub avg_loss: Option<f64>,
    pub backtest_run_start: Option<String>,
    pub backtest_run_end: Option<String>,
    pub code_hash: Option<String>,
    pub runtime_seconds: Option<f64>,
    pub project_id: Option<i64>,
}
