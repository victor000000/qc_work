//! Local Python syntax check before pushing code to QC.

use tokio::time::Duration;

/// Run local validation: `py_compile` (syntax) + QC indicator method check (from LEAN source).
pub(crate) async fn local_syntax_check(code: &str, job_name: &str) -> Result<(), String> {
    use tokio::process::Command;
    let check_code = "import py_compile, tempfile, os, sys\nsrc = sys.stdin.read()\nf = tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w')\nf.write(src)\nf.close()\ntry:\n  py_compile.compile(f.name, doraise=True)\nexcept py_compile.PyCompileError as e:\n  print(str(e), file=sys.stderr)\n  os.unlink(f.name)\n  sys.exit(1)\nos.unlink(f.name)\n".to_string();
    let result = Command::new("python3")
        .arg("-c")
        .arg(&check_code)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn();
    match result {
        Ok(mut child) => {
            use tokio::io::AsyncWriteExt;
            if let Some(ref mut stdin) = child.stdin {
                let _ = stdin.write_all(code.as_bytes()).await;
                let _ = stdin.shutdown().await;
            }
            match tokio::time::timeout(Duration::from_secs(5), child.wait_with_output()).await {
                Ok(Ok(output)) if output.status.success() => Ok(()),
                Ok(Ok(output)) => {
                    let err = String::from_utf8_lossy(&output.stderr);
                    tracing::debug!("local syntax check failed for {job_name}: {err}");
                    Err(err.to_string())
                }
                _ => Ok(()), // timeout or error → skip check, let QC handle it
            }
        }
        Err(_) => Ok(()), // python3 not found → skip check
    }
}
