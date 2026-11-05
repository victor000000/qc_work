//! Alternative-project search used by `lock_project` when the primary is
//! already locked. Atomically inserts the alternative into the lock set
//! BEFORE releasing the mutex (otherwise two slots could race and pick the
//! same free project — `HashSet::insert` would dedup silently, then the
//! second unlock would `remove` a phantom entry and corrupt the set).

use std::collections::HashSet;

use tokio::sync::MutexGuard;

use super::SlotRunner;
use crate::db::{Db, QueueJob};

pub(super) async fn try_alternative_project(
    runner: &SlotRunner,
    locked: &mut MutexGuard<'_, HashSet<i64>>,
    primary: i64,
    strategy: &str,
    job_name: &str,
    job: &QueueJob,
    db: &Db,
) -> Option<i64> {
    if job.requested_project_id.is_some() {
        return None;
    }
    let strat_idx = runner.strategies.iter().position(|s| s.name == strategy)?;
    let mut chosen: Option<i64> = None;
    for pid in &runner.strategies[strat_idx].project_ids {
        if !locked.contains(pid) {
            tracing::debug!(
                "slot-{}: project {primary} locked, switching to {pid} for {strategy}/{job_name}",
                runner.slot_id,
            );
            locked.insert(*pid);
            chosen = Some(*pid);
            break;
        }
    }
    let alt = chosen?;
    let jid = job.id;
    let db_clone = db.clone();
    // If the DB write fails the in-memory lock would point at `alt` while the
    // row still names `primary` — slot pushes code to alt but QC tracks it
    // against primary. Roll back the lock insert and let the caller retry.
    let write_result = db_clone
        .call(move |conn| {
            conn.execute(
                "UPDATE backtest_queue SET project_id=?1 WHERE id=?2",
                duckdb::params![alt, jid],
            )?;
            Ok(())
        })
        .await;
    if let Err(e) = write_result {
        tracing::warn!(
            "slot-{}: failed to rewrite project_id to {alt} for {strategy}/{job_name}: {e}; rolling back lock",
            runner.slot_id,
        );
        locked.remove(&alt);
        return None;
    }
    Some(alt)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    #[tokio::test]
    async fn explicit_project_pin_is_never_rerouted_when_another_strategy_holds_it() {
        let temp = tempfile::tempdir().unwrap();
        let path = crate::db::initialize_strategy(temp.path(), "stest").unwrap();
        let db = Db::open(&path, "stest").unwrap();
        db.call(|conn| {
            conn.execute(
                "INSERT INTO backtest_queue(name,code,project_id) VALUES ('pinned','pass',42)",
                [],
            )?;
            Ok(())
        })
        .await
        .unwrap();
        let (job, _) = db
            .claim_next_job_with_pool("test", 43, None, &[42, 43])
            .await
            .unwrap()
            .unwrap();
        let project_lock = crate::runner::ProjectLock::default();
        project_lock.lock().await.insert(42);
        let runner = SlotRunner::new(crate::runner::SlotRunnerNew {
            slot_id: 0,
            client: Arc::new(crate::client::QcClient::new("unused", "unused")),
            dbs: vec![db.clone()],
            strategies: vec![crate::config::StrategyConfig {
                name: "stest".into(),
                db_path: path,
                project_ids: vec![42, 43],
                weight: 1.0,
            }],
            name_prefix: None,
            rl_state: None,
            session: None,
            project_lock: Arc::clone(&project_lock),
            num_slots: 1,
        });
        let mut locked = project_lock.lock().await;
        let alternative =
            try_alternative_project(&runner, &mut locked, 42, "stest", "pinned", &job, &db).await;
        assert_eq!(alternative, None);
        assert_eq!(locked.len(), 1);
    }
}
