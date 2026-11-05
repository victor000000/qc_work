//! Durable ownership records make cleanup resumable after network/process failures.
use std::path::PathBuf;

fn record_path(project: i64) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!(
        "../../.local/verification/pending-cloud/{project}.json"
    ))
}

pub fn record(project: i64, name: &str) -> anyhow::Result<()> {
    let path = record_path(project);
    std::fs::create_dir_all(path.parent().unwrap())?;
    std::fs::write(
        path,
        serde_json::to_vec_pretty(&serde_json::json!({"project_id":project,"name":name}))?,
    )?;
    Ok(())
}

pub fn cleared(project: i64) -> anyhow::Result<()> {
    match std::fs::remove_file(record_path(project)) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}
