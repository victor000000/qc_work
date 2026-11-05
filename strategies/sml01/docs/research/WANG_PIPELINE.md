# Wang Yiming's quant pipeline — canonical reference

*The end-to-end production line behind this repo's design, reconstructed from the genuine-Wang
lecture corpus + course PDF + Q&A doc, then cross-checked quote-by-quote against the primary
transcripts. This is the conceptual blueprint; the honesty layer on top of it (permute control,
DSR/Holm-Bonferroni, PBO/CSCV, e-values, bit-exact leak proofs) is this repo's own — stronger than
anything Wang teaches.*

> **Provenance.** Of 16 transcribed lectures, ~10 are genuinely Wang Yiming (王一鸣, co-founder of
> overseas fund DCP, AUM ~$1.2–1.3B, ex-Merrill/Knight); the rest are vendor/guest talks and are
> triaged out. **Source shorthand** (gitignored under `refs/`): `SPINE` = uVnOeOcoivw (全流程拆解,
> the pipeline spine) · `RB6` = BV1FnjuzUEJD (the 6-module RB demo) · `ENT` = Ca1n2jgKjrs (entropy)
> · `AE` = vL8DY2NP96I (autoencoders) · `VOL` = tGzbK8c3R_A (volatility/FIGARCH) · `FREQ` =
> WkZ6TUg_gK4 (frequency domain) · `ARB` = q922tUTWmCY (arbitrage-as-trend) · `PROMO` = BV1bpstzBEVm
> (decay-ops / "save 10 years") · `QA` = BV1a6enzLEVw (course Q&A) · `PDF` = wang_course_2026-06.pdf
> (syllabus). Quotes are translated; load-bearing Chinese terms kept in parens.

---

## 0. The one thesis

**The moat is `统筹/协同` — holistic coordination and inter-stage synergy — not any single module.**
A single owner co-designs `axis ⇄ label ⇄ feature ⇄ reducer ⇄ model ⇄ loss` as one closed loop.
Wang is blunt that the chain "basically has no finance in it — the data is financial, but the rest
is mathematical logic and IT logic" (`SPINE`); on a base that merely satisfies financial
interpretability he prefers to "solve it the math way."

> "No stage is the most important; it's the personal coordination ability, the 统筹 ability, that is
> truly critical." (`SPINE`) — "people take detours because they learn scattered pieces and can't
> string them together." (`PROMO`)

Everything serves two hard requirements — **consistency (一致性) and reproducibility (可重复性)**:
identical state + identical data must produce a byte-identical decision *including the confidence
score*. That is *why* only discriminative models are admissible and generative/LLM models are
**banned from the decision loop**.

His own emphasis ranking:
1. **Whole-pipeline coordination** — the part "no one else teaches."
2. **The custom axis** — the single biggest lever (axis swap *alone*, everything else frozen: rebar
   Calmar 1.39–2.13 → 2.82–3.31; **the 5.63 headline needs the axis *plus* combination** — see §5).
3. **Labels are the linchpin (`承上启下`).**
4. **Non-linearity is *why* ML wins** (else use a linear factor model).
5. **No holy grail → combine.**
6. **OOS-of-OOS honesty.**

Second-order principle running through everything: **solve hard problems one dimension up, never
head-on.** Nobody can separate trend from chop in signal space in real time, so change the
*representation* (the axis) to reduce chop frequency rather than build a smarter classifier.

---

## 1. The end-to-end pipeline

### Stage 0 — Name the money first
State which of five money sources the strategy harvests before touching the pipeline:

| Family | Money | Admission signature |
|---|---|---|
| **Trend** | autocorrelation / inertia money | positive serial correlation of price *changes* |
| **Mean/value reversion** | repair of price-vs-value deviation | negative short-lag autocorrelation |
| **Cross-sectional** | relative/ranking money after stripping index β (CAPM/FF3/FF5) | rank dispersion |
| **Arbitrage** | market-friction money (spread = theoretical + friction + risk premium) | the *spread* autocorrelates |
| **Volatility** | directionless sentiment vol-mispricing (mostly options) | — (hedge for the other books) |

All strategies reduce to two classes — **time-series (TS)** and **cross-sectional (CS)** — which
earn *different* money so they run side by side. Unfamiliar problems are **transformed into the
pipeline's domain**, never solved with new machinery: arbitrage → **trend on the spread** (test the
spread for autocorrelation, not for an economic story — "even gold and pork qualify"); regression →
**binned classification**; non-shortable → **short-signal maps to flat**.

