# 0.8.9 test and release plan

Run from /home/vic/qc_work. This package distinguishes executable local review cases from specified integration tests requiring implementation/data/cloud execution. It is not a claim that all planned tests have run.

## Reproduce the review

```bash
PYTHONPATH=. .venv/bin/python -m pytest strategies/sstrangle/poc/v088/test_axis.py -q
PYTHONPATH=. .venv/bin/python -m pytest strategies/sstrangle/research/design_20261030_v089/tests/test_v089_acceptance.py -q --tb=short
```

Current expected observations: baseline 29 pass; adversarial 14 fail and 2 pass. The second command must exit nonzero against v088. Do not convert failures into xfail or change assertions merely to make the report green. Upon implementing v089, move imports/fixture construction to the new contracts and retain these economic/causal oracles. T03 will use quality-ledger state; T10 must additionally assert invalid-shadow status and native callback counts. T11 must test repeated finish and incomplete tails as well.

## Test layers and exact release gates

| Layer | Inputs / procedure | Oracle and pass criterion | Current status |
|---|---|---|---|
| L0 regression | Existing synthetic 29 tests plus T01–T12 and C01–C02 | No regression; all new requirements pass on v089, no waived cases | Executed against v088; 14 failures |
| L1 streaming determinism | Generate 25 calendar sessions; exact threshold equality, 10x overshoot, zero activity, gaps before/after crossing, delayed rows, revisions; checkpoint at every minute | Batch, online, prefix and restored outputs have identical IDs/values/reasons at every decision. Future suffix perturbation leaves past decisions unchanged | Specified; v089 needed |
| L2 calendar/quality | Verified regular, early-close, DST-adjacent and holiday fixtures; duplicate/overlap calendar, wrong label, missing last minute; decisions at open/close and outside interval | Invalid calendars reject. Regular 390 / early 210 intervals; snapshot endpoint handled separately. Gap invalidates only from known time; no cross-gap/overnight return. Finish exactly once | Partially covered locally; expanded verified fixtures needed |
| L3 provider contract | Verify pinned receipt content and every consumed file hash; full declared minute/contract coverage, source type, clocks, quality, listing and methodology | Zero unclassified duplicates/mismatches; all missing cells/exclusions recorded. Strict accepts no unknown clocks or unaccepted model; known future rejected in every mode | Blocked for strict release; staged diagnostics permitted |
| L4 option package | Quote sequences valid→crossed→valid, stale underlying/new Greeks, conflicting ties, same-time decision, new listing, expiry mismatch; 4-leg times at 29/30/31 seconds skew | Latest-state rule, <decision availability, age <=120, skew <=30; selection itself invokes gates, logs all exclusions. No older quote revival | T01/T02/T09 executable; selector tests to implement |
| L5 state/output | Corrupt partial, cursor, history, source/calendar pin; kill writer before final manifest; replay long input by chunks | Invalid restore fails; no duplicated emitted IDs, no completed marker on partial output; memory bounded by configured buffers rather than total rows | T05 executable; expanded integration pending |
| L6 QC short shadow | Preregister identical baseline/shadow source and config on regular+early-close sample; include last-session end, unavailable data and telemetry quota fixtures | Readback matches; actual bar/decision sidecars reconcile; original callback exactly once; orders, quantities, times, fees, official-expiry cash and daily equity equal baseline within cents; injected observer failure marks shadow invalid without changing baseline trading | No cloud execution in this review |
| L7 statistical axis | Common eligible sessions after shared warmup, fixed recipes; chronological development/validation/replication, session-block uncertainty | Report dispersion, duration, overshoot, tails and dependence with exclusions and effective sample. No IID assertion or profit-max selection. Tradeoffs leave recipe selection unresolved | Requires accepted underlying minutes and corrected features |
| L8 funded replay | Separate immutable identities, accepted data + frozen source after L0–L6; C0/C1/P1 native funding/cost/official accounting | Reconcile every order/admission/skip/expiry/cash/mark; preserve margin interventions; report drawdown and capacity. Margin failure is a result, not rerun-to-pass trigger. P1 one/day has no 360/400 annual count gate | Not authorized for release by passing synthetic tests alone |

For L1 use a simple independent scalar reference accumulator and Decimal cash calculations where relevant; do not copy production implementation into the oracle. Floating comparisons require predeclared tolerance (returns/activity absolute 1e-12, money $0.01); discrete IDs, counts, clocks and exclusion reasons require exact equality. Separate deterministic rounding policy from actual economic differences.

## Provider delivery acceptance checklist

Require native one-minute full-session option snapshots, not only the old 13 slot windows; quote event and availability provenance, per-Greek computation/input/availability clocks, exact expiry-time methodology, contract listing/expiry eligibility, sizes/conditions and no-fill-forward flags. Require separately verified SPX one-minute underlying OHLC and SPY actual traded notional/minutes for their respective recipes; option underlying reference snapshots do not substitute automatically. Calendar, source corrections and official settlement publication clocks must be pinned independently. Retain missing-field reasons instead of invented values. A completed stage receipt is not canonical publication.

On delivery: first freeze identity and hash consumed artifacts; validate schema/receipts; run a small independent roundtrip and clock audit; then replay the declared period with coverage/exclusion report. Never replace original pinned evidence or use the words strict-ready based solely on delivered row count. The current inventory is in ../../results/review_v088_20261030/provider_inventory.json.

## Execution and evidence rules

Each run saves code/contract/calendar/data hashes, command, exit status, environment versions, test counts and machine-readable results. Keep baseline and adversarial results separate. Store source-readback and complete orders before reusing a QC project. Reconcile authoritative DuckDB queues and terminal remote identities before any worker/controller action; no duplicate controllers or uncertain-create retries. Cloud tests need a concrete immutable preregistration once implementable, not a placeholder submission.

Stop progression at a failed hard gate; work on the cause and its smallest reproducer. Do not repeatedly poll or launch a long backtest to investigate a local defect. Use staged data to exercise diagnostic paths while preserving strict exclusions. The release remains pending until evidence for each required layer is present; the test matrix records which cases are executable now versus specifications.
