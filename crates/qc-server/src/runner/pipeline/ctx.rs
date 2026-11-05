//! Owned context for the spawned poll+collect task.

use std::sync::Arc;

use tokio::time::Duration;

use crate::client::QcClient;
use crate::db::{Db, QueueJob};
use crate::server::SessionCounters;

/// All context needed by `poll_and_collect`. Owned values — moved into
/// the tokio-spawned task.
pub(crate) struct PollCollectCtx {
    pub slot_id: usize,
    pub client: Arc<QcClient>,
    pub session: Option<Arc<SessionCounters>>,
    pub db: Db,
    pub job: QueueJob,
    pub project_id: i64,
    pub backtest_id: String,
    pub strategy: String,
    pub job_name: String,
    pub prep_elapsed: Duration,
    pub bt_poll: Duration,
    pub bt_timeout: Duration,
}