### Stage 1 — Asset admission by statistical properties
Admit only instruments that *have statistical properties*. Litmus: **"if a small amount of money can
sway the quote, it has no statistical property"** (`FREQ`). Single stocks are **banned** (too noisy,
"models won't converge"); ETFs/broad indices, liquid futures (rebar/RB), crypto (BTC/ETH) are
admitted. For a single name, **build your own equal/custom-weight index first** (`ENT`, `FREQ`).
**Asset physics, not tuning:** suitability is intrinsic — RB has *strong* autocorrelation (industrial
production-chain pricing → long memory); agriculturals are cyclical with *weaker* autocorrelation;
equities have *short* memory. Per-asset **memory length** is calibrated empirically (it's why `VOL`
uses an *adaptive* fractional-d GARCH, longer-d on RB than CSI300). Crypto's 24h density (~5×) makes
2y ≈ 10 domestic-equity years. **Drift detected by label mean:** `ȳ≈0.7` ⇒ long-only asset — convert
the direction regime, never force balance back to 0.5 (forcing raises AUC, collapses Calmar).

### Stage 2 — Data + the distribution diagnostic (anchors the system)
Minute bars suffice (tick only for true HFT). Pay for clean data; for futures, train/infer on the
**continuous index series**, execute on the **dominant contract**, auto-roll. Before modeling:
**first-difference (and 1st–5th-order `分布差分`) the bar closes, standardize, overlay N(0,1)**
(peak density ≈0.4). Real returns are **sharp-peak + fat-tail (尖峰肥尾)**.

> "The peak is in effect the chop frequency (震荡频次); the left and right tails are the money we hope
> to earn." (`SPINE`) — time bars are bad two ways: "first the statistical properties are poor,
> second the data is very non-stationary." (`RB6`)

He **proves** peak height is *positively correlated* with chop frequency — the plot tells you, before
training anything, where you earn (tails) and where you bleed (peak).

### Stage 3 — Custom-axis resampling (his #1 lever)
Abandon the time axis; resample onto an **information-driven axis** — dollar/turnover (成交额) bars,
volume bars, his basic-course **C1 price-action axis**, his advanced **X axis** (near-full
normality), or any axis engineered so the 1st-difference approaches Gaussian (`PDF` M3). Emit a bar
when the accumulator crosses a threshold.

**The true objective is uniform per-bar information density** (open/close dense & volatile,
mid-session sparse) → closer to IID → better statistics → lower drift probability. **Normality /
low-kurtosis is the *symptom*, not the target** — he explicitly corrects students who optimize
kurtosis directly. Chop reduction is a *side effect*.

Engineering details:
- **The threshold IS the trading-cycle dial** — "at resampling time you have already defined your
  trading cycle" (`SPINE`). Match bar count to a frequency you comfortably trade. **Fix cost problems
  HERE by enlarging the bar — never downstream by re-tuning labels.**
- **De-scale / rolling-standardize the threshold** (mandatory live, skipped in demos): a fixed
  turnover threshold means "30亿 today ≠ 30亿 five years ago," so "**your axis itself is drifting**"
  (`RB6`/`AE`). Rolling-standardization (most common), log, or turnover-change.
- **Overnight gaps need no handling** (absorbed inside bars).
- **Simplicity:** GP/symbolic-regression-mined axes overfit — simpler is better.
- **Train across N resampling-PHASE offsets** to wash out start-point sensitivity (`SPINE`; see §2f).
- **Mechanism ROUTER by resampled shape** (`RB6`): three figures — close-to-normal → **trend**; peak
  goes *up* (tails shrink) → **mean-reversion**; **bimodal (二项分布: double-peak at 1st-diff, five
  peaks at 5th-order)** → **event-driven**.

Controlled ablation (everything fixed, axis swapped): RB **time-axis Calmar 1.39–2.13 → custom-axis
2.82–3.31** (single models). A private axis is also **anti-crowding alpha**, and factors that "drift"
on the time axis often revive on a valid axis.

### Stage 4 — Labeling (the linchpin, `承上启下`)
Supervised **binary trend-segment** labels (up=1/down=0) from a **probability model** — a Gaussian
Mixture / probability clustering (概率聚类) on (log) returns; change-point detection (变点检测) and HMM
hidden states are equally valid label *sources*. **The entire up-leg is 1 and the down-leg 0; mid-
trend pullbacks (回调) keep the trend label** — the label encodes the intent "ride the whole trend."

