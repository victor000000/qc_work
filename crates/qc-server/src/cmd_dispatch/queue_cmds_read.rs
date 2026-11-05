//! Read-only queue subcommands: `List` / `Errors` / `Top` / `Context` / `Next` / `Show` / `Status`.

use std::path::Path;

use crate::cli::Command;
use crate::queue;

pub(super) async fn try_dispatch(
    command: Command,
    data_dir: &Path,
) -> anyhow::Result<Option<Command>> {
    match command {
        Command::List {
            strategy,
            status,
            batch,
            name_like,
            limit,
        } => {
            queue::list(
                data_dir,
                strategy.as_deref(),
                &status,
                batch.as_deref(),
                name_like.as_deref(),
                limit,
            )
            .await?;
            Ok(None)
        }
        Command::Errors {
            strategy,
            limit,
            detail,
        } => {
            queue::errors(data_dir, &strategy, limit, detail.as_deref()).await?;
            Ok(None)
        }
        Command::Top {
            strategy,
            batch,
            limit,
        } => {
            queue::top(data_dir, strategy.as_deref(), batch.as_deref(), limit).await?;
            Ok(None)
        }
        Command::Context { strategy } => {
            queue::context(data_dir, &strategy).await?;
            Ok(None)
        }
        Command::Next { strategy } => {
            queue::next_experiment_number(data_dir, &strategy).await?;
            Ok(None)
        }
        Command::Show {
            strategy,
            name,
            code,
        } => {
            queue::show(data_dir, &strategy, &name, code).await?;
            Ok(None)
        }
        Command::Status => {
            queue::status(data_dir).await?;
            Ok(None)
        }
        other => Ok(Some(other)),
    }
}
