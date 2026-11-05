//! Shared `projects.json` read/atomic-write for the CLI commands that
//! manage the QC project pool (`create-projects`, `delete-projects`,
//! `reconcile-projects`). Single source of truth for the file format.

use std::path::{Path, PathBuf};

/// Filename inside `data_dir`. Centralized so a rename (e.g. to
/// `qc-projects.json`) happens in one place.
pub(crate) const FILE_NAME: &str = "projects.json";

/// `data_dir.join(FILE_NAME)`. Use in lieu of repeating the filename literal.
pub(crate) fn path_in(data_dir: &Path) -> PathBuf {
    data_dir.join(FILE_NAME)
}

/// Read `projects.json`. Returns `Ok(Vec::new())` when the file is missing.
///
/// # Errors
/// Returns `Err` if the file exists but is unreadable, isn't valid JSON,
/// or doesn't have a top-level `"projects"` array.
pub(crate) fn read(path: &Path) -> anyhow::Result<Vec<i64>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let content = std::fs::read_to_string(path)?;
    let parsed: serde_json::Value = serde_json::from_str(&content)?;
    let arr = parsed["projects"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("projects.json: \"projects\" is not an array"))?;
    let mut projects = Vec::new();
    for value in arr {
        let id = value.as_i64().filter(|id| *id > 0).ok_or_else(|| {
            anyhow::anyhow!("projects.json: each project ID must be a positive integer")
        })?;
        if !projects.contains(&id) {
            projects.push(id);
        }
    }
    Ok(projects)
}

/// Like `read`, but bails if the file is missing — for commands that
/// can't proceed without an existing project list (`delete-projects`,
/// `reconcile-projects`).
///
/// # Errors
/// Returns `Err` if the file is missing or `read` fails.
pub(crate) fn read_required(path: &Path) -> anyhow::Result<Vec<i64>> {
    if !path.exists() {
        anyhow::bail!("projects.json not found at {}", path.display());
    }
    read(path)
}

/// Atomically write `projects.json` via tmp-file + rename so an interrupt
/// never leaves a half-written file.
///
/// # Errors
/// Returns `Err` on JSON serialization or file IO failure.
pub(crate) fn write_atomic(path: &Path, projects: &[i64]) -> anyhow::Result<()> {
    let json = serde_json::json!({"projects": projects});
    let tmp_path = path.with_extension("json.tmp");
    std::fs::write(&tmp_path, serde_json::to_string_pretty(&json)?)?;
    std::fs::rename(&tmp_path, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_invalid_pool_entries_instead_of_silently_disabling_projects() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join(FILE_NAME);
        for bad in [
            r#"{"projects":[42,"invalid"]}"#,
            r#"{"projects":[-1]}"#,
            r#"{"projects":[]}"#,
        ] {
            std::fs::write(&path, bad).unwrap();
            if bad.contains("[]") {
                assert_eq!(read(&path).unwrap(), Vec::<i64>::new());
            } else {
                assert!(read(&path).is_err());
            }
        }
        std::fs::write(&path, r#"{"projects":[42,42,43]}"#).unwrap();
        assert_eq!(read(&path).unwrap(), vec![42, 43]);
    }
}
