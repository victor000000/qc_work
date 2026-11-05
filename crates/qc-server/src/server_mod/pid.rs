//! OS-backed lock scoped to one runtime directory. Never terminates other servers.
use anyhow::{Context, Result};
use std::fs::{File, OpenOptions};
use std::io::{Seek, SeekFrom, Write};
use std::path::Path;

/// Held for the entire server lifetime. The OS releases it even after a crash.
/// Keep the lock file in place: unlinking it permits a second lock inode race.
pub struct PidGuard {
    _file: File,
}

/// Acquire exclusive ownership of this data directory.
///
/// # Errors
/// Fails if a live server owns the lock or the directory is not writable.
pub fn try_acquire_pid_lock(pid_path: &Path) -> Result<PidGuard> {
    if let Some(parent) = pid_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(pid_path)?;
    file.try_lock()
        .with_context(|| format!("another server owns {}", pid_path.display()))?;
    file.set_len(0)?;
    file.seek(SeekFrom::Start(0))?;
    write!(file, "{}", std::process::id())?;
    file.sync_data()?;
    Ok(PidGuard { _file: file })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn excludes_second_owner_and_releases_after_drop() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("server.pid");
        let first = try_acquire_pid_lock(&path).unwrap();
        assert!(try_acquire_pid_lock(&path).is_err());
        drop(first);
        assert!(try_acquire_pid_lock(&path).is_ok());
    }
    #[test]
    fn independent_runtime_directories_can_run_together() {
        let dir = tempfile::tempdir().unwrap();
        let _first = try_acquire_pid_lock(&dir.path().join("one/server.pid")).unwrap();
        let _second = try_acquire_pid_lock(&dir.path().join("two/server.pid")).unwrap();
    }
}
