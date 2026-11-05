//! `Project` — one entry in the QC `read_project` response.

use serde::Deserialize;
use serde_json::Value;

use super::Collaborator;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Project {
    pub project_id: i64,
    #[serde(default)]
    pub organization_id: String,
    pub name: String,
    #[serde(default)]
    pub modified: String,
    #[serde(default)]
    pub created: String,
    #[serde(default)]
    pub owner_id: i64,
    #[serde(default)]
    pub language: String,
    #[serde(default)]
    pub collaborators: Vec<Collaborator>,
    #[serde(default)]
    pub lean_version_id: Option<i64>,
    #[serde(default)]
    pub lean_pinned_to_master: Option<bool>,
    #[serde(default)]
    pub owner: Option<bool>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub parameters: Vec<Value>,
    #[serde(default)]
    pub libraries: Vec<Value>,
    #[serde(default)]
    pub encrypted: Option<bool>,
    #[serde(default)]
    pub code_running: Option<bool>,
    #[serde(default)]
    pub lean_environment: Option<i64>,
    #[serde(default)]
    pub is_pinned: Option<bool>,
}
