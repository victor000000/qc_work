//! `SlotRunner` struct + constructor — extracted from `mod.rs` so that file
//! stays focused on module declarations.

use std::sync::Arc;

use crate::client::QcClient;
use crate::config::StrategyConfig;
use crate::db::Db;
use crate::pool::WarmPool;

use super::{ProjectLock, RateLimitState};

/// A runner slot — processes one backtest at a time.
///
/// Each slot runs an infinite loop:
/// 1. Take a pre-compiled entry from the warm pool (or fall back to own push+compile)
/// 2. Create a backtest on QC using the `compile_id`
/// 3. Poll until the backtest completes
/// 4. Spawn a background collect task (non-blocking)
/// 5. Unlock the project so the warm pool can reuse it
pub struct SlotRunner {
    pub slot_id: usize,
    pub client: Arc<QcClient>,
    pub dbs: Vec<Db>,
    pub strategies: Vec<StrategyConfig>,

    /// If set, only pick jobs whose name starts with this prefix.
    pub name_prefix: Option<String>,

    /// Shared adaptive rate-limit state (persisted across restarts).
    pub rl_state: Option<RateLimitState>,

    /// Session counters for status reporting (optional, None in tests).
    pub session: Option<Arc<crate::server::SessionCounters>>,

    /// Job counter for rotating through all projects.
    pub(crate) job_counter: usize,

    /// Global lock: projects with pushed code awaiting backtest.
    pub project_lock: ProjectLock,

    /// Shared warm pool of pre-compiled jobs.
    pub warm_pool: Option<Arc<WarmPool>>,

    /// Total slots in deployment — used for backpressure math.
    pub(crate) num_slots: usize,
}

/// Bundled parameters for the `SlotRunner::new` constructor.
pub struct SlotRunnerNew {
    pub slot_id: usize,
    pub client: Arc<QcClient>,
    pub dbs: Vec<Db>,
    pub strategies: Vec<StrategyConfig>,
    pub name_prefix: Option<String>,
    pub rl_state: Option<RateLimitState>,
    pub session: Option<Arc<crate::server::SessionCounters>>,
    pub project_lock: ProjectLock,
    pub num_slots: usize,
}

impl SlotRunner {
    /// Build a runner using only databases belonging to active strategies.
    ///
    /// # Panics
    /// Panics if an active strategy has no matching database.
    #[must_use]
    pub fn new(p: SlotRunnerNew) -> Self {
        let dbs = p
            .strategies
            .iter()
            .map(|strategy| {
                p.dbs
                    .iter()
                    .find(|db| db.strategy == strategy.name)
                    .expect("active strategy must have a database")
                    .clone()
            })
            .collect();
        Self {
            slot_id: p.slot_id,
            client: p.client,
            dbs,
            strategies: p.strategies,
            name_prefix: p.name_prefix,
            rl_state: p.rl_state,
            session: p.session,
            job_counter: 0,
            project_lock: p.project_lock,
            warm_pool: None,
            num_slots: p.num_slots,
        }
    }
}
