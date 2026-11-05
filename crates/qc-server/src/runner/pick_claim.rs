//! Per-strategy claim attempt used by `pick_next`.

use super::SlotRunner;
use crate::db::{Db, QueueJob};

impl SlotRunner {
    /// Try to claim a job from a specific strategy index.
    pub(super) async fn try_claim(&self, strat_idx: usize) -> Option<(QueueJob, Db, i64)> {
        let db = &self.dbs[strat_idx];
        let strat = &self.strategies[strat_idx];
        let project_id =
            strat.project_ids[(self.slot_id + self.job_counter) % strat.project_ids.len()];
        let node_tag = format!("slot-{}", self.slot_id);

        let claim_result = db
            .claim_next_job_with_pool(
                &node_tag,
                project_id,
                self.name_prefix.as_deref(),
                &strat.project_ids,
            )
            .await;

        match claim_result {
            Ok(Some((job, effective_project_id))) => {
                tracing::debug!(
                    "slot-{}: claimed {} from {} (project={effective_project_id})",
                    self.slot_id,
                    job.name,
                    strat.name
                );
                Some((job, db.clone(), effective_project_id))
            }
            Ok(None) => {
                tracing::debug!(
                    "slot-{}: claim returned None for {} (project conflicts)",
                    self.slot_id,
                    strat.name
                );
                None
            }
            Err(e) => {
                tracing::warn!("slot-{}: claim error for {}: {e}", self.slot_id, strat.name);
                None
            }
        }
    }
}
