# 0DTE custom-axis pipeline design

Date: 2026-10-29, Asia/Shanghai. Status: design specification; no new axis strategy, trained model or performance claim. This is an additive research track. Frozen 0.8.5/0.8.7 sources, accounts and provider pins remain unchanged.

## Decision

Add a causal information-clock layer between verified minute observations and feature/label generation. Use a shared SPX price-variation axis for the initial implementation; compare it with SPY traded-value bars and a matched-frequency time-bar control. Align the SPXW option universe to this shared axis. Do not independently resample each expiring option contract: changing listings, expiry, liquidity and asynchronous bars would make package features difficult to compare.

One-minute option data is the minimum requested input resolution for the new research track. It is a finer observation grid, not the custom axis itself, and not proof of executable NBBO or historical availability. Five-minute observations remain archived coarse diagnostics. No interpolation of five-minute quotes or Greeks into fabricated one-minute observations.

The axis is a required research module, not a promised cure for losses or margin failures. C0's margin failure and P1's negative funded result remain findings. The first release constructs and validates the axis and its aligned dataset; no new entry filter is silently introduced.

## What the project sources support

| Source | Passage | Supported interpretation |
|---|---|---|
| `strategies/wang-ml/uni_yt/BV1bpstzBEVm.large-v3.srt` | 00:24:42–00:25:29, cues 787–807 | Resampling aims to make information density within bars more uniform; equal clock durations contain unequal activity; traded value is an example. |
| `strategies/wang-ml/uni_yt/uVnOeOcoivw.large-v3.srt` | 01:02:32–01:03:13, cues 1661–1675 | Custom-axis observations may be closer to IID, but the axis can still drift. This is a lecture claim to test, not permission to assume IID. |
| Same transcript | 01:08:07–01:08:39, cues 1809–1821 | Sample a common index axis and align constituent observations to it. Applying a shared axis to an option chain is our engineering adaptation. |
| `strategies/wang-ml/uni/transcripts/BV1pSnT6yEHT.proofread.txt`, lines 475–500 | Latest retained lecture, 2026-10-18; guide locates this in approximately 19:40–25:55 | Data acquisition/analysis → custom-axis resampling → labels/label validation → features/reduction/training → historical evaluation and reproducible inference. |
| `strategies/wang-ml/qa_doc/wang_qa.tex`, custom-axis formula | Local questions prepared for Wang, not a transcript of his answer | Existing LogDollar proposal uses a rolling standardized log(price × volume) cumulative excursion and TRAIN-only threshold fitting. Do not attribute its exact formula or parameters to Wang. |
| `strategies/wang-ml/autoresearch/modules/bar_builder.py` | Existing implementation | Useful prototype interfaces for dollar, volatility and range bars; not a validated 0DTE implementation. |

The older transcripts are machine transcriptions and contain transcription errors. The latest transcript is terminology-proofread, with its limits recorded in `LATEST_VIDEO_RESEARCH_GUIDE_20261019.txt`. Source hashes and paths are in `source_manifest.json`. No lecture performance examples establish performance here.

## Existing code audit and reuse boundary

`bar_builder.py` accumulates close × volume for dollar bars; its volatility contribution is squared log-return × sqrt(volume), an existing project formula rather than a verified Wang prescription. Its `TickBarBuilder` counts update calls: when fed minutes it counts minutes, not market trades. Its `build_bars` fits thresholds using the entire supplied array; passing evaluation data would leak future scale into historical boundaries. Its emitted record has only close timestamp/log price, without availability, session, overshoot or provenance.

Reuse the update/emit interface, but implement a separate stateful builder with an explicit fit artifact and online replay. Do not copy full-array fitting, label minute counts as ticks, or import the previous ETF performance-selected settings. True tick, imbalance and run bars require trade/event data and are outside this one-minute delivery.

## Initial recipes, fixed before evaluating returns

These are proposed engineering choices, not formulas supplied by Wang. Only two information axes and one time control enter the initial comparison; LogDollar remains documented but deferred.

1. **Primary SPX realized-variation clock:** for consecutive valid same-session minute closes, `u_t = log(S_t / S_(t-1))²`. Accumulate `A += u_t`; complete an axis bar at the first fully available minute for which `A >= theta_d`. No synthetic index volume is required. This measures sampled price variation, not full continuous quadratic variation or all information.
2. **SPY traded-value alternative:** `u_t = trade_notional_t` where genuine dollar turnover is supplied; otherwise explicitly label `u_t = raw_close_t × actual_volume_t` an approximation. Use the same stopping rule. SPY is a tradable activity proxy, not SPX volume and not the SPX settlement price. Never mix exact turnover and the approximation within an experiment.
3. **Time control:** 15 completed minutes per bar, session anchored, with the same availability, gap and feature rules. Compare frequency/distribution metrics at comparable observed event counts; never call it a tick axis.

For each information axis, freeze the scaling rule: `theta_d = median(U_j for the previous 20 complete eligible sessions) / 26`, where `U_j` is that recipe's whole-session activity. The threshold is set before session d using only information available then and is constant throughout d. Target 26 is a research resolution budget (roughly 15-minute average spacing on a regular session), not a guaranteed count or a profit-selected optimum. Twenty complete preceding sessions are required; otherwise no axis decision. Acquire 60 preceding trading sessions to allow warmup and missing-session exclusions.

