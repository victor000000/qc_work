use serde::{Deserialize, Serialize};

// ── Responses ────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ObjectPropertiesResponse {
    #[serde(default)]
    pub metadata: Option<ObjectStoreProperties>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ObjectStoreProperties {
    #[serde(default)]
    pub key: String,
    #[serde(default)]
    pub modified: String,
    #[serde(default)]
    pub created: String,
    #[serde(default)]
    pub size: i64,
    #[serde(default)]
    pub md5: Option<String>,
    #[serde(default)]
    pub mime: Option<String>,
    #[serde(default)]
    pub preview: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GetObjectResponse {
    #[serde(default)]
    pub job_id: Option<String>,
    /// Download URL — paste full URL (including params) into a browser.
    #[serde(default)]
    pub url: Option<String>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ListObjectsResponse {
    #[serde(default)]
    pub path: String,
    #[serde(default, deserialize_with = "objects_or_empty")]
    pub objects: Vec<ObjectStoreSummary>,
    #[serde(default)]
    pub page: Option<i64>,
    #[serde(default)]
    pub total_pages: Option<i64>,
    #[serde(default)]
    pub object_storage_used: Option<i64>,
    #[serde(default)]
    pub object_storage_used_human: Option<String>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ObjectStoreSummary {
    #[serde(default)]
    pub key: String,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub modified: String,
    #[serde(default)]
    pub mime: Option<String>,
    #[serde(default)]
    pub folder: bool,
    #[serde(default)]
    pub size: i64,
}

fn objects_or_empty<'de, D>(deserializer: D) -> Result<Vec<ObjectStoreSummary>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    Ok(Option::<Vec<ObjectStoreSummary>>::deserialize(deserializer)?.unwrap_or_default())
}

// ── Request helpers ──────────────────────────────────────────────

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ObjectKeyReq<'a> {
    pub organization_id: &'a str,
    pub key: &'a str,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ListObjectsReq<'a> {
    pub organization_id: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<&'a str>,
}

#[cfg(test)]
mod tests {
    use super::ListObjectsResponse;

    #[test]
    fn null_pagination_is_valid_for_object_store_listing() {
        let response: ListObjectsResponse = serde_json::from_str(
            r#"{"success":true,"objects":null,"page":null,"totalPages":null,"objectStorageUsed":null}"#,
        )
        .unwrap();
        assert!(response.success);
        assert_eq!(response.total_pages, None);
    }
}
