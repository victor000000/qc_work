use super::*;

async fn fixture() -> (tempfile::TempDir, Db) {
    let temp = tempfile::tempdir().unwrap();
    let path = crate::db::initialize_strategy(temp.path(), "stest").unwrap();
    let db = Db::open(&path, "stest").unwrap();
    db.call(|conn| {
        conn.execute("INSERT INTO backtest_queue(name,code,status,project_id,compile_id,backtest_id) VALUES ('job','pass','running',42,'cid','bid')", [])?;
        Ok(())
    }).await.unwrap();
    (temp, db)
}

#[tokio::test]
async fn rejected_cloud_read_preserves_running_identity() {
    let (_temp, db) = fixture().await;
    let (client, server) = crate::client::test_support::mock_api(vec![(
        "/backtests/read",
        r#"{"success":false,"errors":["permission denied"]}"#,
    )])
    .await;
    assert!(
        recover_one_job(&client, &db, 1, "job".into(), Some("bid".into()), Some(42))
            .await
            .is_err()
    );
    server.await.unwrap();
    let row: (String, String) = db
        .call(|conn| {
            Ok(
                conn.query_row("SELECT status,backtest_id FROM backtest_queue", [], |r| {
                    Ok((r.get(0)?, r.get(1)?))
                })?,
            )
        })
        .await
        .unwrap();
    assert_eq!(row, ("running".into(), "bid".into()));
}

#[tokio::test]
async fn failed_collection_preserves_completed_cloud_result_for_later_recovery() {
    let (_temp, db) = fixture().await;
    db.call(|conn| { conn.execute_batch("DROP INDEX idx_queue_status_priority; ALTER TABLE backtest_queue RENAME TO preserved_queue; CREATE VIEW backtest_queue AS SELECT * FROM preserved_queue;")?; Ok(()) }).await.unwrap();
    let (client, server) = crate::client::test_support::mock_api(vec![(
        "/backtests/read",
        r#"{"success":true,"backtest":{"completed":true,"statistics":{"Total Orders":"1"}}}"#,
    )])
    .await;
    let recovered = tokio::time::timeout(
        std::time::Duration::from_secs(1),
        recover_one_job(&client, &db, 1, "job".into(), Some("bid".into()), Some(42)),
    )
    .await
    .unwrap();
    assert!(recovered.is_err());
    server.await.unwrap();
    assert_eq!(
        db.queue_counts().await.unwrap(),
        vec![("running".into(), 1)]
    );
}

#[tokio::test]
async fn failed_cloud_cancellation_does_not_schedule_a_duplicate() {
    let (_temp, db) = fixture().await;
    let (client, server) = crate::client::test_support::mock_api(vec![
        (
            "/backtests/read",
            r#"{"success":true,"backtest":{"completed":false}}"#,
        ),
        (
            "/backtests/delete",
            r#"{"success":false,"errors":["busy; retry later"]}"#,
        ),
    ])
    .await;
    assert!(
        recover_one_job(&client, &db, 1, "job".into(), Some("bid".into()), Some(42))
            .await
            .is_err()
    );
    server.await.unwrap();
    assert_eq!(
        db.queue_counts().await.unwrap(),
        vec![("running".into(), 1)]
    );
}

#[tokio::test]
async fn cancellation_requeues_without_losing_explicit_project_pin() {
    let (_temp, db) = fixture().await;
    db.call(|conn| {
        conn.execute("UPDATE backtest_queue SET requested_project_id=42", [])?;
        Ok(())
    })
    .await
    .unwrap();
    let (client, server) = crate::client::test_support::mock_api(vec![
        (
            "/backtests/read",
            r#"{"success":true,"backtest":{"completed":false}}"#,
        ),
        ("/backtests/delete", r#"{"success":true}"#),
    ])
    .await;
    recover_one_job(&client, &db, 1, "job".into(), Some("bid".into()), Some(42))
        .await
        .unwrap();
    server.await.unwrap();
    let (job, pid) = db
        .claim_next_job_with_pool("test", 43, None, &[42, 43])
        .await
        .unwrap()
        .unwrap();
    assert_eq!(pid, 42);
    assert_eq!(job.requested_project_id, Some(42));
}
