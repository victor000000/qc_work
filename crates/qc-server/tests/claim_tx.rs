//! Integration tests for `Db::claim_next_job_with_pool` — the atomic
//! pick-and-mark-running transaction. Hot bug surface (project pinning,
//! race-resistant updates), so worth full DuckDB-backed coverage.

use duckdb::Connection;
use qc::db::Db;

const SCHEMA: &str = include_str!("../schema.sql");

fn seed_db(rows: &[(&str, &str, Option<i64>)]) -> (tempfile::NamedTempFile, Db) {
    let tmp = tempfile::NamedTempFile::new().expect("tmp");
    let path = tmp.path().to_path_buf();
    std::fs::remove_file(&path).unwrap();
    let conn = Connection::open(&path).unwrap();
    conn.execute_batch(SCHEMA).unwrap();
    for (name, status, pid) in rows {
        conn.execute(
            "INSERT INTO backtest_queue (name, code, status, project_id) VALUES (?1, 'pass', ?2, ?3)",
            duckdb::params![name, status, pid],
        )
        .unwrap();
    }
    let db = Db::open(&path, "test").expect("open");
    (tmp, db)
}

#[tokio::test]
async fn claims_unrun_queued_job_with_no_pin() {
    let (_tmp, db) = seed_db(&[("q1", "queued", None)]);
    let claimed = db
        .claim_next_job_with_pool("slot-0", 100, None, &[100])
        .await
        .expect("claim ok");
    let Some((job, pid)) = claimed else {
        panic!("expected a claim");
    };
    assert_eq!(job.name, "q1");
    assert_eq!(pid, 100, "default project_id assigned when no pin");

    // The row is now status='running' with node_id and project_id set.
    let row: (String, String, i64) = db
        .call(|c| {
            Ok(c.query_row(
                "SELECT status, node_id, project_id FROM backtest_queue WHERE name='q1'",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )?)
        })
        .await
        .unwrap();
    assert_eq!(row.0, "running");
    assert_eq!(row.1, "slot-0");
    assert_eq!(row.2, 100);
}

#[tokio::test]
async fn honors_project_pin_when_pin_is_free() {
    // Pinned job + a different default project. Claim must use the PIN.
    let (_tmp, db) = seed_db(&[("pinned", "queued", Some(42))]);
    let claimed = db
        .claim_next_job_with_pool("slot-0", 100, None, &[100, 42])
        .await
        .expect("claim ok");
    let (job, pid) = claimed.expect("expected claim");
    assert_eq!(job.requested_project_id, Some(42));
    assert_eq!(
        pid, 42,
        "must claim onto the pinned project, not the default"
    );
}

#[tokio::test]
async fn skips_pinned_job_when_its_project_is_running() {
    // Two jobs: a pinned one whose project is already running, and a fresh
    // queued one. The scan should skip the pinned-but-blocked candidate
    // and claim the next eligible.
    let (_tmp, db) = seed_db(&[
        ("blocker", "running", Some(42)), // occupies project 42
        ("pinned_to_42", "queued", Some(42)),
        ("free", "queued", None),
    ]);
    let claimed = db
        .claim_next_job_with_pool("slot-0", 100, None, &[100])
        .await
        .expect("claim ok");
    let (job, pid) = claimed.expect("expected claim");
    assert_eq!(job.name, "free", "pinned-but-blocked must be skipped");
    assert_eq!(pid, 100);
}

#[tokio::test]
async fn returns_none_when_nothing_to_claim() {
    let (_tmp, db) = seed_db(&[("done_one", "done", None), ("running_one", "running", None)]);
    let claimed = db
        .claim_next_job_with_pool("slot-0", 100, None, &[100])
        .await
        .expect("claim ok");
    assert!(claimed.is_none());
}

#[tokio::test]
async fn name_prefix_filter_with_quote_is_safe() {
    // Regression: name_prefix was string-interpolated into the LIKE clause.
    // A quote in the prefix would break SQL parse and crash the tx. Now
    // bound via ?1 — verify it returns Ok with no claim instead.
    let (_tmp, db) = seed_db(&[("q1", "queued", None)]);
    let claimed = db
        .claim_next_job_with_pool("slot-0", 100, Some("foo'bar"), &[100])
        .await
        .expect("must not panic on quote-in-prefix");
    assert!(claimed.is_none());
}

#[tokio::test]
async fn blocked_pins_do_not_starve_work_after_twenty_candidates() {
    let (_tmp, db) = seed_db(&[("running", "running", Some(42))]);
    db.call(|conn| {
        for i in 0..25 {
            conn.execute(
                "INSERT INTO backtest_queue(name,code,project_id) VALUES (?1,'pass',42)",
                [format!("blocked-{i}")],
            )?;
        }
        conn.execute(
            "INSERT INTO backtest_queue(name,code) VALUES ('ready','pass')",
            [],
        )?;
        Ok(())
    })
    .await
    .unwrap();
    let (job, _) = db
        .claim_next_job_with_pool("slot-0", 100, None, &[100])
        .await
        .unwrap()
        .unwrap();
    assert_eq!(job.name, "ready");
}
