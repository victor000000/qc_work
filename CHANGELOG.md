# Changelog

Reverse-chronological. Dates in local TZ. `git log` is the authoritative
source; this file groups the changes that mattered.

## Documentation review — 2026-11-07

Current guides now distinguish executor 1.2.0, v090 feature engine and v092 diagnostics; correct authentication, CLI, cache bootstrap and hosted-CI boundaries; and inventory public/native prose. Dated research/release facts below are preserved. See [documentation coverage](docs/DOCUMENTATION_AUDIT.md) for exact verification scope and exclusions. This entry records documentation work, not a new trading/runtime release.

## Unreleased (2026-05-21)

### Bugs fixed
- `db_mod::queue_status::mark_failed` panicked on multi-byte UTF-8 error
  messages — `&error[..error.len().min(80)]` lands mid-codepoint on
  Chinese stack traces, etc. (`4a918c00`)
- 4 more same-class `&str[..N]` panic sites in display code + the
  periodic status box (`c51d57f6`)
- `obj-bulk-delete --prefix ""` with `--yes` would walk the org store
  root and delete everything (`50a1b7c6`)
- `obj-bulk-delete` aborted the whole batch on the first network error
  instead of counting + continuing (`50a1b7c6`)
- `db_mod::claim_tx` interpolated `name_prefix` into the SQL `LIKE`
  clause; a quote in the prefix would break the parse (`50a1b7c6`)
- `runner::lock_alt` `let _ = ...` discarded the DB-write failure on
  alt-project rewrite; in-memory lock and DB row could diverge
  (`50a1b7c6`)
- `backtest-log --start <huge>` could overflow `start + LOG_MAX_ROWS`
  (`50a1b7c6`)
- `cmd_dispatch::dispatch` panicked via `unreachable!()` if a Command
  variant was added but not wired (`2db1761b`)
- Last bare `.unwrap()` on `PREV_OVERHEAD.lock()` could kill the
  periodic status task on poison (`e02444f0`)

### Performance
- Logging volume cut ~90 %: dropped 4 redundant log streams, demoted
  4 high-frequency debug lines to trace. `qc_full.log` grew at
  ~10 KB/s before; now ~1 KB/s (`ebb0f52e`, `bbb4d69c`, `ffb39ef6`,
  `4a392dbe`)
- Backtest timeout 15 min → 6 min → 10 min (tuned after observing
  legit long training runs) (`18b392e6`, `90baa4ca`)
- Release binary stripped: 17 MB → 14 MB (`e2e371c5`)

### New CLIs (11 helpers)
- Object store: `obj-list`, `obj-get`, `obj-put`, `obj-delete`,
  `obj-stats`, `obj-props`, `obj-bulk-delete` (`6d129b4f`,
  `6b49a10e`)
- Backtest data: `backtest-log`, `backtest-stats`, `backtest-orders`
  (`6d129b4f`, `6b49a10e`)
- Sweep aggregation: `batch-stats` (`2932d9a1`)

### Refactor
- Every Rust source file under 100 lines (started: ~50 files over;
  ended: 0) (commits `274c4ee2` through `b4ae5ca6`)
- 12 dead `pub use foo::*` glob re-exports removed from
  `models/mod.rs` (`fd719448`)
- Other dead-code cleanups + import tightening (`288946eb`)

### Project hygiene
- `#![forbid(unsafe_code)]` invariant (`9b9e63ba`)
- `rust-toolchain.toml` pinned to 1.95.0 (`4a918c00`)
- CI workflow pinned to same 1.95.0; `cargo audit` step added (0/273
  deps flagged) (`288946eb`, `30757f66`)
- `Cargo.toml` metadata: description, authors, MSRV, `publish = false`
  (`44f195d6`)
- `README.md` (`9b9e63ba`)
- `--version` now includes git short SHA via `build.rs` (`3d14a7db`)

### Tests (was 0; now 23)
- 10 unit (claim_scan pin logic, query_sql binding, fmt_helpers
  char-safety) + 13 integration (queue_status SQL, claim_tx atomic
  pick, cli_smoke end-to-end)
