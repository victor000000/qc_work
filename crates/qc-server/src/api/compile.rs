use anyhow::Result;

use crate::client::QcClient;
use crate::models::compile::{
    CreateCompileReq, CreateCompileResponse, ReadCompileReq, ReadCompileResponse,
};

impl QcClient {
    /// Start a compilation job for a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn create_compile(&self, project_id: i64) -> Result<CreateCompileResponse> {
        self.post("/compile/create", &CreateCompileReq { project_id })
            .await
    }

    /// Poll compilation status.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_compile(
        &self,
        project_id: i64,
        compile_id: &str,
    ) -> Result<ReadCompileResponse> {
        self.post(
            "/compile/read",
            &ReadCompileReq {
                project_id,
                compile_id,
            },
        )
        .await
    }
}
