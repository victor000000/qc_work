//! Dispatch entry point for `queue::*` subcommands. Splits the match across
//! `queue_cmds_write` (mutating commands) and `queue_cmds_read` (read-only).

use std::path::Path;

use crate::cli::Command;

use super::queue_cmds_read;
use super::queue_cmds_write;

/// Returns `Some(())` if the command was a queue subcommand and was handled,
/// or `None` if the caller should continue dispatching to other handler groups.
pub(super) async fn try_dispatch(
    command: Command,
    data_dir: &Path,
) -> anyhow::Result<Option<Command>> {
    let Some(command) = queue_cmds_write::try_dispatch(command, data_dir).await? else {
        return Ok(None);
    };
    queue_cmds_read::try_dispatch(command, data_dir).await
}
