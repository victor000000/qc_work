//! Reconcile dedicated compute-project sources with the queued job's file set.

use crate::client::QcClient;
use crate::rate_limit::{RateLimitState, retry_on_rate_limit};
use std::collections::HashMap;

pub(super) async fn remove_stale_files(
    client: &QcClient,
    state: Option<&RateLimitState>,
    project_id: i64,
    extras: &HashMap<String, String>,
) -> anyhow::Result<()> {
    let response = retry_on_rate_limit(state, 3, || client.read_files(project_id, None)).await?;
    anyhow::ensure!(
        response.success,
        "file listing failed: {:?}",
        response.errors
    );
    for file in response.files {
        // Attached libraries belong to the project configuration, not job uploads.
        if file.is_library || file.name == "main.py" || extras.contains_key(&file.name) {
            continue;
        }
        let deleted =
            retry_on_rate_limit(state, 3, || client.delete_file(project_id, &file.name)).await?;
        anyhow::ensure!(
            deleted.success,
            "stale file deletion failed: {:?}",
            deleted.errors
        );
    }
    Ok(())
}
