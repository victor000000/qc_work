# 0.8.8 custom-axis implementation

This release implements the custom-axis **fixed-schedule shadow** specified in the Wang-materials design. It does not add a learned gate or axis-triggered orders. Frozen 0.8.7 sources/results are not changed.

Implemented:
- `axis.py`: SPX squared-log-return, SPY actual traded-value, separately labeled close×volume approximation, and anchored 15-minute control. Prior-20-complete-session thresholds, 26-event target, session/gap handling, one crossing per input minute, state restart.
- `shadow.py`: closed-bar features, age gating, strict/sampled option alignment and cross-leg quote-clock gate; frozen selector wrapper returns the original result unchanged.
- `pipeline.py`: hash-pinned verified JSON/Parquet bundle ingestion, immutable output directory, full axis/session/threshold/feature/candidate evidence. Parquet option history is queried in bounded two-minute decision windows. Underlying minute history and evidence outputs are currently retained in memory; full-history memory profiling remains necessary before scaling to all symbols/years.
- `qc_adapter.py`, `build_qc_shadow.py`: QC minute bridge and separate source assembly with two telemetry hooks. Removing the hooks reproduces the frozen base source exactly. Assembly compiles and local bridge tests pass; cloud execution has not yet been performed. The example assembly uses a synthetic calendar and must never be submitted as a market test.
- `audit_axis.py`: duration/activity/overshoot, session event counts and within-session return/squared-return dependence summaries. No automatic optimization or IID assertion.
- `provider_stage_smoke.py`: consumes verified staged native1m Parquet for sampled alignment/frozen-selector smoke, separately from strict/full replay acceptance.
- `provider_preflight.py`: reads raw pilot receipts, verifies SHA256 and quote/Greek keys/grid/price parity. It does not promote raw data to verified provider publication.

Run tests from `/home/vic/qc_work`:

```bash
PYTHONPATH=. .venv/bin/python -m pytest strategies/sstrangle/poc/v088/test_axis.py -q
```

Run a delivered and normalized bundle:

```bash
PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v088.pipeline \
  --bundle /absolute/path/to/consumer_manifest.json \
  --out /absolute/path/to/new_v088_result_identity \
  --recipe spx_variation --mode strict
```

When historical clocks are unavailable, `--mode sampled` is a separately labeled diagnostic. It never promotes a run to economic acceptance. A fixed-0.15-DTE vendor Greek method cannot pass strict mode without explicit independent methodology acceptance. Missing underlying warmup prevents information-bar features until 20 complete sessions exist; the pipeline does not synthesize history.

## Consumer bundle contract

Manifest requires `version: "0.8.8"`, `status: "verified"`, `release`, `frequency_seconds: 60`, `upsampled: false`, `input_kind`, `verification_receipt: {path, sha256}`, and `files` mapping `minutes`, `calendar`, `decisions`, `options` to `{path, sha256}`. Paths resolve relative to the manifest. JSON arrays or Parquet are supported. The consumer normalizer must tie these hashes to the provider's verified immutable release and receipt; do not merely set a status on unverified raw data. Fixtures use `input_kind: "synthetic_fixture"` and never represent market evidence.

Minutes: `session` ISO NY day, `symbol` SPX/SPY, timezone-aware `start/end`, nullable `available_at`, `frequency_seconds=60`, raw `open/high/low/close`, `source_row_id`, optional `is_fill_forward=false`; actual `trade_notional` for spy_dollar or real `volume` for spy_close_volume. One-minute underlying bars have end=start+60 seconds. Do not treat a snapshot at 09:30 as a completed 09:30–09:31 trade bar.

Calendar: `session, open, close`, actual instrument session boundaries with aware UTC times. Never infer the trading calendar from rows that happen to exist.

Decisions: `decision_at` timezone-aware plus the original frozen decision/order fields. The runner attaches a sidecar and leaves these fields unchanged. Missing features do not suppress existing trades in shadow mode.

Options: `contract_id, root, expiry, listed_asof, observed_at, quote_ts, available_at, greek_asof, greek_available_at, greek_input_at, frequency_seconds, greek_frequency_seconds, greek_model_accepted, bid, ask, delta, spot, source_row_id`, optional `is_fill_forward`. Both frequencies must be 60. Strict mode rejects unknown/late/stale clocks, unaccepted Greek models, wrong expiry/root, ineligible listings and invalid markets. Keep actual quote clocks distinct from sampling clocks. Preserve sizes/conditions/model details as additional provenance columns. The selected-leg clock gate is applied after selection; alignment alone does not certify a package.

To assemble a separate QC source after obtaining a verified instrument calendar:

```bash
PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v088.build_qc_shadow \
  --base strategies/sstrangle/poc/v087/strategy_official_funded.py \
  --calendar /absolute/path/to/verified_calendar.json \
  --out /absolute/path/to/new_qc_shadow_source
```

This assembles only. Normal campaign submission must still attach the pinned official-settlement and optional alpha input modules, set the frozen configuration, confirm terminal/archive status of previous jobs, and record fresh hashes/identities. The adapter treats native QC delivery as sampled availability, not historical quote availability. Native buying power, margin calls, fees and settlement logic are untouched.

## Current evidence

Results are under `strategies/sstrangle/results/custom_axis_v088_20261029`. Synthetic engineering runs exercise 23 miniature sessions, including 20 warmup sessions. Real provider pilot preflight covers 2024-01-08 and is clearly separated. Full verified one-minute provider replay and QC cloud shadow parity remain pending delivery/integration gates, not completed backtests.
