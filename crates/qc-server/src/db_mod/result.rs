//! Atomic experiment/result persistence: both records commit or neither does.
use super::{Db, Experiment};

impl Db {
    /// Store metrics and mark their running queue row done in one transaction.
    ///
    /// # Errors
    /// Returns an error on SQL failure or if the running queue row has disappeared.
    pub async fn store_completed(
        &self,
        job_id: i64,
        mut exp: Experiment,
        backtest_id: &str,
        runtime_secs: f64,
        result_json: &str,
    ) -> anyhow::Result<()> {
        let bid = backtest_id.to_string();
        exp.backtest_id = bid.clone();
        exp.runtime_seconds = Some(runtime_secs);
        let result = result_json.to_string();
        self.call(move |conn| {
            let tx = conn.unchecked_transaction()?;
            super::experiment::insert_on(&tx, &exp)?;
            let changed = tx.execute(
                "UPDATE backtest_queue SET status='done',completed_at=datetime('now'),
                 backtest_id=?1,runtime_seconds=?2,result_json=?3 WHERE id=?4 AND status='running' AND name=?5",
                duckdb::params![bid, runtime_secs, result, job_id, exp.name],
            )?;
            anyhow::ensure!(
                changed == 1,
                "running job {job_id} disappeared before collection"
            );
            tx.commit()?;
            Ok(())
        })
        .await
    }
}
