# 0.8.7 — implementation, independent replay and continuous QC validation

The frozen design is `../../research/design_20261027_v087/`. Execution evidence is `../../results/qc_poc_20261027_v087/`, especially `RESULTS.md`, `results.json`, `coverage_snapshot.json`, `local_summary.json`, and native account folders. Three accounts are isolated: C0 unfiltered condor, C1 frozen QQQ-range-filter condor, P1 one 10:00 ET put spread. P1 uses exact 20-point protection and a 2% previous closing-equity risk cap.

Status at implementation: three native smoke accounts completed; full native baselines/verification running serially. The independent primary predecision run is data-blocked. Equal-time provider sensitivity runs on 195 SPXW sessions and is not complete historical performance. Strict timestamps, gamma and native/local funding parity remain unproven. No live deployment.

Use the workspace `.venv/bin/python`. Added dependency: exchange-calendars 4.13.2. Native worker timeout is 3600 seconds. Before any restart inspect actual processes and queue/cloud identities; never restart the worker with nonterminal cloud work. Do not launch duplicate controllers. Controller processes may survive a chat turn.

Execution sequence:

1. `audit_coverage.py` creates the initial pinned provider snapshot. Once research runs, do not overwrite this snapshot; a new data release requires a new run identity.
2. `campaign.py smoke` runs the July 8–15, 2022 controls and companion.
3. `research.py` independently selects and accounts from provider Parquet. `diagnostics.py` compares daily feature values and input quality.
4. `continue_pipeline.py` waits for all smoke audits, then archives three full baselines and three fresh verification runs. It requires the independent local attempt before verification.
5. `analyze.py`, `bridge.py`, `report.py` produce native arithmetic checks, fixed-contract attribution, reports and hashes. `finalize.py` refreshes these as primary native accounts finish.
6. `cloud_validation.py` waits for primary verification, then runs the separately frozen `cloud_test_plan.json`: adverse fills, half-equity reserve, DST/early close. Failure records are preserved; unknown transport/create states stop submissions for diagnosis.

The user requested continuous QC testing until further instruction. An app heartbeat named **Continue 0DTE QC validation** checks this work every 15 minutes, diagnoses failures and designs the next distinct test after the matrix. It must honor later steering, avoid duplicate runs and report meaningful findings only. No new resource/subscription purchases or live orders are authorized.

Tests: `PYTHONPATH=scripts:strategies/sstrangle/poc/v087 .venv/bin/python -m pytest strategies/sstrangle/poc/v087/test*.py strategies/sstrangle/poc/v085/test_native_audit.py strategies/sstrangle/poc/v085/test_strategy_features.py -q`.

The local price/funding ledger is independent of QC; source-specific same-input fixture checks are separate from market equivalence. Final flags must distinguish native arithmetic, native reproducibility, sampled independent completeness, strict replay, economics and live readiness. Failed or partial accounts cannot supply valid full-period statistics. The old four-leg quote-side credit deduction was corrected to use actual leg count for P1; frozen v085 files are unchanged.

## Execution and settlement focus (2026-10-27)

Latest user instruction prioritizes realistic fills and settlement differences, followed by a consolidated report for both strategies. All three full baseline/verification pairs reproduced exactly. Unfiltered quote-side execution failed with a native margin call on 2024-01-08; its raw orders, terminal response, logs and matching cloud source are preserved. Do not report its truncated account as successful.

`extended_evidence.py` is a singleton read-only failure archiver and report monitor. It replaces the completed primary `finalize.py` monitor for subsequent diagnostics. `continue_settlement_diagnostics.py` waits for the entire existing matrix to terminate and archive before submitting four short probes from `settlement_diagnostic_execution_plan.json`. It uses a separate telemetry-only adapter; the primary strategy is unchanged. Do not launch duplicate controllers.

`settlement_revalue.py` reprices fixed native trade tapes using the frozen provider release's official settlement values. It covers every baseline trade but does not recalculate funding, admissions or margin. Full-baseline P&L deltas: C0 -$40,058; C1 -$11,631; P1 -$2,817. The native expiry-clock cause remains unproven. Evidence and current status are in `RESULTS.md`, `official_settlement_fixed_tapes.json/parquet`, and each diagnostic's evidence folder. The automation continues analysis and refreshes the final report as tests finish; the full independent pipeline remains unaccepted.
