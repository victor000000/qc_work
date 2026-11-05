//! Command-line interface root.

mod commands;

pub use commands::Command;

use std::path::PathBuf;

use clap::Parser;

/// Embeds the git short SHA captured in build.rs so `--version` reports
/// e.g. `1.2.0 (e2e371c5)` — operators can verify which build is running.
const VERSION: &str = concat!(env!("CARGO_PKG_VERSION"), " (", env!("GIT_SHA"), ")");

#[derive(Parser)]
#[command(name = "qc-backtest-server", version = VERSION)]
pub struct Cli {
    /// Path to the data directory containing strategy databases (S*.duckdb).
    #[arg(long, env = "QC_DATA_DIR", default_value = "data")]
    pub data_dir: PathBuf,

    /// Directory for log files. Defaults to `<data_dir>/logs` if unset.
    #[arg(long)]
    pub log_dir: Option<PathBuf>,

    #[command(subcommand)]
    pub command: Command,
}
