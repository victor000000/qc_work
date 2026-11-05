//! CLI handler for `create-projects` command.

mod suffix;

use std::path::Path;

use self::suffix::compute_next_pool_suffix;
use crate::projects_json;

/// Maximum consecutive failures before bailing out.
const MAX_CONSECUTIVE_FAILURES: usize = 5;

/// Create `count` new QC projects and append their IDs to `projects.json`.
///
/// Names are `bt_pool_<n>` using the lowest free suffix (skipping gaps from
/// prior deletions). `projects.json` is rewritten after every successful
/// creation, and we bail after `MAX_CONSECUTIVE_FAILURES` consecutive errors.
///
/// # Errors
/// Returns `Err` if config loading, file IO, or JSON (de)serialization fails.
pub async fn create_projects(data_dir: &Path, count: usize) -> anyhow::Result<()> {
    let client = crate::qc_setup::load_client(data_dir).await?;
    let projects_path = projects_json::path_in(data_dir);
    let mut projects = projects_json::read(&projects_path)?;
    println!("Current local projects.json: {}", projects.len());

    let next_suffix = compute_next_pool_suffix(&client).await?;
    println!("Next free pool suffix: bt_pool_{next_suffix}");

    let mut consecutive_failures = 0usize;
    let mut current_suffix = next_suffix;
    let mut created = 0usize;

    for i in 0..count {
        let name = format!("bt_pool_{current_suffix}");
        match client.create_project(&name, "Py", None).await {
            Ok(resp) if resp.success => {
                if let Some(p) = resp.projects.first() {
                    println!(
                        "[{}/{count}] Created {name}: project_id={}",
                        i + 1,
                        p.project_id
                    );
                    projects.push(p.project_id);
                    projects_json::write_atomic(&projects_path, &projects)?;
                    consecutive_failures = 0;
                    current_suffix += 1;
                    created += 1;
                } else {
                    anyhow::bail!(
                        "[{}/{count}] {name}: success=true but no project returned — \
                         aborting (created {created} so far)",
                        i + 1
                    );
                }
            }
            Ok(resp) => {
                let msg = if resp.errors.is_empty() {
                    "(no error message)".into()
                } else {
                    resp.errors.join("; ")
                };
                println!("[{}/{count}] FAIL {name}: {msg}", i + 1);
                if resp.errors.iter().any(|e| {
                    let lc = e.to_ascii_lowercase();
                    lc.contains("maximum number of projects") || lc.contains("daily limit")
                }) {
                    println!(
                        "Hit QC daily creation limit — stopping early (created {created} of {count})."
                    );
                    println!("Done. projects.json: {} total", projects.len());
                    return Ok(());
                }
                consecutive_failures += 1;
                current_suffix += 1;
            }
            Err(e) => {
                println!("[{}/{count}] ERROR {name}: {e}", i + 1);
                consecutive_failures += 1;
                current_suffix += 1;
            }
        }
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES {
            anyhow::bail!(
                "{MAX_CONSECUTIVE_FAILURES} consecutive failures — \
                 aborting (created {created} of {count})"
            );
        }
        // Polite spacing between API calls (matches delete_each_and_save).
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
    }
    println!(
        "Done. projects.json: {} total ({created} new)",
        projects.len()
    );
    Ok(())
}
