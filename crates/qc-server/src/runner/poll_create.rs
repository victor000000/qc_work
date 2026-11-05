//! Create backtest on QC.

use std::future::Future;
use std::time::{Duration, Instant};

use anyhow::{Result, bail};

use super::SlotRunner;
use crate::db::QueueJob;
use crate::models::backtest::BacktestResponse;
use crate::rate_limit::retry_on_rate_limit;

/// Capacity is definitively unavailable only when QC rejected the request,
/// returned no execution identity and supplied exclusively capacity errors.
/// A network failure or contradictory response must never trigger another create.
fn capacity_rejection(response: &BacktestResponse) -> bool {
    !response.success
        && response
            .backtest
            .as_ref()
            .is_none_or(|bt| bt.backtest_id.is_empty())
        && !response.errors.is_empty()
        && response
            .errors
            .iter()
            .all(|error| error.to_lowercase().contains("no spare nodes"))
}

/// Retain the caller's warm compile and project lock while waiting for capacity.
/// No detached tasks: dropping/aborting the parent future cancels the sleep.
/// Request timeouts and the post-create backtest timeout remain unchanged.
async fn await_capacity<C, CF, W, WF>(mut create: C, mut wait: W) -> Result<BacktestResponse>
where
    C: FnMut() -> CF,
    CF: Future<Output = Result<BacktestResponse>>,
    W: FnMut(Duration) -> WF,
    WF: Future<Output = ()>,
{
    let mut delay = Duration::from_secs(5);
    loop {
        let response = create().await?;
        if !capacity_rejection(&response) {
            return Ok(response);
        }
        wait(delay).await;
        delay = (delay * 2).min(Duration::from_secs(30));
    }
}

