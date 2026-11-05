# Zero-suppression clippy cleanup

**Date:** 2026-04-20
**Scope:** qc-backtest-server Rust codebase — lint hygiene
**Goal:** `cargo clippy --all-targets --all-features -- -D warnings` exits 0 with every `#[allow(...)]`, every `#![allow(...)]`, and every threshold bump in `clippy.toml` removed. After completion, any new lint warning fails the build.

## Current suppression inventory (25 items)

**Crate-level (`src/lib.rs`):** 4 clippy allows
- `clippy::missing_errors_doc`
- `clippy::missing_panics_doc`
- `clippy::future_not_send`
- `clippy::option_if_let_else`

**Function-level `#[allow(...)]`:** 11 sites
- `clippy::too_many_arguments` × 5 — `server_mod/status.rs`, `pool/job.rs`, `queue/cmd.rs`, `queue/display_box.rs`, `runner/backtest.rs`
- `clippy::too_many_lines` × 2 — `queue/display_context.rs`, `queue/display_show.rs`
- `clippy::cast_precision_loss` × 4 — `server_mod/status.rs`, `server_mod/status_fmt.rs`, `queue/display_gather.rs`, `queue/display_detect.rs`

**Config-level (`clippy.toml`):** 2 threshold bumps
- `too-many-arguments-threshold = 10` (clippy default 7)
- `too-many-lines-threshold = 200` (clippy default 100)

**Active warnings (7) from `cargo clippy`:**
1. `count_busy_slots` unused — `status_query.rs:103`
2. `&PathBuf` should be `&Path` — `config_discover.rs:56`
3. collapsible `if` — `runner/poll.rs:55`
4. collapsible `if` — `server_mod/recover.rs:145`
5. non-binding `let _ = future` — `server_mod/slots.rs:200`
6. useless `format!` — `pool/push.rs:15`
7. missing `is_empty` on struct with `len` — `pool/mod.rs:61`

## Phases

Six phases, one commit each. Each phase verifies by running `cargo clippy --all-targets --all-features -- -D warnings` (must exit 0) and `cargo build --release` (must finish).

### Phase 1 — Mechanical warning fixes

Target: clear the 7 active warnings listed above.

**Actions:**
- Delete `count_busy_slots` from `src/server_mod/status_query.rs` (not called anywhere).
- Change `&PathBuf` to `&Path` in `src/config_discover.rs:56`. Update the call sites (if any) accordingly; `&PathBuf` coerces to `&Path` so callers should compile unchanged.
- Collapse the nested `if` in `src/runner/poll.rs:55-63`:
  - Current: `if let Some(bt_result) = r.backtest.as_ref() { if bt_result.completed { if let Some(err) = &bt_result.error { if !err.is_empty() { ... } } ... } ... }`.
  - Target shape: use `&& let` chains or merge the two layers into one `if let Some(err) = bt_result.error.as_deref().filter(|e| !e.is_empty())`.
- Collapse the nested `if` in `src/server_mod/recover.rs:145`. (Whatever shape clippy suggests — one of the inner `if`s can be merged into the outer condition.)
- Replace the useless `format!(...)` in `src/pool/push.rs:15` with a `&str` literal or a `String::from(...)`/`.to_string()` depending on what the consumer needs.
- Add `pub fn is_empty(&self) -> bool` on `WarmPool` in `src/pool/mod.rs`, returning `self.len() == 0`. Inherits the same locking as `len`.
- Investigate `src/server_mod/slots.rs:200` — the `let _ = some_future` pattern. Determine from the surrounding code whether the future is a `tokio::spawn(...)` handle (which intentionally backgrounds the task) or a bare async call (dropped = never executed = bug):
  - If `spawn` handle: replace `let _ = ...` with `let _handle = ...` or `drop(...)` using `#[allow]`-free idiom (`.await` the handle if ordering matters, or use `tokio::task::JoinHandle::abort_handle` pattern).
  - If bare future: `.await` it or move to an explicit `tokio::spawn(async move { fut.await; });`.

