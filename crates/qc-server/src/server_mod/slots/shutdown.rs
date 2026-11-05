//! Bounded graceful shutdown, retaining unfinished queue rows for crash recovery.
use crate::server::SessionCounters;
use futures::StreamExt;
use std::sync::atomic::Ordering;
use std::time::Duration;

pub(super) async fn wait_for_signal() {
    #[cfg(unix)]
    {
        let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("install SIGTERM handler");
        tokio::select! { _ = tokio::signal::ctrl_c() => {}, _ = term.recv() => {} }
    }
    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
    tracing::info!("shutdown requested; stopping new work and draining in-flight results");
}

pub(super) async fn drain_slots(
    handles: &mut futures::stream::FuturesUnordered<tokio::task::JoinHandle<()>>,
    session: &SessionCounters,
) {
    let grace = tokio::time::timeout(Duration::from_secs(30), async {
        while handles.next().await.is_some() {}
    })
    .await;
    if grace.is_err() {
        for handle in handles.iter() {
            handle.abort();
        }
        // Await cancellation so no slot can launch a new pipeline during drain.
        while handles.next().await.is_some() {}
    }
    let drain = tokio::time::timeout(Duration::from_mins(2), async {
        while session.unfinished_collects.load(Ordering::SeqCst) > 0 {
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    })
    .await;
    if drain.is_err() {
        tracing::warn!(
            "collection drain deadline exceeded; unfinished jobs will recover at restart"
        );
    }
}
