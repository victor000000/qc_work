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

        let cred_db = &dbs[0];
        let qc_user_id = credential(cred_db, "QC_USER_ID", "credentials", "qc_user_id").await?;
        let qc_api_token =
            credential(cred_db, "QC_API_TOKEN", "credentials", "qc_api_token").await?;
        let organization_id =
            credential(cred_db, "QC_ORGANIZATION_ID", "project", "organization_id").await?;

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

async fn credential(db: &Db, env: &str, category: &str, key: &str) -> Result<String> {
    if let Ok(value) = std::env::var(env) {
        anyhow::ensure!(!value.trim().is_empty(), "{env} must not be empty");
        return Ok(value);
    }
    db.get_setting_required(category, key).await
}
