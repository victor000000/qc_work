> Latest 0.9.0 validation (2026-11-05): [C0 margin and IV evidence](../../results/margin_verified_v090_20261105/RESULTS.md). 427 tests passed. Cloud-tested diagnostic/API and publication-race fixes preserve exact native account parity. C0 still fails on margin; IV replay passes but historical root cause remains open. Pre-trigger margin state, full sidecar/feature parity, strict provider inputs and economic acceptance remain gaps.

# 0.9.0 executable design PoC

Implements the [0.9.0 design](../../research/design_20261030_v090/DESIGN.md). Versioned copy of the v089 engine and local bridge, with contract-specific conflict exclusions, malformed-clock diagnostics, positive-activity calibration, complete QC gap-bar export and an explicit SPY time control. v089 is preserved.

`compare_axes.py` adds completion-hash verification and a frozen same-source paired-session comparison. It reports uncertainty and chronological sensitivity, leaves recipe selection empty and keeps economic acceptance false. Existing 0.8.9 consumer bundles remain usable with their original release identities; old checkpoints are intentionally version-incompatible.

From `/home/vic/qc_work`:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  strategies/sstrangle/poc/v090 \
  strategies/sstrangle/research/design_20261030_v090/test_review.py -q

PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v090.pipeline \
  --bundle /absolute/path/manifest.json --out /new/activity \
  --recipe spy_close_volume --mode sampled

PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v090.pipeline \
  --bundle /absolute/path/manifest.json --out /new/control \
  --recipe time_control --control-symbol SPY --mode sampled

PYTHONPATH=. .venv/bin/python -m strategies.sstrangle.poc.v090.compare_axes \
  --left /new/activity --right /new/control --out /new/comparison.json
```

To reproduce the saved old-version failures, run the review with `AXIS_REVIEW_VERSION=v089`; its expected exit code is 1. Do not run all historical adversarial suites expecting a green result: older intentionally failing review artifacts remain preserved.

[Results and acceptance limits](../../results/custom_axis_v090_20261030/RESULTS.md). Synthetic tests and sampled replay confirm engineering behavior; strict data, cloud parity and funded replay remain separate gates.

Detailed workspace setup, module/data reference, fresh synthetic and real-data reproduction, troubleshooting and continuation: [project handbook](../../../../docs/PROJECT_HANDBOOK.md).

Follow-up [2026-11-05 cloud/provider validation](../../results/validation_v090_20261105/RESULTS.md): regular C0 account parity passed, with incomplete minute coverage, early-close errors and licensed sidecar-export restrictions retained as unresolved gates.

Current adapter correction: [exchange-clock fix and cloud evidence](../../results/fix_v090_20261105/RESULTS.md). Naive bars require security exchange timezone metadata. Recent session summaries are bounded to 32; regular/early-close coverage is cloud-confirmed.

[Warmed C1/P1 validation](../../results/warmed_v090_20261105/RESULTS.md): natural native-minute calibration, aggregate `decision_status_counts`, 31 complete sessions and exact account parity. These counts include settlement-only tail dates; they do not establish independent feature-value parity. C0 funding and native IV limitations remain documented.
