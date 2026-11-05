//! Renderer for the periodic status box printed every 60 seconds.

use super::status_fmt::{StatusReport, fmt_int};

#[must_use]
pub fn format_status_report(r: &StatusReport) -> String {
    let h = r.uptime_secs / 3600;
    let m = (r.uptime_secs % 3600) / 60;
    let w = 86; // inner content width (raised +2 for wider `done` column)

    let border_top = format!("┌{}┐", "─".repeat(w));
    let border_mid = format!("├{}┤", "─".repeat(w));
    let border_bot = format!("└{}┘", "─".repeat(w));

    let pad = |s: String| -> String {
        let visible_len = s.chars().count();
        if visible_len < w {
            format!("│{}{}│", s, " ".repeat(w - visible_len))
        } else {
            let mut taken = String::new();
            for (i, c) in s.chars().enumerate() {
                if i >= w {
                    break;
                }
                taken.push(c);
            }
            format!("│{taken}│")
        }
    };

    let mut lines = Vec::new();
    lines.push(String::new());
    lines.push(border_top);
    lines.push(pad(format!(
        "  {:<8} uptime {:>2}h {:02}m   throughput {:>4.1}/min   \
         {} done · {} failed   slots {}/{}",
        r.state,
        h,
        m,
        r.throughput,
        fmt_int(i64::try_from(r.session_completed).unwrap_or(i64::MAX)),
        fmt_int(i64::try_from(r.session_failed).unwrap_or(i64::MAX)),
        r.busy_slots,
        r.total_slots,
    )));
    lines.push(border_mid.clone());

    for s in &r.strategies {
        let total = s.done + s.failed;
        let pct = if total > 0 {
            let done_f = f64::from(u32::try_from(s.done).unwrap_or(u32::MAX));
            let total_f = f64::from(u32::try_from(total).unwrap_or(u32::MAX));
            done_f / total_f * 100.0
        } else {
            0.0
        };
        // Split running into "running" (bt_running on QC) + "prewarm" (compiled, waiting).
        let prewarm = (s.running - s.bt_running).max(0);
        lines.push(pad(format!(
            "  {:<5}  queued {:>4}   running {:>3}   prewarm {:>3}   done {:>11}   failed {:>5}   {:>5.1}%",
            s.name, s.queued, s.bt_running, prewarm,
            fmt_int(s.done), fmt_int(s.failed), pct,
        )));
    }

    if !r.recent_errors.is_empty() {
        lines.push(border_mid);
        for e in &r.recent_errors {
            let name = if e.name.len() > 24 {
                format!("..{}", &e.name[e.name.len() - 22..])
            } else {
                e.name.clone()
            };
            let err = if e.error.len() > 32 {
                &e.error[..32]
            } else {
                &e.error
            };
            lines.push(pad(format!("  ✗ {name}: {err}")));
        }
    }

    lines.push(border_bot);
    lines.join("\n")
}
