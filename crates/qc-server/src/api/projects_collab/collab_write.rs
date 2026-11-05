//! Update + delete collaborator endpoints.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::project::CollaboratorsResponse;
use crate::models::project_req::{DeleteCollaboratorReq, UpdateCollaboratorReq};

impl QcClient {
    /// Update a collaborator's permissions.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn update_collaborator(
        &self,
        project_id: i64,
        collaborator_user_id: &str,
        live_control: bool,
        write: bool,
    ) -> Result<CollaboratorsResponse> {
        self.put(
            "/projects/collaboration/update",
            &UpdateCollaboratorReq {
                project_id,
                collaborator_user_id,
                live_control,
                write,
            },
        )
        .await
    }

    /// Remove a collaborator from a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn delete_collaborator(
        &self,
        project_id: i64,
        collaborator_id: &str,
    ) -> Result<CollaboratorsResponse> {
        self.delete_req(
            "/projects/collaboration/delete",
            &DeleteCollaboratorReq {
                project_id,
                collaborator_id,
            },
        )
        .await
    }
}
