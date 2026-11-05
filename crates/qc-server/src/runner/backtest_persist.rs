//! Post-create persistence: write `backtest_id` to the queue row, then bump
//! global phase counters used by the periodic overhead summary.

#![allow(
    clippy::too_many_arguments,
    reason = "all phases derive from prep_backtest"
)]

use std::time::Instant;

use tokio::time::Duration;

use super::SlotRunner;
use crate::db::{Db, QueueJob};

pub(super) async fn persist_and_record(
    runner: &SlotRunner,
    db: &Db,
    job: &QueueJob,
    backtest_id: &str,
    compile_id: &str,
    push_start: Instant,
    compile_start: Instant,
    compile_phase_dur: Duration,
    bt_create_start: Instant,
) -> anyhow::Result<()> {
    db.record_execution(job.id, compile_id, backtest_id).await?;

    let push_dur = compile_start.duration_since(push_start);
    let create_api_dur = bt_create_start.elapsed();
    let to_ms = |d: Duration| u64::try_from(d.as_millis()).unwrap_or(u64::MAX);
    if let Some(s) = &runner.session {
        use std::sync::atomic::Ordering;
        s.push_ms.fetch_add(to_ms(push_dur), Ordering::SeqCst);
        s.compile_ms
            .fetch_add(to_ms(compile_phase_dur), Ordering::SeqCst);
        s.create_api_ms
            .fetch_add(to_ms(create_api_dur), Ordering::SeqCst);
    }
    // Per-cycle local phase log — replaces the misleading global-atomic-delta
    // version that had cross-slot attribution. All three phases are NODE-IDLE:
    // the QC node only flips `busy=true` once create_backtest returns.
    tracing::debug!(
        target: "qc::pipeline",
        "slot-{} {}: phase_breakdown_ms push={} compile={} create_api={} (local per-cycle, all node-idle)",
        runner.slot_id,
        job.strategy,
        to_ms(push_dur),
        to_ms(compile_phase_dur),
        to_ms(create_api_dur)
    );
    Ok(())
}
