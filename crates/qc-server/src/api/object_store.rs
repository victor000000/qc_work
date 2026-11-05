use anyhow::Result;

use crate::client::QcClient;
use crate::models::common::RestResponse;
use crate::models::object_store::{
    GetObjectResponse, ListObjectsReq, ListObjectsResponse, ObjectKeyReq, ObjectPropertiesResponse,
};

impl QcClient {
    /// Upload a file to the organization Object Store.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn upload_object(
        &self,
        organization_id: &str,
        key: &str,
        data: Vec<u8>,
    ) -> Result<RestResponse> {
        let form = reqwest::multipart::Form::new()
            .text("organizationId", organization_id.to_string())
            .text("key", key.to_string())
            .part(
                "objectData",
                reqwest::multipart::Part::bytes(data).file_name("upload"),
            );
        self.post_multipart("/object/set", form).await
    }

    /// Get metadata (size, md5, mime, etc.) for an object.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn get_object_properties(
        &self,
        organization_id: &str,
        key: &str,
    ) -> Result<ObjectPropertiesResponse> {
        self.post(
            "/object/properties",
            &ObjectKeyReq {
                organization_id,
                key,
            },
        )
        .await
    }

    /// Get a download URL for an object.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn get_object(&self, organization_id: &str, key: &str) -> Result<GetObjectResponse> {
        self.post(
            "/object/get",
            &ObjectKeyReq {
                organization_id,
                key,
            },
        )
        .await
    }

    /// Delete an object from the store.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn delete_object(&self, organization_id: &str, key: &str) -> Result<RestResponse> {
        self.post(
            "/object/delete",
            &ObjectKeyReq {
                organization_id,
                key,
            },
        )
        .await
    }

    /// List objects in a directory path.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn list_objects(
        &self,
        organization_id: &str,
        path: Option<&str>,
    ) -> Result<ListObjectsResponse> {
        let absolute_path = format!("/{}", path.unwrap_or_default().trim_start_matches('/'));
        self.post(
            "/object/list",
            &ListObjectsReq {
                organization_id,
                path: Some(&absolute_path),
            },
        )
        .await
    }
}
