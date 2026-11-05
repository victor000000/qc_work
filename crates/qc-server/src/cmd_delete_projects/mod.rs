//! CLI handler for `delete-projects` — trims the project pool down to the
//! first `keep` IDs in `projects.json` (optionally sorted), deleting all
//! remaining IDs from the QC cloud.

mod run;
mod sort;

use std::path::Path;

use self::run::{confirm_delete, delete_each_and_save};
use self::sort::sort_by_created;
use crate::projects_json;

#[derive(Debug, Clone, Copy)]
pub enum SortBy {
    /// File order — preserve `projects.json` order.
    None,
    /// Ascending by QC `created` timestamp (oldest first). `keep` preserves the OLDEST N.
    CreatedAsc,
    /// Descending by QC `created` timestamp. `keep` preserves the NEWEST N.
    CreatedDesc,
}

impl std::str::FromStr for SortBy {
    type Err = String;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "none" | "" => Ok(Self::None),
            "created" | "created_asc" => Ok(Self::CreatedAsc),
            "created_desc" => Ok(Self::CreatedDesc),
            other => Err(format!(
                "invalid sort-by '{other}': use one of none|created|created_desc"
            )),
        }
    }
}

/// Delete cloud projects beyond the first `keep` in `projects.json`.
/// Failures are preserved in `projects.json` so they can be retried.
///
/// # Errors
/// Returns `Err` if config loading, file IO, JSON (de)serialization,
/// or stdin read (for confirmation) fails.
pub async fn delete_projects(
    data_dir: &Path,
    keep: usize,
    dry_run: bool,
    assume_yes: bool,
    sort_by: SortBy,
) -> anyhow::Result<()> {
    let projects_path = projects_json::path_in(data_dir);
    let mut all_pids = projects_json::read_required(&projects_path)?;
    let client = crate::qc_setup::load_client(data_dir).await?;

    if !matches!(sort_by, SortBy::None) {
        all_pids = sort_by_created(&client, all_pids, sort_by).await?;
    }
    if keep >= all_pids.len() {
        println!(
            "Keep ({keep}) >= total ({}); nothing to delete.",
            all_pids.len()
        );
        return Ok(());
    }
    let (kept, to_delete) = all_pids.split_at(keep);
    println!(
        "Total: {}; keep: {}; delete: {} (sort_by={sort_by:?})",
        all_pids.len(),
        kept.len(),
        to_delete.len(),
    );
    if dry_run {
        println!("DRY-RUN — would delete:");
        for pid in to_delete {
            println!("  {pid}");
        }
        return Ok(());
    }
    if !assume_yes && !confirm_delete(to_delete.len())? {
        println!("Aborted.");
        return Ok(());
    }
    delete_each_and_save(&client, &projects_path, kept, to_delete).await
}
