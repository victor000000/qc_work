//! QC API: project node management.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::project_node::ProjectNodesResponse;
use crate::models::project_req::{ProjectIdReq, UpdateProjectNodesReq};

impl QcClient {
    /// Read the assigned backtest/research/live nodes for a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_project_nodes(&self, project_id: i64) -> Result<ProjectNodesResponse> {
        self.get("/projects/nodes/read", &ProjectIdReq { project_id })
            .await
    }

    /// Update the assigned node set for a project.
    ///
    /// `auto_select_node`: if `Some(true)`, QC's scheduler chooses ANY
    /// available node from the org pool — this is essential for even
    /// load distribution. If `Some(false)`, only the listed nodes are
    /// used and QC falls back to the first allowed node when no `node_id`
    /// is specified in `create_backtest`, causing idle-node skew.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn update_project_nodes(
        &self,
        project_id: i64,
        nodes: Option<&[String]>,
        auto_select_node: Option<bool>,
    ) -> Result<ProjectNodesResponse> {
        self.put(
            "/projects/nodes/update",
            &UpdateProjectNodesReq {
                project_id,
                nodes,
                auto_select_node,
            },
        )
        .await
    }
}
