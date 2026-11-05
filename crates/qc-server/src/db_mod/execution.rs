//! Persist cloud execution identity before releasing the compute project.
use super::Db;

impl Db {
    /// Record the compile and backtest IDs for crash recovery and provenance.
    ///
    /// # Errors
    /// Fails on database errors or when the job no longer belongs to a running attempt.
    pub async fn record_execution(
        &self,
        job_id: i64,
        compile_id: &str,
        backtest_id: &str,
    ) -> anyhow::Result<()> {
        let cid = compile_id.to_string();
        let bid = backtest_id.to_string();
        self.call(move |conn| {
            let changed = conn.execute(
                "UPDATE backtest_queue SET compile_id=?1,backtest_id=?2 WHERE id=?3 AND status='running'",
                duckdb::params![cid,bid,job_id],
            )?;
            anyhow::ensure!(changed == 1, "running job {job_id} disappeared before execution persistence");
            Ok(())
        }).await
    }
}
