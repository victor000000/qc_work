//! Settings table accessors + a generic `queue_counts_table` helper.

use anyhow::{Result, anyhow};

use crate::database::Db;

impl Db {
    /// Read a string setting, returning `None` if absent.
    ///
    /// # Errors
    /// Returns `Err` on SQL execution error.
    pub async fn get_setting(&self, category: &str, key: &str) -> Result<Option<String>> {
        let cat = category.to_string();
        let k = key.to_string();
        self.call(move |conn| {
            let mut stmt =
                conn.prepare("SELECT value FROM settings WHERE category=?1 AND key=?2")?;
            let val = stmt
                .query_row(duckdb::params![cat, k], |row| row.get(0))
                .ok();
            Ok(val)
        })
        .await
    }

    /// Read a string setting; error if missing.
    ///
    /// # Errors
    /// Returns `Err` on SQL execution error or if the setting is absent.
    pub async fn get_setting_required(&self, category: &str, key: &str) -> Result<String> {
        self.get_setting(category, key)
            .await?
            .ok_or_else(|| anyhow!("missing setting {category}/{key}"))
    }

    /// Upsert a string setting with the current timestamp.
    ///
    /// # Errors
    /// Returns `Err` on SQL execution error.
    pub async fn set_setting(&self, category: &str, key: &str, value: &str) -> Result<()> {
        let cat = category.to_string();
        let k = key.to_string();
        let v = value.to_string();
        self.call(move |conn| {
            conn.execute(
                "INSERT OR REPLACE INTO settings (category, key, value, updated_at)
                 VALUES (?1, ?2, ?3, datetime('now'))",
                duckdb::params![cat, k, v],
            )?;
            Ok(())
        })
        .await
    }

    /// Generic queue counts from any table with a `status` column.
    ///
    /// # Errors
    /// Returns `Err` on SQL execution error.
    pub async fn queue_counts_table(&self, table: &str) -> Result<Vec<(String, i64)>> {
        let sql = format!("SELECT status, COUNT(*) FROM {table} GROUP BY status");
        self.call(move |conn| {
            let mut stmt = conn.prepare(&sql)?;
            let rows = stmt
                .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await
    }
}
