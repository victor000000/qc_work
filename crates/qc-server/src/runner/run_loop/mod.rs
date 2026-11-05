//! Main loop orchestrator for `SlotRunner`.
//! Submodules: backpressure, cycle counters, prep dispatch, per-iteration body.

mod backpressure;
mod cycle;
mod iter;
mod iter_run;
mod prep;

use std::time::Instant;

use tokio::time::Duration;

use super::SlotRunner;

fn configured_backtest_timeout(raw: Option<&str>) -> Duration {
    let default = Duration::from_mins(10);
    match raw {
        None => default,
        Some(value) => match value.parse::<u64>() {
            Ok(seconds) if (1..=86_400).contains(&seconds) => Duration::from_secs(seconds),
            _ => {
                tracing::warn!("invalid QC_BACKTEST_TIMEOUT_SECS; using 600 seconds");
                default
            }
        },
    }
}

impl SlotRunner {
    /// Main loop: pick job → lock project → run backtest → collect → unlock.
    pub async fn run(mut self) {
        let timeout_setting = std::env::var("QC_BACKTEST_TIMEOUT_SECS").ok();
        let backtest_timeout = configured_backtest_timeout(timeout_setting.as_deref());
        tracing::info!(
            "slot-{}: backtest timeout {}s",
            self.slot_id,
            backtest_timeout.as_secs()
        );
        let cfg = iter::RunConfig {
            backoff: Duration::from_millis(700),
            timeouts: prep::PrepTimeouts {
                poll_interval: Duration::from_millis(1050),
                backtest_timeout,
            },
            compile_poll: Duration::from_millis(700),
            compile_timeout: Duration::from_mins(1),
        };

        // Stagger slot startup to avoid thundering herd on API
        tokio::time::sleep(Duration::from_millis(
            u64::try_from(self.slot_id).unwrap_or(0) * 210,
        ))
        .await;
        tracing::debug!("slot-{}: started", self.slot_id);

        // Instant at which the previous cycle *ended* (i.e. became ready to
        // start the next one). First cycle has no previous end, so idle_ms
        // is not recorded.
        let mut prev_cycle_end: Option<Instant> = None;
        loop {
            if self
                .session
                .as_ref()
                .is_some_and(|s| s.stopping.load(std::sync::atomic::Ordering::SeqCst))
            {
                break;
            }
            iter::run_one(&mut self, &cfg, &mut prev_cycle_end).await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::configured_backtest_timeout;

    #[test]
    fn backtest_deadline_defaults_and_scoped_override() {
        assert_eq!(configured_backtest_timeout(None).as_secs(), 600);
        assert_eq!(configured_backtest_timeout(Some("1800")).as_secs(), 1800);
        for invalid in ["0", "-1", "bad", "86401", "18446744073709551616"] {
            assert_eq!(configured_backtest_timeout(Some(invalid)).as_secs(), 600);
        }
    }
}
