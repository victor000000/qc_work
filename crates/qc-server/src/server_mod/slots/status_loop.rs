//! Periodic status reporter loop (60s cadence).

use std::sync::Arc;
use std::sync::atomic::Ordering;

use tokio::task::JoinHandle;
use tokio::time::Duration;

use crate::client::QcClient;
use crate::db::Db;
use crate::rate_limit::RateLimitState;
use crate::server::SessionCounters;
use crate::server::status::{StatusTickInput, log_status};

/// Spawn the periodic status reporter — prints status box every 60s.
///
/// Status box: serial loop, prints in order, ~60s cadence.
/// Authoritative QC `busy_slots` is updated by a separate dedicated
/// poller — `log_status` reads from atomic so this loop stays fast
/// (only DB queries + atomic loads).
pub(super) fn spawn_status_loop(
    dbs: Vec<Db>,
    rl_state: RateLimitState,
    session: Arc<SessionCounters>,
    client: Arc<QcClient>,
    num_slots: usize,
    project_id: i64,
) -> JoinHandle<()> {
    let server_start = std::time::Instant::now();
    tokio::spawn(async move {
        let mut ticker = tokio::time::interval(Duration::from_mins(1));
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        ticker.tick().await; // consume immediate first tick
        loop {
            ticker.tick().await;
            rl_state.save(&dbs[0]).await;
            let rl_delay = rl_state.estimated_delay_ms.load(Ordering::Relaxed);
            let uptime = server_start.elapsed().as_secs();
            let completed = session.completed.load(Ordering::SeqCst);
            let failed = session.failed.load(Ordering::SeqCst);
            log_status(StatusTickInput {
                dbs: &dbs,
                uptime_secs: uptime,
                rl_delay_ms: rl_delay,
                session_completed: completed,
                session_failed: failed,
                session: Arc::clone(&session),
                num_slots,
                client: &client,
                project_id,
            })
            .await;
        }
    })
}
