//! Backpressure gate: throttles slot loops based on `active_collects`.

use std::sync::Arc;
use std::sync::atomic::Ordering;

use crate::server::SessionCounters;

/// Apply hard + soft backpressure on `active_collects`.
///
/// Backpressure: avoid unbounded `poll_and_collect` tasks that saturate QC API
/// (causing 10-30s `create_backtest` latency).
/// Post-fix 2026-05-06: `active_collects` now counts only QC-side running bts
/// (poll-only), so the cap maps directly to QC queue depth.
///
/// 2026-05-07 RAISE: at 19+/min throughput with ~80s avg backtest,
/// `active_collects` naturally rides 30-35. Old hard cap 2.25x (=22.5) was
/// actively starving the QC scheduler — server logs showed `starvation: 1125s
/// (6%), idle_slot_secs=1605, ~21 bts missed`. Raised hard 2.25x → 4x (=40)
/// and soft 1.5x → 2.5x (=25). Since `active_collects` is purely QC-side poll
/// state with no local resource pressure, a higher cap just lets the QC
/// scheduler keep all 10 nodes saturated.
///
/// 2026-05-07 PM raise: restart22 saw `active_collects` peaking at 50 vs
/// `hard_cap`=40, triggering 1237 `backpressure_hard` waits and 35s pick-phase
/// stalls. With 53 projects + sem-rotate + pacer-cap in place, the QC API
/// comfortably handles 50+ concurrent reads. Raised hard 4x → 6x (=60),
/// soft 2.5x → 4x (=40). If sustained throughput exceeds ~22/min, can
/// raise further; the cap just exists to prevent runaway poll-task
/// accumulation if QC ever stops responding.
pub(super) async fn apply(
    session: Option<&Arc<SessionCounters>>,
    slot_id: usize,
    num_slots: usize,
) {
    let Some(s) = session else { return };
    let slots = i64::try_from(num_slots).unwrap_or(i64::MAX);
    let mut was_waiting = false;
    // Hard cap loop: don't proceed if too many active collects.
    // 2026-05-08: 12x cap (was 6x) per user direction "loosen the cap" —
    // active_collects naturally rides 30-50 with 10 slots; old 6x=60 cap
    // still triggered backpressure_hard during bursts. 12x=120 gives ample
    // headroom to keep QC scheduler saturated; cap remains as runaway-
    // protection if QC ever stops responding entirely.
    let hard_cap = slots * 12;
    loop {
        let active = s.active_collects.load(Ordering::SeqCst);
        if active <= hard_cap {
            break;
        }
        was_waiting = true;
        tracing::debug!(
            target: "qc::pipeline",
            "slot-{slot_id}: backpressure_hard active_collects={active} hard_cap={hard_cap} (12x slots={slots}) (waiting 350ms)",
        );
        tokio::time::sleep(std::time::Duration::from_millis(350)).await;
    }
    // Stagger creates after release to avoid thundering-herd: when cap
    // drops by 1, ALL 10 slot loops would otherwise detect simultaneously
    // and burst-create 10 bts at once. Per-slot jitter spreads creates
    // across ~450ms.
    if was_waiting {
        tokio::time::sleep(std::time::Duration::from_millis((slot_id as u64) * 35)).await;
    }
    let active = s.active_collects.load(Ordering::SeqCst);
    // 2026-05-08: 8x (was 4x) — matches loosened hard cap.
    let soft_cap = slots * 8;
    if active > soft_cap {
        tracing::debug!(
            target: "qc::pipeline",
            "slot-{slot_id}: backpressure_soft active_collects={active} soft_cap={soft_cap} (8x slots={slots}) (sleep 210ms)",
        );
        tokio::time::sleep(std::time::Duration::from_millis(210)).await;
    }
}
