# OOS Backtest Audit — Synthesis Report
## Look-ahead, Live-faithfulness, and the Model-Only/Everything-Online Standard

> *Produced 2026-06-13 by a 15-agent adversarial audit (7 deep-audit agents × 7 adversarial
> verifiers + synthesis) over `infer.py`/`footer.py`/`infer_online.py`/`verify.py`/`live_trade.py`/
> `portfolio.py`/`sizing_ext.py`/`bar_builder.py`/`features.py`/`labeler.py`/`ml_ext.py` and the
> `run_round.py` crowning path. Finding tags (e.g. `[SIZE-1, HIGH, GLD]`) reference the per-area
> dossier. Companion: `docs/research/WANG_PIPELINE.md` §2 (Wang's online-computability doctrine,
> the conceptual basis for the model-only/everything-online standard tested here).*

---

## 1. HEADLINE VERDICT

**Does the current OOS backtest meet "model-only + everything-online"? NO.** The headline OOS Calmar that crowns every champion is produced by `infer.py` (`scripts/run_round.py:709` renders it, `:715` runs it, `:541` reads `real_calmar` from its statistics). `infer.py` is a **pure replay of batch-saved predictions**: `infer.py.tmpl:135` loads `data.get("predictions", [])`, `:160` reads `p = self.preds[self.idx]`, `:169` calls `_size(...)`, `:176` `set_holdings(...)`. It instantiates **no model**, builds **no custom-axis bars**, computes **no features / reduce / calibration online** — it only re-runs sizing. Those predictions were computed in batch over the full 2009→2026 series in memory at `footer.py.tmpl:470` (`test_preds = _pred_list(pe_cal[:-1], ...)`). So the crown meets a weaker **"frozen-prediction replay"** standard, not the user's "generate custom axis / labeling / features / dim-reduction / predict / sizing ONLINE" requirement. [ARCH-1, FEAT-4, confirmed/high]

**Does it have any actual look-ahead leak? NO — none found, on any surface.** Every adversarial probe of the causal chain came back clean and was independently re-verified:
- Bar thresholds are TRAIN-masked; the only full-series quantity is `len(c)`, an OOS-invariant calendar minute **count** (no prices/returns/volumes), and the historical full-series-sum leak stays fixed (`bar_builder.py:2088-2100` logdollar, `:2157-2161` imbalance; `_train_minute_mask` *fails loud* if `TRAIN_END` is missing, `:1373-1387`). [BAR-6, BARS-CLEAN, confirmed]
- Scaler + reducer fit TRAIN-only (`footer.py.tmpl:244-252`); isotonic fit on **embargoed** labeled VAL only (`:237`, `:345-347`); embargo `= max(200, max(horizons), label_reach)` cannot be out-reached by any deployed labeler (`footer.py.tmpl:223`; trend_leg/ker/revert reach ≤80, regime_gmm/bgm ≤200). [LBL-1, FIT-CLEAN, CAL-1, confirmed]
- OOS preds cover **every** causal test bar (`ex = fv & te_m`, no future-label filter; only the unrealizable last bar dropped), and the leaky legacy trainer path raises `RuntimeError` if ever called (`trainer.py:287-289`). [LBL-2, LABEL-CLEAN, confirmed]
- All base-80 features are trailing-window causal; exogenous as-of joins use `searchsorted(side='right')-1 + ffill`, no bfill, with publication lags. [FEAT-1, FEAT-6, FEAT-7, FEAT-8, confirmed]
- Even the replay is dispatched causally: `infer.py.tmpl:165` consumes a prediction only once `b.end_time >= pred_time`. [CLEAN-1, confirmed]

**Is it live-faithful today? NO — partially.** The crown number is leak-free and self-consistent, but it is **not the artifact that will trade live**, and several confirmed divergences mean the deployed book will not reproduce the crowned/booked numbers (Section 3). The most material: the deployable book `portfolio.py` silently drops GLD's `dd_overlay` throttle, and the live always_long path is pure buy-and-hold while the crown applies a vol-throttle. None of these is a leak; all are fidelity/coverage gaps.

**Bottom line:** the research is honest (no look-ahead), but the *crown does not exercise the live machinery*, and the live machinery has confirmed mismatches against both the crown and the booked portfolio. The fully-online infrastructure to fix this **exists and is well-built** (`infer_online.py`, `live_trade.py`, `verify.py`, bundle persists everything needed — `footer.py.tmpl:408`, `:430-451`, `:738-739`) but is **never invoked by the crowning driver** (`run_round.py:73` imports only `render_train_config, render_infer_cell`). [CLEAN-2, ARCH-2, confirmed/high]

