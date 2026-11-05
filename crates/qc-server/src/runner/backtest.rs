//! Backtest orchestrator: coordinates push → compile → create.
//!
//! Sibling files:
//! - `compile.rs` / `compile_poll.rs`: push code + compile
//! - `poll_create.rs`: create backtest on QC
//! - `backtest_persist.rs`: post-create DB persistence + counter recording
//!
//! Polling and result collection happen asynchronously in
//! `pipeline::poll_and_collect` after the slot releases the project lock.

use anyhow::Result;
use tokio::time::Duration;

use super::SlotRunner;
use crate::db::{Db, QueueJob};

/// Bundled parameters for the prep half of the backtest pipeline.
/// (Poll/timeout values for the post-prep pipeline live in `PrepTimeouts` —
/// kept separate so this struct only holds what `prep_backtest` actually uses.)
pub(crate) struct BacktestParams<'a> {
    pub job: &'a QueueJob,
    pub db: &'a Db,
    pub project_id: i64,
    pub pre_compile_id: Option<String>,
    pub compile_poll: Duration,
    pub compile_timeout: Duration,
}

impl SlotRunner {
    /// Prep a backtest: push code (or skip if pre-compiled), compile,
    /// `create_backtest` on QC. Writes `backtest_id` to queue row.
    ///
    /// Holds the project lock throughout; caller must release after this returns.
    /// Does NOT poll or collect — those happen async in `pipeline::poll_and_collect`.
    ///
    /// Returns `(backtest_id, project_id, create_api_secs)`.
    pub(crate) async fn prep_backtest(
        &self,
        params: BacktestParams<'_>,
    ) -> Result<(String, i64, f64)> {
        let BacktestParams {
            job,
            db,
            project_id,
            pre_compile_id,
            compile_poll,
            compile_timeout,
        } = params;
        let slot = self.slot_id;
        let job_name = &job.name;

        tracing::debug!(
            target: "qc::pipeline",
            "slot-{slot}: prep_started project={project_id} job={job_name}"
        );

        let (compile_id, compile_phase_dur, push_start, compile_start) = self
            .push_and_compile(
                job,
                project_id,
                pre_compile_id,
                compile_poll,
                compile_timeout,
            )
            .await?;
        let push_secs = compile_start.duration_since(push_start).as_secs_f64();
        tracing::debug!(target: "qc::pipeline",
            "slot-{slot}: push_done project={project_id} elapsed={push_secs:.1}s");
        tracing::debug!(target: "qc::pipeline",
            "slot-{slot}: compile_done project={project_id} compile_id={compile_id} elapsed={:.1}s",
            compile_phase_dur.as_secs_f64());

        let (_bt_resp, backtest_id, bt_create_start) = self
            .create_backtest_on_qc(project_id, &compile_id, job)
            .await?;
        let create_api_secs = bt_create_start.elapsed().as_secs_f64();
        tracing::debug!(target: "qc::pipeline",
            "slot-{slot}: create_bt_done project={project_id} backtest_id={backtest_id} elapsed={create_api_secs:.1}s");

        if let Err(error) = super::backtest_persist::persist_and_record(
            self,
            db,
            job,
            &backtest_id,
            &compile_id,
            push_start,
            compile_start,
            compile_phase_dur,
            bt_create_start,
        )
        .await
        {
            crate::runner::pipeline::cancel_qc_backtest(
                &self.client,
                project_id,
                &backtest_id,
                slot,
                job_name,
                "persist",
            )
            .await;
            return Err(error.context("persisting created backtest identity"));
        }

        Ok((backtest_id, project_id, create_api_secs))
    }
}