> "We want to eat the whole up- or down-trend; in the trend there will be pullbacks, but we mark the
> entire segment as long." (`SPINE`)

- Naive next-bar up/down is **"the fakest, completely unusable"** (+10% and +0.01% aren't comparable
  → you label noise, the model learns noise).
- **Trend degree is a parameter** (differencing-order knob; demo labels "5dif"–"9dif" =
  moderate→larger trends), deliberately producing a *ladder/family* of label scales. **Trend level is
  decoupled from axis frequency** (on a 30-min axis you can harvest weekly-level moves).
- **Labels have no good/bad (标签没有好坏之分)** — refuse to score a single label by BIC or per-label
  backtest; the family exists **to be ensembled** (Stage 11).
- **3-class up/down/chop is rejected** as a live target ("financial logic, not math logic" — the
  model collapses it to vol buckets). Binary only.
- **Label-balance hygiene:** aim for a balanced mean (≈0.54 in `ENT`; "≈0.5" data-sufficiency gate in
  `PROMO`).
- **He rejects** AFML book-1 triple-barrier + meta-labeling AND book-2's OLS-t trend scan (replicated,
  "not that good") in favor of clustering/change-point segments.

### Stage 5 — Feature engineering (mathematical, co-designed with the label)
Turn the market into a matrix of purely-mathematical expressions over multiple **window periods**.
Two axes of a feature: the **window** (how much history) and the **expression** (always
differences/ratios, never absolute levels — price 3000 vs 2000 means nothing). Features must
**coordinate (协同) with the label**: "if the label is good but the feature doesn't express it, the
model still won't learn it" (`SPINE`).

> "Data processing, including feature quality, contributes about 70–80% of the model's later
> prediction performance — the model type you pick does not weigh that much." (`ENT`)

- **Demo features = integer-order differencing** ("400 = 80 features × 5 windows", `RB6`).
  **Fractional differencing (d≈0.7–0.8) is the *production* upgrade** (memory + stationarity;
  integer-diff "loses history"). *Demos/syllabus teach integer; live uses fractional.*
- **Entropy (`ENT`):** use **sample entropy (样本熵)**, NOT Shannon (which needs a distribution
  assumption + binning). Dynamic tolerance **`r` from the data RANGE (极差), not std** (std can
  collapse r to null on small windows). Sample entropy is rolling/online-friendly; two series with
  equal std can have different entropy.
- **The 6-category feature framework (`ENT`):** (1) statistical (central tendency, dispersion,
  distribution shape, multi-order stats — *entropy first*); (2) domain (CAPM/FF, IV surface, CCAPM);
  (3) relational (correlation, autocorrelation, mutual information, DCC-GARCH, graph/GNN);
  (4) math-transform (wavelet/Fourier/HHT/VMD, fractional, kernel); (5) time-series & event
  (policy/news/NLP); (6) automated (TSFresh/OpenFE/TSL).
- **Frequency-domain as a COMPLEMENT, never a replacement (`FREQ`):** VMD preferred over HHT
  (math-optimized, anti-noise, no mode-mixing); CWT+SWT (synchro-squeezing re-concentrates energy);
  **never plain FFT** (mode-mixes, repaints). Window = 50–100× trade period. **"Cycle overfitting
  (周期过拟合)" is a distinct failure** (period/asset mismatch).
- **Regime expressions as FEATURES, never decision rules** — HMM states, state-entropy, fractal
  dimension fed in; "let the model infer the trade signal."
- **LSTM/BP-net outputs as FEATURES, not as the predictor** — direct LSTM prediction "always lags by
  one"; feed its output into the downstream tree.
- **Wall-clock-anchored fixed lookback (`ENT`, genuinely-new):** on variable-duration event bars any
  time-dependent feature (vol, sample entropy) suffers **feature-meaning drift** (one bar 120 min,
  next 30). Fix: keep the **close event-driven** but compute the feature over a **fixed backward
  wall-clock window** (e.g. 150 min) — stable meaning, leak-free, custom-axis benefit retained.

### Stage 6 — Screen features against the LABEL, not returns
> "The factor is unimportant; the test method is the most valuable secret." (`FREQ`)

Score features **against the label** (the denoised regime), not against noisy returns/IC-IR. Primary
operator: **Information Gain (IG = H(Y) − H(Y|X))**, keep top-K (e.g. top-30 of ~200). Single-factor
IC/IR testing carries **survivorship bias** — individually-dead factors may form effective
*nonlinear* combinations, so screen *inside* the nonlinear pipeline; prefer **add/remove causal
ablation** over correlation, and **rank-based** correlation over Pearson/R² (which assume normality).

