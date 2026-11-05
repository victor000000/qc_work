// Re-export all public items from submodules so callers keep using `queue::enqueue(...)` etc.
mod cmd;
mod cmd_cancel;
mod cmd_clean;
mod cmd_dup_check;
mod cmd_manage;
mod discovery;
mod display;
mod display_box;
mod display_context;
mod display_context_batch;
mod display_context_meta;
mod display_context_top;
mod display_detail;
mod display_detect;
mod display_fmt;
mod display_gather;
mod display_gather_helpers;
mod display_overhead;
mod display_show;
mod display_show_detail;
mod display_show_queue;
mod fmt_helpers;
mod query;
mod query_results;
mod query_results_detail;
mod query_sql;
mod query_top;

pub use cmd::{QueueCmdInput, enqueue};
pub use cmd_cancel::{cancel, cancel_all};
pub use cmd_clean::clean;
pub use cmd_manage::retry;
pub use display::status;
pub use display_context::context;
pub use display_detail::next_experiment_number;
pub use display_show::show;
pub use query::list;
pub use query_results::errors;
pub use query_top::top;

pub(crate) use discovery::{all_dbs, open_db, strategy_targets};
pub(crate) use fmt_helpers::{head_chars, tail_chars, truncate_name};

// -- Type aliases for complex DB row tuples (shared across submodules) --

pub(crate) type QueueRow = (String, String, i64, Option<String>, Option<String>);
pub(crate) type ExperimentRow = (String, f64, f64, f64, f64, i64, Option<String>);
pub(crate) type ExperimentDetail = (
    String,
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<i64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<String>,
    Option<i64>, // project_id
);
pub(crate) type QueueDetail = (String, Option<String>, Option<String>, Option<String>);
