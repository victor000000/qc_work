# Project handbook and continuation guide

Validation addendum 2026-11-05: [latest results](../strategies/sstrangle/results/validation_v090_20261105/RESULTS.md). Cloud jobs have now executed: regular C0 account parity passed, but incomplete observer sessions, early-close failures and restricted sidecar export block full acceptance. The October 31 procedures and October 30 evidence below remain dated references. Use the updated backlog before further cloud work.

Updated 2026-10-31. This is the reusable workspace guide. Verified SSTRANGLE results referenced here were produced on 2026-10-30; this documentation update does not establish new cloud or provider status.

## Current release boundary (reviewed 2026-11-07)

The executor is 1.2.0, the axis engine below is 0.9.0, and the newest diagnostic tool is [0.9.2](../strategies/sstrangle/poc/v092/README.md). Versioned engines and diagnostic modules have different identities; the 0.9.2 release did not rename the feature engine or establish a margin/IV solver fix.

Use [configuration](CONFIGURATION.md), [environment](ENVIRONMENT.md), [CLI](../USAGE.md), [operations](OPERATIONS.md) and [CI](CI_CD.md) for current setup/operation commands. The detailed contracts and reproduction below retain the v090 research scope. Links to omitted results, adjacent provider paths and `.local` records are operational-only evidence references; public source does not include those datasets. Synthetic fixtures must remain labeled synthetic. A sampled replay never silently satisfies strict historical availability gates.

For a bounded new probe, assemble source with `python -m strategies.sstrangle.poc.v092.build_probe --help`, then inspect its base/plan hashes before any separately scoped cloud submission. Decode exported runtime statistics through `python -m strategies.sstrangle.poc.v092.receipt --help`. Help calls are safe; assembly writes a new source directory. A complete set must pass integrity, schema, phase and window checks. Callback labels do not establish margin-scan order.

## 1. Start here

This workspace combines a shared Rust QuantConnect (QC) executor with separate Python strategy research projects. The feature-engine SSTRANGLE design is [0.9.0](../strategies/sstrangle/research/design_20261030_v090/DESIGN.md). Its local engineering tests and sampled PoCs pass. Strict provider data, actual QC cloud parity and funded economic acceptance remain open.

Read [current work](CURRENT_WORK.md) for dated results, [next steps](TODO.md) for dependencies, and [CLI usage](../USAGE.md) before operating the executor. Historical reports and saved continuation files describe their own run identities; they are not live queue monitors.

| Question | Authoritative starting point |
|---|---|
| What is the intended 0.9.0 behavior? | [Design](../strategies/sstrangle/research/design_20261030_v090/DESIGN.md) |
| What actually ran? | [Results](../strategies/sstrangle/results/custom_axis_v090_20261030/RESULTS.md), [acceptance matrix](../strategies/sstrangle/results/custom_axis_v090_20261030/acceptance_matrix.json) |
| Which exact code/data produced it? | [Evidence manifest](../strategies/sstrangle/results/custom_axis_v090_20261030/manifest.json), each replay's `input_manifest.json` and `COMPLETE.json` |
| How does the execution infrastructure work? | [Architecture](ARCHITECTURE.md), [CLI usage](../USAGE.md) |
| How should databases be accessed? | [DuckDB access protocol](DUCKDB_MIGRATION.md) |
| Where does acquisition belong? | Adjacent `/home/vic/data_providers` project; this project consumes pinned deliveries |
| What remains unfinished? | [Current backlog](TODO.md), [0.9.0 continuation state](../strategies/sstrangle/results/custom_axis_v090_20261030/continuation_state.json) |

## 2. Workspace map and ownership

| Location | Responsibility |
|---|---|
| `crates/qc-server/` | Rust CLI, QC API client, scheduling, queues and execution persistence |
| `qc_storage/` | Shared Python storage support |
| `tests/` | Workspace Python tests |
| `scripts/` | Setup, checks, migration, export and operational utilities |
| `strategies/s001/`, `s002/`, `sml01/` | Separate fundamental/cross-sectional/ML projects; use their own instructions and tests |
| `strategies/sstrangle/` | Options strategies, local engines, versioned PoCs, designs and evidence |
| `strategies/ss45dte/` | Separate options strategy; SSTRANGLE revisions do not automatically change it |
| `strategies/wang-ml/` | Separate historical ML research and references |
| `data/` | Private runtime databases, logs and pool configuration; credentials are stored separately |
| `docs/` | Workspace architecture, operations, status and navigation |
| `workspaces/` | Imported LEAN/incubation resources; see its README |

