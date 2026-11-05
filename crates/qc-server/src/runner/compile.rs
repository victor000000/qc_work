//! Push code to a QC project and kick off compilation.
//!
//! The follow-up `poll_compile` step lives in `compile_poll.rs`.

use std::time::Instant;

use anyhow::{Result, bail};
use tokio::time::Duration;

use super::SlotRunner;
use crate::db::QueueJob;
use crate::rate_limit::retry_on_rate_limit;

impl SlotRunner {
    /// Push code to a project and compile it.
    ///
    /// Returns `(compile_id, compile_duration, push_start, compile_start)`.
    /// If `pre_compile_id` is provided, skips push+compile entirely.
    pub(crate) async fn push_and_compile(
        &self,
        job: &QueueJob,
        project_id: i64,
        pre_compile_id: Option<String>,
        compile_poll: Duration,
        compile_timeout: Duration,
    ) -> Result<(String, Duration, Instant, Instant)> {
        let slot = self.slot_id;
        let job_name = &job.name;

        // Fast path: already pre-compiled by warm pool
        if let Some(pcid) = pre_compile_id {
            tracing::debug!("slot-{slot}: [{job_name}] using pre-compiled {pcid}");
            return Ok((pcid, Duration::ZERO, Instant::now(), Instant::now()));
        }

        // Safety: verify project is locked before pushing
        {
            let locked = self.project_lock.lock().await;
            if !locked.contains(&project_id) {
                tracing::error!(
                    "slot-{slot}: BUG — project {project_id} not locked \
                     before push for {job_name}!"
                );
                bail!("project_not_locked");
            }
        }

        tracing::debug!(
            "slot-{slot}: [{job_name}] pushing {} bytes (+{} extra files) to project {project_id}",
            job.code.len(),
            job.extra_files_map().len()
        );
        let push_start = Instant::now();

        // Shared upload path (main.py + any extra_files), identical to the warm pool.
        crate::pool::push::push_files(
            &self.client,
            self.rl_state.as_ref(),
            project_id,
            job,
            job_name,
        )
        .await?;
        tracing::debug!(
            "slot-{slot}: [{job_name}] push OK in {:.1}s",
            push_start.elapsed().as_secs_f64()
        );

        let compile_start = Instant::now();

        let compile = retry_on_rate_limit(self.rl_state.as_ref(), 3, || {
            self.client.create_compile(project_id)
        })
        .await?;

        if !compile.success {
            bail!("compile_create: {:?}", compile.errors);
        }

        let compile_id = compile.compile_id;
        tracing::debug!("slot-{slot}: [{job_name}] compile created: {compile_id}");

        let compile_dur = self
            .poll_compile(
                project_id,
                &compile_id,
                job_name,
                compile_poll,
                compile_timeout,
            )
            .await?;

        Ok((compile_id, compile_dur, push_start, compile_start))
    }
}
