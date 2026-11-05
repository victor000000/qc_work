//! Collaborator + the two collaborator-listing response shapes.

use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Collaborator {
    pub uid: i64,
    pub live_control: bool,
    pub permission: String,
    #[serde(default)]
    pub public_id: String,
    #[serde(default)]
    pub profile_image: String,
    #[serde(default)]
    pub email: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub bio: String,
    #[serde(default)]
    pub owner: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CollaboratorsResponse {
    #[serde(default)]
    pub collaborators: Vec<Collaborator>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ReadCollaboratorsResponse {
    #[serde(default)]
    pub collaborators: Vec<Collaborator>,
    #[serde(default)]
    pub user_live_control: bool,
    #[serde(default)]
    pub user_permissions: String,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}
