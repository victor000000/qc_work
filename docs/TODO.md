> Current documentation correction (2026-11-07): executor 1.2.0 / axis engine 0.9.0 / diagnostics 0.9.2. Use [documentation guide](README.md), [CI](CI_CD.md) and [operations](OPERATIONS.md) for current commands. Dated results/checklists below retain their original scope; omitted private artifacts and past account checks are not present readiness certification.

## Current acceptance dependencies — 2026-11-07

1. Validate v092 native group APIs/runtime capacity and exact matched cloud account parity before interpreting probe receipts.
2. Establish actual margin-scan ordering and pre-trigger composition; do not infer either from callback labels.
3. Retain the historical IV cause as unresolved until failing contract/inputs/trace exist.
4. Complete independent sidecar/feature parity, strict provider inputs and economic acceptance separately.

> Latest 0.9.0 validation (2026-11-05): [C0 margin and IV evidence](../strategies/sstrangle/results/margin_verified_v090_20261105/RESULTS.md). 427 tests passed. Cloud-tested diagnostic/API and publication-race fixes preserve exact native account parity. C0 still fails on margin; IV replay passes but historical root cause remains open. Pre-trigger margin state, full sidecar/feature parity, strict provider inputs and economic acceptance remain gaps.

# Next steps

## After warmed C1/P1 parity (2026-11-05)

[Latest evidence](../strategies/sstrangle/results/warmed_v090_20261105/RESULTS.md). Warmed observer execution and native account parity are confirmed for C1/P1 across 31 sessions. Remaining work: authorized independent sidecar/feature-value verification; actual native IV failing-input diagnosis; C0 margin-intervention diagnosis; strict provider acceptance; failure/quota injection and eventual economic release. C0 stopped before warmup and retains its original funding. Earlier tasks requesting initial warmed C1/P1 runs are superseded by these results.

## After the verified clock fix (2026-11-05)

[Evidence](../strategies/sstrangle/results/fix_v090_20261105/RESULTS.md): regular/early-close observer coverage and short C0 account parity are now passed. Earlier coverage/fill-forward tasks below are historical findings resolved by exchange-timezone conversion. Next: authorized sidecar verification, warmed-axis/C1/P1 cloud tests, independent native IV-convergence diagnosis, then strict provider and funded acceptance gates. The IV solver was not changed; a clean fresh baseline is not a general fix.

## Validation findings to resolve (2026-11-05)

[Latest evidence](../strategies/sstrangle/results/validation_v090_20261105/RESULTS.md). Regular C0 account parity is established for the short sample. Before further acceptance: diagnose QC native bar timezone/session coverage (345/390 and 330/390 final-session counts), early-close fill-forward rejection, and the baseline IV-convergence error. Resolve sidecar verification within QC licensing permissions; the download was explicitly denied. Then run a preregistered warmed-axis/C1/P1 comparison. Strict SPX/clock/listing/Greek provider gates and full funded acceptance remain open. Six jobs are terminal; no validation controller remains active.

## Current 0.9.0 continuation (2026-10-31)

Local design tests and sampled PoCs are complete. Use the [handbook](PROJECT_HANDBOOK.md) for reproducible commands and the [acceptance matrix](../strategies/sstrangle/results/custom_axis_v090_20261030/acceptance_matrix.json) for evidence scope.

1. Admit a new pinned provider release with verified SPX warmup, historical clocks, PIT listing and accepted expiry-time Greeks. Done when receipt and row-level strict checks pass with explicit coverage/exclusions.
2. Reconcile live QC queues and prepare a short frozen baseline/shadow comparison. Done when actual source readback, sidecars, orders, fees, expiry cash and equity reconcile; local assembly is insufficient.
3. Freeze a funded experiment only after the preceding hard gates pass. Preserve native margin interventions and failed accounts; report economics separately from engineering acceptance.
4. Preregister future evaluation before inspecting new observations. The existing historical comparison is not an untouched holdout.

The older sections below preserve historical workstreams and their dated dependencies.

## Version 0.8.5 next gates (2026-10-26)

[Design and evidence](../strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.md). The condor baseline/local/final-QC loop is complete; the optional put-spread baseline is rejected on a native margin call. Preserve both outcomes.

