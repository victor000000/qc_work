//! Sort project IDs by their QC `created` timestamp.

use super::SortBy;

/// Reorder `pids` by their `created` timestamp from QC. Projects whose
/// metadata can't be fetched are appended at the end (stable order
/// preserved among them).
pub(super) async fn sort_by_created(
    client: &crate::client::QcClient,
    pids: Vec<i64>,
    sort_by: SortBy,
) -> anyhow::Result<Vec<i64>> {
    let resp = client.read_project(None, None, None).await?;
    if !resp.success {
        anyhow::bail!(
            "read_project failed: {}",
            if resp.errors.is_empty() {
                "(no message)".into()
            } else {
                resp.errors.join("; ")
            }
        );
    }
    let by_id: std::collections::HashMap<i64, String> = resp
        .projects
        .into_iter()
        .map(|p| (p.project_id, p.created))
        .collect();
    let mut tagged: Vec<(i64, Option<String>)> = pids
        .into_iter()
        .map(|pid| (pid, by_id.get(&pid).cloned()))
        .collect();
    tagged.sort_by(|a, b| match (&a.1, &b.1) {
        (Some(x), Some(y)) => match sort_by {
            SortBy::CreatedDesc => y.cmp(x),
            _ => x.cmp(y),
        },
        (Some(_), None) => std::cmp::Ordering::Less,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (None, None) => std::cmp::Ordering::Equal,
    });
    Ok(tagged.into_iter().map(|(p, _)| p).collect())
}
