#![warn(clippy::pedantic)]
#![forbid(unsafe_code)]

// ── QC API layer ────────────────────────────────────────────────
pub mod api;
pub mod client;
pub mod models;

// ── Database layer ──────────────────────────────────────────────
pub mod database;
mod database_settings;
#[path = "db_mod/mod.rs"]
pub mod db;

// ── Server + runner pipeline ────────────────────────────────────
pub mod config;
mod config_discover;
mod config_load;
mod config_resolve;
pub mod pool;
pub mod runner;
#[path = "server_mod/mod.rs"]
pub mod server;

// ── CLI + queue commands ────────────────────────────────────────
pub mod cli;
pub mod cmd_create_projects;
pub mod cmd_delete_projects;
pub mod cmd_dispatch;
pub mod cmd_reconcile_projects;
mod projects_json;
mod qc_setup;
pub mod queue;

// ── Utilities ───────────────────────────────────────────────────
pub mod log_setup;
pub mod rate_limit;
pub mod test_api;
