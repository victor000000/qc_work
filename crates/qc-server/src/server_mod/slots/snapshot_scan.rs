//! Aggregate `(queued, prewarm, bt_running, distinct_busy_slots)` across DBs.

use crate::db::Db;

pub(super) async fn scan_dbs(dbs: &[Db]) -> (i64, i64, i64, usize) {
    let mut bt_running = 0i64;
    let mut prewarm = 0i64;
    let mut queued = 0i64;
    let mut distinct_slots: std::collections::HashSet<String> = std::collections::HashSet::new();
    for db in dbs {
        let (q, r, b, slot_ids): (i64, i64, i64, Vec<String>) = db
            .call(|conn| {
                let q: i64 = conn
                    .query_row(
                        "SELECT COUNT(*) FROM backtest_queue WHERE status='queued'",
                        [],
                        |r| r.get(0),
                    )
                    .unwrap_or(0);
                let r: i64 = conn
                    .query_row(
                        "SELECT COUNT(*) FROM backtest_queue \
                         WHERE status='running' AND backtest_id IS NULL",
                        [],
                        |row| row.get(0),
                    )
                    .unwrap_or(0);
                let b: i64 = conn
                    .query_row(
                        "SELECT COUNT(*) FROM backtest_queue \
                         WHERE status='running' AND backtest_id IS NOT NULL",
                        [],
                        |row| row.get(0),
                    )
                    .unwrap_or(0);
                let mut stmt = conn.prepare(
                    "SELECT DISTINCT node_id FROM backtest_queue \
                     WHERE status='running' AND node_id LIKE 'slot-%'",
                )?;
                let ids: Vec<String> = stmt
                    .query_map([], |row| row.get::<_, String>(0))?
                    .filter_map(std::result::Result::ok)
                    .collect();
                Ok((q, r, b, ids))
            })
            .await
            .unwrap_or((0, 0, 0, Vec::new()));
        queued += q;
        prewarm += r;
        bt_running += b;
        for id in slot_ids {
            distinct_slots.insert(id);
        }
    }
    (queued, prewarm, bt_running, distinct_slots.len())
}
