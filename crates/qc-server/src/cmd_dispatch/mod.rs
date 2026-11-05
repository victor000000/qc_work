//! CLI command dispatch — routes parsed commands to handlers.

mod backtest_data_cmds;
mod backtest_orders_cmd;
mod batch_stats_cmd;
mod log_cmds;
mod objstore_cmds;
mod objstore_io;
mod objstore_list;
mod objstore_meta;
mod queue_cmds;
mod queue_cmds_read;
mod queue_cmds_write;
mod read_code;

use std::path::Path;

use crate::cli::Command;
use crate::{cmd_create_projects, cmd_delete_projects, cmd_reconcile_projects, server, test_api};

/// Dispatch a parsed CLI `Command` to its handler.
///
/// # Errors
/// Returns `Err` if the invoked subcommand handler fails.
pub async fn dispatch(command: Command, data_dir: &Path) -> anyhow::Result<()> {
    let Some(command) = queue_cmds::try_dispatch(command, data_dir).await? else {
        return Ok(());
    };
    let Some(command) = objstore_cmds::try_dispatch(command, data_dir).await? else {
        return Ok(());
    };
    let Some(command) = log_cmds::try_dispatch(command, data_dir).await? else {
        return Ok(());
    };
    let Some(command) = backtest_data_cmds::try_dispatch(command, data_dir).await? else {
        return Ok(());
    };
    match command {
        Command::InitStrategy { strategy } => {
            crate::db::initialize_strategy(data_dir, &strategy)?;
        }
        Command::Serve => server::serve(data_dir.to_path_buf()).await?,
        Command::TestApi => test_api::test_api(data_dir).await?,
        Command::CreateProjects { count } => {
            cmd_create_projects::create_projects(data_dir, count).await?;
        }
        Command::DeleteProjects {
            keep,
            dry_run,
            yes,
            sort_by,
        } => {
            let parsed_sort: cmd_delete_projects::SortBy =
                sort_by.parse().map_err(|e: String| anyhow::anyhow!(e))?;
            cmd_delete_projects::delete_projects(data_dir, keep, dry_run, yes, parsed_sort).await?;
        }
        Command::ReconcileProjects { prune_orphans } => {
            cmd_reconcile_projects::reconcile_projects(data_dir, prune_orphans).await?;
        }
        // Queue / objstore / log / backtest_data variants are all consumed
        // by the try_dispatch chains above. Reaching here means a Command
        // variant was added in cli/commands.rs but not wired into any
        // dispatcher — surface that as a clear error rather than a panic.
        other => anyhow::bail!(
            "internal: Command::{other:?} reached final dispatch without a handler — \
             add it to one of the try_dispatch chains in cmd_dispatch/"
        ),
    }
    Ok(())
}
