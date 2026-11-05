//! Async poll+collect task launched by `run_loop` after `prep_backtest`.
//!
//! Responsibilities:
//! - Poll QC until backtest completes (or timeout)
//! - Parse results and store via `collect_from_response`
//! - `mark_done` / `mark_failed` on the queue row
//! - Emit `qc::pipeline` debug events capturing the lifecycle
//! - Manage `active_collects` counter via RAII guard
//!
//! Does NOT hold the project lock. Uses `(project_id, backtest_id)` only.

mod cleanup;
mod collect_phase;
mod ctx;
mod guard;
mod handlers;
mod handlers_err;
mod transient;

pub(crate) use cleanup::cancel_qc_backtest;
pub(crate) use collect_phase::spawn_poll_and_collect;
pub(crate) use ctx::PollCollectCtx;