Keep research outputs separate from queue state. Preserve frozen strategy sources and failed campaigns. A new design number does not update an old funded account or turn an old failure into success.

## 3. Environment and setup

Use native Linux or Ubuntu WSL and the Linux virtual environment. Commands below assume `/home/vic/qc_work` as the current directory. Docker is unnecessary for the documented default workflow.

For a new environment, install the prerequisites described in [ENVIRONMENT.md](ENVIRONMENT.md), then run:

```bash
cd /home/vic/qc_work
./scripts/setup.sh
```

The setup script checks Rustup, creates/reuses a Python 3.12 `.venv`, installs `requirements-dev.lock`, installs workspace Python packages in editable mode and builds the release binary. Rust is pinned in `rust-toolchain.toml`. Do not rebuild or reinstall a working environment merely to read documentation or inspect saved results.

```bash
.venv/bin/python --version
.venv/bin/python -c 'import duckdb, pyarrow, pandas, pytest; print("research imports OK")'
```

The research stack includes DuckDB and PyArrow for bounded Parquet replay. QC supplies its own cloud runtime: local imports and compilation cannot prove cloud API compatibility. Credential names and executor configuration are documented in the root README; never copy secret values into reports, commands saved in documentation, or source control.

## 4. SSTRANGLE 0.9.0 code map

All paths in this table are under `strategies/sstrangle/poc/v090/`.

| Module | Main interface | Responsibility |
|---|---|---|
| `axis.py` | `Axis`, `seed`, `begin`, `update`, `finish`, `checkpoint`, `restore` | Streaming calibration, minute consumption, gap segmentation, bars and restart state |
| `shadow.py` | `features`, `align_options`, `select_package`, `ShadowAdapter` | Causal features, latest-known quote validation, package clock gate and isolated callback |
| `contracts.py` | Calendar, receipt and strict-provider validators | Structural identity, artifact attestation and admission gates |
| `pipeline.py` | `read_bundle`, `run`, CLI | Session replay, decision-time observations, streamed evidence and final completion hashes |
| `fixtures.py` | `make_bundle`, `seal_fixture` | Explicit synthetic inputs and test-only receipt creation |
| `audit_axis.py` | `audit` | Per-session descriptive output |
| `compare_axes.py` | `read_complete`, `compare`, CLI | Same-source paired-session diagnostics and bootstrap intervals |
| `qc_adapter.py` | `QCShadow` | Isolated native-minute observer, sidecar export and finalization |
| `build_qc_shadow.py` | `build`, CLI | Assemble frozen v087 strategy with observation hooks; does not submit it |
| `test_axis.py`, `test_acceptance.py`, `test_integration.py`, `test_v090.py` | pytest cases | Behavior, causal oracles, restart, provenance, output and bridge checks |

The additional [review test](../strategies/sstrangle/research/design_20261030_v090/test_review.py) selects the old or new implementation using `AXIS_REVIEW_VERSION`. It intentionally fails on v089 for four documented defects. Keep these historical failures distinct from current acceptance tests.

The observed pipeline is: pinned bundle → receipt/calendar validation → streaming axis → as-of decision features and option alignment → JSONL evidence → completion manifest → matched-session comparison. Package selection is available separately in `shadow.py`; the replay's aligned-candidate count is not a count of selected packages or executed trades.

## 5. Behavioral contracts to preserve

- A native minute is a 60-second observed interval, not a five-minute row replicated five times. Reject fill-forward and wrong-underlying inputs.
- Decisions use information available strictly before their deadline. Equal-time observations are excluded by default. Sampled mode may assume missing clocks; known future clocks remain invalid.
- Thresholds use 20 complete positive-activity prior sessions available before the open, divided by target 26. Zero-activity observed sessions can be complete without entering calibration.
- A missing minute resets the return anchor and creates a new segment when the gap is known. Completed decisions are immutable. Partial bars and tails do not become ready features.
- Activity bars consume whole minutes and record overshoot. Time controls use 15-minute boundaries from session open. `control_symbol=SPY` explicitly permits the matched SPY time experiment; the default control remains SPX.
- Latest known invalid quotes block the affected contract. Conflicting latest ties exclude that contract; healthy contracts remain usable, and a strictly newer unambiguous observation can recover it.
- Quote, Greek as-of and underlying-input ages must each satisfy the 120-second gate. Selected-leg quote skew must satisfy the 30-second gate. Listing and Greek-method claims still need provider evidence for strict acceptance.
- Event returns use the preceding completed close in the same segment. Minute variation, squared event-return sums and open-to-close returns have distinct meanings.
- Observer failures invalidate telemetry. Native trading/funding exceptions propagate. Source-body preservation and local mocks are preliminary checks, not account parity.