For an early-close session, use the same threshold; fewer events are expected. Do not calculate today's threshold from today's total or force 26 events. No intraday recalibration, volatility targeting of positions or capital change is implied. The mathematical rule is frozen; its numeric threshold may evolve causally from past data. Record training/evaluation separation even for unsupervised axis selection.

## Exact streaming semantics

- Read UTC event timestamps, interval start/end and source availability separately; map sessions using the actual instrument calendar and America/New_York. A bar ending at 10:00 cannot influence a 10:00 order unless its availability and deterministic processing order prove that it arrived first. The primary fixed-slot comparison uses strictly earlier completed bars.
- A historical minute is usable only after its interval end and verified availability. Offline backfill receipt time is acquisition lineage, not historical availability. Where unavailable, produce a separately labeled sampled-assumption dataset; strict replay stays blocked.
- Process accepted minutes in stable `(available_at, event_time, source_sequence)` order under a declared late-data policy. Reject duplicates and revisions from the original as-of path; a correction produces a new dataset identity. Preserve the receipt and reason for exclusion.
- For SPX, the first valid session close initializes the return reference. Do not include overnight return in intraday variation. Store overnight gap as a distinct context feature if verified data exists.
- One input minute can produce at most one completed axis bar. Include that entire minute, record `overshoot = A - theta_d`, then reset A to zero. Do not split a minute or manufacture multiple simultaneous crossings. This boundary rule must be identical locally and in QC.
- Reset unfinished accumulation at session end. Save an incomplete tail with `is_complete=false`; it is excluded from trading features. Do not force a trade or carry a tail into the next expiry/session.
- A missing expected minute invalidates the current partial bar. Clear it, reinitialize the price reference on the next valid minute, and record a gap segment; do not bridge the missing return. A vendor-verified no-trade minute is distinguished from missing data. Do not silently fill forward stale quotes.
- Record wall-clock duration, number of valid input minutes, activity and overshoot for each bar. At a fixed decision, a completed bar older than 30 minutes is stale for the initial feature interface; skip with a reason. Sparse/quiet sessions are evidence, not a reason to relax the rule.
- Use closed bars only. Every bar carries the maximum of input availability times and computation completion semantics. Prefix replay, batch replay and restarted replay must produce identical bar identities and boundaries.

## Option alignment and the one-minute requirement

SPX/SPY establish event boundaries; one-minute SPXW NBBO/Greeks provide cross-contract state, fills and marks. Full-session coverage is required because axis boundaries are not known before replay. Selected-trade-only data and minute windows around the old 13 slots are insufficient.

For each decision deadline, select the last independently eligible observation per contract. In strict mode require quote-event time ≤ historical availability ≤ decision deadline; use actual quote age, not interval label, with the inherited 120-second maximum and 30-second maximum inter-leg quote-event skew. Greeks must have their own as-of/model/input clocks and be available before decision. Use synchronized underlying references. One-minute snapshots can still fail these gates, and those failures remain explicit.

Persist the entire candidate/exclusion table, not only selected contracts. Apply actual listing/expiry eligibility and exact wing geometry. Keep raw quote observations distinct from trade OHLC, bid/ask minute aggregates and filled-forward snapshots. Official settlement is consumed only by expiry accounting, never the predecision axis/features.

For future axis-triggered execution, wait for the axis close to be available and use an explicitly subsequent eligible quote observation for modeled fills. Snapshot spread crossing with commissions/slippage is still a fill model, not proof of multi-leg liquidity, queue priority or attainable fills. Sizes and quote conditions remain required diagnostics.

## Integration into the QC → local → QC pipeline

| Stage | Deliverable | Gate |
|---|---|---|
| 0. Data acceptance | New release pin, one-minute coverage matrix, clocks/provenance and gaps | No 5m interpolation; no invented clocks; complete declared pilot coverage |
| 1. Axis engine | `axis_recipe.json`, `axis_thresholds.parquet`, `axis_bars.parquet`, `axis_state.json`, replay checks | Causal scaling; deterministic prefix/restart parity; session/gap tests |
| 2. Aligned research table | `axis_option_observations.parquet`, `decision_features.parquet`, candidate exclusions | All observations available by deadline; no unfinished bars or future joins |
| 3. Statistical axis audit | `axis_quality.json` and plots | Compare time control on TRAIN and chronological validation before selecting an axis |
| 4. Fixed-schedule shadow | Original C0/C1/P1 decisions plus axis features; no rule changes | Exact legacy opening/expiry/cash parity; axis computation cannot alter trading |
| 5. Optional learned gate | Separately specified labels/model, frozen before evaluation | Leakage-safe chronological validation; predictions logged before trading |
| 6. Local funded replay → QC verification | New immutable strategy/data identities, full source/order/mark/settlement archives | Native buying power, official settlement and all realistic costs; explain every admission difference |

