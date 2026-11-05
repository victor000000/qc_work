//! Job claiming: atomically pick + mark running in one transaction.
//!
//! The sync transaction body that runs on the `DuckDB` worker thread lives
//! in `claim_tx.rs` so this file just orchestrates the async wrapper.

use anyhow::Result;

use super::Db;
use super::claim_tx::run_claim_tx;
use super::types::QueueJob;

impl Db {
    /// Atomically claim the next queued job, with a fallback `project_pool`.
    ///
    /// # Errors
    /// Returns `Err` on SQL execution error.
    pub async fn claim_next_job_with_pool(
        &self,
        node_id: &str,
        project_id: i64,
        name_prefix: Option<&str>,
        project_pool: &[i64],
    ) -> Result<Option<(QueueJob, i64)>> {
        let strategy = self.strategy.clone();
        let nid = node_id.to_string();
        let prefix = name_prefix.map(std::string::ToString::to_string);
        let pool = project_pool.to_vec();
        self.call(move |conn| {
            run_claim_tx(conn, &strategy, &nid, project_id, prefix.as_deref(), &pool)
        })
        .await
    }
}
