//! Result collection: read backtest stats from QC and store in experiments.

use anyhow::Result;

use super::collect_parse::parse_and_store;
use super::collect_retry::slow_path_retry;
use crate::client::QcClient;
use crate::db::{Db, QueueJob};
use crate::models::backtest::BacktestResponse;
use crate::rate_limit::stat_i64;

/// Collect results directly from a poll response (no extra API call).
/// If the poll response has empty stats (QC populates async), falls back
/// to retry-read.
///
/// # Errors
/// Returns `Err` on HTTP transport failure during retry-read or SQL error
/// when marking the job failed or inserting experiment rows.
pub async fn collect_from_response(
    client: &QcClient,
    job: &QueueJob,
    db: &Db,
    project_id: i64,
    backtest_id: &str,
    runtime_secs: f64,
    response: BacktestResponse,
) -> Result<Option<f64>> {
    validate_response(&response)?;
    // `Total Orders` is the last field QC populates after a backtest
    // completes — its PRESENCE (Some(_), even Some(0)) means stats are
    // ready. The old check required >0, which conflated "QC hasn't
    // populated yet" with "ran but legitimately traded 0 times", causing
    // zero-trade backtests to loop slow_path_retry → false `stats_not_returned`.
    let has_stats = response.backtest.as_ref().is_some_and(|bt| {
        !bt.statistics.is_empty() && stat_i64(&bt.statistics, "Total Orders").is_some()
    });

    if has_stats {
        tracing::debug!(
            target: "qc::pipeline",
            "qc_collect_path job={} stats_count={} path=fast",
            job.name,
            response.backtest.as_ref().map_or(0, |bt| bt.statistics.len())
        );
        return parse_and_store(job, db, project_id, backtest_id, runtime_secs, &response).await;
    }

    let stats_count = response
        .backtest
        .as_ref()
        .map_or(0, |bt| bt.statistics.len());
    tracing::debug!(
        target: "qc::pipeline",
        "qc_collect_path job={} stats_count={stats_count} path=slow_retry",
        job.name
    );
    slow_path_retry(client, job, db, project_id, backtest_id, runtime_secs).await
}

/// End-of-algorithm failures can arrive after QC first reports completion.
pub(super) fn validate_response(response: &BacktestResponse) -> Result<()> {
    anyhow::ensure!(
        response.success,
        "result read rejected: {:?}",
        response.errors
    );
    let bt = response
        .backtest
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("result read has no backtest"))?;
    if let Some(error) = bt.error.as_deref().filter(|error| !error.is_empty()) {
        anyhow::bail!("runtime_error: {error}");
    }
    let status = bt.status.as_deref().unwrap_or_default();
    anyhow::ensure!(
        bt.has_initialize_error != Some(true) && !status.to_ascii_lowercase().contains("error"),
        "runtime_error: {status}"
    );
    Ok(())
}
