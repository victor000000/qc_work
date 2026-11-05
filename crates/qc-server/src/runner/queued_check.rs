//! Cross-DB queued-work scan helper.

use super::SlotRunner;

impl SlotRunner {
    /// Check if any strategy DB has queued work (parallel scan).
    pub(crate) async fn any_queued_work(&self) -> bool {
        let mut set = tokio::task::JoinSet::new();
        for db in &self.dbs {
            let db = db.clone();
            set.spawn(async move {
                db.call(|conn| {
                    let n: i64 = conn.query_row(
                        "SELECT COUNT(*) FROM backtest_queue \
                         WHERE status='queued' LIMIT 1",
                        [],
                        |r| r.get(0),
                    )?;
                    Ok(n > 0)
                })
                .await
                .unwrap_or(false)
            });
        }
        while let Some(res) = set.join_next().await {
            if matches!(res, Ok(true)) {
                set.abort_all();
                return true;
            }
        }
        false
    }
}
