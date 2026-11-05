//! Integration tests for `Db::mark_done` / `mark_failed` / `queue_counts`.
//!
//! Seeds a temp DuckDB with the production `backtest_queue` schema and
//! exercises the queue-status surface end-to-end. Regression coverage for
//! the bug class where SQL bindings (recently fixed in `claim_tx.rs`) or
//! status-string drift could silently break the runner.

use duckdb::Connection;
use qc::db::Db;

const SCHEMA: &str = include_str!("../schema.sql");
const SEED: &str = "    INSERT INTO backtest_queue (id, name, code, status) VALUES
        (1, 'q1', 'pass', 'queued'),
        (2, 'q2', 'pass', 'queued'),
        (3, 'r1', 'pass', 'running'),
        (4, 'd1', 'pass', 'done'),
        (5, 'd2', 'pass', 'done'),
        (6, 'f1', 'pass', 'failed');
";

fn tmp_db() -> (tempfile::NamedTempFile, Db) {
    let tmp = tempfile::NamedTempFile::new().expect("tmp file");
    let path = tmp.path().to_path_buf();
    std::fs::remove_file(&path).unwrap();
    Connection::open(&path)
        .unwrap()
        .execute_batch(&format!("{SCHEMA}{SEED}"))
        .unwrap();
    let db = Db::open(&path, "test").expect("open db");
    (tmp, db)
}

#[tokio::test]
async fn queue_counts_groups_by_status() {
    let (_tmp, db) = tmp_db();
    let mut counts = db.queue_counts().await.expect("queue_counts");
    counts.sort_by(|a, b| a.0.cmp(&b.0));
    assert_eq!(
        counts,
        vec![
            ("done".to_string(), 2),
            ("failed".to_string(), 1),
            ("queued".to_string(), 2),
            ("running".to_string(), 1),
        ]
    );
}

#[tokio::test]
async fn mark_done_updates_status_and_metadata() {
    let (_tmp, db) = tmp_db();
    db.mark_done(3, "cid_x", "bt_y", 42.5, Some("{\"k\":1}"))
        .await
        .expect("mark_done");
    let row: (
        String,
        Option<String>,
        Option<String>,
        Option<f64>,
        Option<String>,
    ) = db
        .call(|c| {
            Ok(c.query_row(
                "SELECT status, compile_id, backtest_id, runtime_seconds, result_json
                 FROM backtest_queue WHERE id=3",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
            )?)
        })
        .await
        .unwrap();
    assert_eq!(row.0, "done");
    assert_eq!(row.1.as_deref(), Some("cid_x"));
    assert_eq!(row.2.as_deref(), Some("bt_y"));
    assert!((row.3.unwrap() - 42.5).abs() < 1e-9);
    assert_eq!(row.4.as_deref(), Some("{\"k\":1}"));
}

#[tokio::test]
async fn mark_failed_bumps_retry_count() {
    let (_tmp, db) = tmp_db();
    db.mark_failed(3, "boom", None).await.expect("mark_failed");
    db.mark_failed(3, "boom2", None)
        .await
        .expect("mark_failed 2");
    let row: (String, Option<String>, i64) = db
        .call(|c| {
            Ok(c.query_row(
                "SELECT status, error_message, retry_count
                 FROM backtest_queue WHERE id=3",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )?)
        })
        .await
        .unwrap();
    assert_eq!(row.0, "failed");
    assert_eq!(row.1.as_deref(), Some("boom2"));
    assert_eq!(row.2, 2);
}

#[tokio::test]
async fn mark_failed_handles_multibyte_error_message_safely() {
    // Regression: pre-fix code did `&error[..error.len().min(80)]`, which
    // panics if byte 80 lands mid-codepoint. The bug was masked in tests
    // because tracing::debug! is callsite-gated without a subscriber, but
    // would fire in production where debug logging is enabled. We install
    // a real subscriber here to force the format expression to evaluate.
    use tracing_subscriber::fmt;
    let _guard = fmt()
        .with_max_level(tracing::Level::DEBUG)
        .with_test_writer()
        .try_init();
    let (_tmp, db) = tmp_db();
    let long = "中".repeat(200); // 3-byte UTF-8 chars; byte 80 is mid-codepoint
    db.mark_failed(3, &long, None)
        .await
        .expect("mark_failed unicode");
}

#[tokio::test]
async fn collecting_without_compile_id_preserves_existing_identity() {
    let (_tmp, db) = tmp_db();
    db.call(|conn| {
        conn.execute(
            "UPDATE backtest_queue SET compile_id='original' WHERE id=3",
            [],
        )?;
        Ok(())
    })
    .await
    .unwrap();
    db.mark_done(3, "", "bt", 1.0, None).await.unwrap();
    let cid: String = db
        .call(|conn| {
            Ok(conn.query_row(
                "SELECT compile_id FROM backtest_queue WHERE id=3",
                [],
                |row| row.get(0),
            )?)
        })
        .await
        .unwrap();
    assert_eq!(cid, "original");
}

#[tokio::test]
async fn execution_identity_requires_running_job_and_survives_collection() {
    let (_tmp, db) = tmp_db();
    assert!(db.record_execution(1, "cid", "bid").await.is_err());
    db.record_execution(3, "cid", "bid").await.unwrap();
    db.mark_done(3, "", "bid", 1.0, None).await.unwrap();
    let ids: (String, String) = db
        .call(|conn| {
            Ok(conn.query_row(
                "SELECT compile_id,backtest_id FROM backtest_queue WHERE id=3",
                [],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )?)
        })
        .await
        .unwrap();
    assert_eq!(ids, ("cid".into(), "bid".into()));
}
