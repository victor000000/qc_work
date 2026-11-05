//! Failure-path handlers for poll/collect outcomes.
//!
//! Preserve cloud execution and its identity when local polling or collection fails.

use std::sync::atomic::Ordering;

use super::ctx::PollCollectCtx;
use super::transient::is_qc_transient_poll_error;

pub(super) async fn handle_collect_err(ctx: &PollCollectCtx, err: &str) {
    tracing::error!(
        "slot-{}: collect failed for {}: {err}",
        ctx.slot_id,
        ctx.job_name
    );
    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: collect_failed slot-{} project={} bt={} error={err}",
        ctx.slot_id, ctx.project_id, ctx.backtest_id
    );
    // Poll already confirmed completion. Preserve the QC result for recovery
    // when a local database write or delayed statistics collection fails.
    let _ = ctx
        .db
        .mark_failed(ctx.job.id, &format!("collect: {err}"), None)
        .await;
    if let Some(ref s) = ctx.session {
        s.failed.fetch_add(1, Ordering::SeqCst);
    }
}

pub(super) async fn handle_poll_err(ctx: &PollCollectCtx, err: &str) {
    tracing::error!(
        "slot-{}: poll failed for {}: {err}",
        ctx.slot_id,
        ctx.job_name
    );
    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: poll_failed slot-{} project={} bt={} error={err}",
        ctx.slot_id, ctx.project_id, ctx.backtest_id
    );
    // A local timeout does not establish that the remote execution stopped.
    // Never delete it or clear its identity to launch a replacement. Even a
    // terminal loader failure is evidence to preserve before a manual retry.
    if is_qc_transient_poll_error(err) {
        tracing::warn!(
            "slot-{}: {} infrastructure failure preserved for explicit recovery; bt={}",
            ctx.slot_id,
            ctx.job_name,
            ctx.backtest_id
        );
    }

    let _ = ctx
        .db
        .mark_failed(ctx.job.id, &format!("poll: {err}"), None)
        .await;
    if let Some(ref s) = ctx.session {
        s.failed.fetch_add(1, Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::time::Duration;

    #[tokio::test]
    async fn poll_failure_never_deletes_or_requeues_existing_cloud_execution() {
        for err in [
            "request timed out",
            "runtime_error: Unable to import python module",
        ] {
            let temp = tempfile::tempdir().unwrap();
            let path = crate::db::initialize_strategy(temp.path(), "stest").unwrap();
            let db = crate::db::Db::open(&path, "stest").unwrap();
            db.call(|conn| {
                conn.execute("INSERT INTO backtest_queue(name,code,status,project_id,compile_id,backtest_id) VALUES ('job','pass','running',42,'cid','bid')", [])?;
                Ok(())
            }).await.unwrap();
            let job = db
                .call(|conn| {
                    Ok(conn.query_row(
                        &format!(
                            "SELECT {} FROM backtest_queue",
                            crate::db::QUEUEJOB_SELECT_COLUMNS
                        ),
                        [],
                        |row| crate::db::queue_job_from_row(row, "stest"),
                    )?)
                })
                .await
                .unwrap();
            let (client, mut server) = crate::client::test_support::mock_api(vec![(
                "/backtests/delete",
                r#"{"success":true}"#,
            )])
            .await;
            let ctx = PollCollectCtx {
                slot_id: 0,
                client: Arc::new(client),
                session: None,
                db: db.clone(),
                job,
                project_id: 42,
                backtest_id: "bid".into(),
                strategy: "stest".into(),
                job_name: "job".into(),
                prep_elapsed: Duration::ZERO,
                bt_poll: Duration::from_secs(1),
                bt_timeout: Duration::from_secs(10),
            };
            handle_poll_err(&ctx, err).await;
            let state: (String, i64, String, String) = db
                .call(|conn| {
                    Ok(conn.query_row(
                        "SELECT status,project_id,compile_id,backtest_id FROM backtest_queue",
                        [],
                        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
                    )?)
                })
                .await
                .unwrap();
            assert_eq!(state, ("failed".into(), 42, "cid".into(), "bid".into()));
            assert!(
                tokio::time::timeout(Duration::from_millis(100), &mut server)
                    .await
                    .is_err(),
                "Unexpected cloud cancellation request"
            );
            server.abort();
        }
    }
}
