# 0.8.9 implementation

Versioned implementation of the corrected custom-axis design. Original v088 sources and review failures remain unchanged. This adds causal sampling and fixed-schedule shadow telemetry; it does not introduce a new entry rule or claim funded economic acceptance.

## Delivered modules

- `axis.py`: streaming thresholds and boundaries, as-of gap events, return anchors/minute variation, session identity, bounded retention and integrity-checked checkpoints with source cursor/calendar pin.
- `shadow.py`: gap-aware features, independent input/quote/Greek clocks, latest-known market validation, actual selected-package skew gate and isolated observational callback.
- `contracts.py`, `pipeline.py`: receipt-content binding, published/staged distinction, calendar/decision coverage, per-session replay and streamed JSONL output with a completion manifest written last.
- `qc_adapter.py`, `build_qc_shadow.py`: isolated observer, actual engine receipt clock, bounded telemetry shards under unique run IDs, explicit idempotent finalization and preserved native strategy body.
- `provider_bundle.py`: read-only canonical snapshot importer for a sampled SPY close-times-volume diagnostic, including source hashes and exact option canonical/stage parity. It does not promote strict readiness.
- `provider_stage_smoke.py`: one-minute quote/Greek alignment and package selection against retained staging artifacts; preserves known clocks.

Use the event-bearing Axis object with `features(axis, decision_at)`. A bare bar list is retained for descriptive/legacy tests but cannot prove there was no intervening gap. The production pipeline and adapters use Axis state. `last_return` now means consecutive complete-bar close return; `open_to_close_return`, minute variation and event-return squared sums have separate names. There is no return anchor across session or gap boundaries.

## Tests

From `/home/vic/qc_work`:

```bash
PYTHONPATH=. .venv/bin/python -m pytest strategies/sstrangle/poc/v089 -q
```

The original adversarial suite remains under `research/design_20261030_v089/tests` targeting v088 and intentionally still fails there. `test_acceptance.py` targets v089, using the event-bearing feature API for T03 and a correctly resealed fixture for T07, so the calendar test exercises the calendar gate rather than failing earlier on receipt integrity. Neither test weakens the original acceptance assertion.

## Bundle and replay

Consumer manifest: version `0.8.9`, status `verified`, release identity, native frequency 60, upsampled false, four hash-pinned files (`minutes`, `calendar`, `decisions`, `options`) and a hash-pinned verification receipt. Receipt content must match release, frequency and every artifact hash. Provider bundles declare staged/published state, coverage and calendar verification; strict mode additionally requires canonical publication and strict replay readiness. Option/Greek row clocks are independently checked during replay. Fixture attestations cannot be relabeled as provider data.

Large provider tables use Parquet. Calendar and decisions use JSON. The engine holds one underlying session and a bounded bar/history buffer; option queries load only each decision's two-minute window. Sidecars are JSONL, not the old whole-history JSON arrays. Verify `COMPLETE.json` and its hashes before treating output as complete. Interrupted/failed output has no completion marker and must not be reused as a new identity.

```bash
PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v089.pipeline \
  --bundle /absolute/path/to/manifest.json --out /new/evidence/directory \
  --recipe spy_close_volume --mode sampled
```

For a newly published native-minute source, use a new snapshot/data-run identity. The canonical importer CLI takes `--snapshot`, `--stage-proof`, `--start`, `--end`, and a fresh `--out` directory. It is deliberately a sampled SPY importer. The full strict SPX pipeline remains gated on verified SPX OHLC/warmup, historical clocks, point-in-time listing evidence and accepted Greek methodology. No fabricated SPX volume, five-minute upsampling or source substitution.

## QC boundary

Assembly copies frozen v087 trading source with initialization, observation and finalization hooks. It exports hashed sidecar shards to Object Store under a fresh UUID; native orders, funding and margin models remain untouched. Only observer-owned exceptions are isolated. A telemetry failure invalidates the shadow; native strategy exceptions still propagate. Local bridge tests are not cloud API or account-parity acceptance. Short cloud verification and full funded replay remain separate gates.

See `../../results/custom_axis_v089_20261030/RESULTS.md` for actual runs and remaining limitations.
