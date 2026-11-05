//! Custom event formatter producing `[PREFIX] [LEVEL]`-bracketed lines.

use tracing::Level;
use tracing_subscriber::fmt::time::ChronoLocal;
use tracing_subscriber::fmt::{self, FormatEvent, FormatFields};
use tracing_subscriber::registry::LookupSpan;

/// Custom formatter that outputs: `2026-03-26 13:44:38 [INFO] message`
/// With optional prefix: `2026-03-26 13:44:38 [BRAIN] [INFO] message`
pub(super) struct BracketFormat {
    pub timer: ChronoLocal,
    pub show_target: bool,
    pub prefix: Option<String>,
}

impl<S, N> FormatEvent<S, N> for BracketFormat
where
    S: tracing::Subscriber + for<'a> LookupSpan<'a>,
    N: for<'a> FormatFields<'a> + 'static,
{
    fn format_event(
        &self,
        ctx: &fmt::FmtContext<'_, S, N>,
        mut writer: fmt::format::Writer<'_>,
        event: &tracing::Event<'_>,
    ) -> std::fmt::Result {
        // Timestamp
        use tracing_subscriber::fmt::time::FormatTime;
        self.timer.format_time(&mut writer)?;

        // Optional prefix
        if let Some(ref pfx) = self.prefix {
            write!(writer, " [{pfx}]")?;
        }

        // [LEVEL]
        let level = *event.metadata().level();
        let tag = match level {
            Level::ERROR => " [ERROR]",
            Level::WARN => " [WARN] ",
            Level::INFO => " [INFO] ",
            Level::DEBUG => " [DEBUG]",
            Level::TRACE => " [TRACE]",
        };
        write!(writer, "{tag}")?;

        // Optional target
        if self.show_target {
            write!(writer, " {}", event.metadata().target())?;
        }

        write!(writer, " ")?;
        ctx.field_format().format_fields(writer.by_ref(), event)?;
        writeln!(writer)
    }
}
