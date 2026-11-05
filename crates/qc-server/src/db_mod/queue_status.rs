//! Queue-row state transitions: `mark_done`, `mark_failed`, `queue_counts`.

use anyhow::Result;

use super::Db;

impl Db {
    /// Mark a job as done with `compile_id`, `backtest_id`, and runtime.
    ///
    /// # Errors
    /// Returns `Err` on SQL execution error.
    pub async fn mark_done(
        &self,
        job_id: i64,
        compile_id: &str,
        backtest_id: &str,
        runtime_secs: f64,
        result_json: Option<&str>,
    ) -> Result<()> {
        tracing::debug!(
            "{}: mark_done job_id={job_id} bt={backtest_id} \
             runtime={runtime_secs:.1}s",
            self.strategy
        );
        let cid = compile_id.to_string();
        let bid = backtest_id.to_string();
        let rj = result_json.map(std::string::ToString::to_string);
        self.inner
            .call(move |conn| {
                conn.execute(
                    "UPDATE backtest_queue
                     SET status='done', completed_at=datetime('now'),
                         compile_id=CASE WHEN ?1='' THEN compile_id ELSE ?1 END, backtest_id=?2,
                         runtime_seconds=?3, result_json=?4
                     WHERE id=?5",
                    duckdb::params![cid, bid, runtime_secs, rj, job_id],
                )?;
                Ok(())
            })
            .await
    }

    /// Mark a job as failed with error message.
    ///
    /// # Errors
    /// Returns `Err` on SQL execution error.
    pub async fn mark_failed(
        &self,
        job_id: i64,
        error: &str,
        result_json: Option<&str>,
    ) -> Result<()> {
        // Truncate on a char boundary — `&error[..80]` panics if byte 80
        // lands mid-codepoint, which can happen with non-ASCII errors
        // (Chinese stack traces, etc.) once tracing is initialized in prod.
        let err_preview: String = error.chars().take(80).collect();
        tracing::debug!(
            "{}: mark_failed job_id={job_id} error={err_preview}",
            self.strategy
        );
        let err = error.to_string();
        let rj = result_json.map(std::string::ToString::to_string);
        self.inner
            .call(move |conn| {
                conn.execute(
                    "UPDATE backtest_queue
                     SET status='failed', completed_at=datetime('now'),
                         error_message=?1, retry_count=retry_count+1,
                         result_json=?2
                     WHERE id=?3",
                    duckdb::params![err, rj, job_id],
                )?;
                Ok(())
            })
            .await
    }

    /// Return `(status, count)` pairs for the `backtest_queue` table.
    ///
    /// # Errors
    /// Returns `Err` on SQL execution error.
    pub async fn queue_counts(&self) -> Result<Vec<(String, i64)>> {
        self.inner
            .call(|conn| {
                let mut stmt = conn.prepare(
                    "SELECT status, COUNT(*) FROM backtest_queue \
                     GROUP BY status",
                )?;
                let rows = stmt
                    .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?
                    .collect::<Result<Vec<_>, _>>()?;
                Ok(rows)
            })
            .await
    }
}
