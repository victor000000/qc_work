//! QC API: project collaboration + node management.

mod collab_write;
mod nodes;

use anyhow::Result;

use crate::client::QcClient;
use crate::models::common::RestResponse;
use crate::models::project::{CollaboratorsResponse, ReadCollaboratorsResponse};
use crate::models::project_req::{CreateCollaboratorReq, LockProjectReq, ProjectIdReq};

impl QcClient {
    /// Add a collaborator to a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn create_collaborator(
        &self,
        project_id: i64,
        collaborator_user_id: &str,
        live_control: bool,
        write: bool,
    ) -> Result<CollaboratorsResponse> {
        self.post(
            "/projects/collaboration/create",
            &CreateCollaboratorReq {
                project_id,
                collaborator_user_id,
                collaboration_live_control: live_control,
                collaboration_write: write,
            },
        )
        .await
    }

    /// List collaborators on a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_collaborators(&self, project_id: i64) -> Result<ReadCollaboratorsResponse> {
        self.get("/projects/collaboration/read", &ProjectIdReq { project_id })
            .await
    }

    /// Acquire the collaboration edit lock for a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn lock_project(
        &self,
        project_id: i64,
        code_source_id: &str,
    ) -> Result<RestResponse> {
        self.post(
            "/projects/collaboration/lock/acquire",
            &LockProjectReq {
                project_id,
                code_source_id,
            },
        )
        .await
    }
}
