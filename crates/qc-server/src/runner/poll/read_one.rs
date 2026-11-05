//! Issue one `read_backtest` poll and classify the response.
//!
//! Returns `Ok(Some(resp))` on success, `Ok(None)` on a rate limit or transient
//! read failure, and `Err(e)` on a permanent read error. Retrying a read keeps
//! the same execution under the original outer polling deadline.

use std::time::Instant;

use anyhow::Result;

use crate::client::{QcClient, is_transient_error};
use crate::models::backtest::BacktestResponse;
use crate::rate_limit::is_rate_limit;

pub(super) async fn poll_read_once(
    client: &QcClient,
    project_id: i64,
    backtest_id: &str,
    job_name: &str,
    poll_count: u32,
    progress: f64,
    backoff_factor: &mut u32,
) -> Result<Option<BacktestResponse>> {
    let read_start = Instant::now();
    match client.read_backtest(project_id, backtest_id).await {
        Ok(r) => {
            let read_ms = read_start.elapsed().as_millis();
            if read_ms > 3_000 {
                tracing::debug!(
                    target: "qc::pipeline",
                    "qc_poll_slow job={job_name} bt={backtest_id} poll={poll_count} read_ms={read_ms} progress={progress:.2}"
                );
            }
            if *backoff_factor > 1 {
                tracing::debug!(
                    target: "qc::pipeline",
                    "[{job_name}] backoff_reset poll={poll_count} (was {backoff_factor}x)"
                );
            }
            *backoff_factor = 1;
            Ok(Some(r))
        }
        Err(e) if is_rate_limit(&e) => {
            *backoff_factor = (*backoff_factor * 2).min(4);
            tracing::debug!(
                target: "qc::pipeline",
                "[{job_name}] rate_limit on poll {poll_count} — backoff_factor={backoff_factor}"
            );
            Ok(None)
        }
        Err(e) if is_transient_error(&e) => {
            // The per-request retry budget may expire during an outage while
            // the cloud algorithm keeps running. Keep this poll task/identity
            // alive; poll_backtest_unlocked still enforces its original budget.
            *backoff_factor = backoff_factor.saturating_mul(2).min(16);
            tracing::warn!(
                target: "qc::pipeline",
                "[{job_name}] poll_read_unavailable poll={poll_count} bt={backtest_id} backoff_factor={backoff_factor}; retrying same execution within original deadline: {e}"
            );
            Ok(None)
        }
        Err(e) => {
            tracing::debug!(
                target: "qc::pipeline",
                "[{job_name}] poll_error poll={poll_count} error={e}"
            );
            Err(e)
        }
    }
}
