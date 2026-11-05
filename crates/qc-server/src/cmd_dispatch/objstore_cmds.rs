//! Dispatch entry for object-store CLI subcommands.

use std::path::Path;

use crate::cli::Command;

use super::{objstore_io, objstore_list, objstore_meta};

pub(super) async fn try_dispatch(
    command: Command,
    data_dir: &Path,
) -> anyhow::Result<Option<Command>> {
    match command {
        Command::ObjList { path } => {
            objstore_list::list(data_dir, path.as_deref()).await?;
            Ok(None)
        }
        Command::ObjStats { path } => {
            objstore_list::stats(data_dir, path.as_deref()).await?;
            Ok(None)
        }
        Command::ObjGet { key, out } => {
            objstore_io::get(data_dir, &key, out.as_ref()).await?;
            Ok(None)
        }
        Command::ObjPut { key, file } => {
            objstore_io::put(data_dir, &key, &file).await?;
            Ok(None)
        }
        Command::ObjDelete { key, yes } => {
            objstore_io::delete(data_dir, &key, yes).await?;
            Ok(None)
        }
        Command::ObjProps { key } => {
            objstore_meta::props(data_dir, &key).await?;
            Ok(None)
        }
        Command::ObjBulkDelete { prefix, yes } => {
            objstore_meta::bulk_delete(data_dir, &prefix, yes).await?;
            Ok(None)
        }
        other => Ok(Some(other)),
    }
}
