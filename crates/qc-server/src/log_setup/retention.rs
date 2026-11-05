//! Log retention sweeper.
//!
//! Daily-rotated logs accumulate forever otherwise. Sweeps `log_dir`
//! hourly and deletes any regular file whose mtime is older than
//! `RETENTION`. The currently-open log file is touched on every write,
//! so its mtime is always fresh — the sweeper never races it.

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

const RETENTION: Duration = Duration::from_hours(16);
const SWEEP_INTERVAL: Duration = Duration::from_hours(1);

pub(super) fn spawn(log_dir: PathBuf) {
    sweep(&log_dir);
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(SWEEP_INTERVAL).await;
            sweep(&log_dir);
        }
    });
}

fn sweep(log_dir: &Path) {
    let Ok(cutoff) = SystemTime::now().checked_sub(RETENTION).ok_or(()) else {
        return;
    };
    let entries = match std::fs::read_dir(log_dir) {
        Ok(e) => e,
        Err(e) => {
            tracing::warn!("log retention: read_dir({}) failed: {e}", log_dir.display());
            return;
        }
    };
    let mut deleted = 0u32;
    let mut bytes = 0u64;
    for entry in entries.flatten() {
        let Ok(meta) = entry.metadata() else { continue };
        if !meta.is_file() {
            continue;
        }
        let Ok(mtime) = meta.modified() else { continue };
        if mtime >= cutoff {
            continue;
        }
        let path = entry.path();
        let size = meta.len();
        match std::fs::remove_file(&path) {
            Ok(()) => {
                deleted += 1;
                bytes += size;
                tracing::info!(
                    "log retention: deleted {} ({} bytes, age >16h)",
                    path.display(),
                    size
                );
            }
            Err(e) => {
                tracing::warn!("log retention: rm {} failed: {e}", path.display());
            }
        }
    }
    if deleted > 0 {
        tracing::info!("log retention sweep: removed {deleted} files ({bytes} bytes)");
    }
}
