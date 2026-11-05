//! Show details: queue fallback + code display.

use anyhow::Result;
use duckdb::OptionalExt;

use crate::db::Db;

use super::QueueDetail;

/// Try the queue table as fallback when experiment not found.
pub(super) async fn show_queue_fallback(
    db: &Db,
    strategy: &str,
    name: &str,
    n: &str,
) -> Result<bool> {
    let n2 = n.to_string();
    let q: Option<QueueDetail> = db
        .call(move |conn| {
            conn.query_row(
                "SELECT status, description, error_message, \
                 batch FROM backtest_queue WHERE name=?1",
                [&n2],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .optional()
            .map_err(Into::into)
        })
        .await?;

    if let Some((status, desc, err, batch)) = q {
        println!("=== {strategy}/{name} (queue only) ===");
        println!(
            "status: {status}  batch: {}",
            batch.as_deref().unwrap_or("-")
        );
        if let Some(d) = &desc {
            println!("description: {d}");
        }
        if let Some(e) = &err {
            println!("error: {e}");
        }
        Ok(true)
    } else {
        println!("{strategy}/{name}: not found");
        Ok(false)
    }
}

/// Show the code for a job from the queue table.
pub(super) async fn show_code(db: &Db, n: &str) -> Result<()> {
    let n3 = n.to_string();
    let code: Option<String> = db
        .call(move |conn| {
            let from_queue: Option<String> = conn
                .query_row(
                    "SELECT code FROM backtest_queue \
                     WHERE name=?1",
                    [&n3],
                    |row| row.get(0),
                )
                .optional()?;
            Ok(from_queue)
        })
        .await?;

    if let Some(c) = &code {
        println!("\n--- code ---");
        println!("{c}");
    } else {
        println!("\n(no code stored)");
    }
    Ok(())
}