---

## 2. LOOK-AHEAD — Confirmed leaks + surfaces proven clean

### Confirmed leaks
**NONE.** Across six independent audit areas (bars, features, labels/reduce/calib/predict, sizing, normalization, completeness sweep) **zero** real look-ahead leaks were found. This is the strongest part of the verdict.

### Surfaces proven clean (ranked by deploy-criticality)
1. **Bar thresholds — champion axes logdollar (GLD/USO/DXJ) & imbalance (DIA).** TRAIN-masked; `len(c)` is an OOS-invariant count, not a value; `_train_minute_mask` fails loud. [BAR-6, BARS-CLEAN] `bar_builder.py:2088-2100`, `:2157-2161`, `:1373-1387`
2. **Builder `update()` causality — all axes.** Strict decide-then-update; jump/volofvol standardize by *strictly-past* bipower; no full-array statistic in any `update()`. Batch==online for identical warmup. [BAR-7] `bar_builder.py:812`, `:873`
3. **Fit-time masking — all champions.** Scaler/reducer TRAIN-only, isotonic embargoed-VAL-only, no `.fit()` touches OOS. [FIT-CLEAN, RED-2, CAL-1] `footer.py.tmpl:244-252`, `:345-347`
4. **Embargo cannot be out-reached.** `label_reach` plumbed as a structural guard; embargo floor 200 covers all built-in labelers. [LBL-1] `footer.py.tmpl:223`
5. **OOS prediction coverage / no future-label trade selection.** `ex = fv & te_m`; legacy leaky trainer fail-loud fenced. [LBL-2, LABEL-CLEAN] `footer.py.tmpl:239`, `trainer.py:287-289`
6. **Base-80 features causal.** Trailing windows, `min_periods=W`, no center/forward/bfill; causal-prefix `nancumsum`/`maximum.accumulate` only. [FEAT-1, FEAT-8] `features.py:234-309`
7. **Exogenous as-of joins causal** (SPY/FRED/oil/IV): right-side searchsorted + ffill, publication lags. (Unused by current champions.) [FEAT-6]
8. **fracdiff is a TRAIN-fit causal bar axis**, not a feature; order frozen via TRAIN ADF. [FEAT-7]
9. **Predict / calibrate fidelity.** np.interp == isotonic.transform within ULP; xgb `iteration_range`, lgbm `best_iteration`, lgbm_bag 5-seed average, ensemble averaging all reproduce batch. [PRED-1, CAL-1, META-1]
10. **The replay is causal** (dispatch on `b.end_time >= pred_time`). [CLEAN-1]
11. **Cell-key suffix single-sourced** → the vacuous-permute-gate class is structurally prevented. [PSUF-CLEAN] `psuf.py:26-40`

### Leak-GUARD coverage gaps (not active leaks, latent regression risk)
- **BAR-3 (low):** `test_bar_threshold_leak.py` runtime teeth (`NEW_AXES`, `:41-42`) omit the 4 newest deployable ext axes (permclock/mpnov/pecusum/calmonset); AST check never parses `bar_ext.py`. Those four are currently TRAIN-clean by reading, but unguarded against regression. Affects: none deployed.
- **BAR-4 (low, DIA-adjacent):** the AST rule only scans np-reductions assigned directly to `total/thresh/delta/fast`; the imbalance family's `sigma = float(np.std(sdt))` intermediate (`bar_builder.py:2161`) is unscanned, so a regression from `sdt = sd[keep]` → `sdt = sd` (full-series) would pass the test. Code is clean today; this is DIA's live axis, so worth closing. Fix: add `imbalance` to `NEW_AXES` teeth and trace simple intermediates.

---

## 3. OOS→LIVE SKEW — Confirmed divergences between crown and live path

Ranked by deploy impact. "Crown" = `infer.py` replay; "Book" = `portfolio.py`; "Live" = `live_trade.py`.

