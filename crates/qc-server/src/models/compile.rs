use serde::{Deserialize, Serialize};

// ── Responses ────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateCompileResponse {
    #[serde(default)]
    pub compile_id: String,
    #[serde(default)]
    pub state: String, // "InQueue" | "BuildSuccess" | "BuildError"
    #[serde(default)]
    pub parameters: Vec<FileParameters>,
    #[serde(default)]
    pub project_id: i64,
    #[serde(default)]
    pub signature: Option<String>,
    #[serde(default)]
    pub signature_order: Vec<String>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ReadCompileResponse {
    #[serde(default)]
    pub compile_id: String,
    #[serde(default)]
    pub state: String,
    #[serde(default)]
    pub logs: Vec<String>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileParameters {
    #[serde(default)]
    pub file: String,
    #[serde(default)]
    pub parameters: Vec<ParameterDetail>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ParameterDetail {
    #[serde(default)]
    pub line: i64,
    #[serde(default, rename = "type")]
    pub type_: String,
}

// ── Request helpers ──────────────────────────────────────────────

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CreateCompileReq {
    pub project_id: i64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ReadCompileReq<'a> {
    pub project_id: i64,
    pub compile_id: &'a str,
}
