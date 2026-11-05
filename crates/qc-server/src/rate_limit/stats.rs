//! Parse QC statistics map values ("12.34%", "$1,234.56", ...) into numbers.

use std::collections::HashMap;

/// Parse a percentage string like "12.34%" -> 12.34, or a dollar string like "$1,234.56" -> 1234.56.
pub(crate) fn parse_stat(s: &str) -> Option<f64> {
    let cleaned = s.replace(['$', '%', ',', ' '], "");
    cleaned.parse().ok()
}

/// Parse a QC statistics map value to f64.
pub(crate) fn stat_f64(stats: &HashMap<String, String>, key: &str) -> Option<f64> {
    stats.get(key).and_then(|v| parse_stat(v))
}

pub(crate) fn stat_i64(stats: &HashMap<String, String>, key: &str) -> Option<i64> {
    stats.get(key).and_then(|v| v.replace(',', "").parse().ok())
}