Consult the design and executable tests for boundary cases. Do not weaken an oracle just to obtain a green suite; document intentional contract changes and retain the old reproducer.

## 6. Input bundle and output reference

A consumer manifest identifies version (`0.8.9` or `0.9.0`), verified status, release, native frequency 60, `upsampled=false`, input kind, four file references and a pinned verification receipt. Each reference has `path` and `sha256`. The four required inputs are `minutes`, `calendar`, `decisions` and `options`.

Provider minute/option tables must be Parquet; small fixture inputs can be JSON. Paths resolve relative to the manifest. The receipt must attest the same release, frequency and artifact hashes. Provider state must explicitly be staged or published and match publication attestation, with coverage and calendar verification. Strict provider replay additionally requires published state and `strict_replay_ready=true`; subsequent row-level validation still applies. Never edit a failed receipt into a passing one.

| Input | Key fields and interpretation |
|---|---|
| Calendar | `session`, `open`, `close`; UTC-aware bounds with New York session identity |
| Minute | `session`, `symbol`, `start`, `end`, `available_at`, native frequency, OHLC, `source_row_id`; volume or traded notional as the recipe requires |
| Decision | `decision_at` and preserved strategy payload; deadline must fall in a declared session |
| Option | Contract identity/root/expiry/listing flag, observation and quote clocks, Greek availability/as-of/input clocks, native frequencies, accepted-model flag, bid/ask/delta/spot and provenance; package selection also needs strike/right |

The calendar validator checks structural consistency, not independent exchange truth. Provider calendar provenance is therefore necessary. Receipt hashes establish integrity and binding, not authenticity without a trusted external source.

| Output | Use |
|---|---|
| `axis_bars.jsonl` | Complete/incomplete bars, IDs, segments, activity, thresholds and source rows |
| `axis_thresholds.jsonl` | Frozen daily thresholds and calibration source end |
| `session_audit.jsonl` | Expected/observed minute counts and session completeness |
| `quality_events.jsonl` | Gap/invalidation evidence with known times |
| `decision_shadow.jsonl` | Original decision plus as-of axis features/status |
| `aligned_options.jsonl` | Candidate observations and explicit exclusions per decision |
| `axis_diagnostics.jsonl` | Descriptive session statistics |
| `axis_state.json` | Final integrity-checked checkpoint |
| `axis_quality.json` | Run summary, source/calendar hashes and scope |
| `input_manifest.json` | Original consumed manifest |
| `COMPLETE.json` | Written last; hashes all completed run files |

No completion marker means incomplete output. Use a fresh directory for another attempt. Compare code verifies output inventory and hashes; do not add unmanifested files inside a completed replay directory. Keep annotations in a sibling report.

## 7. Tests and reproduction

The general workspace check runs Rust formatting/Clippy/tests and Python project suites:

```bash
./scripts/check.sh
```

It does not include versioned v090 acceptance tests. Run these explicitly:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  strategies/sstrangle/poc/v090 \
  strategies/sstrangle/research/design_20261030_v090/test_review.py -q
```

Expected saved result: 91 passing cases. The complete recorded 417-case command is:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests strategies/sstrangle/tests \
  strategies/sstrangle/poc/v088/test_axis.py strategies/sstrangle/poc/v089 \
  strategies/sstrangle/poc/v090 \
  strategies/sstrangle/research/design_20261030_v090/test_review.py -q --tb=short
```

Do not recursively collect every historical review directory and expect all tests to pass. The old-version defect reproduction is deliberately nonzero:

```bash
AXIS_REVIEW_VERSION=v089 PYTHONPATH=. .venv/bin/python -m pytest \
  strategies/sstrangle/research/design_20261030_v090/test_review.py -q --tb=short
```

Expected: four failures, exit 1. [Saved final tests](../strategies/sstrangle/results/custom_axis_v090_20261030/final_tests.txt) record the successful current suite. Counts are dated evidence, not a promise that future edits cannot add cases.

### Fresh synthetic PoC

Use a new temporary output identity. The following runs all four synthetic recipes without contacting QC or the provider:

```bash
PYTHONPATH=. .venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import mkdtemp
from strategies.sstrangle.poc.v090.fixtures import make_bundle
from strategies.sstrangle.poc.v090.pipeline import run
out = Path(mkdtemp(prefix='axis-v090-'))
bundle = make_bundle(out / 'input')
for recipe in ('spx_variation', 'spy_dollar', 'spy_close_volume', 'time_control'):
    print(run(bundle, out / recipe, recipe))
print('Artifacts:', out)
PY
```

