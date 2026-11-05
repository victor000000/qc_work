//! Resolve a strategy's project IDs from shared `projects.json` or legacy
//! per-DB `cloud_project_id[_N]` settings. Empty result keeps the DB around
//! for credential-only commands like `create-projects`.

use anyhow::Result;

use crate::db::Db;

pub(super) async fn resolve_project_ids(db: &Db, name: &str, shared: &[i64]) -> Result<Vec<i64>> {
    if !shared.is_empty() {
        return Ok(shared.to_vec());
    }
    let mut pids = Vec::new();
    if let Some(v) = db.get_setting("project", "cloud_project_id").await?
        && let Ok(id) = v.parse::<i64>()
    {
        pids.push(id);
    }
    for n in 2..=20 {
        if let Some(v) = db
            .get_setting("project", &format!("cloud_project_id_{n}"))
            .await?
            && let Ok(id) = v.parse::<i64>()
        {
            pids.push(id);
        }
    }
    if pids.is_empty() {
        tracing::warn!("{name}: no project IDs (strategy disabled, db kept for credentials)");
    }
    Ok(pids)
}
