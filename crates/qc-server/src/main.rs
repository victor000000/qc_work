use clap::Parser;
use tracing_subscriber::EnvFilter;

use qc::cli::{Cli, Command};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    let _log_guards = if matches!(&cli.command, Command::Serve) {
        let log_dir = cli
            .log_dir
            .clone()
            .unwrap_or_else(|| cli.data_dir.join("logs"));
        Some(qc::log_setup::init(&log_dir, "qc"))
    } else {
        tracing_subscriber::fmt()
            .with_env_filter(
                EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
            )
            .init();
        None
    };

    qc::cmd_dispatch::dispatch(cli.command, &cli.data_dir).await
}
