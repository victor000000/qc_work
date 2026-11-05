//! End-to-end smoke tests against the actual binary. Catches regressions
//! in clap wiring, subcommand routing, and the `--help` / `--version`
//! convention — none of which the library-level tests exercise.

use std::process::{Command, Output};

fn bin() -> String {
    env!("CARGO_BIN_EXE_qc-backtest-server").to_string()
}

fn run(args: &[&str]) -> Output {
    Command::new(bin())
        .args(args)
        .output()
        .expect("binary should execute")
}

#[test]
fn version_includes_git_sha() {
    let out = run(&["--version"]);
    assert!(out.status.success(), "exit code != 0");
    let stdout = String::from_utf8(out.stdout).unwrap();
    // Format: `qc-backtest-server 1.2.0 (<sha>)` or `1.2.0 (unknown)`.
    assert!(stdout.starts_with("qc-backtest-server "), "got: {stdout:?}");
    assert!(stdout.contains(" ("), "missing git SHA marker: {stdout:?}");
    assert!(
        stdout.contains(")\n") || stdout.ends_with(")"),
        "got: {stdout:?}"
    );
}

#[test]
fn help_lists_core_subcommands() {
    let out = run(&["--help"]);
    assert!(out.status.success());
    let stdout = String::from_utf8(out.stdout).unwrap();
    // A representative slice — if any of these drop out of the help
    // section, something broke in clap-derive routing.
    for needle in [
        "serve",
        "queue",
        "list",
        "errors",
        "top",
        "context",
        "show",
        "status",
        "create-projects",
        "delete-projects",
        "obj-list",
        "obj-get",
        "obj-put",
        "obj-stats",
        "obj-bulk-delete",
        "backtest-log",
        "backtest-stats",
        "backtest-orders",
        "batch-stats",
    ] {
        assert!(
            stdout.contains(needle),
            "help missing subcommand `{needle}`:\n{stdout}"
        );
    }
}

#[test]
fn unknown_subcommand_exits_nonzero() {
    let out = run(&["this-is-not-a-real-subcommand"]);
    assert!(!out.status.success(), "expected non-zero exit");
    let stderr = String::from_utf8(out.stderr).unwrap();
    // clap's error format mentions the unknown argument.
    assert!(
        stderr.contains("unrecognized")
            || stderr.contains("unknown")
            || stderr.contains("not a valid"),
        "stderr didn't flag the bad subcommand:\n{stderr}"
    );
}

#[test]
fn obj_bulk_delete_refuses_empty_prefix() {
    // Regression for the live-test guard in objstore_meta.rs.
    // Don't need real QC creds — bail fires before any HTTP call.
    let out = run(&[
        "--data-dir",
        "/tmp/nonexistent-data-dir-for-cli-test",
        "obj-bulk-delete",
        "--prefix",
        "",
        "--yes",
    ]);
    assert!(!out.status.success());
}

#[test]
fn initialize_and_queue_multifile_job_from_cli() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().to_str().unwrap();
    let init = run(&["--data-dir", path, "init-strategy", "--strategy", "scli"]);
    assert!(
        init.status.success(),
        "{}",
        String::from_utf8_lossy(&init.stderr)
    );
    let main = dir.path().join("main.py");
    let extras = dir.path().join("extras.json");
    std::fs::write(&main, "import helper\n").unwrap();
    std::fs::write(&extras, r#"{"helper.py":"value = 42"}"#).unwrap();
    let queued = run(&[
        "--data-dir",
        path,
        "queue",
        "--strategy",
        "scli",
        "--name",
        "multi",
        "--code-file",
        main.to_str().unwrap(),
        "--extra-files",
        extras.to_str().unwrap(),
    ]);
    assert!(
        queued.status.success(),
        "{}",
        String::from_utf8_lossy(&queued.stderr)
    );
    let conn = duckdb::Connection::open(dir.path().join("SCLI.duckdb")).unwrap();
    let extra: String = conn
        .query_row(
            "SELECT extra_files FROM backtest_queue WHERE name='multi'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(&extra).unwrap()["helper.py"],
        "value = 42"
    );
}
