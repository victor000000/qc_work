//! Pretty-print the full detail block for one experiment.

use super::ExperimentDetail;

pub(super) fn print_experiment_detail(strategy: &str, name: &str, detail: ExperimentDetail) {
    let (
        status,
        desc,
        hyp,
        based,
        batch,
        cagr,
        dd,
        car_mdd,
        sharpe,
        sortino,
        orders,
        wr,
        net_pnl,
        prob_sharpe,
        hash,
        proj_id,
    ) = detail;

    println!("=== {strategy}/{name} ===");
    println!(
        "status: {status}  batch: {}",
        batch.as_deref().unwrap_or("-")
    );
    if let Some(d) = &desc {
        println!("description: {d}");
    }
    if let Some(h) = &hyp {
        println!("hypothesis: {h}");
    }
    if let Some(b) = &based {
        println!("based_on: {b}");
    }
    println!();
    println!("Performance:");
    println!("  CAGR:    {:>8.2}%", cagr.unwrap_or(0.0));
    println!("  DD:      {:>8.2}%", dd.unwrap_or(0.0));
    println!("  CAR/MDD: {:>8.3}", car_mdd.unwrap_or(0.0));
    println!("  Sharpe:  {:>8.3}", sharpe.unwrap_or(0.0));
    println!("  Sortino: {:>8.3}", sortino.unwrap_or(0.0));
    println!("  Orders:  {:>8}", orders.unwrap_or(0));
    println!("  WinRate: {:>8.1}%", wr.unwrap_or(0.0));
    println!("  NetPnL:  {:>8.1}%", net_pnl.unwrap_or(0.0));
    println!("  ProbSR:  {:>8.1}%", prob_sharpe.unwrap_or(0.0));
    if let Some(h) = &hash {
        println!("  Hash:    {h}");
    }
    if let Some(p) = proj_id {
        println!("  Project: {p}");
    }
}
