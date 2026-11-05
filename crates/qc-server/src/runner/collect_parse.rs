//! Parse backtest stats from QC response and store in experiments table.

use std::time::Instant;

use anyhow::Result;

use crate::db::{Db, QueueJob};
use crate::models::backtest::BacktestResponse;
use crate::rate_limit::{stat_f64, stat_i64};

mod build_exp;

/// Parse stats from a `BacktestResponse` and store in experiments table.
pub(crate) async fn parse_and_store(
    job: &QueueJob,
    db: &Db,
    project_id: i64,
    backtest_id: &str,
    runtime_secs: f64,
    r: &BacktestResponse,
) -> Result<Option<f64>> {
    let bt = r
        .backtest
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("no backtest in response"))?;

    // Persist the raw QC result (status + statistics + runtimeStatistics) into
    // backtest_queue.result_json so a strategy whose objective is a CUSTOM runtime
    // metric (e.g. SML01's da_oos / sharpe_oos / val_auc / train_auc) can read it
    // straight from the DB — no second live QC fetch. s001/s002 ignore this column.
    let result_json = serde_json::json!({
        "status": bt.status.clone().unwrap_or_default(),
        "statistics": &bt.statistics,
        "runtimeStatistics": &bt.runtime_statistics,
    })
    .to_string();

    let stats = &bt.statistics;
    let total_orders = stat_i64(stats, "Total Orders");
    tracing::debug!(
        "collect: {} orders={:?} stats_count={}",
        job.name,
        total_orders,
        stats.len()
    );

    let result_status = if total_orders == Some(0) || total_orders.is_none() {
        "zero_orders"
    } else if stats.is_empty() {
        "no_stats"
    } else {
        "success"
    };

    let cagr = stat_f64(stats, "Compounding Annual Return");
    let dd = stat_f64(stats, "Drawdown");
    let car_mdd = match (cagr, dd) {
        (Some(c), Some(d)) if d.abs() > 0.001 => Some(c / d),
        _ => None,
    };

    let exp = build_exp::build_experiment(
        job,
        bt,
        backtest_id,
        project_id,
        runtime_secs,
        result_status,
        cagr,
        dd,
        car_mdd,
        total_orders,
        job.content_hash()?,
    );

    // 2026-05-07: threshold dropped to 100ms — restart33 at 500ms logged
    // 0 events; the 3s collect-tail lives in the gap AFTER mark_done.
    let t_collect_start = Instant::now();
    db.store_completed(job.id, exp, backtest_id, runtime_secs, &result_json)
        .await?;

    let collect_ms = t_collect_start.elapsed().as_millis();
    if collect_ms > 100 {
        tracing::debug!(
            target: "qc::pipeline",
            "qc_collect_db job={} transaction_ms={collect_ms}",
            job.name
        );
    }

    tracing::debug!(
        job = %job.name, status = result_status, car_mdd = ?car_mdd,
        cagr = ?cagr, dd = ?dd, orders = ?total_orders, project = project_id,
        backtest = backtest_id, runtime_s = format!("{runtime_secs:.1}"),
        stats_count = stats.len(), "experiment stored"
    );

    Ok(car_mdd)
}