The first implementation adds modules under a new `strategies/sstrangle/poc/custom_axis/` namespace: `contracts.py` (schemas), `axis_builder.py` (streaming state), `calibrate.py` (past-only thresholds), `align_options.py` (as-of joins), `audit_axis.py`, `qc_axis_adapter.py`. This document specifies interfaces; these modules are not yet implemented. Existing v087 `research.py` groups by fixed HH:MM; it cannot be reused unchanged for irregular-axis alignment. Provider ingestion remains in data_providers, while these sampling, modeling and risk decisions remain in qc_work.

Minimum axis row: `axis_id, recipe_hash, data_release, session, segment_id, sequence, start_event_time, end_event_time, available_at, threshold_source_end, threshold, activity, overshoot, input_minutes, duration_seconds, open/high/low/close, is_complete, quality_flags, source_row_hashes`. Preserve SPX and SPY identities separately. Feature row additionally records `decision_at, last_axis_id, axis_age_seconds, feature_recipe_hash` and option/Greek observation identities. Threshold/state serialization must support replay without refitting.

Initial feature audit: last completed axis return; cumulative return over 3/6 closed bars; 3/6-bar squared-return sum; wall-clock duration and activity intensity; option ATM IV/skew and selected-leg spread only when point-in-time Greeks/quotes pass. Keep minutes-to-expiry, wall-clock time, overnight gap and calendar context explicit. Six event bars do not represent a constant theta-decay horizon. Do not train a filter merely because the dataset can be generated.

If labels are later introduced, define them separately from the axis: e.g. realized underlying variation to expiry or the frozen package's net expiry payoff under realistic entry costs. Record label start/end/availability; outcome settlement can appear only in labels/accounting. An event-count horizon is not interchangeable with hold-to-expiry economics. Forward-only state inference is mandatory for any regime model.

## Statistical and engineering acceptance

Hard engineering gates: no future availability joins; thresholds use only prior complete sessions; identical prefix/batch/online/restart outputs; no synthetic multiple events within a minute; explicit missing/stale/early-close/DST/tail treatment; complete row provenance; old decision/cash parity in shadow mode. Include fixtures where a threshold crosses exactly, a minute overshoots, a gap occurs, a revision arrives late and a session has no completed bar.

Audit information-density dispersion, bar-duration quantiles, overshoot ratios, event count by session/time-of-day, distributions of returns and squared returns, tail behavior, autocorrelation of returns/absolute/squared returns, and stability across chronological windows. Report uncertainty with session blocks, not independent-trade resampling. Normal-looking returns, low kurtosis or a nonsignificant test do not establish IID; squared-return dependence and expiry-label overlap remain relevant.

Do not select the axis by the most profitable historical backtest. Predeclare a small comparison, use data-quality/causality gates first, then choose only if reduced activity dispersion and acceptable duration/overshoot behavior persist out of sample without worsening tail/dependence diagnostics. If recipes trade off those objectives, retain the time control and report an unresolved choice rather than inventing a scalar optimum after inspection. A statistical pass is not a profitability pass.

Proposed chronological research partitions: 2022-05-16–2023-12-29 development, 2024 validation, 2025–2026-10-22 historical replication. This entire period has already been examined in 0.8.7, so the last partition is not an untouched holdout. Freeze the new recipe before prospective accumulation after 2026-10-22; record which later sessions were already inspected. Training/validation labels are purged at split boundaries through expiry; use session-grouped chronological evaluation and an embargo covering the label horizon. Do not randomly split bars or overlapping same-day options because custom axes are alleged to be closer to IID.

Economic gates remain separate: complete period, realistic execution assumptions, all fees, official expiry cash, native margin intervention, no supplemental capital, marked drawdown, skipped/admitted trades and capacity limits. One-entry-per-day P1 cannot inherit a 360/400-trade annual threshold. Do not use custom axes to force a desired trade count or erase previous failures.

## Deferred axis-triggered trading

After the fixed-schedule shadow and any separately frozen model tests pass, a distinct experiment may trade on completed axis events. It needs a new contract specifying first/last entry times, maximum packages/day, minimum inter-entry time, maximum concurrent exposure and an opportunity-matched time control. Preserve physical time to expiry and native portfolio funding. Those trading-rule choices are deliberately not selected in this design; generating a custom axis does not authorize an unbounded entry schedule.

## Immediate work order and blockers

1. Send `DATA_REQUIREMENTS.md` to the provider chat and obtain feasibility/coverage receipts. One-minute SPXW quotes/Greeks and underlying minutes are P0; genuine quote clocks remain a separate hard gate.
2. Implement the streaming builder and synthetic leakage/session tests locally; these do not need provider completion.
3. Verify a bounded one-minute pilot, then build shadow axes with a new data-run identity. Compare SPX variation, SPY activity and the time control without strategy tuning.
4. Publish axis-quality and shadow-parity results. Only a separate preregistered experiment contract can define a learned gate or axis-triggered strategy for full replay.

Current blocker: the verified provider recheck of release 20261028T110443Z_ea3a5193 found no historical availability timestamps in the SPXW quote/Greek panels, and almost no quote-event clocks. More one-minute rows alone cannot resolve strict replay. No subscriptions or purchases are authorized by this requirement.
