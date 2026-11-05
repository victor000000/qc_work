use qc::db::{Db, Experiment, initialize_strategy};

#[tokio::test]
async fn failed_queue_transition_rolls_back_experiment_insert() {
    let dir = tempfile::tempdir().unwrap();
    let path = initialize_strategy(dir.path(), "stx").unwrap();
    let db = Db::open(&path, "stx").unwrap();
    db.call(|conn| {
        conn.execute("INSERT INTO backtest_queue(name,code,status) VALUES ('job','pass','running')", [])?;
        conn.execute_batch("DROP INDEX idx_queue_status_priority; ALTER TABLE backtest_queue RENAME TO preserved_queue; CREATE VIEW backtest_queue AS SELECT * FROM preserved_queue;")?;
        Ok(())
    }).await.unwrap();
    let exp = Experiment {
        name: "job".into(),
        status: "success".into(),
        ..Experiment::default()
    };
    assert!(db.store_completed(1, exp, "bt", 1.0, "{}").await.is_err());
    db.call(|conn| {
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM experiments", [], |r| r
                .get::<_, i64>(0))?,
            0
        );
        assert_eq!(
            conn.query_row("SELECT status FROM backtest_queue", [], |r| r
                .get::<_, String>(0))?,
            "running"
        );
        Ok(())
    })
    .await
    .unwrap();
}

#[tokio::test]
async fn refreshing_metrics_preserves_experiment_id_and_research_notes() {
    let dir = tempfile::tempdir().unwrap();
    let path = initialize_strategy(dir.path(), "stx").unwrap();
    let db = Db::open(&path, "stx").unwrap();
    db.call(|conn| {
        conn.execute("INSERT INTO experiments(id,name,notes,created_at) VALUES (77,'job','important research annotation','original-time')", [])?;
        conn.execute("INSERT INTO backtest_queue(name,code,status,compile_id) VALUES ('job','pass','running','cid')", [])?;
        Ok(())
    }).await.unwrap();
    let exp = Experiment {
        name: "job".into(),
        status: "success".into(),
        car_mdd: Some(1.25),
        ..Experiment::default()
    };
    db.store_completed(1, exp, "bt", 1.0, "{}").await.unwrap();
    db.call(|conn| {
        let stored: (i64, String, String, f64) = conn.query_row(
            "SELECT id,notes,created_at,car_mdd FROM experiments",
            [],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )?;
        assert_eq!(
            stored,
            (
                77,
                "important research annotation".into(),
                "original-time".into(),
                1.25
            )
        );
        assert_eq!(
            conn.query_row("SELECT compile_id FROM backtest_queue", [], |r| r
                .get::<_, String>(0))?,
            "cid"
        );
        Ok(())
    })
    .await
    .unwrap();
}
