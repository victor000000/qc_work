//! Explicit cloud smoke test. Creates and deletes only its own temporary project.
//! cargo test --test live_qc -- --ignored --nocapture
#[path = "support/live_cleanup.rs"]
mod live_cleanup;
use anyhow::{Context, Result, ensure};
use qc::client::QcClient;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const CODE: &str = "from AlgorithmImports import *\nclass Smoke(QCAlgorithm):\n def initialize(self):\n  self.set_start_date(2024, 1, 2)\n  self.set_end_date(2024, 1, 5)\n  self.set_cash(100000)\n  self.add_equity('SPY', Resolution.DAILY)\n def on_data(self, data):\n  if not self.portfolio.invested:\n   self.set_holdings('SPY', 0.1)\n";

#[tokio::test]
#[ignore = "requires QC credentials and consumes cloud backtest compute"]
async fn real_qc_compile_backtest_collect_and_cleanup() -> Result<()> {
    let data_dir = std::env::var_os("QC_DATA_DIR").map_or_else(
        || std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data"),
        std::path::PathBuf::from,
    );
    let db = qc::db::Db::open(&data_dir.join("S001.duckdb"), "s001")?;
    let user = db.get_setting_required("credentials", "qc_user_id").await?;
    let token = db
        .get_setting_required("credentials", "qc_api_token")
        .await?;
    let org = db
        .get_setting_required("project", "organization_id")
        .await?;
    let client = QcClient::new(user, token);
    ensure!(
        client.authenticate().await?.success,
        "authentication rejected"
    );
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let created = client
        .create_project(&format!("qc-work-smoke-{stamp}"), "Py", Some(&org))
        .await?;
    ensure!(
        created.success,
        "project creation rejected: {:?}",
        created.errors
    );
    let project = created
        .projects
        .first()
        .context("no created project")?
        .project_id;
    live_cleanup::record(project, &created.projects[0].name)?;
    println!("created isolated smoke project {project}");
    let outcome = tokio::time::timeout(Duration::from_mins(8), exercise(&client, project)).await;
    let cleanup = client.delete_project(project).await?;
    ensure!(
        cleanup.success,
        "cleanup failed for project {project}: {:?}",
        cleanup.errors
    );
    live_cleanup::cleared(project)?;
    println!("deleted smoke project {project}");
    outcome.context("live test exceeded 8 minute limit")??;
    Ok(())
}

async fn exercise(client: &QcClient, project: i64) -> Result<()> {
    let pushed = client
        .update_file_contents(project, "main.py", CODE)
        .await?;
    ensure!(pushed.success, "upload rejected: {:?}", pushed.errors);
    let compiled = client.create_compile(project).await?;
    ensure!(
        compiled.success,
        "compile creation rejected: {:?}",
        compiled.errors
    );
    loop {
        let state = client.read_compile(project, &compiled.compile_id).await?;
        ensure!(
            state.success && state.state != "BuildError",
            "compile failed: {:?}",
            state.logs
        );
        if state.state == "BuildSuccess" {
            break;
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
    let created = client
        .create_backtest(project, &compiled.compile_id, "isolated-smoke", None)
        .await?;
    ensure!(created.success, "backtest rejected: {:?}", created.errors);
    let bid = created.backtest.context("no created backtest")?.backtest_id;
    println!("launched smoke backtest {bid}");
    let started = Instant::now();
    let response = loop {
        let response = client.read_backtest(project, &bid).await?;
        ensure!(
            response.success,
            "backtest read rejected: {:?}",
            response.errors
        );
        let result = response.backtest.as_ref().context("no backtest response")?;
        ensure!(
            result.error.as_deref().is_none_or(str::is_empty),
            "runtime error: {:?}",
            result.error
        );
        if result.completed && result.statistics.contains_key("Total Orders") {
            break response;
        }
        tokio::time::sleep(Duration::from_secs(3)).await;
    };
    let temp = tempfile::tempdir()?;
    let path = qc::db::initialize_strategy(temp.path(), "ssmoke")?;
    let local = qc::db::Db::open(&path, "ssmoke")?;
    let code = CODE.to_string();
    local
        .call(move |conn| {
            conn.execute(
                "INSERT INTO backtest_queue(name,code,status) VALUES ('smoke',?1,'queued')",
                [&code],
            )?;
            Ok(())
        })
        .await?;
    let (job, _) = local
        .claim_next_job_with_pool("smoke", project, None, &[project])
        .await?
        .context("no smoke job")?;
    qc::runner::collect::collect_from_response(
        client,
        &job,
        &local,
        project,
        &bid,
        started.elapsed().as_secs_f64(),
        response,
    )
    .await?;
    local
        .call(|conn| {
            let status: String =
                conn.query_row("SELECT status FROM backtest_queue", [], |row| row.get(0))?;
            ensure!(status == "done", "collection did not mark done");
            let count: i64 =
                conn.query_row("SELECT COUNT(*) FROM experiments", [], |row| row.get(0))?;
            ensure!(count == 1, "collection did not persist experiment");
            Ok(())
        })
        .await?;
    println!("real QC compilation, execution and DuckDB result collection passed");
    Ok(())
}
