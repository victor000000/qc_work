//! Single job warming: find work, lock project, push code, compile.

use std::time::Instant;

use super::WarmEntry;
use super::job_attempt::try_strategy;
use crate::client::QcClient;
use crate::config::StrategyConfig;
use crate::db::Db;
use crate::rate_limit::RateLimitState;
use crate::runner::ProjectLock;

/// Bundled parameters for warming a single job.
pub(crate) struct PoolJobParams<'a> {
    pub client: &'a QcClient,
    pub dbs: &'a [Db],
    pub strategies: &'a [StrategyConfig],
    pub project_lock: &'a ProjectLock,
    pub counter: usize,
    pub name_prefix: &'a Option<String>,
    pub rl_state: &'a Option<RateLimitState>,
}

/// Warm a single job: find queued work, lock a project, push+compile.
///
/// Returns `Some(WarmEntry)` on success, `None` if no work or no free projects.
pub(crate) async fn warm_one_job(params: PoolJobParams<'_>) -> Option<WarmEntry> {
    let warm_start = Instant::now();
    // Strategy ordering: rotate by counter so each strategy gets equal
    // "first-pick" attempts across many calls.
    let n = params.dbs.len();
    let mut strat_indices: Vec<usize> = (0..n).collect();
    if n > 0 {
        let offset = params.counter % n;
        strat_indices.rotate_left(offset);
    }

    for &si in &strat_indices {
        if let Some(entry) = try_strategy(&params, si, warm_start).await {
            return Some(entry);
        }
    }

    // trace! — the warm-pool loop fires ~30/sec when idle; was 127k lines/hr
    // of debug spam (60% of qc_full.log volume).
    tracing::trace!(
        "warm-pool: no work or no free projects (took {}ms)",
        warm_start.elapsed().as_millis()
    );
    None
}
