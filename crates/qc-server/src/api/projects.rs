//! QC API: project CRUD operations.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::common::RestResponse;
use crate::models::project::ProjectListResponse;
use crate::models::project_req::{
    CreateProjectReq, ProjectIdReq, ReadProjectQuery, UpdateProjectReq,
};

impl QcClient {
    // ── Projects CRUD ────────────────────────────────────────────

    /// Create a new project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn create_project(
        &self,
        name: &str,
        language: &str,
        organization_id: Option<&str>,
    ) -> Result<ProjectListResponse> {
        self.post(
            "/projects/create",
            &CreateProjectReq {
                name,
                language,
                organization_id,
            },
        )
        .await
    }

    /// Read project metadata; omit `project_id` to list projects in the range.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_project(
        &self,
        project_id: Option<i64>,
        start: Option<i64>,
        end: Option<i64>,
    ) -> Result<ProjectListResponse> {
        self.get(
            "/projects/read",
            &ReadProjectQuery {
                project_id,
                start,
                end,
            },
        )
        .await
    }

    /// Update project name and/or description.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn update_project(
        &self,
        project_id: i64,
        name: Option<&str>,
        description: Option<&str>,
    ) -> Result<RestResponse> {
        self.put(
            "/projects/update",
            &UpdateProjectReq {
                project_id,
                name,
                description,
            },
        )
        .await
    }

    /// Delete a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn delete_project(&self, project_id: i64) -> Result<RestResponse> {
        self.delete_req("/projects/delete", &ProjectIdReq { project_id })
            .await
    }
}
