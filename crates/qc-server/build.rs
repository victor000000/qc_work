//! Capture the current git short SHA at compile time so the binary's
//! `--version` reports e.g. `1.2.0 (e2e371c5)`. Falls back to "unknown"
//! when not in a git tree.
//!
//! Rebuild trigger: re-run whenever HEAD moves (cargo's default behavior
//! is fine — it re-runs build.rs every clean build, and the env-var
//! output makes the rustc invocation differ when SHA changes, so the
//! main crate recompiles only when SHA changes).

use std::process::Command;

fn main() {
    #[cfg(target_os = "linux")]
    {
        println!("cargo:rustc-link-arg=-Wl,-rpath,$ORIGIN");
        println!("cargo:rustc-link-arg=-Wl,-rpath,$ORIGIN/deps");
    }
    let sha = Command::new("git")
        .args(["rev-parse", "--short", "HEAD"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "unknown".into());
    println!("cargo:rustc-env=GIT_SHA={sha}");
    // Re-run if HEAD or the packed refs move so the embedded SHA stays
    // accurate without `cargo clean`.
    println!("cargo:rerun-if-changed=.git/HEAD");
    println!("cargo:rerun-if-changed=.git/refs/heads");
    println!("cargo:rerun-if-changed=.git/packed-refs");
}
