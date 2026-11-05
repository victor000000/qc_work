use qc::config::StrategyConfig;
use qc::db::{Db, initialize_strategy};
use qc::runner::{SlotRunner, SlotRunnerNew};
use std::sync::Arc;

#[test]
fn new_strategies_have_independent_queues_and_complete_schema() {
    let dir = tempfile::tempdir().unwrap();
    for strategy in ["salpha", "sbeta"] {
        let path = initialize_strategy(dir.path(), strategy).unwrap();
        let conn = duckdb::Connection::open(path).unwrap();
        conn.execute(
            "INSERT INTO backtest_queue(name,code) VALUES ('same-name','pass')",
            [],
        )
        .unwrap();
        assert!(
            conn.prepare("SELECT extra_files,result_json FROM backtest_queue")
                .is_ok()
        );
        assert!(
            conn.prepare("SELECT car_mdd,project_id FROM experiments")
                .is_ok()
        );
        initialize_strategy(dir.path(), strategy).unwrap();
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM backtest_queue", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            1
        );
    }
    assert!(initialize_strategy(dir.path(), "../escape").is_err());
}

#[test]
fn scheduler_matches_active_strategies_by_name_after_disabled_db() {
    let dir = tempfile::tempdir().unwrap();
    let disabled = initialize_strategy(dir.path(), "sdisabled").unwrap();
    let active = initialize_strategy(dir.path(), "sactive").unwrap();
    let runner = SlotRunner::new(SlotRunnerNew {
        slot_id: 0,
        client: Arc::new(qc::client::QcClient::new("test", "test")),
        dbs: vec![
            Db::open(&disabled, "sdisabled").unwrap(),
            Db::open(&active, "sactive").unwrap(),
        ],
        strategies: vec![StrategyConfig {
            name: "sactive".into(),
            db_path: active,
            project_ids: vec![42],
            weight: 1.0,
        }],
        name_prefix: None,
        rl_state: None,
        session: None,
        project_lock: qc::runner::ProjectLock::default(),
        num_slots: 1,
    });
    assert_eq!(runner.dbs.len(), 1);
    assert_eq!(runner.dbs[0].strategy, runner.strategies[0].name);
}

#[tokio::test]
async fn retry_removes_previous_run_results_and_identity() {
    let dir = tempfile::tempdir().unwrap();
    let path = initialize_strategy(dir.path(), "sretry").unwrap();
    let db = Db::open(&path, "sretry").unwrap();
    db.call(|conn| {
        conn.execute("INSERT INTO backtest_queue(name,code,status,backtest_id,compile_id,node_id,runtime_seconds,completed_at,result_json) VALUES ('retry','pass','failed','old-bt','old-compile','old-node',9,'yesterday','{}')", [])?;
        Ok(())
    }).await.unwrap();
    qc::queue::retry(dir.path(), "sretry", Some("retry"), None)
        .await
        .unwrap();
    db.call(|conn| {
        let cleared: bool = conn.query_row("SELECT status='queued' AND backtest_id IS NULL AND compile_id IS NULL AND node_id IS NULL AND runtime_seconds IS NULL AND completed_at IS NULL AND result_json IS NULL FROM backtest_queue", [], |r| r.get(0))?;
        assert!(cleared);
        Ok(())
    }).await.unwrap();
}

#[test]
fn opening_legacy_queue_adds_execution_columns_without_losing_jobs() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("SLEGACY.duckdb");
    let conn = duckdb::Connection::open(&path).unwrap();
    conn.execute_batch("CREATE TABLE backtest_queue(id INTEGER PRIMARY KEY, name TEXT, code TEXT, status TEXT, priority INTEGER); INSERT INTO backtest_queue VALUES (1,'preserved','pass','queued',5);").unwrap();
    drop(conn);
    let _db = Db::open(&path, "slegacy").unwrap();
    let conn = duckdb::Connection::open(&path).unwrap();
    let original: String = conn
        .query_row("SELECT name FROM backtest_queue WHERE id=1", [], |r| {
            r.get(0)
        })
        .unwrap();
    assert_eq!(original, "preserved");
    assert!(
        conn.prepare("SELECT extra_files,result_json,project_id FROM backtest_queue")
            .is_ok()
    );
}
