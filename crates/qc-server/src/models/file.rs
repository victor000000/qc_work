use serde::{Deserialize, Serialize};

// ── Responses ────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectFilesResponse {
    #[serde(default)]
    pub files: Vec<ProjectFile>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectFile {
    #[serde(default)]
    pub id: Option<i64>,
    #[serde(default)]
    pub project_id: i64,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub content: String,
    #[serde(default)]
    pub modified: String,
    #[serde(default)]
    pub open: bool,
    #[serde(default)]
    pub is_library: bool,
}

// ── Request helpers ──────────────────────────────────────────────

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CreateFileReq<'a> {
    pub project_id: i64,
    pub name: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code_source_id: Option<&'a str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ReadFilesReq<'a> {
    pub project_id: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code_source_id: Option<&'a str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateFileNameReq<'a> {
    pub project_id: i64,
    pub name: &'a str,
    pub new_name: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code_source_id: Option<&'a str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateFileContentsReq<'a> {
    pub project_id: i64,
    pub name: &'a str,
    pub content: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code_source_id: Option<&'a str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct DeleteFileReq<'a> {
    pub project_id: i64,
    pub name: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code_source_id: Option<&'a str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct PatchFileReq<'a> {
    pub project_id: i64,
    pub patch: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code_source_id: Option<&'a str>,
}
