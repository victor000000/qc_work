//! Recover one cloud execution without discarding an unreadable or uncollected result.
use crate::client::QcClient;
use crate::db::{Db, QueueJob};
use crate::runner::collect::collect_from_response;
use anyhow::{Result, ensure};

pub(super) async fn recover_one_job(
    client: &QcClient,
    db: &Db,
    job_id: i64,
    name: String,
    backtest_id: Option<String>,
    project_id: Option<i64>,
) -> Result<()> {
    if let (Some(bt_id), Some(pid)) = (&backtest_id, project_id)
        && !bt_id.is_empty()
    {
        // An unreadable cloud state is not evidence that the job should rerun.
        let response = client.read_backtest(pid, bt_id).await?;
        if !response.success && missing(&response.errors) {
            requeue_job(db, job_id).await?;
            tracing::info!("{name}: QC record no longer exists — requeued");
            return Ok(());
        }
        ensure!(
            response.success,
            "{name}: recovery read rejected: {:?}",
            response.errors
        );
        let result = response
            .backtest
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("{name}: successful recovery read has no backtest"))?;
        if let Some(error) = result.error.as_deref().filter(|error| !error.is_empty()) {
            db.mark_failed(job_id, error, None).await?;
            return Ok(());
        }
        if result.completed {
            let job = fetch_job_row(db, job_id).await?;
            // Keep the cloud result and execution IDs if collection/SQL fails.
            collect_from_response(client, &job, db, pid, bt_id, 0.0, response).await?;
            tracing::info!("{name}: completed QC result recovered");
            return Ok(());
        }
        let cancelled = client.delete_backtest(pid, bt_id).await?;
        ensure!(
            cancelled.success || missing(&cancelled.errors),
            "{name}: cannot requeue before QC cancellation succeeds: {:?}",
            cancelled.errors
        );
    }
    requeue_job(db, job_id).await?;
    tracing::info!("{name}: requeued");
    Ok(())
}

fn missing(errors: &[String]) -> bool {
    errors.iter().any(|error| {
        let lower = error.to_ascii_lowercase();
        lower.contains("not found") || lower.contains("does not exist")
    })
}

async fn fetch_job_row(db: &Db, job_id: i64) -> Result<QueueJob> {
    let strategy = db.strategy.clone();
    db.call(move |conn| {
        Ok(conn.query_row(
            &format!(
                "SELECT {} FROM backtest_queue WHERE id=?1",
                crate::db::QUEUEJOB_SELECT_COLUMNS
            ),
            [job_id],
            |row| crate::db::queue_job_from_row(row, &strategy),
        )?)
    })
    .await
}

async fn requeue_job(db: &Db, job_id: i64) -> Result<()> {
    db.call(move |conn| {
        let changed = conn.execute(
            "UPDATE backtest_queue SET status='queued',started_at=NULL,completed_at=NULL,
             node_id=NULL,backtest_id=NULL,compile_id=NULL,project_id=NULL,
             result_json=NULL,error_message=NULL,runtime_seconds=NULL
             WHERE id=?1 AND status='running'",
            [job_id],
        )?;
        ensure!(changed == 1, "recovery lost running job {job_id}");
        Ok(())
    })
    .await
}

#[cfg(test)]
mod tests;
