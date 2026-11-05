//! `/files/create` + `/files/read` — file listing and creation.
//!
//! Write/update/patch/delete endpoints live in `files_write.rs`.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::common::RestResponse;
use crate::models::file::{CreateFileReq, ProjectFilesResponse, ReadFilesReq};

impl QcClient {
    /// Create a file in a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn create_file(
        &self,
        project_id: i64,
        name: &str,
        content: Option<&str>,
    ) -> Result<RestResponse> {
        self.post(
            "/files/create",
            &CreateFileReq {
                project_id,
                name,
                content,
                code_source_id: None,
            },
        )
        .await
    }

    /// Read files in a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_files(
        &self,
        project_id: i64,
        name: Option<&str>,
    ) -> Result<ProjectFilesResponse> {
        self.post(
            "/files/read",
            &ReadFilesReq {
                project_id,
                name,
                code_source_id: None,
            },
        )
        .await
    }
}
