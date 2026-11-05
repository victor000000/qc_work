//! Mutating queue subcommands: `Queue` / `Cancel` / `CancelAll` / `Clean` / `Retry`.

use std::path::Path;

use crate::cli::Command;
use crate::queue;

use super::read_code::read_code;

pub(super) async fn try_dispatch(
    command: Command,
    data_dir: &Path,
) -> anyhow::Result<Option<Command>> {
    match command {
        Command::Queue {
            strategy,
            name,
            code_file,
            extra_files,
            code_stdin,
            batch,
            priority,
            description,
            hypothesis,
            based_on,
            project_id,
        } => {
            let code = read_code(code_file.as_ref(), code_stdin)?;
            let extras = extra_files.map(std::fs::read_to_string).transpose()?;
            queue::enqueue(queue::QueueCmdInput {
                data_dir,
                strategy: &strategy,
                name: &name,
                code: &code,
                extra_files: extras.as_deref(),
                batch: batch.as_deref(),
                priority,
                description: description.as_deref(),
                hypothesis: hypothesis.as_deref(),
                based_on: based_on.as_deref(),
                project_id,
            })
            .await?;
            Ok(None)
        }
        Command::Cancel { strategy, name } => {
            queue::cancel(data_dir, &strategy, &name).await?;
            Ok(None)
        }
        Command::CancelAll { strategy, batch } => {
            queue::cancel_all(data_dir, &strategy, batch.as_deref()).await?;
            Ok(None)
        }
        Command::Clean {
            strategy,
            older_than_days,
            include_cancelled,
            dry_run,
        } => {
            queue::clean(
                data_dir,
                strategy.as_deref(),
                older_than_days,
                include_cancelled,
                dry_run,
            )
            .await?;
            Ok(None)
        }
        Command::Retry {
            strategy,
            name,
            batch,
        } => {
            queue::retry(data_dir, &strategy, name.as_deref(), batch.as_deref()).await?;
            Ok(None)
        }
        other => Ok(Some(other)),
    }
}
