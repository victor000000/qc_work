//! Build an `Experiment` row from a QC backtest response.
//!
//! Pulled out of `collect_parse.rs` so the orchestrator stays under 100 lines.

#![allow(
    clippy::too_many_arguments,
    reason = "all derived values live in the parent fn"
)]

use crate::db::{Experiment, QueueJob};
use crate::models::backtest::BacktestResult;
use crate::rate_limit::{stat_f64, stat_i64};

pub(super) fn build_experiment(
    job: &QueueJob,
    bt: &BacktestResult,
    backtest_id: &str,
    project_id: i64,
    runtime_secs: f64,
    result_status: &str,
    cagr: Option<f64>,
    dd: Option<f64>,
    car_mdd: Option<f64>,
    total_orders: Option<i64>,
    content_hash: String,
) -> Experiment {
    let stats = &bt.statistics;
    let code_hash = Some(content_hash);
    Experiment {
        name: job.name.clone(),
        backtest_id: backtest_id.to_string(),
        batch: job.batch.clone(),
        status: result_status.to_string(),
        description: job.description.clone(),
        hypothesis: job.hypothesis.clone(),
        based_on: job.based_on.clone(),
        start_date: bt.backtest_start.clone(),
        end_date: bt.backtest_end.clone(),
        cagr,
        dd,
        car_mdd,
        sharpe: stat_f64(stats, "Sharpe Ratio"),
        sortino: stat_f64(stats, "Sortino Ratio"),
        total_orders,
        win_rate: stat_f64(stats, "Win Rate"),
        alpha: stat_f64(stats, "Alpha"),
        beta: stat_f64(stats, "Beta"),
        expectancy: stat_f64(stats, "Expectancy"),
        profit_loss_ratio: stat_f64(stats, "Profit-Loss Ratio"),
        annual_std_dev: stat_f64(stats, "Annual Standard Deviation"),
        annual_variance: stat_f64(stats, "Annual Variance"),
        information_ratio: stat_f64(stats, "Information Ratio"),
        tracking_error: stat_f64(stats, "Tracking Error"),
        treynor_ratio: stat_f64(stats, "Treynor Ratio"),
        probabilistic_sharpe: stat_f64(stats, "Probabilistic Sharpe Ratio"),
        net_profit_pct: stat_f64(stats, "Net Profit"),
        loss_rate: stat_f64(stats, "Loss Rate"),
        total_fees: stat_f64(stats, "Total Fees"),
        start_equity: stat_f64(stats, "Start Equity"),
        end_equity: stat_f64(stats, "End Equity"),
        portfolio_turnover: stat_f64(stats, "Portfolio Turnover"),
        drawdown_recovery: stat_i64(stats, "Drawdown Recovery"),
        estimated_capacity: stat_f64(stats, "Estimated Strategy Capacity"),
        lowest_capacity_asset: stats.get("Lowest Capacity Asset").cloned(),
        avg_win: stat_f64(stats, "Average Win"),
        avg_loss: stat_f64(stats, "Average Loss"),
        backtest_run_start: bt.created.clone(),
        backtest_run_end: None,
        code_hash,
        runtime_seconds: Some(runtime_secs),
        project_id: Some(project_id),
    }
}
