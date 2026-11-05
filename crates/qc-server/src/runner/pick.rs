//! Weighted-random job picking across strategy queues.
//!
//! The per-strategy claim step lives in `pick_claim.rs`.

use super::SlotRunner;
use crate::db::{Db, QueueJob};

impl SlotRunner {
    /// Fair weighted pick across all strategy queues.
    ///
    /// 1. Find which strategies have queued work.
    /// 2. Weighted random selection (weight from `strategy/scheduler_weight`).
    /// 3. Atomically claim from the chosen strategy.
    /// 4. If claim fails (race), try other strategies.
    pub(crate) async fn pick_next(&self) -> Option<(QueueJob, Db, i64)> {
        let slot = self.slot_id;
        let mut available: Vec<(usize, f64)> = Vec::new();

        for (i, db) in self.dbs.iter().enumerate() {
            let prefix = self.name_prefix.clone();
            let has_work = db
                .call(move |conn| {
                    let n: i64 = match &prefix {
                        Some(p) => conn.query_row(
                            "SELECT COUNT(*) FROM backtest_queue \
                             WHERE status='queued' AND name LIKE ?1 LIMIT 1",
                            [format!("{p}%")],
                            |r| r.get(0),
                        )?,
                        None => conn.query_row(
                            "SELECT COUNT(*) FROM backtest_queue \
                             WHERE status='queued' LIMIT 1",
                            [],
                            |r| r.get(0),
                        )?,
                    };
                    Ok(n > 0)
                })
                .await
                .unwrap_or(false);
            // trace! — per-strategy probe inside the pick loop; was ~5k
            // lines/50k sample with has_work=false. The "selected STRAT"
            // line a few lines below stays at debug for diagnostic value.
            tracing::trace!(
                "slot-{slot}: pick_next: strategy[{i}]={} has_work={has_work}",
                self.strategies[i].name
            );
            if has_work {
                available.push((i, self.strategies[i].weight));
            }
        }

        if available.is_empty() {
            // trace! — fires once per pick when idle (~80 lines/sec when no work
            // is queued). The outer `acquire_job` no-work branch stays at debug.
            tracing::trace!("slot-{slot}: pick_next: no strategies have work");
            return None;
        }

        let total_weight: f64 = available.iter().map(|(_, w)| w).sum();
        let mut roll = fastrand::f64() * total_weight;
        let mut selected_idx = available[0].0;
        for &(idx, weight) in &available {
            roll -= weight;
            if roll <= 0.0 {
                selected_idx = idx;
                break;
            }
        }
        tracing::debug!(
            "slot-{slot}: pick_next: selected strategy[{selected_idx}]={}",
            self.strategies[selected_idx].name
        );

        if let Some(result) = self.try_claim(selected_idx).await {
            return Some(result);
        }
        // Selected strategy failed — try others
        for &(idx, _) in &available {
            if idx == selected_idx {
                continue;
            }
            if let Some(result) = self.try_claim(idx).await {
                return Some(result);
            }
        }
        tracing::debug!("slot-{slot}: pick_next: all claims failed");
        None
    }
}
