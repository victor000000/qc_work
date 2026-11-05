//! Queue enqueue command.
//!
//! Sub-modules:
//! - `cmd_cancel.rs`: cancel, `cancel_all`
//! - `cmd_clean.rs`: clean
//! - `cmd_manage.rs`: retry

use std::path::Path;

use anyhow::Result;

use super::cmd_dup_check::{check_no_duplicate_name, warn_on_duplicate_hash};
use super::open_db;

/// Bundled input for the `enqueue` command.
pub struct QueueCmdInput<'a> {
    pub data_dir: &'a Path,
    pub strategy: &'a str,
    pub name: &'a str,
    pub code: &'a str,
    pub extra_files: Option<&'a str>,
    pub batch: Option<&'a str>,
    pub priority: i64,
    pub description: Option<&'a str>,
    pub hypothesis: Option<&'a str>,
    pub based_on: Option<&'a str>,
    pub project_id: Option<i64>,
}

/// Enqueue a backtest job.
///
/// # Errors
/// Returns `Err` on SQL execution error or if the job name already exists.
pub async fn enqueue(input: QueueCmdInput<'_>) -> Result<()> {
    let db = open_db(input.data_dir, input.strategy)?;
    let validation_job = crate::db::QueueJob {
        id: 0,
        name: input.name.to_string(),
        code: input.code.to_string(),
        extra_files: input.extra_files.map(str::to_owned),
        description: None,
        hypothesis: None,
        based_on: None,
        batch: None,
        requested_project_id: input.project_id,
        priority: input.priority,
        strategy: input.strategy.to_string(),
    };
    validation_job.validated_extra_files()?;
    anyhow::ensure!(
        input.project_id.is_none_or(|id| id > 0),
        "project ID must be positive"
    );
    anyhow::ensure!(input.code.len() <= 128_000, "main.py exceeds size limit");
    let hash = validation_job.content_hash()?;

    check_no_duplicate_name(&db, input.strategy, input.name).await?;
    warn_on_duplicate_hash(&db, &hash).await?;

    let name = input.name.to_string();
    let code = input.code.to_string();
    let extra_files = input.extra_files.map(str::to_owned);
    let batch = input.batch.map(std::string::ToString::to_string);
    let desc = input.description.map(std::string::ToString::to_string);
    let hyp = input.hypothesis.map(std::string::ToString::to_string);
    let based = input.based_on.map(std::string::ToString::to_string);
    let priority = input.priority;
    let project_id = input.project_id;
    let hash_insert = hash;

    db.call(move |conn| {
        conn.execute(
            "INSERT INTO backtest_queue \
             (name, code, code_hash, batch, priority, \
              description, hypothesis, based_on, status, \
              project_id, extra_files, requested_project_id)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8,'queued',?9,?10,?9)",
            duckdb::params![
                name,
                code,
                hash_insert,
                batch,
                priority,
                desc,
                hyp,
                based,
                project_id,
                extra_files
            ],
        )?;
        Ok(())
    })
    .await?;

    let pid_msg = project_id
        .map(|p| format!(" project={p}"))
        .unwrap_or_default();
    println!(
        "queued {}/{} (priority={priority}{pid_msg})",
        input.strategy, input.name
    );
    Ok(())
}