Expected completed bars are 57, 60, 60 and 92 respectively. Fixtures establish engineering behavior and cannot be promoted to provider evidence using `seal_fixture`.

### Fresh real-data sampled comparison

This uses the retained delivery; availability of its files is required. The source identity stays unchanged. Every output directory is new.

```bash
axis_run_dir=$(mktemp -d /tmp/axis-v090-real-XXXXXX)
axis_bundle=/home/vic/qc_work/strategies/sstrangle/results/custom_axis_v089_20261030/canonical_sampled_bundle/manifest.json
PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v090.pipeline \
  --bundle "$axis_bundle" --out "$axis_run_dir/activity" \
  --recipe spy_close_volume --mode sampled
PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v090.pipeline \
  --bundle "$axis_bundle" --out "$axis_run_dir/control" \
  --recipe time_control --control-symbol SPY --mode sampled
PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v090.compare_axes \
  --left "$axis_run_dir/activity" --right "$axis_run_dir/control" \
  --out "$axis_run_dir/comparison.json"
```

Expected: 37 declared sessions, 33 complete, activity 278 bars, control 858 before common-session restriction. Comparison uses 13 complete post-warmup sessions, 278 versus 338 bars. Both decision replays have 12 ready features among 13 October 22 decisions. The same provider bundle is expected to reject strict mode before output creation.

## 8. Interpreting evidence and troubleshooting

| Observation | Meaning and next action |
|---|---|
| `strict provider replay not ready` | Required attestation is absent. Obtain a new verified delivery; do not relabel sampled output |
| Delivery/receipt hash mismatch | Artifact bytes differ. Locate the original pinned files or create a new source identity with valid verification |
| `new output identity required` | Destination exists. Use a fresh directory and retain the previous attempt |
| `no_completed_axis` | Warmup or first event is not ready. Inspect thresholds and source coverage |
| `gap_waiting_for_complete_axis` | A known gap invalidated the previous segment; wait for a complete new-segment bar |
| `stale_axis` | Last eligible completed bar is older than 30 minutes |
| Conflict or invalid-clock exclusions | Inspect affected source rows; retain reasons and healthy-contract results |
| Missing `COMPLETE.json` | Replay failed or was interrupted. Preserve logs; fix the smallest reproducer and use new output identity |
| Incompatible comparison | Underlying, release, hashes, mode, calendar or input kind differs. Recreate a genuinely matched pair |
| QC polling timeout | Local transport status is insufficient. Reconcile remote run identity before retrying or restarting |

A completed sampled run proves a pipeline completed under stated assumptions. It does not establish historical availability, listing eligibility, accepted Greeks, realistic fills or profitability. The 13-session comparison is historical and small; its session bootstrap does not capture inter-day dependence. No recipe was selected by the saved comparison.

## 9. Continuing the project

1. Inspect current design, acceptance matrix and continuation state. Reconcile actual queues/provider inventory before operational actions; dated documentation is not live state.
2. For strict data work, require verified SPX minute warmup, historical quote/Greek/input clocks, point-in-time listing and accepted expiry-time Greek methodology. Freeze the new delivery and record missing coverage explicitly.
3. Rerun the smallest relevant causal checks, then a fresh bounded replay. Record commands, exit codes, environment and source/input/output hashes.
4. Prepare a short QC baseline/shadow comparison with frozen source/config, source readback and actual sidecar collection. Validate orders, quantities, times, fees, official expiry cash and equity. Reconcile authoritative queue state before submission; never restart an active controller to force progress.
5. Only after the hard gates pass, freeze the funded experiment. Preserve native margin interventions and failed outcomes. One-entry-per-day P1 does not inherit the old 360/400 annual trade-count gate.

There is no active background controller created by the 0.9.0 task. The unsubmitted source assembly is not evidence of an executed cloud job. Existing historical funded results remain separate from the custom-axis PoC.

## 10. Documentation maintenance and handoff

Update the current-work summary when evidence changes, the backlog when dependencies change, and the README/index when the current design changes. Keep detailed behavior in the versioned design, runnable commands in this handbook or module README, and measured results beside immutable run outputs.

For each handoff, record: objective; current code/design version; immutable source and data identity; completed commands and outputs; failed cases; exact pending gates; live run IDs if verified; and the next bounded action. A new contributor should be able to reproduce a local result without access to this chat.

Do not rewrite a frozen design/evidence manifest to disguise changed assumptions. Create a new revision or a dated addendum. Retain failed review cases and original inputs, and verify documentation links after moving files. No credentials or licensed raw-data dumps belong in documentation.
