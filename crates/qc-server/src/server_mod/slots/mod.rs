//! Slot runner launch and periodic status/monitoring loop.

mod launch;
mod launch_spawn;
mod qc_poller;
mod snapshot;
mod snapshot_scan;
mod status_loop;
mod warm;

pub(crate) use launch::{LaunchSlotsParams, launch_slots};

mod shutdown;
