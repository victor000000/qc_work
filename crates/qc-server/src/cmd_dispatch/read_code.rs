//! Read backtest source from a file or stdin.

pub(super) fn read_code(
    code_file: Option<&std::path::PathBuf>,
    code_stdin: bool,
) -> anyhow::Result<String> {
    if code_stdin {
        use std::io::Read;
        let mut buf = String::new();
        std::io::stdin().read_to_string(&mut buf)?;
        return Ok(buf);
    }
    if let Some(path) = code_file {
        if path.as_os_str() == "-" {
            use std::io::Read;
            let mut buf = String::new();
            std::io::stdin().read_to_string(&mut buf)?;
            return Ok(buf);
        }
        return std::fs::read_to_string(path)
            .map_err(|e| anyhow::anyhow!("read {}: {e}", path.display()));
    }
    anyhow::bail!("must specify --code-file <path> or --code-stdin")
}
