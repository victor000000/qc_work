//! Top-level `read_project` response shape + the embedded `LeanVersion`.

use serde::Deserialize;

use super::Project;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectListResponse {
    #[serde(default)]
    pub projects: Vec<Project>,
    #[serde(default)]
    pub versions: Vec<LeanVersion>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LeanVersion {
    pub id: i64,
    #[serde(default)]
    pub created: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub lean_hash: String,
    #[serde(default)]
    pub lean_cloud_hash: String,
    #[serde(default)]
    pub name: String,
    #[serde(default, rename = "ref")]
    pub ref_: String,
    #[serde(default)]
    pub public: Option<bool>,
}
