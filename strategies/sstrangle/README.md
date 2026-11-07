> 2026-11-07: 0.9.1/0.9.2 diagnostic design, self-review and implementation: [release evidence](../../docs/releases/qc-v092-review.md). Cloud and economic acceptance remain open.

> Latest 0.9.0 validation (2026-11-05): [C0 margin and IV evidence](results/margin_verified_v090_20261105/RESULTS.md). 427 tests passed. Cloud-tested diagnostic/API and publication-race fixes preserve exact native account parity. C0 still fails on margin; IV replay passes but historical root cause remains open. Pre-trigger margin state, full sidecar/feature parity, strict provider inputs and economic acceptance remain gaps.

> Latest validation: [warmed C1/P1 parity confirmed](results/warmed_v090_20261105/RESULTS.md). 422 tests; 31 complete sessions and ready-axis evaluations for C1/P1. C0 margin failure and unresolved IV/sidecar/provider gates are retained.

> Latest result (2026-11-05): [0.9.0 minute-coverage fix verified](results/fix_v090_20261105/RESULTS.md). 421 tests and four QC runs pass; regular/early-close coverage and short account parity confirmed. Remaining gates are documented.

> Latest validation (2026-11-05): [six QC cloud runs and provider audit](results/validation_v090_20261105/RESULTS.md). Regular account parity passed; full cloud and strict provider acceptance remain open.

> Current design: [0.9.0 tested custom-axis pipeline](research/design_20261030_v090/DESIGN.md). Local engineering confirmation: **417 tests passed**, four defect reproductions fixed, synthetic and real SPY PoCs completed. [Evidence](results/custom_axis_v090_20261030/RESULTS.md). Strict provider acceptance, native QC cloud parity and funded economics remain open. Historical strategy results below remain preserved.

# Options and short-strangle research

Historical funded reference: **[Version 0.8.5](research/design_20261026_v085/DESIGN_REPORT.pdf)** — completed condor QC baseline → local research → funded QC verification, plus a rejected put-spread add-on. [Readable design](research/design_20261026_v085/DESIGN_REPORT.md) · [implementation](poc/v085/README.md) · [evidence](results/qc_poc_20261026_v085/final_verification.json). Native candidate: 3,510 trades, $251,600.30 net, 16.2% MDD, 2.019 Calmar. Research-only; later-period comparison and settlement/model gaps prevent an alpha/deployment claim.

[Draft 0.8](research/design_20261024_v8/DESIGN_REPORT.pdf) remains preserved historical robustness/funded evidence. Its findings inform 0.7.5; robust alpha is not established.


Start with [current work](../../docs/CURRENT_WORK.md), [next steps](../../docs/TODO.md), and [the 0.8.5 design](research/design_20261026_v085/DESIGN_REPORT.pdf). Historically, three audited SPX baselines exceed 360 whole episodes in every included year. The revised condor has 12,884 episodes; Draft 0.6 records admission recovery, naked-strategy funding, expiry/calendar fixes and source-parity limits.

## Results and implementation

- **Draft 0.6 three-demo PoC:** [comparison](results/qc_three_demo_poc_20261023/analysis/comparison.csv) · [annual gate](results/qc_three_demo_poc_20261023/analysis/annual.csv) · [native audit verification](results/qc_three_demo_poc_20261023/final_verification.json) · [adapter](poc/v06/README.md).

- **Frozen Draft 0.5 audio-demo QC control:** 9,841 whole SPX episodes, every included year above 360; $100,000 -> $220,672.98, native marked MDD 47.5%. [Audit](results/qc_baseline_poc_20261023/full_v5_evidence/audit.json) · [source conventions](poc/SOURCE_CONTRACT.txt).

- **Original frozen baseline:** audited insolvency on 2020-03-12, $60,000 → −$42.29. [Report](results/strangle_basket_20261018_191012/baseline_report/REPORT.md).
- **Later broad research control:** completed through 2026-09-30, ending $48,817.43, Calmar −0.068. [Report](results/strangle_basket-calmar_20261019_204146/research_report/REPORT.txt). The Calmar >2 objective is not achieved.
- **Local research:** [reconciled joined dataset](results/liquidity_local_research_20261020/summary.json) and [AKQuant replay adapter](local/README.md) exist. Full independent option-path simulation and the proposed feature platform remain pending.

The original US baseline is preserved. New intraday/strategy-family research is described in the draft; do not apply its proposed rules to frozen runs or treat the older top-50/top-100 prototype as a launch instruction.

## Where things live

| Path | Purpose |
|---|---|
| `basket/` | Existing basket strategy implementation |
| `optimization/` | Research variants, diagnostics and continuation metadata |
| `local/` | Local replay/AKQuant tooling and limitations |
| `liquidity/` | Historical options-liquidity selector prototype |
| `research/design_20261026_v085/` | Current measured design, PDF, charts and findings |
| `poc/v085/` | Native baseline, local search, frozen QC verification and failure audit |
| `research/design_20261023_v6/` | Historical overall design and comment resolution |
| `poc/` | Frozen Draft 0.5 audio-demo baseline and original audit |
| `poc/v06/` | Three-demo adapter, wing diagnosis, and native 4/2/1-leg audit |
| `results/` | Frozen campaigns, real exports, audits, DuckDB/Parquet and failures |

[Workspace setup](../../README.md) · [Rust CLI reference](../../USAGE.md) · [documentation guide](../../docs/README.md).

## Evidence and operational state

[Baseline state](research/CURRENT_BASELINE_PROGRESS.json) and [research state](optimization/CURRENT_RESEARCH_PROGRESS.json) retain detailed run history. Use the current summary fields and saved terminal evidence; older nested snapshots can describe superseded runs. Check live state before operational actions. Do not restart the Rust server while a cloud execution is nonterminal.

[Historical README snapshot](README.history-20261021.md) preserves the previous narrative and commands exactly as they stood. It contains superseded running-state claims and is reference material only. Use current docs and actual run manifests for operations.

Source transcript received 2026-10-24: [Tom — conviction and position sizing](research/tom_position_sizing_20261024/README.txt) · [readable transcript](research/tom_position_sizing_20261024/transcript.readable.en.txt). Preserved separately from the frozen Draft 0.7 experiments.
