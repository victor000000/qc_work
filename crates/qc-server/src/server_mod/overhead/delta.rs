//! Delta + log emission between two `OverheadSnapshot`s.

#![expect(
    clippy::cast_precision_loss,
    reason = "ms counters u64 → f64 ratios; magnitudes stay well under 2^53"
)]

use super::OverheadSnapshot;

/// Diff two snapshots and emit a single debug log on `qc::overhead`.
///
/// `num_slots` and `wall_secs` are used to show utilization ratios.
pub fn emit_delta(
    prev: &OverheadSnapshot,
    curr: &OverheadSnapshot,
    num_slots: usize,
    wall_secs: u64,
) {
    let pool = curr.pool_wait_ms.saturating_sub(prev.pool_wait_ms);
    let lock = curr.lock_wait_ms.saturating_sub(prev.lock_wait_ms);
    let push = curr.push_ms.saturating_sub(prev.push_ms);
    let compile = curr.compile_ms.saturating_sub(prev.compile_ms);
    let create_api = curr.create_api_ms.saturating_sub(prev.create_api_ms);
    let poll_tail = curr.poll_tail_ms.saturating_sub(prev.poll_tail_ms);
    let idle = curr.idle_ms.saturating_sub(prev.idle_ms);
    let bt_run = curr.bt_run_ms.saturating_sub(prev.bt_run_ms);

    let overhead_total = pool + lock + push + compile + create_api + poll_tail + idle;
    let pct = |part: u64| -> f64 {
        if overhead_total == 0 {
            0.0
        } else {
            (part as f64) * 100.0 / (overhead_total as f64)
        }
    };

    let (per_strat_lines, total_cycles) = build_strategy_lines(prev, curr);

    let slot_wall_ms = u128::from(wall_secs) * (num_slots as u128) * 1000;
    let overhead_of_wall_pct = if slot_wall_ms == 0 {
        0.0
    } else {
        (overhead_total as f64) * 100.0 / (slot_wall_ms as f64)
    };

    tracing::debug!(
        target: "qc::overhead",
        "overhead summary (last {wall_secs}s, {num_slots} slots, wall={}s):\n  \
         {}\n  \
         total: cycles={total_cycles} overhead={:.1}s ({:.1}% of slot-wall)\n\
         phase breakdown:\n  \
         push={:.1}s({:.1}%)  compile={:.1}s({:.1}%)  create_api={:.1}s({:.1}%)  poll_tail={:.1}s({:.1}%)\n  \
         pool_wait={:.1}s({:.1}%)  lock_wait={:.1}s({:.1}%)  idle={:.1}s({:.1}%)\n  \
         bt_run={:.1}s  (product — not overhead)",
        wall_secs * (num_slots as u64),
        per_strat_lines.join("\n  "),
        overhead_total as f64 / 1000.0, overhead_of_wall_pct,
        push as f64 / 1000.0, pct(push),
        compile as f64 / 1000.0, pct(compile),
        create_api as f64 / 1000.0, pct(create_api),
        poll_tail as f64 / 1000.0, pct(poll_tail),
        pool as f64 / 1000.0, pct(pool),
        lock as f64 / 1000.0, pct(lock),
        idle as f64 / 1000.0, pct(idle),
        bt_run as f64 / 1000.0,
    );
}

fn build_strategy_lines(prev: &OverheadSnapshot, curr: &OverheadSnapshot) -> (Vec<String>, u64) {
    let mut lines: Vec<String> = Vec::new();
    let mut total_cycles: u64 = 0;
    for (name, cycles_now, oh_now) in &curr.per_strategy {
        let (cycles_prev, oh_prev) = prev
            .per_strategy
            .iter()
            .find(|(n, _, _)| n == name)
            .map_or((0, 0), |(_, c, o)| (*c, *o));
        let d_cycles = cycles_now.saturating_sub(cycles_prev);
        if d_cycles == 0 {
            continue;
        }
        total_cycles += d_cycles;
        let d_oh = oh_now.saturating_sub(oh_prev);
        let avg_ms = (d_oh as f64) / (d_cycles as f64);
        lines.push(format!(
            "{name}: cycles={d_cycles} overhead={:.1}s avg={:.2}s/cycle",
            d_oh as f64 / 1000.0,
            avg_ms / 1000.0
        ));
    }
    (lines, total_cycles)
}
