//! Poll a running backtest until completion.

mod read_one;
mod tier;

use std::time::Instant;

use anyhow::{Result, bail};
use tokio::time::{Duration, sleep};

use self::read_one::poll_read_once;
use self::tier::tiered_poll_delay;

/// Poll a backtest to completion. Spawned from `pipeline::poll_and_collect`
/// after the project lock is released, so this fn takes `client` directly
/// (no `&self`). Uses tiered delays + per-task 429 elasticity.
pub(crate) async fn poll_backtest_unlocked(
    client: &crate::client::QcClient,
    project_id: i64,
    backtest_id: &str,
    job_name: &str,
    _bt_poll_hint: Duration, // ignored — tiers chosen internally
    bt_timeout: Duration,
) -> Result<(crate::models::backtest::BacktestResponse, f64, u32)> {
    tokio::time::timeout(
        bt_timeout,
        poll_inner(client, project_id, backtest_id, job_name, bt_timeout),
    )
    .await
    .map_err(|_| anyhow::anyhow!("backtest_timeout: {job_name}"))?
}

async fn poll_inner(
    client: &crate::client::QcClient,
    project_id: i64,
    backtest_id: &str,
    job_name: &str,
    bt_timeout: Duration,
) -> Result<(crate::models::backtest::BacktestResponse, f64, u32)> {
    tracing::debug!("[{job_name}] polling backtest {backtest_id} (tiered)");
    let bt_run_start = Instant::now();
    let deadline = Instant::now() + bt_timeout;
    let mut poll_count: u32 = 0;
    let mut progress: f64 = 0.0;
    let mut backoff_factor: u32 = 1;

    loop {
        let delay = tiered_poll_delay(poll_count + 1, progress, backoff_factor);
        if !delay.is_zero() {
            sleep(delay).await;
        }
        poll_count += 1;
        // trace! — fires per poll cycle (350-1500ms). The `progress_update`
        // line below already emits at debug on every progress jump; that's
        // sufficient for state-tracking without per-poll spam.
        tracing::trace!(
            target: "qc::pipeline",
            "[{job_name}] poll_attempt #{poll_count} delay_before={:.3}s progress={progress:.2} backoff={backoff_factor}x",
            delay.as_secs_f64()
        );

        let Some(r) = poll_read_once(
            client,
            project_id,
            backtest_id,
            job_name,
            poll_count,
            progress,
            &mut backoff_factor,
        )
        .await?
        else {
            continue; // Temporary read/rate-limit failure; retain the same ID/deadline.
        };

        if let Some(bt_result) = r.backtest.as_ref() {
            let new_progress = bt_result.progress;
            if (new_progress - progress).abs() > 0.01 {
                tracing::debug!(
                    target: "qc::pipeline",
                    "[{job_name}] progress_update poll={poll_count} progress={new_progress:.2} status={:?}",
                    bt_result.status.as_deref().unwrap_or("?")
                );
            }
            progress = new_progress;
            if bt_result.completed {
                if let Some(err) = &bt_result.error
                    && !err.is_empty()
                {
                    tracing::debug!(
                        target: "qc::pipeline",
                        "[{job_name}] runtime_error_detected poll={poll_count} error={err}"
                    );
                    bail!("runtime_error: {err}");
                }
                let bt_phase_secs = bt_run_start.elapsed().as_secs_f64();
                tracing::debug!(
                    target: "qc::pipeline",
                    "[{job_name}] tier_summary polls={poll_count} bt_run={bt_phase_secs:.1}s final_progress={progress:.2}"
                );
                return Ok((r, bt_phase_secs, poll_count));
            }
        }

        if Instant::now() > deadline {
            // Include `progress` so post-mortem can distinguish stuck-near-0
            // (likely Initialize hang) from stalled-at-N% (likely an inf
            // loop in user code after start). progress is 0.0-1.0 (QC's
            // own backtest_progress field).
            bail!(
                "backtest_timeout after {}s ({poll_count} polls, progress={progress:.2})",
                bt_timeout.as_secs()
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::client::test_support::mock_api_status;

    #[tokio::test]
    async fn exhausted_request_retries_resume_same_execution_until_completed() {
        // Seven 503s exhaust one complete HTTP request retry budget. The next
        // outer poll must observe the SAME backtest, not return a local failure
        // or call any create/delete endpoint. This uses real local HTTP I/O.
        let mut replies = vec![("/backtests/read", 503, "temporary gateway outage"); 7];
        replies.push((
            "/backtests/read",
            200,
            r#"{"success":true,"backtest":{"projectId":42,"backtestId":"existing","completed":false,"progress":0.6,"status":"In Progress..."}}"#,
        ));
        replies.push((
            "/backtests/read",
            200,
            r#"{"success":true,"backtest":{"projectId":42,"backtestId":"existing","completed":true,"progress":1,"status":"Completed."}}"#,
        ));
        let (client, server) = mock_api_status(replies).await;
        let (response, _, polls) = poll_backtest_unlocked(
            &client,
            42,
            "existing",
            "recover-read",
            Duration::from_secs(1),
            Duration::from_secs(60),
        )
        .await
        .unwrap();
        let backtest = response.backtest.unwrap();
        assert_eq!(backtest.project_id, 42);
        assert_eq!(backtest.backtest_id, "existing");
        assert!(backtest.completed);
        assert_eq!(polls, 3);
        server.await.unwrap();
    }

    #[tokio::test]
    async fn permanent_read_denial_is_not_retried_as_a_network_outage() {
        let (client, server) =
            mock_api_status(vec![("/backtests/read", 401, "unauthorized")]).await;
        let result = poll_backtest_unlocked(
            &client,
            42,
            "existing",
            "deny-read",
            Duration::from_secs(1),
            Duration::from_secs(5),
        )
        .await;
        assert!(result.unwrap_err().to_string().contains("401"));
        server.await.unwrap();
    }

    #[tokio::test]
    async fn actual_runtime_error_is_not_retried_even_if_it_mentions_503() {
        let (client, server) = mock_api_status(vec![(
            "/backtests/read", 200,
            r#"{"success":true,"backtest":{"projectId":42,"backtestId":"existing","completed":true,"progress":0.6,"status":"Runtime Error","error":"strategy rejected value503"}}"#,
        )]).await;
        let result = poll_backtest_unlocked(
            &client,
            42,
            "existing",
            "runtime-error",
            Duration::from_secs(1),
            Duration::from_secs(5),
        )
        .await;
        assert!(
            result
                .unwrap_err()
                .to_string()
                .starts_with("runtime_error:")
        );
        server.await.unwrap();
    }

    #[tokio::test]
    async fn original_budget_bounds_transport_retry_time() {
        let (client, server) =
            mock_api_status(vec![
                ("/backtests/read", 503, "temporary gateway outage",);
                7
            ])
            .await;
        let result = poll_backtest_unlocked(
            &client,
            42,
            "existing",
            "bounded-read",
            Duration::from_secs(1),
            Duration::from_secs(1),
        )
        .await;
        assert!(result.unwrap_err().to_string().contains("backtest_timeout"));
        // Outer cancellation must not consume another request budget or send
        // any cancellation request to a cloud execution.
        assert!(!server.is_finished());
        server.abort();
    }

    #[tokio::test]
    async fn backtest_budget_includes_delay_before_first_api_poll() {
        let mut client = crate::client::QcClient::new("unused", "unused");
        client.base_url = "http://127.0.0.1:1".into();
        let result = poll_backtest_unlocked(
            &client,
            1,
            "bt",
            "test",
            Duration::from_secs(1),
            Duration::from_millis(10),
        )
        .await;
        assert!(result.unwrap_err().to_string().contains("backtest_timeout"));
    }
}
