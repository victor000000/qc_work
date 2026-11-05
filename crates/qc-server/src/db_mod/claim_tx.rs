//! Synchronous claim transaction body (runs on the `DuckDB` worker thread).

use anyhow::Result;
use duckdb::Connection;

use super::claim_scan::scan_candidates;
use super::types::QueueJob;

pub(super) fn run_claim_tx(
    conn: &Connection,
    strategy: &str,
    node_id: &str,
    project_id: i64,
    prefix: Option<&str>,
    pool: &[i64],
) -> Result<Option<(QueueJob, i64)>> {
    let tx = conn.unchecked_transaction()?;

    let mut running_projects: Vec<i64> = Vec::new();
    {
        let mut stmt = tx.prepare(
            "SELECT DISTINCT project_id FROM backtest_queue \
             WHERE status='running' AND project_id IS NOT NULL",
        )?;
        let rows = stmt.query_map([], |row| row.get::<_, i64>(0))?;
        for p in rows.flatten() {
            running_projects.push(p);
        }
    }

    let candidates: Vec<(i64, Option<i64>)> = if let Some(p) = prefix {
        // Bind the prefix to avoid SQL injection from quotes/wildcards.
        let pat = format!("{p}%");
        let mut stmt = tx.prepare(
            "SELECT id, COALESCE(requested_project_id, project_id) FROM backtest_queue
             WHERE status='queued' AND name LIKE ?1
             ORDER BY priority ASC, id ASC",
        )?;
        stmt.query_map([&pat], |row| Ok((row.get(0)?, row.get(1)?)))?
            .filter_map(std::result::Result::ok)
            .collect()
    } else {
        let mut stmt = tx.prepare(
            "SELECT id, COALESCE(requested_project_id, project_id) FROM backtest_queue
             WHERE status='queued'
             ORDER BY priority ASC, id ASC",
        )?;
        stmt.query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?
            .filter_map(std::result::Result::ok)
            .collect()
    };

    let result = scan_candidates(&candidates, &running_projects, project_id, pool);
    tracing::debug!(
        "{node_id}: claim scan: {} candidates, {} skipped \
         (project conflicts), running_projects={running_projects:?}",
        candidates.len(),
        result.skipped
    );

    let Some(job_id) = result.job_id else {
        // trace! — happy-side race miss; fires per claim attempt when all
        // candidates conflict with active projects. The scan log above stays
        // at debug for diagnostic context when needed.
        tracing::trace!(
            "{node_id}: no claimable job (all {} candidates conflict)",
            result.skipped
        );
        return Ok(None);
    };
    let effective_project_id = result.effective_project_id;

    tx.execute(
        "UPDATE backtest_queue
         SET status='running', started_at=datetime('now'),
             node_id=?1, requested_project_id=COALESCE(requested_project_id, project_id), project_id=?2
         WHERE id=?3 AND status='queued'",
        duckdb::params![node_id, effective_project_id, job_id],
    )?;

    let job = tx.query_row(
        &format!(
            "SELECT {} FROM backtest_queue WHERE id=?1",
            super::types::QUEUEJOB_SELECT_COLUMNS
        ),
        [job_id],
        |row| super::types::queue_job_from_row(row, strategy),
    )?;

    tx.commit()?;
    Ok(Some((job, effective_project_id)))
}