**Success:** 0 warnings from `cargo clippy --all-targets`. All 11 function-level allows and 4 crate-level allows still in place (we haven't touched them yet).

### Phase 2 — Remove two cheap crate-level allows

Target: remove `clippy::future_not_send` and `clippy::option_if_let_else` from `src/lib.rs`.

**Actions:**
- Edit `src/lib.rs`, leaving the crate attribute as:
  ```rust
  #![allow(
      clippy::missing_errors_doc,
      clippy::missing_panics_doc,
  )]
  ```
  (Phase 6b will drop the last two.)
- Run clippy. For each new warning:
  - `future_not_send`: Most async fns in this codebase are already `Send`; any that aren't are likely holding `!Send` guards across `.await`. Fix by dropping guards before await, or by wrapping the non-Send operation in `spawn_blocking`.
  - `option_if_let_else`: Rewrite `if let Some(x) = opt { f(x) } else { g() }` as `opt.map_or_else(g, f)` where the closures don't capture mutable state. If the rewrite harms readability, keep the `if let` form and lift to `#[allow(clippy::option_if_let_else)]` on that specific expression — we accept tightly-scoped allows when ergonomics demands it.

**Success:** crate-level allows reduced to 2 (`missing_errors_doc`, `missing_panics_doc`). 0 warnings.

### Phase 3 — Revert `clippy.toml` thresholds

**Actions:**
- Delete `too-many-arguments-threshold = 10`, restoring clippy default 7.
- Delete `too-many-lines-threshold = 200`, restoring clippy default 100.
- If `clippy.toml` becomes empty, delete the file.

Run clippy. New warnings appear on any function with ≥8 arguments or >100 lines that lacks a `#[allow]`. Phase 4 and 5 fix these.

**Success:** `clippy.toml` removed (or empty of threshold keys). Any new warnings surfaced are acknowledged as phase-4/5 input — do not fix them in this phase. However `cargo clippy -- -D warnings` MUST still pass, so we accept that Phase 3 temporarily re-enables the 5 `too_many_arguments` and 2 `too_many_lines` function-level allows, which now refer to a stricter default threshold.

Verification for Phase 3 is:
- `clippy.toml` content matches expected end state
- `cargo clippy --all-targets -- -D warnings` still passes (because function-level allows cover the stricter threshold)

### Phase 4 — Eliminate `too_many_arguments` allows by bundling

Target: remove all 5 function-level `#[allow(clippy::too_many_arguments)]` by introducing parameter structs.

**Actions per site:**

1. `src/server_mod/status.rs::log_status` — 9 args → `StatusTickInput` struct carrying `dbs: &[Db]`, `uptime_secs: u64`, `rl_delay_ms: u64`, `session: Arc<SessionCounters>`, `num_slots: usize`, `client: &Arc<QcClient>`, `project_id: i64`. Caller (`slots.rs` status loop) constructs the struct each tick. The `_rl_delay_ms` unused warning the old signature had (underscore prefix) gets preserved via the struct field doc.
2. `src/runner/backtest.rs::run_backtest` — 8 args → `BacktestParams` struct: `project_id: i64`, `pre_compile_id: Option<String>`, `compile_poll: Duration`, `compile_timeout: Duration`, `bt_poll: Duration`, `bt_timeout: Duration`. Caller `run_loop.rs` builds once per cycle.
3. `src/pool/job.rs` — bundle its >7 args into `PoolJobParams`. Inspect the function to name the struct faithfully.
4. `src/queue/cmd.rs` — bundle into `QueueCmdInput`.
5. `src/queue/display_box.rs` — bundle into `BoxRenderParams`.

For each, verify the struct is local to the module (no pub if only used internally).

**Success:** 5 `#[allow(clippy::too_many_arguments)]` attributes removed; clippy clean.

### Phase 5 — Eliminate `too_many_lines` allows by extracting helpers

Target: remove 2 function-level `#[allow(clippy::too_many_lines)]`.

**Actions:**
1. `src/queue/display_context.rs` — find the >100-line function; extract 2-4 private helpers that each do one step (e.g., `build_header`, `format_rows`, `assemble_output`). The original function becomes a thin orchestrator.
2. `src/queue/display_show.rs` — same approach.

Name helpers by responsibility. Keep them private to the module unless a genuine cross-module caller emerges (none expected).

**Success:** 2 `#[allow(clippy::too_many_lines)]` removed.

### Phase 6 — Eliminate remaining allows (largest)

Two sub-phases, separate commits.

**Phase 6a — `cast_precision_loss` (4 sites)**

Each site performs `u64 as f64` or `i64 as f64` where precision loss is theoretically possible above 2^53. For each site:

1. `src/server_mod/status.rs:37` — `completed as f64 / (uptime_secs as f64 / 60.0)`. `completed` and `uptime_secs` are cycle/second counters that won't exceed 2^53 in any realistic run. Use `u32::try_from(x).map(f64::from)` pattern with a graceful fallback, or lift to `#[expect(clippy::cast_precision_loss, reason = "counter bounded by usize exec time")]` which is NOT an allow — `expect` is auto-remove-if-not-fired, i.e. self-cleaning lint.
2. `src/server_mod/status_fmt.rs:65` — same analysis. Same treatment.
3. `src/queue/display_gather.rs:72` — same.
4. `src/queue/display_detect.rs:66` — same.

Preference: use `#[expect(..., reason = "...")]` everywhere. It's an explicit opt-in with justification, and if the cast ever becomes unreachable, clippy flags it. This removes the `#[allow]` pattern entirely while keeping the semantic escape hatch.

**Phase 6b — remove `missing_errors_doc` + `missing_panics_doc` crate allows**

This is the largest chunk. Remove both from `lib.rs`. Clippy will then require:
- `# Errors` section in the doc of every public `Result<_, _>`-returning function
- `# Panics` section in the doc of every function containing `panic!`, `unreachable!`, or `.unwrap()` / `.expect()`

Actions:
1. Run clippy; capture the full list of offending sites.
2. For each public `Result`-returning fn: add a brief `# Errors` paragraph describing failure modes. Keep to ≤2 sentences.
3. For each panicking fn: add `# Panics` describing the panic condition.
4. **Non-public functions**: `missing_errors_doc` only fires on `pub` items by default. So we only need to document public surface.
5. Where a panicking call is an invariant guard that should never fire (`expect("mutex poisoned")`), add a one-line `# Panics` noting that.

Expect ~100-200 sites. This is mechanical; most doc comments will be 1-2 lines.

**Success:** `src/lib.rs` has no `#![allow(...)]` attribute at all. All public fns have required doc sections. Clippy passes with `-D warnings`.

## Success criteria (end-state)

1. `cargo clippy --all-targets --all-features -- -D warnings` exits 0.
2. `cargo build --release` finishes with 0 warnings.
3. `grep -rn "#\[allow\|#!\[allow" src/` prints nothing.
4. `clippy.toml` either absent or contains no threshold bumps (non-threshold settings OK).
5. All existing functional behavior unchanged — no `bt/m` throughput regression, no new runtime errors, 6 intermediate commits all pass clippy+build gates.

## Non-goals

- No throughput optimization — that's a separate spec (`2026-04-20-infra-overhead-instrumentation-design.md`).
- No new tests — codebase has no existing test harness; adding one is out of scope here.
- No rustfmt changes beyond what clippy-fix produces naturally.
- No dependency upgrades.
- No MSRV change.

## Risk and rollback

- Phase 1 is low risk (mechanical).
- Phase 2 could expose a latent `Send` issue; rollback is trivial (re-add the allow).
- Phase 4's parameter struct refactor touches function signatures across files; verify each call site compiles and the struct field names are unambiguous.
- Phase 6b is mechanical but high-volume; commit after each module to keep diffs reviewable.

Each phase is its own commit. Rollback = `git revert <phase-commit>`.

## Verification command (runs after every phase)

```
cd /home/bwg/qc_work
cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tail -10
cargo build --release 2>&1 | tail -5
grep -rn "#\[allow\|#!\[allow" src/ | wc -l   # should monotonically decrease
```
