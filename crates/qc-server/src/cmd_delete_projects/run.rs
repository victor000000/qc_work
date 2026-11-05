//! Issue the delete RPCs and rewrite `projects.json`.

use std::path::Path;

/// True if the QC delete error indicates the project no longer exists.
/// Such IDs should be DROPPED from projects.json, not preserved as "failed".
fn is_already_gone(errors: &[String]) -> bool {
    errors.iter().any(|e| {
        let lc = e.to_ascii_lowercase();
        lc.contains("does not exist") || lc.contains("not found")
    })
}

pub(super) async fn delete_each_and_save(
    client: &crate::client::QcClient,
    projects_path: &Path,
    kept: &[i64],
    to_delete: &[i64],
) -> anyhow::Result<()> {
    let mut failed: Vec<(i64, String)> = Vec::new();
    let mut already_gone = 0usize;
    let mut deleted_ok = 0usize;
    for (i, pid) in to_delete.iter().enumerate() {
        match client.delete_project(*pid).await {
            Ok(resp) if resp.success => {
                println!("[{}/{}] {pid}: OK", i + 1, to_delete.len());
                deleted_ok += 1;
            }
            Ok(resp) => {
                if is_already_gone(&resp.errors) {
                    println!(
                        "[{}/{}] {pid}: already gone (dropping from projects.json)",
                        i + 1,
                        to_delete.len(),
                    );
                    already_gone += 1;
                } else {
                    let msg = if resp.errors.is_empty() {
                        "(no error message)".into()
                    } else {
                        resp.errors.join("; ")
                    };
                    println!("[{}/{}] {pid}: FAIL {msg}", i + 1, to_delete.len());
                    failed.push((*pid, msg));
                }
            }
            Err(e) => {
                let msg = e.to_string();
                println!("[{}/{}] {pid}: ERROR {msg}", i + 1, to_delete.len());
                failed.push((*pid, msg));
            }
        }
        // Polite spacing between requests.
        tokio::time::sleep(std::time::Duration::from_millis(300)).await;
    }

    // projects.json reflects only the `kept` slice — every requested-delete
    // ID is removed from the file, regardless of whether the QC API succeeded.
    // Rationale: projects.json is a cache of the active pool, not a retry
    // queue. Failed deletes are reported separately; the user can re-add IDs
    // manually if they intend to retry.
    let new_pids: Vec<i64> = kept.to_vec();
    let json = serde_json::json!({"projects": new_pids});
    let tmp_path = projects_path.with_extension("json.tmp");
    std::fs::write(&tmp_path, serde_json::to_string_pretty(&json)?)?;
    std::fs::rename(&tmp_path, projects_path)?;
    println!(
        "Updated projects.json: {} kept (all {} requested-delete IDs removed: \
         {deleted_ok} OK + {already_gone} already-gone + {} failed-but-removed)",
        kept.len(),
        to_delete.len(),
        failed.len(),
    );
    if !failed.is_empty() {
        println!(
            "Failed IDs (still on QC, REMOVED from projects.json — re-add manually if retrying):"
        );
        for (pid, msg) in &failed {
            println!("  {pid}: {msg}");
        }
    }
    Ok(())
}

/// Prompt the user for confirmation before destructive delete. Reads stdin
/// for `y`/`yes` (case-insensitive). Anything else returns false.
pub(super) fn confirm_delete(count: usize) -> anyhow::Result<bool> {
    use std::io::Write;
    print!("About to delete {count} QC projects. Continue? [y/N] ");
    std::io::stdout().flush()?;
    let mut buf = String::new();
    std::io::stdin().read_line(&mut buf)?;
    let answer = buf.trim().to_ascii_lowercase();
    Ok(matches!(answer.as_str(), "y" | "yes"))
}