### Stage 7 — Dimensionality reduction / reconstruction (pre-training overfit suppression)
Reduce ~300–400 dims before the model. **Two purposes:** remove collinearity/noise; and **cut
constraint terms (约束项) → suppress overfitting**.
- **Linear PCA** (demo default; doubles as screening) **and non-linear autoencoders** (`AE`: standard
  AE "does nothing"; **VAE his favorite** — latent mean + log-variance; also recurrent/adversarial).
  May **concatenate** PCA-10 ⊕ AE-10 = 20 dims.
- **Dim selection:** PCA by explained-variance; AE by MSE elbow (train every dim 1→N). **Always
  prefer the LOWER dimension over the best backtest** (fewer constraints = more generalization). Low
  MSE ≠ good (standard AE has the tiniest MSE *because it does nothing*).
- **Variance budget — note the internal tension:** `RB6`/`ARB` cite **99.99% → ~35–40 dims**; **`AE`
  explicitly says 95%+, even 99%, "NOT 99.99% — don't inflate the number."** Faithful range:
  **95–99.99% (lecture-dependent)**, with `AE` the conservative anchor.
- **Train-only fit + freeze the transform** (`RB6`): "fit PCA on the portion you take, say 70%, then
  **save that model** and reuse it… applying PCA to the whole will definitely produce a walk-forward
  problem." (The live-inference money-loss story attaches here — see §2d.)
- **CVAE (conditional/supervised) = label-guided reduction** folding factor-selection + dynamic
  weighting into the latent space; runs **label-free at inference** (the only train-vs-inference
  asymmetry he discusses). After a *supervised* AE, the final model **must be a tree**.

### Stage 8 — Model (discriminative trees only)
Gradient-boosted **trees — XGBoost / LightGBM / CatBoost / NGBoost** — as the final model:
interpretable, best on structured/tabular data. **Raw LSTM/Transformer as final model is banned**
("terrible on structured data," "always lags by one") — they belong on *unstructured* NLP data,
converted to features upstream. Linear models can't express finance's nonlinearity (the whole reason
for the ML path). Generative/LLM banned from decisions (consistency + reproducibility). RL only in
quasi-closed environments. **Classification over regression always** (bin if you must); **volatility
is the one sane regression target** (FIGARCH, per-asset memory). **CV is matched to the bar type**
(`ARB`, the richest source): on the **time axis you are NOT IID → strictly time-ordered K-segment CV;
a shuffled KFold is FORBIDDEN**; on a **resampled near-IID axis he "dares use stratified (分层) CV."**
*(This is the known divergence from our purged-CV stance — see §4.)*

### Stage 9 — Evaluation ("out-of-sample of out-of-sample")
Backtest only on a **完全无关的 later period (样本外的样本外)** — never the inner train/test/val split
("looking at the internal test set is slightly cheating"); combination weights from TRAIN only.
**Headline = Calmar (卡玛) = annualized return / max drawdown** ("we rarely look at Sharpe") because it
**governs sizing**: with a DD budget you bound forward return (ann ≈ Calmar × DD-budget). Plus his
proprietary **DA = drawdown AREA (回撤面积)** = the underwater-region area (a recovery-speed proxy) and
**MDT = max-DD duration (in bars)**. **Sharpe/Sortino are not annualized → ordinal use only, never
read the absolute value.** Every claim by **controlled single-module ablation** (freeze all, swap
one); **report nulls openly** (`VOL` showed a no-pattern 3D plot anyway); benchmark vol forecasts vs
the **naive unconditional-vol baseline**.

> "Nothing changed — features, backtest, train, window, CV, DR didn't change — only the axis changed;
> that's why the custom axis is extremely critical." (`RB6`)

### Stage 10 — Meta-sizing (the secondary / 二级 model)
A **second-level (meta) decision model** runs *simultaneously* with the primary and reports whether
the level-1 call is right/wrong. **Critical sizing rule (`FREQ`):** the **level-1 probability is NOT
a calibrated accuracy and cannot be used for sizing** (a two-class model is "always on," so its raw
confidence isn't an accuracy); **only the level-2 probability expresses accuracy → size off IT** (add
/reduce). Note: the `PDF` lists this *separately* from a distinct **capital-scale (资金管理规模)** lever
— **meta-decision ≠ AUM-scaling**.

