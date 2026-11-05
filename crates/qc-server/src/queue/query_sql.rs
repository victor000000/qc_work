//! Build the dynamic SQL + bound params for `queue list`.

pub(super) struct ListFilters<'a> {
    pub statuses: &'a [String],
    pub batch: Option<&'a str>,
    pub name_like: Option<&'a str>,
    pub limit: usize,
}

pub(super) fn build_list_sql(f: &ListFilters<'_>) -> (String, Vec<String>) {
    let mut conditions = vec!["1=1".to_string()];
    let mut params: Vec<String> = Vec::new();

    let placeholders: Vec<String> = f
        .statuses
        .iter()
        .enumerate()
        .map(|(i, _)| format!("?{}", i + 1))
        .collect();
    conditions.push(format!("status IN ({})", placeholders.join(",")));
    for s in f.statuses {
        params.push(s.clone());
    }

    if let Some(b) = f.batch {
        params.push(b.to_string());
        conditions.push(format!("batch=?{}", params.len()));
    }
    if let Some(pat) = f.name_like {
        params.push(pat.to_string());
        conditions.push(format!("name LIKE ?{}", params.len()));
    }
    params.push((i64::try_from(f.limit).unwrap_or(i64::MAX)).to_string());
    let limit_idx = params.len();

    let where_clause = conditions.join(" AND ");
    let sql = format!(
        "SELECT name, status, priority, batch, submitted_at \
         FROM backtest_queue
         WHERE {where_clause}
         ORDER BY priority ASC, id DESC LIMIT ?{limit_idx}"
    );
    (sql, params)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|x| (*x).to_string()).collect()
    }

    #[test]
    fn status_only_emits_placeholders_in_order() {
        let (sql, params) = build_list_sql(&ListFilters {
            statuses: &s(&["queued", "running"]),
            batch: None,
            name_like: None,
            limit: 20,
        });
        assert!(sql.contains("status IN (?1,?2)"));
        assert!(sql.ends_with("LIMIT ?3"));
        assert_eq!(params, vec!["queued", "running", "20"]);
    }

    #[test]
    fn batch_and_name_like_get_distinct_placeholders() {
        let (sql, params) = build_list_sql(&ListFilters {
            statuses: &s(&["done"]),
            batch: Some("py_bl05"),
            name_like: Some("%g080%"),
            limit: 5,
        });
        assert!(sql.contains("status IN (?1)"));
        assert!(sql.contains("batch=?2"));
        assert!(sql.contains("name LIKE ?3"));
        assert!(sql.ends_with("LIMIT ?4"));
        assert_eq!(params, vec!["done", "py_bl05", "%g080%", "5"]);
    }
}
