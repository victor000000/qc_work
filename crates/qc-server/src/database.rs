//! Async-safe `DuckDB` operations with a process-wide advisory access protocol.
//! Settings helpers live in `database_settings.rs`.

use std::fs::OpenOptions;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use anyhow::{Context, Result, anyhow};
use duckdb::Connection;

/// All operations run via `spawn_blocking` so they don't block the tokio runtime.
#[derive(Clone)]
pub struct Db {
    path: Arc<PathBuf>,
    gate: Arc<Mutex<()>>,
}

impl Db {
    /// Open a `DuckDB` database using the shared process access protocol.
    ///
    /// # Errors
    /// Returns `Err` if locking, connection setup or filesystem access fails.
    pub fn open(path: &Path) -> Result<Self> {
        let db = Self {
            path: Arc::new(path.to_path_buf()),
            gate: Arc::new(Mutex::new(())),
        };
        db.sync_call(|_| Ok(()))?;
        Ok(db)
    }

    /// Serialize processes, then open and close `DuckDB` within one operation.
    /// No process retains a native handle while waiting for cloud work.
    pub(crate) fn sync_call<F, T>(&self, f: F) -> Result<T>
    where
        F: FnOnce(&mut Connection) -> Result<T>,
    {
        let _gate = self.gate.lock().map_err(|e| anyhow!("db lock: {e}"))?;
        let mut options = OpenOptions::new();
        options.read(true).write(true).create(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut access_path = self.path.as_os_str().to_os_string();
        access_path.push(".access.lock");
        let access = options.open(access_path)?;
        access.lock()?;
        let path = &*self.path;
        let mut conn =
            Connection::open(path).with_context(|| format!("open {}", path.display()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if path.is_file() {
                std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
            }
        }
        conn.execute_batch("SET TimeZone='UTC'; CREATE MACRO IF NOT EXISTS datetime(value, modifier := NULL) AS strftime(CAST(current_timestamp AS TIMESTAMP) + COALESCE(TRY_CAST(modifier AS INTERVAL), INTERVAL '0 second'), '%Y-%m-%d %H:%M:%S');")?;
        f(&mut conn)
    }

    /// Run a closure on the connection in a blocking thread.
    ///
    /// # Errors
    /// Returns `Err` if the mutex is poisoned, the `spawn_blocking` task
    /// panics, or the closure returns `Err`.
    pub async fn call<F, T>(&self, f: F) -> Result<T>
    where
        F: FnOnce(&Connection) -> Result<T> + Send + 'static,
        T: Send + 'static,
    {
        let db = self.clone();
        tokio::task::spawn_blocking(move || db.sync_call(|conn| f(conn))).await?
    }
}
