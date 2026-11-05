//! Pre-push validation: file-size cap + local syntax check.
//!
//! Returns `true` if the job is OK to push; returns `false` after marking
//! the job terminally failed and releasing the project lock.

use crate::db::{Db, QueueJob};
use crate::pool::push::local_syntax_check;
use crate::runner::ProjectLock;

const QC_FILE_MAX: usize = 128_000;

pub(super) async fn pre_push_validate(
    job: &QueueJob,
    db: &Db,
    project_lock: &ProjectLock,
    project_id: i64,
    job_name: &str,
) -> bool {
    if let Err(error) = job.validated_extra_files() {
        let _ = db
            .mark_failed(job.id, &format!("invalid extra_files: {error}"), None)
            .await;
        project_lock.lock().await.remove(&project_id);
        return false;
    }
    // Local size pre-check — QC rejects files > 128_000 chars. Pushing them
    // anyway burns API calls AND warmer requeues silently → infinite retry
    // loop (230+ retries observed today). Mark terminally failed.
    if job.code.len() > QC_FILE_MAX {
        let used = job.code.len();
        tracing::warn!(
            "warm-pool: {job_name} exceeds QC max file size \
             ({used} > {QC_FILE_MAX}), marking failed"
        );
        let _ = db
            .mark_failed(
                job.id,
                &format!(
                    "push_failed: [\"File exceeds the maximum size of \
                     {QC_FILE_MAX} characters by using {used}.\"]"
                ),
                None,
            )
            .await;
        project_lock.lock().await.remove(&project_id);
        return false;
    }

    // Local syntax check catches IndentationError/SyntaxError before a QC roundtrip.
    if let Err(err) = local_syntax_check(&job.code, job_name).await {
        tracing::warn!("warm-pool: local syntax check failed for {job_name}, marking failed");
        let _ = db
            .mark_failed(
                job.id,
                &format!(
                    "warmpool_compile_error: [\"local: {}\"]",
                    err.chars().take(200).collect::<String>()
                ),
                None,
            )
            .await;
        project_lock.lock().await.remove(&project_id);
        return false;
    }
    true
}
