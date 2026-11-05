//! Warm pool helpers: push code, compile, poll compile status.

mod compile;
mod reconcile;
mod syntax;
#[cfg(test)]
mod tests;

pub(crate) use compile::{compile_code, poll_compile};
pub(crate) use syntax::local_syntax_check;

use crate::client::QcClient;
use crate::db::QueueJob;
use crate::rate_limit::{RateLimitState, retry_on_rate_limit};

/// Upload a job's project files to QC: `main.py` (from `job.code`) first, then
/// every entry of `job.extra_files` (sorted for stable logs). The single shared
/// upload path used by BOTH the warm pool and the runner slot, so the two can
/// never diverge. For single-file strategies (s001/s002) `extra_files` is empty,
/// so this is exactly the old "push main.py" behaviour.
///
/// # Errors
/// Returns `Err` if any file upload transport-fails or QC reports `!success`.
pub(crate) async fn push_files(
    client: &QcClient,
    rl_state: Option<&RateLimitState>,
    project_id: i64,
    job: &QueueJob,
    job_name: &str,
) -> anyhow::Result<()> {
    let extras = job.validated_extra_files()?;
    reconcile::remove_stale_files(client, rl_state, project_id, &extras).await?;
    let main = retry_on_rate_limit(rl_state, 3, || {
        client.update_file_contents(project_id, "main.py", &job.code)
    })
    .await?;
    if !main.success {
        anyhow::bail!("push_failed main.py: {:?}", main.errors);
    }

    if !extras.is_empty() {
        let mut names: Vec<&String> = extras.keys().collect();
        names.sort(); // deterministic upload order for reproducible logs
        for name in names {
            // never let an extra file shadow main.py (it is pushed from job.code)
            if name == "main.py" {
                continue;
            }
            let content = &extras[name];
            // QC's /files/update only UPDATES an existing file ("File not found" for a
            // brand-new one), so create-then-update is exists-safe: create seeds the file
            // (or errors harmlessly if it already lingers from a prior job on this shared
            // project), update then sets the authoritative content. Mirrors SML01's
            // historical direct-QC client.
            let _ = retry_on_rate_limit(rl_state, 3, || {
                client.create_file(project_id, name, Some(content))
            })
            .await; // best-effort: an "already exists" create is expected and ignored
            let r = retry_on_rate_limit(rl_state, 3, || {
                client.update_file_contents(project_id, name, content)
            })
            .await?;
            if !r.success {
                anyhow::bail!("push_failed extra file {name}: {:?}", r.errors);
            }
        }
        tracing::debug!(
            "pushed {} extra file(s) for {job_name} to project {project_id}",
            extras.len()
        );
    }
    Ok(())
}

pub(crate) async fn push_code(
    client: &QcClient,
    rl_state: Option<&RateLimitState>,
    project_id: i64,
    job: &QueueJob,
    job_name: &str,
) -> Result<(), ()> {
    match push_files(client, rl_state, project_id, job, job_name).await {
        Ok(()) => {
            tracing::debug!("warm-pool: pushed {job_name} to project {project_id}");
            Ok(())
        }
        Err(e) => {
            tracing::warn!("warm-pool: push failed for {job_name}: {e} — requeuing");
            Err(())
        }
    }
}
