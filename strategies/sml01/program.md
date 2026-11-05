# autoresearch

An autonomous research loop (in the spirit of [karpathy/autoresearch](https://github.com/karpathy/autoresearch))
that hunts single-ticker trading edges on ETFs. Each round the agent reads this file + `knowledge.json`,
designs ONE experiment, runs it for real on QuantConnect (project 31338454), scores it on REAL
out-of-sample Calmar, and keeps it iff it beats the champion AND every honesty gate passes.
Single ticker, no cross-ticker ensembling, simple over complex.

This is an LLM pointed at a number it can game, so most of this file is gates, not method. A backtest
happily reports a great Calmar that is a look-ahead leak, a multiple-testing fluke, or plain drift;
telling a real edge from those three impostors is the whole job.

## The loop

1. **Re-validate, then target.** Stored Calmars go stale as the OOS window grows — re-race
   champion-vs-`always_long` before trusting any stored number. Target the weakest ETF.
2. **Design ONE recipe** — `axis × label × features × reduce × model × sizing`. Every confirmed edge
   came from a NEW mechanism, never knob-tuning; grinding a structureless name only raises everyone's
   deflation bar.
3. **Race it A/B on the 2 QC nodes:**

   ```bash
   python3 scripts/run_round.py '<CONFIG_A>' '<CONFIG_B>'   # no args: auto-pick from hypotheses.json
   ```

   A CONFIG is `{ticker, axis, labeler, thresh, sizing}` + optional `{reduce, n_components, features,
   model, calibration, horizons, permute_labels}`; labelers ensemble with `+`.
4. **Keep iff ALL gates pass; log either way.** A human crowns. Save exactly 3 files per round —
   `results/round_results.csv` + `knowledge.json` + `docs/research/ETF_SCREEN_TABLE.md` — and commit.

## Keep gates — all must hold

| Gate | Threshold |
|---|---|
| Deployable | trades > 80, train+infer completed, DA present |
| Beats champion | winner Calmar > re-validated previous best |
| Learnable structure | val_auc > 0.52 |
| Survives deflation | > expected-max of N noise trials (`always_long` exempt) |
| PSR significance | Bonferroni-deflated `psr > 1 − 0.05/N_trials` |
| Permuted-label control | real edge over buy-hold > 0.15 AND permuted < 40% of real |

The **permute control is the decisive test** (shuffle TRAIN labels only, separate `_perm` cell;
GLD: 4.70→0.76). It must FAIL LOUD: a 0-trade control leg refuses the KEEP. When reading old
backtests, derive champion-vs-permute legs from the LEDGER row (ledger time = QC+8h), never assume
A/B orientation.

## No look-ahead — the leak contract (fixed, `random_state=42`)

```
event bars → StandardScaler → reduce → model(depth 3, lr .03, n 200) → calibrate (embargoed VAL)
           → de Prado CDF bet × causal overlay
```

- **Bar thresholds are TRAIN-fit only**, extrapolated identically OOS. A full-series `np.sum` here
  once inflated a whole leaderboard; `tests/test_bar_threshold_leak.py` guards it — run after ANY
  bar-builder change.
- **Labels may look ahead, never beyond `_EMBARGO`**; smoothers block-decode at the OOS boundary;
  features past-only; sizing identical in backtest and live.
- **The OOS backtest is online, leak-free, ObjectStore-replay-only** (`docs/analysis/BACKTEST_AUDIT.md`).
  Proofs: `verify.py` (bars ≤1e-9), `infer_online.py` (preds ≤1e-6).
- **Cell keys come only from `lb.harness.psuf.cell_suffix`** — key collisions made gates vacuous three
  times; `tests/test_psuf_tokens.py` guards all knob combinations.
- **Leaks are found by re-running with the fix, not by reading code.** Audits miss them.

## QC constraints

64,000 UTF-8 bytes per file (code only; `tests/test_render_budget.py` guards champion renders). New
axes → `bar_ext.py`; features/reduces/models/calibration → `ml_ext.py`; sizing → `sizing_ext.py`.
QC files must be lint-clean: no `getattr`, no nested-quote f-strings. **Lean CANNOT catch lookup
errors** (AttributeError/NameError escape try/except — proven twice): guard with `hasattr`. The QC
sandbox has no internet; probe silent feeds via `set_runtime_statistic`. Splits: train ≤ 2021-08,
val ≤ 2023-08, OOS ≤ now. Each backtest hard-capped at 5 min.

## The honesty stack

Never crown on LLM judgment — only on real QC Calmar, then: deflated Sharpe · session DSR
Holm-Bonferroni · permute control · decay monitor · e-values · PBO/CSCV · cost stress (book holds at
5bp) · drawdown-shape (Ulcer/Pain/Martin, `lb.metrics`) · regime-split (`scripts/audit/regime_split.py`)
· deflated Calmar (`scripts/audit/deflated_calmar.py`, MC max-of-N bootstrap null). Only GLD survives
the full Holm-Bonferroni burden; every other edge is provisional. **Weight conviction by DSR and
recovery-pain (Martin), not raw Calmar** — Calmar flatters slow-bleeders.

## The book (common-grid 2026-06-12; all online-proven `preds_match=1`)

| Ticker | Config | Calmar | Status |
|---|---|---:|---|
| **GLD** | logdollar / `trend_leg+regime_gmm` / dd_overlay / t.40 / n16 vae **lgbm_bag** | **4.70** | Crown. Permute-confirmed, Bonferroni PASS, regime-split PASS, deflated p=0.003, live-deployable. |
| **USO** | logdollar / `revert` / cdf_plain / t.45 / correlation | **2.82** | Oil mean-reversion engine. Permute-confirmed, decay-strengthening, deflated p=0.043. |
| DIA | imbalance / `bgm+ker` / cdf_overlay / t.50 | 1.66 | Candidate seat, fully gated + online-proven. |
| DXJ | logdollar / `ker` / cdf_overlay / t.45 | 1.85 | Verified Japan option (most regime-uniform edge); seat = human decision. |
| HYG/TIP/DBC/IWM/UUP | `always_long` (×cdf) | 1.97/0.90/0.69/0.50/0.37 | Decorrelation seats; timing retired. |
| IJR / FEZ / PRFZ | — | — | Watchlist only: IJR isotonic-plateau knife-edge (beta re-cut 2.51→0.58), FEZ regime-fragile, PRFZ replication-failed. |

**Proposal A (Calmar² weights, awaiting human):** GLD 57.7 / USO 20.8 / HYG 10.1 / DIA 7.1 / TIP 2.1 /
DBC 1.2 / IWM 0.6 / UUP 0.4. Two replication-confirmed engines, asset-intrinsic: gold-trend (GLD→IAU)
and oil-reversion (USO→UCO).

## Laws (each bought with races)

- **Predictability ≠ profit.** Indices carry auc 0.94–0.97 reversion that never monetizes; on GLD,
  higher-auc challengers lose on Calmar. Val_auc admits, only Calmar crowns.
- **Equity-index timing (QQQ/SPY/IWM) is closed at every door.** The one real crack — QQQ
  `permclock/bgm+ker` 1.51 > BH 1.24 — proved REPLAY-REAL but STRUCTURALLY NON-DEPLOYABLE: the edge
  lives in depth-3 interactions of exactly 5 early-stopped trees on a float32 split boundary, and
  every stabilization (more trees, bagging, stumps, logit) kills it. Corollary: **tiny early-stopped
  ensembles are float-edge decision-unstable — never live-grade.** `always_long` is the deployable
  optimum on indices.
- **Mechanism-paired components.** Trend/bullion: unsupervised projection + lgbm. Reversion/oil: raw
  selection + xgb (any projection craters it). Component choice is asset physics; nothing transfers
  without a replication race.
- **Panel additions dilute.** Every feature block beyond the base 80 lost on the engines under every reducer.
- **Drifters (val_auc≈0.5) are buy-hold-optimal**; new methods only help where structure exists
  (val_auc>0.6). `trend_leg+regime_gmm` degenerates on up-drifters — use `tertile` there.

## Closed — don't re-grind

Depth-3 capacity · meta-labeling · uniqueness weights · sticky-HMM · cross-asset/exogenous features
(auc up, Calmar down = the overfit signature) · VIXY carry · universe siblings (SLV/GDX/XME) ·
oil-reversion beyond oil · the 2026-06-11 innovation backlog (14/14 raced; only wins lgbm/lgbm_bag,
GLD-only) · the 311-ETF screen + Tier-3 sweep (DXJ the sole verified discovery; 10 stale-window
mirages refuted) · options-IV channel (no conversion; harvester `precompute_iv.py` + `features='iv'`
retained) · Chronos. Retained-idle primitives live in `sizing_ext` / `ml_ext` / `bar_ext`.

## The frontier

Research exhausted within current data. **Human decisions pending:** adopt proposal A · DXJ seat ·
new data modality (options IV / COT / flows — the only true reopener).

Autonomous — decide and run the next experiment, don't ask.