1. Diagnose native buying-power/grouping behavior and actual margin-call fills before reconsidering the spread. Do not infer broker equivalence from an isolated maximum-loss formula.
2. Complete official SPXW PM settlement coverage, resolve native-reference differences and evaluate any corrected account path as a new frozen campaign.
3. Follow the [eleven-underlying requirement](OPTIONOMEGA_0DTE_5M_DATA_REQUIREMENTS_20261026.md): inventory, 17-date pilot, quote/availability clocks, gamma/Greek units, and decision-window timing. Current QQQ delivery is sampled and partly populated, not strict admission.
4. Build the complete opportunity ledger and independent quote/selection/funding replay; measure 5m-versus-finer discrepancies before broader research.
5. Preregister genuinely future evaluation and shared-capital portfolio rules. The historical Calmar above 2 is not evidence of robust alpha or deployment approval.

## Previous Draft 0.7.5 sequence (2026-10-26)

[Reviewed design](../strategies/sstrangle/research/design_20261026_v075/DESIGN_REPORT.md). Completed locally: strict quote/package input checker, session and scope planning, archived six-account reproduction and pinned provider-sample diagnostics. Next: finish and admit the bounded SPXW pilot; measure 5m timing/price differences; build the full opportunity ledger and independent quote/settlement replay; only then freeze a bounded experiment and validate its funding natively. QQQ surface readiness is separate from its price bars. Unknown clocks, margin deficits and failed filters remain visible. No new profitable strategy or native campaign is claimed.

## Draft 0.8 completed and remaining (2026-10-24)

Completed: full-equity scope with no Tom caps, 150-feature search, historical walk-forward/cost/threshold/tail/bootstrap diagnostics, frozen rules, matched extended-period native controls/candidates, and a reserved July14–October22 historical interval. All fixed full native runs pass the annual 360 gate. See [report](../strategies/sstrangle/research/design_20261024_v8/DESIGN_REPORT.pdf).

Remaining: robust alpha evidence and prospective validation, stable adaptive frequency control without retrospective selection, independent option-market/margin simulation, and exact Option Omega parity. Passing execution verification is not deployment approval. Tom sizing is deferred at the user's request.

## Draft 0.7 completed and remaining (2026-10-24)

Completed: independent baseline payoff arithmetic, fresh unfiltered condor control, 2,592-rule local search, frozen feature inputs/predicates, three final funded QC candidates, annual >=360 gate, exact common-trade parity and native funding attribution. See [audited report](../strategies/sstrangle/research/design_20261024_v7/DESIGN_REPORT.pdf).

Remaining: exact Option Omega trade export/config parity, independently sourced option paths and official settlement verification, certified historical feature availability, full unfilled-opportunity local simulator, and fresh prospective evaluation. Older entries below describe historical gaps; the three Draft 0.7 candidates now have final funded QC verification.

## Draft 0.65 follow-up (2026-10-24)

Completed: two funded native delta-tolerance tests; annual 360 gate; local 211-field packs and 288-rule screens per baseline; later-period/cluster diagnostics. See [verified design](../strategies/sstrangle/research/design_20261024_v065/DESIGN_REPORT.pdf).

Remaining: original Option Omega trade CSV/config reconciliation; certified intraday/options feature availability; row-level unfilled opportunity ledger; native funded validation before promoting a local alpha; fresh prospective/untouched evaluation. Existing retrospective filters are not validated funded strategies.

Updated: 2026-10-23. Follow this order; this is a backlog, not authorization to purchase data or deploy. [Current work](CURRENT_WORK.md) · [overall design](../strategies/sstrangle/research/design_20261023_v6/DESIGN_REPORT.pdf).

## 1. Review and specify — current work

| ID / type | Deliverable | Done when |
|---|---|---|
| REVIEW-01 / Decision | Review Draft 0.6 and record accepted changes/open questions | Scope, sequence and assumptions are recorded; a draft is not labelled implemented |
| B02 / Detail design | Strategy rules: entry windows, monthly/0DTE variants, exits, overlap, funding and fees | Rules are executable and source-demo uncertainties are explicit |
| F01 / Detail design | Typed feature schema, availability clocks, formula/vector/group operators and label separation | Point-in-time joins and operator semantics have worked examples and test cases |
| DATA-01 / Data gap | Consolidated provider contract for US/CN only, following design review | Keys, timestamps, intervals, quotes/OI/IV, actions, calendars, manifests and coverage gates specified; prior requests clearly superseded where needed |
| U01 / Decision | Initial SPX then SPY/QQQ scope and expansion criteria | Option liquidity and historical availability criteria documented; top-50/top-100 retained as deferred comparisons |

