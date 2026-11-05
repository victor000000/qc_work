//! `ServerConfig::load` — assembles strategies + credentials from disk.

use std::path::Path;

use anyhow::Result;

use crate::config::{ServerConfig, StrategyConfig};
use crate::config_discover::{discover_strategy_dbs, load_shared_projects};
use crate::config_resolve::resolve_project_ids;
use crate::db::Db;

impl ServerConfig {
    /// Load config from all strategy databases found in `data_dir`.
    /// Project IDs are loaded from shared `projects.json` (not per-strategy DBs).
    ///
    /// # Errors
    /// Returns `Err` if no `S*.duckdb` is found, SQL queries fail, or required
    /// credential settings are missing.
    pub async fn load(data_dir: &Path) -> Result<(Self, Vec<Db>)> {
        let mut dbs = Vec::new();
        let mut strategies = Vec::new();

        let shared_project_ids = load_shared_projects(data_dir)?;
        let db_files = discover_strategy_dbs(data_dir);
        if db_files.is_empty() {
            anyhow::bail!(
                "no strategy databases (S*.duckdb) found in {}",
                data_dir.display()
            );
        }

        for (name, path) in &db_files {
            let db = Db::open(path, name)?;
            let project_ids = resolve_project_ids(&db, name, &shared_project_ids).await?;
            if project_ids.is_empty() {
                dbs.push(db);
                continue;
            }
            let weight: f64 = db
                .get_setting("strategy", "scheduler_weight")
                .await?
                .and_then(|v| v.parse().ok())
                .unwrap_or(1.0);
            anyhow::ensure!(
                weight.is_finite() && weight > 0.0,
                "{name}: scheduler_weight must be finite and positive"
            );
            strategies.push(StrategyConfig {
                name: name.clone(),
                db_path: path.clone(),
                project_ids,
                weight,
            });
            dbs.push(db);
        }

        let credential_path = std::env::var_os("QC_CREDENTIALS_FILE").map_or_else(
            || {
                data_dir
                    .parent()
                    .unwrap_or(data_dir)
                    .join(".local/credentials.json")
            },
            std::path::PathBuf::from,
        );
        let qc_user_id = credential(&credential_path, "QC_USER_ID", "qc_user_id")?;
        let qc_api_token = credential(&credential_path, "QC_API_TOKEN", "qc_api_token")?;
        let organization_id = match std::env::var("QC_ORGANIZATION_ID") {
            Ok(value) => value,
            Err(_) => {
                dbs[0]
                    .get_setting_required("project", "organization_id")
                    .await?
            }
        };

        Ok((
            Self {
                qc_user_id,
                qc_api_token,
                organization_id,
                strategies,
                node_ids: Vec::new(),
            },
            dbs,
        ))
    }
}

fn credential(path: &Path, env: &str, key: &str) -> Result<String> {
    if let Ok(value) = std::env::var(env) {
        anyhow::ensure!(!value.trim().is_empty(), "{env} must not be empty");
        return Ok(value);
    }
    private_credential(path, key)
}

fn private_credential(path: &Path, key: &str) -> Result<String> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        anyhow::ensure!(
            std::fs::metadata(path)?
                .permissions()
                .mode()
                .trailing_zeros()
                >= 6,
            "QC credential file must have mode 0600"
        );
    }
    let content = std::fs::read(path)
        .map_err(|_| anyhow::anyhow!("Set QC credentials in environment or private file"))?;
    let values: serde_json::Value = serde_json::from_slice(&content)
        .map_err(|_| anyhow::anyhow!("Invalid QC credential JSON"))?;
    let value = values
        .get(key)
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    anyhow::ensure!(!value.trim().is_empty(), "Missing private credential {key}");
    Ok(value.to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn private_file_required_and_errors_do_not_echo_values() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("credentials.json");
        assert!(private_credential(&path, "qc_api_token").is_err());
        std::fs::write(&path, r#"{"qc_api_token":"test-only-token"}"#).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644)).unwrap();
            assert!(private_credential(&path, "qc_api_token").is_err());
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        assert_eq!(
            private_credential(&path, "qc_api_token").unwrap(),
            "test-only-token"
        );
        std::fs::write(&path, "sensitive malformed content").unwrap();
        assert!(
            !private_credential(&path, "qc_api_token")
                .unwrap_err()
                .to_string()
                .contains("sensitive")
        );
    }
}
