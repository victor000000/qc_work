//! Full shared-server smoke test; two strategy queues, one disposable QC project.
#[path = "support/live_cleanup.rs"]
mod live_cleanup;
use anyhow::{Context, Result, ensure};
use qc::client::QcClient;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

#[tokio::test]
#[ignore = "explicit QC server test; uses private credentials and cloud compute"]
async fn shared_server_isolates_two_strategies_and_shuts_down() -> Result<()> {
    let data = std::env::var_os("QC_DATA_DIR").map_or_else(
        || std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data"),
        std::path::PathBuf::from,
    );
    let source = qc::db::Db::open(&data.join("S001.duckdb"), "s001")?;
    let user = std::env::var("QC_USER_ID")?;
    let token = std::env::var("QC_API_TOKEN")?;
    let org = source
        .get_setting_required("project", "organization_id")
        .await?;
    let client = QcClient::new(&user, &token);
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let response = client
        .create_project(&format!("qc-server-smoke-{stamp}"), "Py", Some(&org))
        .await?;
    ensure!(response.success, "create project: {:?}", response.errors);
    let pid = response
        .projects
        .first()
        .context("created project missing")?
        .project_id;
    live_cleanup::record(pid, &response.projects[0].name)?;
    println!("created isolated server-test project {pid}");
    let temp = tempfile::tempdir()?;
    let mut child = None;
    let outcome = tokio::time::timeout(Duration::from_mins(8), async {
        let alpha = qc::db::initialize_strategy(temp.path(), "salpha")?;
        let beta = qc::db::initialize_strategy(temp.path(), "sbeta")?;
        let late = qc::db::initialize_strategy(temp.path(), "slate")?;
        let conn = duckdb::Connection::open(&alpha)?;
        conn.execute("INSERT OR REPLACE INTO settings(category,key,value) VALUES ('project','organization_id',?1)", [&org])?;
        std::fs::write(temp.path().join("projects.json"), serde_json::to_vec(&serde_json::json!({"projects": [pid]}))?)?;
        let common = "from AlgorithmImports import *\nclass Smoke(QCAlgorithm):\n def initialize(self):\n  self.set_start_date(2024,1,2)\n  self.set_end_date(2024,1,5)\n  self.set_cash(100000)\n  self.add_equity('SPY',Resolution.DAILY)\n";
        let alpha_code = format!("import qc_work_isolation_probe_58f2c\n{common}  assert qc_work_isolation_probe_58f2c.VALUE == 42\n def on_data(self,data):\n  if not self.portfolio.invested: self.set_holdings('SPY',0.1)\n");
        conn.execute("INSERT INTO backtest_queue(name,code,extra_files) VALUES ('alpha',?1,?2)", duckdb::params![alpha_code, r#"{"qc_work_isolation_probe_58f2c.py":"VALUE = 42"}"#])?;
        drop(conn);
        child = Some(Command::new(env!("CARGO_BIN_EXE_qc-backtest-server"))
            .arg("--data-dir").arg(temp.path()).arg("serve")
            .env_remove("QC_DATA_DIR").env("QC_USER_ID", &user).env("QC_API_TOKEN", &token).env_remove("QC_ORGANIZATION_ID")
            .stdout(Stdio::null()).stderr(Stdio::from(std::fs::File::create(temp.path().join("server.stderr"))?)).spawn()?);
        wait_done(&alpha, child.as_mut().unwrap()).await?;
        println!("strategy alpha: done with uploaded qc_work_isolation_probe_58f2c.py");
        let beta_code = format!("{common}  try:\n   import qc_work_isolation_probe_58f2c\n  except ImportError:\n   pass\n  else:\n   raise Exception('stale qc_work_isolation_probe_58f2c leaked across strategies')\n def on_data(self,data):\n  if not self.portfolio.invested: self.set_holdings('SPY',0.1)\n");
        qc::db::Db::open(&beta, "sbeta")?.call(move |conn| { conn.execute("INSERT INTO backtest_queue(name,code) VALUES ('beta',?1)", [&beta_code])?; Ok(()) }).await?;
        wait_done(&beta, child.as_mut().unwrap()).await?;
        println!("strategy beta: done; prior strategy qc_work_isolation_probe_58f2c was removed");
        let late_code = format!("{common} def on_end_of_algorithm(self):\n  raise RuntimeError('late end-of-algorithm failure')\n");
        qc::db::Db::open(&late, "slate")?.call(move |conn| { conn.execute("INSERT INTO backtest_queue(name,code) VALUES ('late_error',?1)", [&late_code])?; Ok(()) }).await?;
        wait_failed(&late, child.as_mut().unwrap()).await?;
        println!("late end-of-algorithm error: failed queue row, no successful experiment");
        Ok::<(), anyhow::Error>(())
    }).await;
    let stopped = match child.as_mut() {
        Some(child) => stop_server(child).await,
        None => Ok(()),
    };
    // Diagnostics are optional: failure must never bypass cloud cleanup.
    let manifest: Vec<_> = match client.read_files(pid, None).await {
        Ok(files) => files
            .files
            .iter()
            .map(|file| serde_json::json!({"name":file.name,"isLibrary":file.is_library}))
            .collect(),
        Err(error) => vec![serde_json::json!({"diagnostic_error":error.to_string()})],
    };
    let cleanup = client.delete_project(pid).await;
    println!("QC source manifest at shutdown: {manifest:?}");
    let artifacts = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join(format!("../../.local/verification/live-server-{pid}"));
    std::fs::create_dir_all(&artifacts)?;
    std::fs::write(
        artifacts.join("manifest.json"),
        serde_json::to_vec_pretty(&manifest)?,
    )?;
    for directory in [temp.path().to_path_buf(), temp.path().join("logs")] {
        for entry in std::fs::read_dir(directory).into_iter().flatten().flatten() {
            if entry.file_type()?.is_file()
                && (entry.file_name().to_string_lossy().starts_with("qc")
                    || entry.file_name() == "server.stderr")
            {
                let _ = std::fs::copy(entry.path(), artifacts.join(entry.file_name()));
            }
        }
    }
    let cleanup = cleanup?;
    ensure!(
        cleanup.success,
        "delete temporary project {pid}: {:?}",
        cleanup.errors
    );
    live_cleanup::cleared(pid)?;
    println!("deleted isolated server-test project {pid}");
    if !matches!(&outcome, Ok(Ok(()))) {
        eprintln!(
            "{}",
            std::fs::read_to_string(temp.path().join("server.stderr")).unwrap_or_default()
        );
        for entry in std::fs::read_dir(temp.path().join("logs"))
            .into_iter()
            .flatten()
            .flatten()
        {
            if entry.file_name().to_string_lossy().starts_with("qc.log") {
                let log = std::fs::read_to_string(entry.path()).unwrap_or_default();
                eprintln!(
                    "{}",
                    log.lines()
                        .rev()
                        .take(20)
                        .collect::<Vec<_>>()
                        .into_iter()
                        .rev()
                        .collect::<Vec<_>>()
                        .join("\n")
                );
            }
        }
    }
    outcome.context("shared server test exceeded eight minutes")??;
    stopped?;
    Ok(())
}

async fn wait_done(path: &std::path::Path, child: &mut Child) -> Result<()> {
    let db = qc::db::Db::open(path, "stest")?;
    loop {
        ensure!(
            child.try_wait()?.is_none(),
            "server exited before collecting result"
        );
        let (status, error, result, count): (String, Option<String>, Option<String>, i64) = db
            .call(|conn| {
                let (status, error, result) = conn.query_row(
                    "SELECT status,error_message,result_json FROM backtest_queue LIMIT 1",
                    [],
                    |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
                )?;
                let count = conn.query_row("SELECT COUNT(*) FROM experiments", [], |r| r.get(0))?;
                Ok((status, error, result, count))
            })
            .await?;
        ensure!(status != "failed", "job failed: {error:?}");
        if status == "done" {
            ensure!(result.is_some(), "raw result missing");
            ensure!(count == 1, "experiment missing");
            return Ok(());
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}

async fn wait_failed(path: &std::path::Path, child: &mut Child) -> Result<()> {
    let db = qc::db::Db::open(path, "stest")?;
    loop {
        ensure!(
            child.try_wait()?.is_none(),
            "server exited before error collection"
        );
        let (status, error, count): (String, Option<String>, i64) = db
            .call(|conn| {
                let (status, error) = conn.query_row(
                    "SELECT status,error_message FROM backtest_queue LIMIT 1",
                    [],
                    |row| Ok((row.get(0)?, row.get(1)?)),
                )?;
                let count = conn.query_row("SELECT COUNT(*) FROM experiments", [], |r| r.get(0))?;
                Ok((status, error, count))
            })
            .await?;
        ensure!(
            status != "done",
            "end-of-algorithm error was accepted as completed"
        );
        if status == "failed" {
            ensure!(
                error
                    .unwrap_or_default()
                    .contains("late end-of-algorithm failure"),
                "unexpected failure"
            );
            ensure!(count == 0, "failed backtest stored as an experiment");
            return Ok(());
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
}

async fn stop_server(child: &mut Child) -> Result<()> {
    if let Some(status) = child.try_wait()? {
        ensure!(status.success(), "server exited early: {status}");
        return Ok(());
    }
    #[cfg(unix)]
    {
        Command::new("kill")
            .arg("-TERM")
            .arg(child.id().to_string())
            .status()?;
    }
    #[cfg(not(unix))]
    {
        child.kill()?;
    }
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        if let Some(status) = child.try_wait()? {
            ensure!(status.success(), "server shutdown failed: {status}");
            return Ok(());
        }
        if Instant::now() > deadline {
            child.kill()?;
            child.wait()?;
            anyhow::bail!("graceful shutdown did not finish in 15 seconds");
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
}