impl SlotRunner {
    /// Create a backtest on QC, retaining the warm compile while capacity is busy.
    ///
    /// Returns `(response, backtest_id, create_start_time)`.
    pub(crate) async fn create_backtest_on_qc(
        &self,
        project_id: i64,
        compile_id: &str,
        job: &QueueJob,
    ) -> Result<(crate::models::backtest::BacktestResponse, String, Instant)> {
        let slot = self.slot_id;
        let job_name = &job.name;

        tracing::debug!(
            "slot-{slot}: [{job_name}] creating backtest \
             on project {project_id}"
        );
        let bt_create_start = Instant::now();

        // 2026-05-07: max_retries 1→0 — slot bails on rate-limit → ~7s recovery
        // (was ~28s) by rotating to a different project. Restart25 evidence:
        // 177 hits/9min ≈ ~7 min slot time recovered. Push+compile are
        // sub-second so re-prep cost is negligible.
        // 2026-05-10: removed create_backtest semaphore — pacer + per-call
        // backpressure are the sole governors now.
        let bt = retry_on_rate_limit(self.rl_state.as_ref(), 0, || {
            let cid = compile_id.to_string();
            let name = job.name.clone();
            async move {
                let resp = await_capacity(
                    || async {
                        if let Some(rls) = self.rl_state.as_ref() {
                            let pacer_wait = rls.claim_create_slot();
                            if pacer_wait.as_millis() > 50 {
                                tracing::debug!(
                                    target: "qc::api",
                                    "qc_create_pacer_wait slot-{slot} job={job_name} wait_ms={}",
                                    pacer_wait.as_millis()
                                );
                                tokio::time::sleep(pacer_wait).await;
                            }
                        }
                        self.client.create_backtest(project_id, &cid, &name, None).await
                    },
                    |delay| async move {
                        tracing::debug!(
                            target: "qc::pipeline",
                            "slot-{slot}: [{job_name}] capacity_wait project={project_id} compile={compile_id} retry_seconds={} (retaining warm compile and project lock)",
                            delay.as_secs()
                        );
                        tokio::time::sleep(delay).await;
                    },
                ).await?;

                if !resp.success {
                    let err_msg = format!("{:?}", resp.errors);
                    let lower = err_msg.to_lowercase();
                    if lower.contains("too many") || lower.contains("slow down") {
                        // Push the global pacer forward so every slot waits
                        // through the cooldown — kills the retry-storm pattern.
                        if let Some(rls) = self.rl_state.as_ref() {
                            rls.record_rate_limit_hit();
                        }
                        tracing::debug!(target: "qc::api",
                            "qc_rate_limit_hit slot-{slot} job={job_name} project={project_id} (pacer +5s, retry with backoff)");
                        bail!("rate_limit: {err_msg}");
                    }
                    if lower.contains("no spare nodes") {
                        bail!("backtest_create: contradictory capacity rejection; execution identity={:?}; original response must be investigated before retry", resp.backtest.as_ref().map(|bt| &bt.backtest_id));
                    }
                    bail!("backtest_create: {err_msg}");
                }
                Ok(resp)
            }
        })
        .await?;

        let backtest_id = bt
            .backtest
            .as_ref()
            .map(|b| b.backtest_id.clone())
            .unwrap_or_default();

        if backtest_id.is_empty() {
            bail!("backtest_create: no backtestId returned");
        }

        tracing::debug!(
            "slot-{slot}: [{job_name}] backtest created: \
             {backtest_id} in {:.1}s",
            bt_create_start.elapsed().as_secs_f64()
        );

        Ok((bt, backtest_id, bt_create_start))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::collections::VecDeque;
    use std::future::ready;

    fn response(value: serde_json::Value) -> BacktestResponse {
        serde_json::from_value(value).unwrap()
    }

    fn busy() -> BacktestResponse {
        response(
            serde_json::json!({"success":false,"errors":["There are no spare nodes available in your cluster."]}),
        )
    }

    #[tokio::test]
    async fn capacity_wait_reuses_prepared_identity_without_reupload_or_recompile() {
        let responses = RefCell::new(VecDeque::from([
            busy(),
            busy(),
            response(
                serde_json::json!({"success":true,"backtest":{"backtestId":"real-created-id"}}),
            ),
        ]));
        let requests = RefCell::new(Vec::new());
        let waits = RefCell::new(Vec::new());
        let result = await_capacity(
            || {
                requests
                    .borrow_mut()
                    .push((31_338_455, "same-warm-compile"));
                ready(Ok(responses.borrow_mut().pop_front().unwrap()))
            },
            |delay| {
                waits.borrow_mut().push(delay.as_secs());
                ready(())
            },
        )
        .await
        .unwrap();
        assert_eq!(result.backtest.unwrap().backtest_id, "real-created-id");
        assert_eq!(
            *requests.borrow(),
            vec![(31_338_455, "same-warm-compile"); 3]
        );
        assert_eq!(*waits.borrow(), vec![5, 10]);
    }

    #[tokio::test]
    async fn ambiguous_network_failure_is_not_retried() {
        let requests = RefCell::new(0);
        let result = await_capacity(
            || {
                *requests.borrow_mut() += 1;
                ready(Err(anyhow::anyhow!("request observation timeout")))
            },
            |_| {
                panic!("Ambiguous create must not wait or retry");
                #[allow(unreachable_code)]
                ready(())
            },
        )
        .await;
        assert!(result.is_err());
        assert_eq!(*requests.borrow(), 1);
    }

    #[test]
    fn mixed_errors_success_or_any_execution_identity_are_not_capacity_rejections() {
        assert!(capacity_rejection(&busy()));
        for value in [
            serde_json::json!({"success":false,"errors":["no spare nodes","invalid compile"]}),
            serde_json::json!({"success":false,"errors":["no spare nodes"],"backtest":{"backtestId":"possibly-live"}}),
            serde_json::json!({"success":true,"errors":["no spare nodes"]}),
            serde_json::json!({"success":false,"errors":["Too many requests"]}),
        ] {
            assert!(!capacity_rejection(&response(value)));
        }
    }

    #[tokio::test]
    async fn cancelling_parent_stops_capacity_wait_without_another_create() {
        let attempts = RefCell::new(0);
        let waiting = await_capacity(
            || {
                *attempts.borrow_mut() += 1;
                ready(Ok(busy()))
            },
            |_| std::future::pending::<()>(),
        );
        assert!(
            tokio::time::timeout(Duration::from_millis(5), waiting)
                .await
                .is_err()
        );
        assert_eq!(*attempts.borrow(), 1);
    }

    #[tokio::test]
    async fn capacity_backoff_is_bounded_without_requeueing() {
        let attempts = RefCell::new(0);
        let waits = RefCell::new(Vec::new());
        await_capacity(
            || {
                *attempts.borrow_mut() += 1;
                ready(Ok(if *attempts.borrow() <= 6 {
                    busy()
                } else {
                    response(serde_json::json!({"success":true,"backtest":{"backtestId":"id"}}))
                }))
            },
            |delay| {
                waits.borrow_mut().push(delay.as_secs());
                ready(())
            },
        )
        .await
        .unwrap();
        assert_eq!(*waits.borrow(), vec![5, 10, 20, 30, 30, 30]);
    }
}
