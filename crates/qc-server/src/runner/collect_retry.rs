//! Slow-path retry: QC marked the backtest `completed=true` but the
//! statistics field is still empty. Poll `/backtests/read` with adaptive
//! back-off until stats appear (or budget runs out).

use anyhow::Result;

use super::collect_parse::parse_and_store;
use crate::client::QcClient;
use crate::db::{Db, QueueJob};
use crate::rate_limit::stat_i64;

/// 2026-05-08 evidence (1651 collects): 93% take this slow-retry path; of
/// those 77% finish at retry-1, 23% at retry-2, 0.4% past retry-2. Old
/// [1,2,3,5,8,10,15,20,25,30,30,30] over-spent on the 0.4% tail. Tunings
/// applied: retry-2 2s→1s (saves ~1s on ~480 BTs/day); first-delay jitter
/// 0-500ms (spreads retry-1 fan-out after convoy bursts); downstream
/// [3,5,8,10]→[2,3,5,8] faster ramp for the rare retry-3+ path. Total
/// back-off ~170s (was 179s). Delays in ms = 70% of original budget.
const RETRY_DELAYS_MS: [u64; 12] = [
    700, 700, 1400, 2100, 3500, 5600, 10500, 14000, 17500, 21000, 21000, 21000,
];

pub(super) async fn slow_path_retry(
    client: &QcClient,
    job: &QueueJob,
    db: &Db,
    project_id: i64,
    backtest_id: &str,
    runtime_secs: f64,
) -> Result<Option<f64>> {
    retry_with_schedule(
        client,
        job,
        db,
        project_id,
        backtest_id,
        runtime_secs,
        &RETRY_DELAYS_MS,
    )
    .await
}

async fn retry_with_schedule(
    client: &QcClient,
    job: &QueueJob,
    db: &Db,
    project_id: i64,
    backtest_id: &str,
    runtime_secs: f64,
    delays: &[u64],
) -> Result<Option<f64>> {
    for (attempt, delay) in delays.iter().enumerate() {
        let attempt = attempt + 1;
        let jitter_ms = if attempt == 1 {
            fastrand::u64(0..350)
        } else {
            0
        };
        tokio::time::sleep(std::time::Duration::from_millis(delay + jitter_ms)).await;
        match client.read_backtest(project_id, backtest_id).await {
            Ok(r) => {
                super::collect::validate_response(&r)?;
                // PRESENCE of Total Orders (even ==0) = QC done populating
                // — see collect.rs note. Previous `> 0` killed zero-trade
                // backtests with a false `stats_not_returned`.
                let ok = r.backtest.as_ref().is_some_and(|bt| {
                    !bt.statistics.is_empty() && stat_i64(&bt.statistics, "Total Orders").is_some()
                });
                if ok {
                    tracing::debug!("collect: {} stats populated on retry {attempt}", job.name);
                    return parse_and_store(job, db, project_id, backtest_id, runtime_secs, &r)
                        .await;
                }
                tracing::debug!(
                    "collect: {} retry {attempt}/{} still empty",
                    job.name,
                    delays.len()
                );
            }
            Err(e) => {
                tracing::warn!(
                    "collect: {} retry {attempt}/{} read error: {e}",
                    job.name,
                    delays.len()
                );
            }
        }
    }

    let err_msg = format!(
        "stats_not_returned: QC returned completed=true but statistics \
         never populated after {} retries",
        delays.len()
    );
    tracing::error!("collect: {} {err_msg}", job.name);
    anyhow::bail!(err_msg)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn late_end_of_algorithm_error_cannot_store_zero_order_success() {
        let temp = tempfile::tempdir().unwrap();
        let path = crate::db::initialize_strategy(temp.path(), "stest").unwrap();
        let db = Db::open(&path, "stest").unwrap();
        db.call(|conn| {
            conn.execute(
                "INSERT INTO backtest_queue(name,code) VALUES ('late_error','pass')",
                [],
            )?;
            Ok(())
        })
        .await
        .unwrap();
        let (job, _) = db
            .claim_next_job_with_pool("test", 1, None, &[1])
            .await
            .unwrap()
            .unwrap();
        let (client, server) = crate::client::test_support::mock_api(vec![("/backtests/read",
            r#"{"success":true,"backtest":{"completed":true,"status":"Runtime Error","error":"Cannot save model","statistics":{"Total Orders":"0"}}}"#)]).await;
        let error = retry_with_schedule(&client, &job, &db, 1, "bt", 0.0, &[0])
            .await
            .unwrap_err();
        assert!(error.to_string().contains("Cannot save model"));
        db.call(|conn| {
            assert_eq!(
                conn.query_row("SELECT count(*) FROM experiments", [], |r| r
                    .get::<_, i64>(0))?,
                0
            );
            assert_eq!(
                conn.query_row("SELECT status FROM backtest_queue", [], |r| r
                    .get::<_, String>(0))?,
                "running"
            );
            Ok(())
        })
        .await
        .unwrap();
        server.await.unwrap();
    }

    #[tokio::test]
    async fn exhausted_statistics_budget_is_an_error_not_a_success_without_metric() {
        let temp = tempfile::tempdir().unwrap();
        let path = crate::db::initialize_strategy(temp.path(), "stest").unwrap();
        let db = Db::open(&path, "stest").unwrap();
        db.call(|conn| {
            conn.execute(
                "INSERT INTO backtest_queue(name,code) VALUES ('empty','pass')",
                [],
            )?;
            Ok(())
        })
        .await
        .unwrap();
        let (job, _) = db
            .claim_next_job_with_pool("test", 1, None, &[1])
            .await
            .unwrap()
            .unwrap();
        let result = retry_with_schedule(
            &QcClient::new("unused", "unused"),
            &job,
            &db,
            1,
            "bt",
            0.0,
            &[],
        )
        .await;
        assert!(
            result
                .unwrap_err()
                .to_string()
                .contains("stats_not_returned")
        );
    }
}
