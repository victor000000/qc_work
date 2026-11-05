use serde::{Deserialize, Serialize};

/// Base response returned by every QC API endpoint.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RestResponse {
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}