| # | Divergence | Affected champion(s) | Sev | Where it bites |
|---|---|---|---|---|
| 1 | **`portfolio.py._size` has no `dd_overlay` branch** → GLD book replays as plain cdf, drawdown throttle dropped | **GLD** (57.7% book weight) | **HIGH** | Book metric only (port_calmar/MaxDD); solo crown & live correct |
| 2 | **`live_trade` constant_long ignores sizing** → deploys pure buy-and-hold; crown+book replay p=1 through cdf_overlay vol-throttle | **HYG/TIP/DBC/IWM/UUP** | **MEDIUM** | Live magnitude (long-only; ~26% Calmar overstatement on HYG: 2.03 vs 1.61) |
| 3 | **Live bar builder warms 220d, crown/verify warm from 2009 origin** → persistent sub-bar phase offset on reset-on-emit axes | GLD/USO/DXJ (logdollar), DIA (imbalance) | MEDIUM | Live bars provably not byte-identical to crowned bars |
| 4 | **220d history can't fill the 820-bar warmup** (~525 of 820 bars; comment claims "~30 days" but needs ~234 trading days) → live is FLAT ~2-3 months after deploy | GLD/USO/DXJ/DIA | MEDIUM | One-time deploy delay; no capital loss, resumes warm |
| 5 | **vae(n16)→lgbm_bag re-encoded numpy-float32 live vs torch-float32 batch** → ULP latent drift can flip lgbm splits; verified on only 1/5 OOS bars | **GLD** | MEDIUM | Live path ~20%-proven to match crown on the #1 weight |
| 6 | **Entropy stride-grid phase reconstruction (`oos_start_abs + anchor`) assumes first live bar == 2023-08-01** → mis-phased in genuine forward-live | all (entropy is base) | MEDIUM | True-live only; bounded (entropy slow, ffill'd, ≤stride-1 off) |
| 7 | **VAL scorer has no position hysteresis** (positions=target every bar) while crown/live HOLD inside the dead-band | GLD/DIA/DXJ | MEDIUM | VAL selection is an imperfect proxy of OOS, not the deployed number |
| 8 | **Cold rbuf (crown/book) vs warm rbuf (live)** → overlay multiplier differs for first ~12-60 fires | GLD (dd), DIA/DXJ (cdf_overlay) | LOW | Transient over <60 of ~1400 OOS bars |
| 9 | **`portfolio.py` uses hardcoded bands 0.005/0.003** vs infer's cell `rebal_band` 0.01/0.01 (and never reads cell band) | all book champions | LOW | Turnover/cost mismatch; book ≠ superposition of solo crowns |
| 10 | **`live_trade`/`portfolio` are sizing SUBSETS** (no cond_es/ddbreaker/short_carry/crashsoft/tilt/tilt_up/kelly_dd) → silently fall to cdf_plain | none current (DXJ raced cond_es) | MEDIUM (latent) | A future crown in any of these would mis-deploy silently |
| 11 | **Online/live `build_feats` is base-args only** (no rich/termstruct/cross-asset/extra_feats) | none current (all base-feature) | LOW (latent) | Any future exotic-feature crown breaks live; infer_online self-catches via featlen, but `live_trade` has no guard |

Notes:
- #1, #2 are the only items that distort a **currently-reported deployed number**. #1 corrupts the headline **book** Calmar/MaxDD (GLD dominant weight, throttle dropped — `portfolio.py.tmpl:19-53`, GLD champion `dd_overlay` per `program.md:87`); #2 makes the **live** always_long seats a different (un-throttled) strategy than scored (`live_trade.py.tmpl:98-100`, `:233-239`).
- The crown's **solo per-asset** numbers for GLD/USO/DIA/DXJ are internally self-consistent and `infer.py._size` is a faithful branch-for-branch copy of the VAL engine for all 16 modes [SIZE-7, clean] — the skew is in the **book aggregate** and the **live deploy**, not the solo crown.
- **REFUTED/guarded, not counted:** aim/aim_dd/aim_cdf (SIZE-3) — structurally confirmed missing from all `_size`, but **gated out of `VALID_SIZING`** (`run_round.py:163-167`) so unreachable through the driver; treat as guarded dead code, not a live risk.

---

## 4. REPLAY-vs-ONLINE GAP — Why the crown is not a true online run

The crown metric and a true online run are **different software artifacts that happen to share frozen predictions** for the prediction stage only:

- **What the crown actually exercises online:** only **sizing** (`infer.py._size` + `set_holdings`), and it does so with a **cold, minute-close rbuf** (`infer.py.tmpl:124`, `:178-181`). [ARCH-1, ARCH-3]
- **What it replays (does NOT generate):** custom-axis bars, unsupervised labeling, features, dim-reduction, predict, calibration — all loaded from `cell_*.json`. [ARCH-1, FEAT-4]
- **What proves online-equivalence today:** `infer_online.py` cross-checks `p_live == p_saved` — but only on **every 5th OOS bar** (`_XSTRIDE=5`, `:165`), **tolerates up to 2 unmatched** (`:233`), runs **only for BUILDER_CLASSES axes**, builds **base features only**, and **never trades, never calls `_size`, never compares positions or Calmar** (grep for `_size|set_holdings` in `infer_online.py.tmpl` is empty). [ARCH-4, ARCH-7, COV-1] So the **entire sizing/execution stage that produces the crown Calmar has no online-equivalence proof anywhere.**
- **Worse:** the one stage that diverges cold-vs-warm (sizing, ARCH-3) is exactly the stage that is **never** online-verified (ARCH-4) — the two gaps compound.
- **Nothing wires this into crowning:** `render_infer_online`, `render_verify`, `render_live_trade`, `render_portfolio` have **zero callers in the crowning driver**; they live in `scripts/research/verify_*.py` and are manual, out-of-band. `render_live_trade` has **zero callers anywhere**. [ARCH-2, BAR-2]

**What this risks:**
1. **A champion can be crowned and booked without its online bar/prediction/sizing equivalence ever being proven in the same run.** The "~1e-8 match" is from audit memory, not re-run this session, and holds only for builder-axis + base-feature cells. [CLEAN-2 caveat]
2. **The live path provably won't reproduce the crowned bars** (220d vs origin warmup → persistent phase offset on logdollar/imbalance — BAR-1), so even with identical predictions the live equity curve diverges at the bar level.
3. **For GLD specifically**, the live re-encode of the vae latent in numpy-float32 can flip lgbm splits on the 80% of OOS bars never cross-checked (RED-1) — a genuine replay-vs-online gap on the dominant book weight.
4. **For a future cross-asset/rich-feature or non-builder-axis champion**, the online/live path would build the **wrong feature vector** or have **no live path at all**, and crowning has no gate to stop it. (`live_trade` has no featlen guard — ARCH-5, FEAT-5, COV FEAT-1.)

The crown is **immune to online float drift** (it's a replay) — but that immunity is exactly the problem: it can't detect a live divergence that would only appear in a true online run.

---

## 5. PRIORITIZED FIX LIST (by deploy impact)

**P0 — corrupts a currently-reported deployed number**

1. **Add `dd_overlay` (and `cond_es`/`ddbreaker`) to `portfolio.py._size`; raise on unknown mode.** `portfolio.py.tmpl:19-53` has no `dd_overlay` branch, so GLD (`dd_overlay`, 57.7% weight) silently replays as plain cdf in the book. Copy the branch verbatim from `infer.py.tmpl:72-80` (or import `sizing_ext._size`), and add a fail-loud guard: if the cell's `sizing` matches no branch, `raise` instead of returning plain cdf. [SIZE-1 / SIZE-PORT-1, HIGH, GLD]

2. **Make `live_trade` constant_long honor the cell sizing** (or re-crown always_long with `cdf_plain`). `live_trade.py.tmpl:98-100` and `:233-239` deploy pure buy-hold; crown+book apply a cdf_overlay vol-throttle. Either feed p=1.0 through `_size(1.0, thresh, sizing, warm_rbuf)` in the live constant_long path, or re-crown the 5 seats with `sizing='cdf_plain'` so crown==book==live. [SKEW-1 / completeness SIZE-2, MEDIUM, HYG/TIP/DBC/IWM/UUP]

**P1 — live deployment won't reproduce the backtest**

3. **Warm the live builder to the full 820-bar warmup, ideally from origin or a persisted accumulator.** `live_trade.py.tmpl:22` `_HIST_DAYS=220` warms ~525 of 820 bars and leaves a persistent reset-on-emit phase offset. Either warm from the 2009 origin like `verify.py`, or persist the batch builder's exact accumulator state at VAL_END in the bundle and seed the live builder with it. Fixes both BAR-1 (phase offset) and WARM-1 (cold-start trade delay). [BAR-1 + WARM-1, MEDIUM, GLD/USO/DXJ/DIA]

4. **Harden the GLD vae→lgbm_bag live encode against split-edge flips and prove it at 100% coverage.** `ml_ext.py:452-479` (torch f32 batch) vs `infer_online.py.tmpl:128-134` / `live_trade.py.tmpl:185-190` (numpy f32 live). Serialize the vae in float64 and encode live in float64, and set `_XSTRIDE=1` for vae/tree cells recording `max_pred_diff` before crowning. [RED-1, MEDIUM, GLD]

5. **Persist a true 2009-origin bar counter for the entropy phase**, or make entropy phase-invariant (compute every bar / causal recursive estimator). `live_trade.py.tmpl:248-266` reconstructs `abs_now` assuming first on_data bar == 2023-08-01, false in forward-live. [ARCH-6 / FEAT-3, MEDIUM, all on true-live]

**P2 — verification coverage / latent**

6. **Gate crowning on a full-coverage online proof.** In `run_round.py`, after a tentative KEEP, render+run `infer_online` at `_XSTRIDE=1` (full OOS) AND a trading `live_trade` backtest; refuse the crown unless `p_live==p_saved` on **all** OOS bars AND positions/Calmar match replay within tolerance. Extend `infer_online` to trade (call `_size`, compare positions/Calmar) and to constant_long. [ARCH-2, ARCH-4, COV-1, BAR-2]

7. **Unify the four `_size` copies to one source of truth + add deploy-time sizing-coverage guard.** `live_trade`/`portfolio` are strict subsets; generate them from `sizing_ext._size` or import it, and fail loud on an unsupported mode. [SIZE-2]

8. **Plumb `CONFIG['features']` + cross-asset carriers into `infer_online`/`live_trade`, and hard-block crowning any non-base-reproduced cell.** Add a featlen guard to `live_trade` (it has none). [ARCH-5, FEAT-5]

9. **Make `portfolio.py` read each champion's `rebal_band`** instead of hardcoded 0.005/0.003, and warm its rbuf like live. [SIZE-6, RBUF-1]

10. **Close the leak-guard blind spots:** add permclock/mpnov/pecusum/calmonset and imbalance to `NEW_AXES` teeth in `test_bar_threshold_leak.py:41`; extend the AST scan to `bar_ext.py` and to trace `sigma`-style intermediates. [BAR-3, BAR-4]

11. **Mirror the dead-band hysteresis into the VAL scorer** (`sizing_ext._cstats_sized`) so `val_da` is computed on the same banded path the crown realizes. [SIZE-4]

---

## 6. DESIGN — A fully-online OOS backtest (promote `live_trade.py` to the metric producer)

The plumbing already exists [CLEAN-2, DESIGN-1]; the work is to **make the crown number come from a trading, everything-online run** and to **prove equivalence at full coverage**.

### Architecture
Render and run a **`live_trade`-style trading backtest over the OOS window** as the headline-Calmar producer, wired into `run_round.py` exactly where `render_infer_cell` is today (`run_round.py:709`/`:715`). It loads **only** the frozen bundle (`scaler_mean/scale`, `kept_idx`, `reduce_tf`, `booster+family`, `best_iter`, `cal_x/cal_y`, `meta` gate, `oos_start_abs`, `bar_type/bar_thresh`) and **generates everything else online**: custom-axis bars → features → reduce → predict → calibrate → meta-gate → `_size` → `set_holdings`. Keep `infer.py` replay as a **fast pre-filter and regression check** (replay Calmar must match online Calmar within tolerance — NOT bit-exact, because warm rbuf + entropy phase legitimately differ).

### Guards required to stay leak-free and reproducible
1. **Warmup = full origin (or persisted accumulator state)**, not 220d, so online bars are byte-identical to batch (fixes BAR-1/WARM-1). Persist the builder's accumulator residual at VAL_END in the bundle.
2. **No future info enters the bundle** — already true: scaler/reduce on TRAIN, isotonic on embargoed VAL, embargo `=max(200,horizons,reach)`. The online run never re-fits anything; it only loads frozen artifacts (so it cannot introduce a leak the batch didn't have). [LBL-1, FIT-CLEAN, CAL-1]
3. **Feature mode parity:** persist `CONFIG['features']` + cross-asset symbol in the bundle; reconstruct the **same** `build_feats(...)` call + `extra_feats`. Hard-block crowning if the online featlen ≠ batch featlen. [ARCH-5, FEAT-5]
4. **Float-stable encode:** serialize vae in float64, encode live in float64; for tree families add a tiny probability dead-zone near split edges, or prefer float-stable families under vae reduce. [RED-1]
5. **Entropy phase from a true origin counter** (or phase-invariant features) so forward-live matches training. [ARCH-6, FEAT-3]
6. **One `_size` source of truth** shared by VAL/crown/online/book, with a fail-loud unknown-mode guard, and constant_long routed through `_size(1.0,...)` everywhere. [SIZE-1, SIZE-2, SKEW-1]
7. **Warm rbuf identically** across the online metric and live (from the same origin/persisted state). [ARCH-3, SIZE-5, RBUF-1]

### Verification that must accompany it (the part that is missing today)
A KEEP cannot be crowned unless, **on 100% of OOS bars** (not the current 1/5 sample, not ≤2-unmatched tolerance):
- **Bars:** online builder bars == batch bars byte-exact (`verify.py` logic, `_XSTRIDE=1`, builder-axis required; hard-block non-BUILDER_CLASSES axes). [ARCH-7, BAR-2]
- **Predictions:** `p_online == p_saved` ≤1e-6 on **every** OOS bar, with `max_pred_diff` recorded. [ARCH-4, COV-1, RED-1]
- **Sizing/positions:** the online run **trades** and its positions + equity + Calmar match the replay within a documented tolerance (it cannot be bit-exact for overlay champions — warm vs cold rbuf and entropy phase differ by design; the assertion needs a non-trivial tolerance, not equality). [DESIGN-1 caveat, ARCH-3]
- **constant_long:** add an explicit online check that replays p=1.0 through `_size` so the always_long seats' sizing path is proven (would have surfaced SKEW-1). [COV-1]

Once this passes, the headline Calmar **is** the deployed strategy's Calmar, and "transition to live trading smoothly" is satisfied because the metric producer and the live trader are the same code path differing only in start date and data feed.

---

## RESIDUAL RISKS (candid)

- **No leak ≠ live-faithful.** The clean look-ahead bill of health is solid and re-verified, but it says nothing about whether the deployed book reproduces the booked numbers — and two confirmed items (P0-1 GLD dd_overlay drop in the book; P0-2 always_long live buy-hold) mean **the reported book Calmar and the live always_long seats are already wrong relative to what's crowned/deployed.**
- **The "~1e-8 online==batch" claim is stale** — asserted from memory, not re-run this session, and only ever covered builder-axis + base-feature cells at 1/5 sampling. Treat it as *necessary-but-unproven* until full-coverage gating exists.
- **GLD is the concentration risk on every axis:** 57.7% book weight, the only `dd_overlay` champion (book mis-sized), the only vae→lgbm_bag champion (float-drift, 20%-verified), and a logdollar reset-on-emit axis (live phase offset). The dominant position is the least-verified live path.
- **True forward-live (start = today) is materially less tested than the 2023-08-01-anchored verification backtest** — the entropy phase reconstruction and the 220d warmup are both correct *only* for a backtest that starts at VAL_END, and no test exercises the genuine forward-live anchor. [ARCH-6, FEAT-3, WARM-1]
- **Latent traps for the next champion:** any cond_es/ddbreaker/tilt/kelly_dd sizing, any cross-asset/rich-feature mode, or any non-BUILDER_CLASSES axis would crown fine and then **silently mis-deploy or have no live path**, with no gate to catch it. The frontier is moving toward exactly these (DXJ already raced cond_es; cross-asset features were reopened per memory), so these latent gaps are on the critical path, not hypothetical.

Relevant files: `/home/ubuntu/qc_work/SML01/scripts/run_round.py`, `/home/ubuntu/qc_work/SML01/src/lb/harness/orchestrator.py`, `/home/ubuntu/qc_work/SML01/src/lb/templates/infer.py.tmpl`, `/home/ubuntu/qc_work/SML01/src/lb/templates/infer_online.py.tmpl`, `/home/ubuntu/qc_work/SML01/src/lb/templates/live_trade.py.tmpl`, `/home/ubuntu/qc_work/SML01/src/lb/templates/portfolio.py.tmpl`, `/home/ubuntu/qc_work/SML01/src/lb/templates/verify.py.tmpl`, `/home/ubuntu/qc_work/SML01/src/lb/templates/footer.py.tmpl`, `/home/ubuntu/qc_work/SML01/src/lb/modules/sizing_ext.py`, `/home/ubuntu/qc_work/SML01/src/lb/modules/bar_builder.py`, `/home/ubuntu/qc_work/SML01/src/lb/modules/features.py`, `/home/ubuntu/qc_work/SML01/src/lb/modules/ml_ext.py`, `/home/ubuntu/qc_work/SML01/tests/test_bar_threshold_leak.py`.