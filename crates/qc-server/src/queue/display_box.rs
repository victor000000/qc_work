//! Status box formatter: draws the bordered status display.

/// Bundled parameters for the status box renderer.
pub(super) struct BoxRenderParams<'a> {
    pub state: &'a str,
    pub uptime_h: u64,
    pub uptime_m: u64,
    pub speed: f64,
    pub session_ok: i64,
    pub session_fail: i64,
    pub overhead_pct: f64,
    pub strat_lines: &'a [String],
    pub error_lines_raw: &'a [(String, String)],
}

/// Print the status box to stdout.
pub(super) fn print_status_box(params: &BoxRenderParams<'_>) {
    let &BoxRenderParams {
        state,
        uptime_h,
        uptime_m,
        speed,
        session_ok,
        session_fail,
        overhead_pct: _overhead_pct,
        strat_lines,
        error_lines_raw,
    } = params;
    let bw = 84;
    let border_top = format!("\u{250c}{}\u{2510}", "\u{2500}".repeat(bw));
    let border_mid = format!("\u{251c}{}\u{2524}", "\u{2500}".repeat(bw));
    let border_bot = format!("\u{2514}{}\u{2518}", "\u{2500}".repeat(bw));

    let pad = |s: &str| -> String {
        let len = s.chars().count();
        if len < bw {
            format!("\u{2502}{}{}\u{2502}", s, " ".repeat(bw - len))
        } else {
            let mut taken = String::new();
            for (i, c) in s.chars().enumerate() {
                if i >= bw {
                    break;
                }
                taken.push(c);
            }
            format!("\u{2502}{taken}\u{2502}")
        }
    };

    println!("{border_top}");
    println!(
        "{}",
        pad(&format!(
            "  {state:<8} uptime {uptime_h:>2}h {uptime_m:02}m   \
             throughput {speed:>4.1}/min   \
             {session_ok} done \u{00b7} {session_fail} failed",
        ))
    );
    println!("{border_mid}");
    for line in strat_lines {
        let len = line.chars().count();
        if len < bw {
            println!("{}{}\u{2502}", line, " ".repeat(bw - len));
        } else {
            println!("{line}\u{2502}");
        }
    }
    if !error_lines_raw.is_empty() {
        println!("{border_mid}");
        for (name, err) in error_lines_raw {
            let n = if name.chars().count() > 24 {
                format!("..{}", super::tail_chars(name, 22))
            } else {
                name.clone()
            };
            let e = super::head_chars(err, 32);
            println!("{}", pad(&format!("  \u{2717} {n}: {e}")));
        }
    }
    println!("{border_bot}");
}
