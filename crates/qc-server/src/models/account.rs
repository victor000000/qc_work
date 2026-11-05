use serde::Deserialize;

use super::project::LeanVersion;

// ── Account ──────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AccountResponse {
    #[serde(default)]
    pub organization_id: String,
    #[serde(default)]
    pub credit_balance: f64,
    #[serde(default)]
    pub card: Option<Card>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Card {
    #[serde(default)]
    pub brand: String,
    #[serde(default)]
    pub expiration: String,
    #[serde(default)]
    pub last4: String,
}

// ── Lean Versions ────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LeanVersionsResponse {
    #[serde(default)]
    pub versions: Vec<LeanVersion>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}