### Stage 11 — Combination (his no-grail generalization device)
**There is no holy-grail single model/label.** The headline device: combine models sharing the **same
trading cycle but carrying DIFFERENT trend-degree LABELS** (each its own model), combined **at the
signal/position layer** with agreement-gating. You cannot classify regime live (the boundary
problem), so let differently-trended models **indirectly sense market state from a higher dimension**:
**agreement = trend = hold; disagreement = chop = flat** — genuine flat periods with *no explicit
threshold*.

> "We can't judge the market's regime, so we use the combination of models with different trend labels
> to indirectly resist uncertainty — we solve it from a higher dimension." (`SPINE`)

- **Netting (统筹):** within **one axis** signals are simultaneous → **compute the NET position first**
  so opposing signals cancel without paying fees. **Netting boundary:** across **different axes**
  signals arrive at different times → **cannot net, must execute each** (a clean no-look-ahead
  execution limit).
- **2–3 combos suffice** (they tested up to 100 just to find the boundary).
- **Selection:** among consistent equity curves take the **lower-dimensional** member, not the
  highest-Calmar; if the family is wildly uneven, **refuse to select from it** (anti-survivorship).
- The headline **RB Calmar 5.63** came from *simply stacking a few same-axis, different-trend-label
  models* (987 trades + 226 flat) — **axis + combination, not axis alone.** **Multi-AXIS** combination
  (`PDF` Sec.9, independent models on different *clocks*) is a described extension, demoed *lower*
  (the `ARB` multi-axis arb combo is Calmar 4.58). Combination is also the **route to AUM capacity** —
  not perfecting one model.

### Stage 12 — Live inference (a distinct, hard stage)
Training is "only half the work." Live = **real-time resampling + real-time inference (实时采样,实时推理)**
on each completed custom bar, rebuilt from the minute stream. CS: resample the **index** and align
constituents to it. Futures: train/infer on the continuous **index**, order on the **main contract**,
auto-roll. The online-computability doctrine governs what may run here — see §2.

### Stage 13 — Decay-ops
Custom-axis edges still drift (less than time-axis); **don't use one model forever.** Four-layer
defense (`PROMO`): (1) **DD-breach alarm** (live MaxDD vs listed MaxDD — "the dumbest method");
(2) **live shadow model groups** beside the traded one; (3) **incremental retrain every 3–6 months,
before failure**; (4) **universal cross-instrument model** (train-once, "never fails," trades away
per-asset peak return). **Warning:** incremental retraining **can BREAK a working model** (a Shanghai
institution's degraded after incrementing) — **gate any retrain on a label-balance (mean ≈ 0.5)
data-sufficiency check** (if already balanced, more data is unneeded and risky). Vol forecast (`VOL`)
is an **auxiliary plugin** with a **rolling/"alive" threshold**, never primary alpha.

### Stage 14 — Book construction
Diversify across **many symbols × multiple axes/periods** in parallel (choppy names sit flat at zero
cost while trending names pay); **short signal → FLAT** on long-only/drift assets; size by **Calmar
against the product's DD covenant** (Calmar 3 × 15% budget ⇒ ~45% expected annual). Capacity comes
from **diversity**, not from perfecting one model.

---

## 2. The online-computability / look-ahead doctrine (the crux for this repo)

Wang's deployability test is one sharp idea repeated across `ENT`/`FREQ`/`ARB`: **online-computability
is the dividing line between a deployable signal and an offline analysis tool.**

**(a) Labels may use the future; the deployed SIGNAL may not.** Trend labels legitimately span the
whole up-leg — "the future label must be based on the future state (以未来的状态为依据)" (`SPINE`); for
the labeler "you can simply use future return as the feature" (`RB6`). Look-ahead **in Y only**.
*Faithful caveat:* when a student raised the **Viterbi-style** worry (trend-labeling peeks past T),
Wang **did not cleanly separate label-leakage from signal-leakage** — he pivoted to "labels have no
good/bad" and "resampling → IID → change the CV." Our repo's clean label/signal split (the G3
invariant, `n_pred == n_test_bars` sentinel) is **our** discipline, not an explicit Wang proof.

**(b) "Anything that can infer its regime accurately ONLINE would itself be the trading model."**
Route every **global-optimum / repainting** method to **labels/features, never to live trading**:
- **HMM / Markov / change-point** re-optimize the whole path on each new bar (today's "long" flips
  tomorrow on an *earlier* bar). "If a model CAN achieve online computation, that online-computable
  model can serve as your trading model" (`ENT`). Harness HMM only by exporting its **historical
  hidden-state path as labels/features** for a downstream online tree.
