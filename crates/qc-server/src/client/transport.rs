//! Transport-layer impl: `GET` / `POST` / `PUT` / `DELETE` / multipart.
//!
//! Thin method wrappers over the shared `json_request` helper. Multipart
//! sits here because it doesn't share the retry/JSON-body machinery.

use anyhow::Result;
use reqwest::Method;
use serde::Serialize;
use serde::de::DeserializeOwned;

use super::QcClient;
use super::trace::traced_call;

// `+ Sync` on the Serialize body so the returned futures are Send —
// otherwise tokio's multi-thread runtime can't spawn or await them
// across thread boundaries (clippy::future_not_send caught this).

impl QcClient {
    /// POST with JSON body → deserialize JSON response.
    pub(crate) async fn post<T: DeserializeOwned>(
        &self,
        path: &str,
        body: &(impl Serialize + Sync),
    ) -> Result<T> {
        self.json_request(Method::POST, path, Some(body)).await
    }

    /// GET with query parameters → deserialize JSON response.
    pub(crate) async fn get<T: DeserializeOwned>(
        &self,
        path: &str,
        query: &(impl Serialize + Sync),
    ) -> Result<T> {
        let url = format!("{}{}", self.base_url, path);
        let mut attempt = 0usize;
        super::retry::with_retry(path, || {
            attempt += 1;
            let url = url.clone();
            async move {
                traced_call(path, "GET", attempt, || async {
                    let resp = self
                        .http
                        .get(&url)
                        .headers(self.headers()?)
                        .query(query)
                        .send()
                        .await?
                        .error_for_status()?;
                    Ok(resp.json().await?)
                })
                .await
            }
        })
        .await
    }

    /// PUT with JSON body.
    pub(crate) async fn put<T: DeserializeOwned>(
        &self,
        path: &str,
        body: &(impl Serialize + Sync),
    ) -> Result<T> {
        self.json_request(Method::PUT, path, Some(body)).await
    }

    /// DELETE with JSON body.
    pub(crate) async fn delete_req<T: DeserializeOwned>(
        &self,
        path: &str,
        body: &(impl Serialize + Sync),
    ) -> Result<T> {
        self.json_request(Method::DELETE, path, Some(body)).await
    }

    /// POST multipart form (for binary uploads). No retry — form body is a single-shot stream.
    pub(crate) async fn post_multipart<T: DeserializeOwned>(
        &self,
        path: &str,
        form: reqwest::multipart::Form,
    ) -> Result<T> {
        let url = format!("{}{}", self.base_url, path);
        traced_call(path, "POST(multipart)", 1, || async {
            let resp = self
                .http
                .post(&url)
                .headers(self.headers()?)
                .multipart(form)
                .send()
                .await?
                .error_for_status()?;
            Ok(resp.json().await?)
        })
        .await
    }
}
