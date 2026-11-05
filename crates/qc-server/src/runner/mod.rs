//! `SlotRunner` — the core backtest execution unit.
//!
//! Struct + constructor in `slot_runner.rs`; behavior methods in the other
//! sibling modules (`acquire`, `backtest`, `collect`, `compile`, ...).

pub mod acquire;
pub mod acquire_pool;
pub mod backtest;
pub mod backtest_persist;
pub mod collect;
pub mod collect_parse;
pub mod collect_retry;
pub mod compile;
pub mod compile_poll;
pub mod errors;
pub mod lock;
pub mod lock_alt;
pub mod pick;
pub mod pick_claim;
pub mod pipeline;
pub mod poll;
pub mod poll_create;
pub mod queued_check;
pub mod run_loop;
pub mod slot_runner;

use std::collections::HashSet;
use std::sync::Arc;

use tokio::sync::Mutex;

/// Global lock tracking which project IDs currently have code pushed
/// but not yet backtested. Prevents two slots from pushing code to
/// the same project and overwriting each other.
pub type ProjectLock = Arc<Mutex<HashSet<i64>>>;

// Re-export so existing `crate::runner::RateLimitState` references keep working.
pub use crate::rate_limit::RateLimitState;
pub use slot_runner::{SlotRunner, SlotRunnerNew};
