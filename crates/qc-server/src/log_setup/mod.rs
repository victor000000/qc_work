//! Logging initialization (file rolling + console layers).

mod format;
mod layers;
mod retention;

use std::path::Path;

use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::fmt::time::ChronoLocal;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::{EnvFilter, Layer, fmt};

use self::format::BracketFormat;

/// Initialize logging with a server name for distinct log files and prefixes.
///
/// - `name = "qc"` → `qc.log`, `qc_full.log`, console prefix `[QC]`
///
/// # Panics
/// Panics if an `EnvFilter` directive fails to parse.
#[must_use]
pub fn init(log_dir: &Path, name: &str) -> Vec<WorkerGuard> {
    std::fs::create_dir_all(log_dir).ok();

    let mut guards = Vec::new();
    let prefix = name.to_uppercase();

    let info_layer = layers::info_layer(log_dir, name, prefix.clone(), &mut guards);
    let debug_layer = layers::debug_layer(log_dir, name, prefix.clone(), &mut guards);

    // Console: colored [PREFIX] [LEVEL]
    let console_layer = fmt::layer()
        .event_format(BracketFormat {
            timer: ChronoLocal::new("%H:%M:%S".to_string()),
            show_target: false,
            prefix: Some(prefix),
        })
        .with_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")));

    tracing_subscriber::registry()
        .with(console_layer)
        .with(info_layer)
        .with(debug_layer)
        .init();

    retention::spawn(log_dir.to_path_buf());

    guards
}
