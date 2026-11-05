//! Dispatch entry for backtest-log CLI subcommands.

use std::path::Path;

use anyhow::Result;
use duckdb::OptionalExt;

use crate::cli::Command;
use crate::queue::open_db;

use crate::qc_setup::load_client_and_org;

pub(super) async fn try_dispatch(command: Command, data_dir: &Path) -> Result<Option<Command>> {
    match command {
        Command::BacktestLog {
            strategy,
            name,
            start,
            end,
        } => {
            backtest_log(data_dir, &strategy, &name, start, end).await?;
            Ok(None)
        }
        other => Ok(Some(other)),
    }
}

const LOG_PAGE: i64 = 200;
const LOG_MAX_ROWS: i64 = 100_000;

async fn backtest_log(
    data_dir: &Path,
    strategy: &str,
    name: &str,
    start: i64,
    end_opt: Option<i64>,
) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    let n = name.to_string();
    let row: Option<(Option<String>, Option<i64>)> = db
        .call(move |conn| {
            conn.query_row(
                "SELECT backtest_id, project_id FROM backtest_queue WHERE name=?1",
                [&n],
                |r| Ok((r.get::<_, Option<String>>(0)?, r.get::<_, Option<i64>>(1)?)),
            )
            .optional()
            .map_err(Into::into)
        })
        .await?;
    let Some((bt_id_opt, proj_id_opt)) = row else {
        anyhow::bail!("{strategy}/{name}: not found in queue");
    };
    let Some(backtest_id) = bt_id_opt else {
        anyhow::bail!("{strategy}/{name}: no backtest_id recorded yet");
    };
    let Some(project_id) = proj_id_opt else {
        anyhow::bail!("{strategy}/{name}: no project_id recorded");
    };

    let (client, _org) = load_client_and_org(data_dir).await?;
    let mut cursor = start;
    let cap = end_opt.unwrap_or_else(|| start.saturating_add(LOG_MAX_ROWS));
    while cursor < cap {
        let page_end = cursor.saturating_add(LOG_PAGE).min(cap);
        let resp = client
            .read_backtest_log(project_id, &backtest_id, cursor, page_end)
            .await?;
        if !resp.success {
            anyhow::bail!("read_backtest_log failed: {:?}", resp.errors);
        }
        if resp.log.is_empty() {
            break;
        }
        let got = resp.log.len();
        for line in &resp.log {
            println!("{line}");
        }
        if i64::try_from(got).unwrap_or(0) < (page_end - cursor) {
            break;
        }
        cursor = page_end;
    }
    Ok(())
}
