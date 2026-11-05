//! QC-specific database wrapper.
//!
//! Submodules:
//! - `claim`: job claiming (`claim_next_job_with_pool`)
//! - `experiment`: `insert_experiment`
//! - `queue_status`: `mark_done` / `mark_failed` / `queue_counts`
//! - `types`: data structs (`QueueJob`, `Experiment`)

pub mod claim;
mod job_files;
mod schema;
pub use schema::{initialize_strategy, validate_strategy_id};
mod claim_scan;
mod claim_tx;
mod execution;
pub mod experiment;
mod queue_status;
mod result;
pub mod types;

use std::ops::Deref;
use std::path::Path;

use anyhow::Result;

use crate::database::Db as BaseDb;

// Re-export types so `crate::db::QueueJob` still works everywhere
pub use types::{Experiment, QUEUEJOB_SELECT_COLUMNS, QueueJob, queue_job_from_row};

/// QC-specific database wrapper.
/// Derefs to `shared::Db` for transparent access to settings, `call()`, etc.
#[derive(Clone)]
pub struct Db {
    inner: BaseDb,
    pub strategy: String,
}

impl Deref for Db {
    type Target = BaseDb;
    fn deref(&self) -> &BaseDb {
        &self.inner
    }
}

impl Db {
    /// Open a strategy-scoped database at `path`.
    ///
    /// # Errors
    /// Returns `Err` if the underlying `DuckDB` connection cannot be opened.
    pub fn open(path: &Path, strategy: &str) -> Result<Self> {
        let db = BaseDb::open(path)?;
        db.sync_call(|conn| {
            let tx = conn.transaction()?;
            schema::upgrade(&tx)?;
            tx.commit()?;
            Ok(())
        })?;
        Ok(Self {
            inner: db,
            strategy: strategy.to_string(),
        })
    }
}
