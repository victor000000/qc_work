//! Small logging helpers used by `serve` — extracted so `serve.rs` stays
//! under 100 lines.

use anyhow::Result;

use crate::config::ServerConfig;
use crate::db::Db;

pub(super) async fn log_queue_counts(dbs: &[Db]) -> Result<()> {
    for db in dbs {
        let counts = db.queue_counts().await?;
        let summary: String = counts
            .iter()
            .map(|(s, c)| format!("{s}={c}"))
            .collect::<Vec<_>>()
            .join(" ");
        tracing::info!("{} queue: {summary}", db.strategy);
    }
    Ok(())
}

pub(super) fn log_strategies(config: &ServerConfig) {
    tracing::info!(
        "strategies: {}",
        config
            .strategies
            .iter()
            .map(|s| {
                let pids = s
                    .project_ids
                    .iter()
                    .map(i64::to_string)
                    .collect::<Vec<_>>()
                    .join(",");
                format!("{}(w={}, projects=[{pids}])", s.name, s.weight)
            })
            .collect::<Vec<_>>()
            .join(", ")
    );
}
