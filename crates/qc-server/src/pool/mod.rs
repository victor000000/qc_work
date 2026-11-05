//! Global warm pool: continuously pre-warms jobs on free projects.
//!
//! Submodules:
//! - `claim`: `strategy_has_work`, `lock_free_project`, `claim_job`, `requeue_job`
//! - `filler`: background task that fills the warm pool
//! - `job`: `warm_one_job` orchestrator
//! - `job_steps`: push + compile + poll steps
//! - `push`: `push_code`, `compile_code`, `poll_compile`

pub mod claim;
pub mod filler;
mod filler_batch;
pub mod job;
mod job_attempt;
pub(crate) mod job_steps;
mod job_validate;
pub mod push;

use std::collections::VecDeque;
use std::time::Instant;

use tokio::sync::Mutex;

use crate::db::{Db, QueueJob};
use crate::runner::ProjectLock;

pub use filler::{WarmPoolFillerParams, warm_pool_filler};

/// A ready-to-backtest entry: code pushed, compile done, project locked.
pub struct WarmEntry {
    pub job: QueueJob,
    pub db: Db,
    pub project_id: i64,
    pub compile_id: String,
    pub strategy: String,
    pub warmed_at: Instant,
}

/// Shared pool of pre-warmed entries.
pub struct WarmPool {
    pub(crate) entries: Mutex<VecDeque<WarmEntry>>,
    _project_lock: ProjectLock,
    pub(crate) max_entries: usize,
}

impl WarmPool {
    pub fn new(project_lock: ProjectLock, max_entries: usize) -> Self {
        Self {
            entries: Mutex::new(VecDeque::new()),
            _project_lock: project_lock,
            max_entries,
        }
    }

    /// Take a warm entry from the pool (FIFO).
    pub async fn take(&self) -> Option<WarmEntry> {
        self.entries.lock().await.pop_front()
    }

    /// How many entries are ready.
    pub async fn len(&self) -> usize {
        self.entries.lock().await.len()
    }

    /// True if the pool currently holds no entries.
    pub async fn is_empty(&self) -> bool {
        self.entries.lock().await.is_empty()
    }

    /// Add a warm entry to the pool.
    pub(crate) async fn push(&self, entry: WarmEntry) {
        self.entries.lock().await.push_back(entry);
    }
}
