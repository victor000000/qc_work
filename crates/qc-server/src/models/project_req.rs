//! Project request helpers (serialized as JSON bodies).

use serde::Serialize;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CreateProjectReq<'a> {
    pub name: &'a str,
    pub language: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub organization_id: Option<&'a str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateProjectReq<'a> {
    pub project_id: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<&'a str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ProjectIdReq {
    pub project_id: i64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CreateCollaboratorReq<'a> {
    pub project_id: i64,
    pub collaborator_user_id: &'a str,
    pub collaboration_live_control: bool,
    pub collaboration_write: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateCollaboratorReq<'a> {
    pub project_id: i64,
    pub collaborator_user_id: &'a str,
    pub live_control: bool,
    pub write: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct DeleteCollaboratorReq<'a> {
    pub project_id: i64,
    pub collaborator_id: &'a str,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LockProjectReq<'a> {
    pub project_id: i64,
    pub code_source_id: &'a str,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateProjectNodesReq<'a> {
    pub project_id: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nodes: Option<&'a [String]>,
    /// When true, QC's scheduler picks any available node from the org's
    /// pool. When false, only manually-pinned nodes are used (default per
    /// project after `update_project_nodes` with explicit `nodes` list,
    /// which causes idle-node skew because `create_backtest` doesn't
    /// specify a `node_id` and QC falls back to the first project-allowed).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auto_select_node: Option<bool>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ReadProjectQuery {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub start: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub end: Option<i64>,
}
