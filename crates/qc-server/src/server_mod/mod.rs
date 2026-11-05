//! Server startup: config load, auth, node discovery, slot launch.

mod log_helpers;
mod node_broadcast;
mod node_discover;
pub mod overhead;
pub mod pid;
pub mod recover;
mod serve;
mod session;
pub mod slots;
pub mod status;
mod status_aggregate;
mod status_emit;
pub mod status_fmt;
mod status_fmt_render;
pub(crate) mod status_query;
mod status_query_recent;

pub use serve::serve;
pub use session::SessionCounters;
