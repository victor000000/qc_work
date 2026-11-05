//! Per-file tracing layer constructors.

use std::path::Path;

use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::Layer;
use tracing_subscriber::fmt::time::ChronoLocal;
use tracing_subscriber::{EnvFilter, fmt};

use super::format::BracketFormat;

const TIME_S: &str = "%Y-%m-%d %H:%M:%S";
const TIME_MS: &str = "%Y-%m-%d %H:%M:%S%.3f";
const NOISY: &str = "h2=info,hyper=info,hyper_util=info,reqwest=info,rustls=info";

/// Build the daily-rotated, non-blocking writer for a given filename.
fn daily_writer(
    log_dir: &Path,
    file: &str,
    guards: &mut Vec<WorkerGuard>,
) -> tracing_appender::non_blocking::NonBlocking {
    let appender = tracing_appender::rolling::daily(log_dir, file);
    let (writer, guard) = tracing_appender::non_blocking(appender);
    guards.push(guard);
    writer
}

fn fmt_layer<S>(
    writer: tracing_appender::non_blocking::NonBlocking,
    fmt_pat: &str,
    show_target: bool,
    prefix: Option<String>,
) -> fmt::Layer<
    S,
    fmt::format::DefaultFields,
    BracketFormat,
    tracing_appender::non_blocking::NonBlocking,
>
where
    S: tracing::Subscriber + for<'a> tracing_subscriber::registry::LookupSpan<'a>,
{
    fmt::layer()
        .with_writer(writer)
        .with_ansi(false)
        .event_format(BracketFormat {
            timer: ChronoLocal::new(fmt_pat.to_string()),
            show_target,
            prefix,
        })
}

pub(super) fn info_layer<S>(
    log_dir: &Path,
    name: &str,
    prefix: String,
    guards: &mut Vec<WorkerGuard>,
) -> Box<dyn Layer<S> + Send + Sync>
where
    S: tracing::Subscriber + for<'a> tracing_subscriber::registry::LookupSpan<'a>,
{
    let w = daily_writer(log_dir, &format!("{name}.log"), guards);
    fmt_layer::<S>(w, TIME_S, false, Some(prefix))
        .with_filter(EnvFilter::new("info"))
        .boxed()
}

pub(super) fn debug_layer<S>(
    log_dir: &Path,
    name: &str,
    prefix: String,
    guards: &mut Vec<WorkerGuard>,
) -> Box<dyn Layer<S> + Send + Sync>
where
    S: tracing::Subscriber + for<'a> tracing_subscriber::registry::LookupSpan<'a>,
{
    let w = daily_writer(log_dir, &format!("{name}_full.log"), guards);
    fmt_layer::<S>(w, TIME_MS, true, Some(prefix))
        .with_filter(EnvFilter::new(format!("debug,{NOISY}")))
        .boxed()
}