- **Frequency decompositions** repaint at the live edge (same boundary problem). **Arbitrage
  hidden-state (MSAR/MSGARCH/HMM)** has the "fatal" boundary problem → route arbitrage into
  **trend-on-the-spread** instead (`ARB`).

**(c) The BOUNDARY / EDGE effect (边界效应) is the deployability trap — NRBO is his fix (`FREQ`).**
Decomposition is fine on history, but at the current bar the forward data doesn't exist, so the
live-edge computation is inaccurate — these filters are explicitly **non-causal (非因果)**. Fix:
**NRBO (Newton-Raphson Boundary Optimization, 牛顿拉夫逊边界优化)** — a sliding-window convolution that
**pads a "transition band" (过渡带) of near-real virtual data weighted by current real-time
volatility/mean** (edge distortion ∝ volatility): "not guessing — a weighted backfill (补缺)."
**VMD + NRBO** is his recommended deployable combo; add a **recursive wavelet (RWA)** for incremental
online computation; in the time domain use (extended) Kalman. **Never plain FFT live.** The only
legitimately-forward input allowed is **option implied volatility (引波)**; everything else must be
historical. (`FREQ` also: predict up/down probability or vol, **never the next price/return** — too
noisy.)

**(d) The linear-DR live-inference pitfall that "cost real money" — reconciled (don't overstate).**
Three distinct primary facts, kept separate:
1. `QA` — the one war-story: *"in the dimensionality-reduction part, during inference we hit
   live-trading problems and actually lost a lot of money (亏过很多钱)."* It attaches to **both linear
   and non-linear DR**, and **Wang gives NO mechanism.**
2. `PDF` M6 — two bullets: *"the problems LINEAR DR brings to live inference"* and *"how to SOLVE
   them"* — and the syllabus's stated cure is **switching to the non-linear autoencoder**, not
   "freeze the PCA."
3. `RB6` — the **train-only fit + save/freeze-the-projection** rule (whole-data PCA = walk-forward
   problem).

**Faithful synthesis:** the only *explicit* fix-rule Wang states is **train-only fit + freeze/persist
the transform** (`RB6`); the money-loss *mechanism itself is unstated* (`QA`); and the syllabus's
*headline cure is "use the non-linear AE"* (`PDF`). So "freeze the loadings" is **our** inferred fix,
not Wang's confirmed cause. **Repo consequence:** the OOS *replay* is immune (the transform runs only
in the training algo), but any LIVE deploy of the GLD `vae`/any PCA config must **freeze loadings**
and prove it online.

**(e) De-scaled / rolling-standardized axis thresholds (去量纲).** A raw turnover/volume threshold
drifts ("30万手 N years ago ≠ now → your axis itself is floating"), so **rolling-standardize the
threshold** before resampling (`AE`/`RB6`/`PROMO`). Operational thresholds must be **"alive, not
dead"** — rolling quantities, never fixed magic numbers (`VOL`).

**(f) Resampling-PHASE sensitivity.** If the live resampling start-point differs from training,
"performance differs a little (多少会有一点点差别)"; mitigation: **train over ALL phase-shifted resampling
cycles ("N倍于重采样") to wash out the dependence** (`SPINE`, + a `PROMO` questioner flagged volume-bar
data-start instability). *Scope: `SPINE`/`PROMO` only.*

**(g) "Identical code paths offline/online" is an INFERENCE, not a Wang claim.** `SPINE` says only
"real-time resample, real-time inference," and `PDF`/`PROMO` say one released codebase carries both
train and live ("runs directly once you swap in your model") — implying a frozen-model shared-code
pattern, **but he never asserts the paths are byte-identical.** Our bit-exact `online==saved`
verification (≤1e-6) has **no Wang analog** — it is *our* stricter standard, and it is exactly the
guarantee the OOS-backtest-must-equal-live work is trying to make real.

**(h) Execution-layer no-look-ahead (`ARB`).** Netting + the netting-boundary (same-axis nettable,
cross-axis must each execute) is itself a causal execution constraint; arbitrage adds a demand to
**count the fault-tolerance/slippage band into the backtest.**

---

## 3. The honesty / anti-overfit doctrine

- **Distribution diagnostic as the prior** — read where you earn (tails) vs bleed (peak) *before*
  training.