## 2. Prove the smallest complete pipeline — partial PoC evidence

| ID / type | Deliverable | Required evidence |
|---|---|---|
| Q01 / PoC | QC order/trade export and multi-leg round trip | Pagination, identity, quantities, fees, timestamps and account totals reconcile |
| B01 + B03 / PoC + Acceptance | Three SPX baselines, then predeclared parameter neighborhoods | At least 360 complete episodes per included year per ticker; enough usable trades without mistaking overlaps for independent samples; realistic costs/execution |
| D01 + D02 / PoC + Decision | Provider admission and storage/entitlement proposal | Actual coverage, compressed bytes, retention costs and explicit access gaps; no assumed purchase approval |
| T01 / PoC | 5/15/30/60-minute local pipeline benchmark | Measured RAM/disk/CPU/throughput, matching trade paths, risk-clock behavior and AKQuant limitations |
| LOCAL-01 / Acceptance | Versioned trade-feature Parquet plus Jupyter example | One-to-one identities, no lookahead, labels separated, missingness/provenance retained; notebook and batch results agree |

### Next baseline/data detail work

- Draft 0.6 diagnoses the 3,606 wing skips and tests feasible exact-width recovery. Next: predeclare delta-tolerance sensitivities, resolve residual chain gaps, audit native margin groups, and compare source quote/delta definitions and historical expiry fees against the original demo export.
- Freeze a parameter-neighborhood and baseline acceptance plan before selection. The annual count gate is met, but 13 overlapping entries per day are dependent observations.
- Admit the actual SPX provider release and build exogenous entry-safe features on the new tape. Its three native decision fields are not the full proposed provider feature panel.

## 3. Research and validate — pending successful PoC

| ID / type | Deliverable | Required evidence |
|---|---|---|
| F02 / TODO | Expand BRAIN field/formula mappings and candidate search | Reproducible local definitions, bounded resources and complete trial ledger; unsupported inputs flagged |
| R01 / TODO | Robustness specification and staged tests | Time splits, untouched holdout policy, multiple-testing controls, cost stress, parameter stability and Monte Carlo scope declared before selection |
| P01 / Detail design | Funded portfolio construction | Shared capital/margin, exposures, Greeks, correlation and stress tested; no averaging strategy Calmars |
| QC-FINAL / Acceptance | Final QC individual and portfolio tests | Frozen inputs/code, genuine fill/account reconciliation and local-versus-QC differences explained |
| RELEASE-01 / Decision | Review report and version 1.0.0 | Overall design → detail design → measured PoC → revision/review completed; user decides incubation/deployment |

## Measured PoC evidence — 2026-10-23

- Draft 0.6: all three full SPX baselines pass the annual gate and native accounting. [Verified evidence](../strategies/sstrangle/results/qc_three_demo_poc_20261023/final_verification.json) · [findings](../strategies/sstrangle/research/design_20261023_v6/POC_REPORT.txt). Remaining work includes source parity, delta tolerances, margin portability, provider features and OOS validation.

- Frozen Draft 0.5 control: 9,841 whole SPX episodes, all five included years pass >=360, complete native-order/expiry/account reconciliation and zero residuals. Source numerical parity and parameter neighborhoods remain pending. [Evidence](../strategies/sstrangle/results/qc_baseline_poc_20261023/).
- Local checks: 188 historical episodes / 1,134 fills reconcile; 28/28 saved trades have entry-safe daily features; 5/15/30/60-minute sparse-bar workload and AKQuant conditional replay pass. These do not complete quote admission, economic frequency validation or final QC parity. [Report](../strategies/sstrangle/research/design_20261023_v5/POC_REPORT.txt).
- Q01 native identity/tag/fee/settlement and Q01-RAW page archival pass at this PoC scope. The generic Rust typed exporter still omits unmodeled fields and can time out on a large final read; the PoC raw adapter uses bounded I/O workers, checkpoints and cached identity-verified terminal reads.

## Completed in the prior documentation review

- Added one documentation index, one current-work page and this ordered backlog.
- Replaced the accumulated strategy README with a concise entry point; preserved its historical snapshot.
- Corrected current continuation metadata using saved terminal evidence; retained the previous JSON snapshot.
- Kept frozen strategies, campaign evidence and reviewed PDF versions unchanged.

When closing an item, add a dated evidence link and its limitations. Keep detailed substeps in the relevant specification rather than growing this page into an experiment log.
