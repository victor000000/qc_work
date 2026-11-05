//! Aggregate per-strategy counts across all DBs for the status report.

use crate::db::Db;

use super::status_fmt::{RecentFailure, StrategyStatus};
use super::status_query::gather_status;

pub(super) struct Aggregate {
    pub total_queued: i64,
    pub total_running: i64,
    pub strategies: Vec<StrategyStatus>,
    pub recent_errors: Vec<RecentFailure>,
}

pub(super) async fn aggregate_strategies(dbs: &[Db]) -> Aggregate {
    let mut total_queued = 0i64;
    let mut total_running = 0i64;
    let mut strategies = Vec::new();
    let mut recent_errors = Vec::new();
    for db in dbs {
        if let Some((strat, errors)) = gather_status(db).await {
            total_queued += strat.queued;
            total_running += strat.running;
            strategies.push(strat);
            recent_errors.extend(errors);
        }
    }
    Aggregate {
        total_queued,
        total_running,
        strategies,
        recent_errors,
    }
}