- **OOS-of-OOS (样本外的样本外)** — a later, fully-unrelated window; the inner test split is "slightly
  cheating"; combination weights from TRAIN only.
- **Controlled single-module ablation** — freeze everything, swap one stage; how he attributes every
  claim.
- **Family-consistency, refuse-to-select** — inspect the whole trained family across the dim grid;
  consistent → take the **lower-dim** member; wildly uneven → **refuse to select from that family.**
- **Prefer lower dimension over best backtest** (fewer constraint terms = more generalization).
- **No subjective pre-judgment** — visualize, or hold all else fixed and vary one stage.
- **Report nulls openly**; **replicate the canon before trusting it** (replicated & rejected de
  Prado's triple-barrier + OLS-t trend-scan; "methods are bought with losses" — NRBO came from
  residual plots of failed paddings).
- **Metrics: Calmar + DA + MDT; Sharpe/Sortino ordinal-only.**

---

## 4. Reconciliation with this repo

**Built / exceeds:** information-driven bars (`logdollar`/`imbalance` = his #1 lever); probabilistic
trend-segment labels (`trend_leg`/`regime_gmm`/`bgm`); **information-gain** screening (the one Wang
lever adopted by name); trees-only depth-capped; classification not regression; Calmar + drawdown-area
(`lb.metrics`); OOS-of-OOS via real online replay; long-only mapping for drifters (his `ȳ≈0.7`);
asset-physics mechanism routing; single-instrument specificity. The **honesty stack** (permute
control, DSR/Holm-Bonferroni, PBO/CSCV, Hansen SPA, MinBTL, e-values, bit-exact online==saved ≤1e-6,
bar determinism ≤1e-9, adversarial leak audits) is **far stronger than anything Wang teaches** — he
runs uncorrected best-of-N label sweeps and eyeballs family consistency.

**Closed by experiment here (stronger evidence than his demos):** sticky-HMM labeler
(predictable-not-profitable); the **label-level** `tleg fast+mid+slow` "+" blend that *averages
calibrated predictions* (3.66 < 4.02 — dilutes); meta-labeling-as-gate. **VAE closure was reversed:**
torch VAE 3.954 > pca 3.843 on GLD, permute-confirmed — **Wang's nonlinear-reduce doctrine validated**,
and it is the deployed GLD crown's reducer.

**He does / we (mostly) don't:**
- **Same-ticker SIGNAL-level combination + netting** — independent models per trend-degree (or per
  axis), combined at the *position* layer with **agreement-gating + net-before-order**. This is
  mechanically different from our dead `tleg` blend (which averaged *predictions*); his version is his
  headline 5.63 lift and is **unraced here**.
- **Rolling de-scaled** bar thresholds (ours are TRAIN-only constants + log transform).
- **Frequency-domain features** with boundary engineering (our spectral *bar-axis* died; freq
  *features* never built).
- **Regime-as-FEATURE** (we use regime as labeler/gate only).
- **Wall-clock-anchored feature windows** (ours are bar-count windows).
- **Scheduled retrain cadence + live shadow fleet** (we re-validate reactively).
- **Meta-prob as continuous sizing** (we use meta only as a hard gate; size from the calibrated
  *primary* via the de Prado CDF).

**Known CV divergence (Wang is a primary source *for* the disagreement):** Wang licenses stratified
KFold *on resampled near-IID bars* — but **on the time axis he insists on strictly time-ordered
K-segment CV and forbids shuffled KFold** (`ARB`). We keep **purged/embargoed time-ordered CV
everywhere** (overlap IS the signal; uniqueness weights hurt) — the deliberately conservative branch.

**Genuinely-new, never-raced, in-rule levers:**
1. **Distribution-shape mechanism router** (normal→trend / peak-up→reversion / bimodal→event) as a
   front-of-funnel acceptance test.
2. **Near-Gaussian low-density clocks** (RealVar@5k / Vol@5k) — deliberately near-IID low-N bars.
3. **Variance-budget minimum-K PCA** (95–99.99%, smallest-K-within-tolerance).
4. **Same-ticker signal-level agreement-gated combination + netting.**
5. **Regime-as-FEATURE** (posterior + its rolling entropy into the tree).
6. **Wall-clock-anchored feature windows** on event bars.
7. **Meta-probability as continuous sizing source.**
8. **PCA/VAE live-freeze guard** (his "lost real money" warning; backtest immune, live must freeze) +
   resampling-phase invariance certificate + decay-ops bundle (shadow fleet + 3–6mo retrain gated on
   label-mean ≈ 0.5).

---

## 5. Concrete numbers (his cited ablations)

**Axis swap — controlled single-module ablation, RB, ~25 months OOS (`RB6`; everything else held;
time-axis config = 240-min, 10-fold, window 75, linear PCA, 400 integer-diff features):**

| Config | Return | MaxDD | **Calmar** | DA | Trades |
|---|---:|---:|---:|---:|---:|
| TIME 5th-order | 33.81 | 11.69 | **1.39** | 54.3 | 1492 |
| TIME 9th-order | 35.71 | 8.07 | **2.13** | 39.97 | — |
| CUSTOM 5th | 58.44 | 9.67 | 2.90 | ~34 | — |
| CUSTOM 6th | 70 | 10 | **3.31** | 34.45 | — |
| CUSTOM 7th | 62.3 | 9.16 | 3.27 | 24.81 | — |
| CUSTOM 8th | 47.82 | 7.81 | 3.19 | 29.92 | — |
| CUSTOM 9th | 65.3 | 11.12 | 2.82 | 30.22 | — |

→ axis-only swap: **Calmar 1.39–2.13 → 2.82–3.31** (single models).

**Combination lift, RB:** a few same-axis, different-trend-label models, simply stacked → **return
67.81, MaxDD 5.78 (~halved), Calmar 5.63, DA 23.46, 987 trades + 226 flat** (avg ann ~32.55%, MDT 56).
*5.63 = axis + combination, NOT axis alone; the demo deliberately uses the weaker integer-diff +
linear-PCA config, so it's a FLOOR.*

**Entropy swap — controlled ablation, RB ~25 mo, 300 features held, swap 30 integer-diff → 30 sample-
entropy (`ENT`; folds=5, windows 5→3, PCA reduce):**

| Setting | Return | MaxDD | **Calmar** | DA |
|---|---:|---:|---:|---:|
| Exp A (6th-order label) w/o entropy | 47.34 | 7.43 | >3 | 31.56 |
| Exp A **+ 30 entropy** | 50.54 | 6.66 | **4.51** | 25.45 |
| Exp B (stronger-trend label) w/o entropy | 54.16 | 8.37 | 3.1 | 30.96 |
| Exp B **+ 30 entropy** | 63.25 | 6.85 | **4.44** | 23.43 |

**Other:** dimension parsimony — 30-dim slightly beats 7-dim → **pick 7-dim** (`PROMO`). PCA budget —
400→35 dims @ 99.99% (`RB6`), ~40 @ 99.99% (`ARB`), **95%+/99% "NOT 99.99%" (`AE`)** (tension). AE/axis
ablation is **confounded** (both axis AND reducer changed, `AE`: 4.23–4.28 → 5.38 — the +1 Calmar
can't be credited to the AE alone; MSE@30-dim: standard AE 0.0082 *because it does nothing*, VAE
0.646). Demos: CSI300 ETF 15mo Calmar ~5 (ret 107.21 / MaxDD 15.69 / DA 6.23); ETH 12mo no-leverage
Calmar 5.23 (ret 81.14 / MaxDD 15.5 / DA 86); arbitrage (glass–soda, `ARB`) Calmar 4.58 (838 trades +
196 flat). Vol (`VOL`): FIGARCH, 16y, 20-day rolling-std target, vs unconditional-vol baseline;
fractional-diff production order **d≈0.7–0.8**.

---

## 6. Source corpus

Genuine-Wang lectures (gitignored, `refs/uni/transcripts/*.large-v3.txt`): `uVnOeOcoivw` (SPINE),
`BV1FnjuzUEJD` (RB6), `Ca1n2jgKjrs` (ENT), `vL8DY2NP96I` (AE), `tGzbK8c3R_A` (VOL), `WkZ6TUg_gK4`
(FREQ), `q922tUTWmCY` (ARB), `BV1bpstzBEVm` (PROMO), `BV1a6enzLEVw` (QA). Plus
`refs/pdfs/wang_course_2026-06.pdf` (PDF — 7-page syllabus, 11 sections, 6 first-public levers) and
`refs/qa_doc/wang_qa.tex` (our questions + cited specs).

*Reconstructed from a 13-agent primary-source extraction (one reader per lecture) + adversarial
fact-check; quotes and ablation numbers verified against the transcripts. Where the lectures
themselves disagree (PCA budget, fracdiff demo-vs-production), both readings are kept and flagged.*
