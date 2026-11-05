//! Preserve experiment identity and research annotations when refreshing results.
use super::{Db, Experiment};
use anyhow::Result;

impl Db {
    /// Insert or update execution metrics, preserving unmentioned research columns.
    ///
    /// # Errors
    /// Returns an error if the experiment cannot be stored.
    pub async fn insert_experiment(&self, exp: Experiment) -> Result<()> {
        self.call(move |conn| insert_on(conn, &exp)).await
    }
}

pub(super) fn insert_on(conn: &duckdb::Connection, exp: &Experiment) -> Result<()> {
    conn.execute(
        include_str!("../../sql/insert_experiment.sql"),
        duckdb::params![
            exp.name,
            exp.backtest_id,
            exp.batch,
            exp.status,
            exp.description,
            exp.hypothesis,
            exp.based_on,
            exp.start_date,
            exp.end_date,
            exp.cagr,
            exp.dd,
            exp.car_mdd,
            exp.sharpe,
            exp.sortino,
            exp.total_orders,
            exp.win_rate,
            exp.alpha,
            exp.beta,
            exp.expectancy,
            exp.profit_loss_ratio,
            exp.annual_std_dev,
            exp.annual_variance,
            exp.information_ratio,
            exp.tracking_error,
            exp.treynor_ratio,
            exp.probabilistic_sharpe,
            exp.net_profit_pct,
            exp.loss_rate,
            exp.total_fees,
            exp.start_equity,
            exp.end_equity,
            exp.portfolio_turnover,
            exp.drawdown_recovery,
            exp.estimated_capacity,
            exp.lowest_capacity_asset,
            exp.avg_win,
            exp.avg_loss,
            exp.backtest_run_start,
            exp.backtest_run_end,
            exp.code_hash,
            exp.runtime_seconds,
            exp.project_id,
        ],
    )?;
    Ok(())
}
