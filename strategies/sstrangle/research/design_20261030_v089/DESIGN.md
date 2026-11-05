# 0.8.9 — causal custom-axis design correction

2026-10-30. Status: design and executable regression requirements prepared; production implementation and release acceptance pending. Supersedes the corresponding semantics of 0.8.8, not its immutable source or historical results. See REVIEW_V088.md, TEST_PLAN.md and test_matrix.json.

## Scope and source basis

Retain Wang Yiming's information-density sampling motivation and shared index axis, as documented with local transcript passages in ../design_20261029_v088/DESIGN.md. The exact recipes, 20-session calibration and 26-event target are our research choices, not claims attributed to Wang. One-minute data supplies observations; it is not itself a custom axis. No IID, profitability or executable-liquidity claim follows from resampling.

Deliver a deterministic SPX variation axis, SPY traded-dollar alternative and 15-minute time control, aligned to SPXW observations. SPY close-times-volume remains separately labeled approximation. Do not invent SPX volume. Preserve fixed C0/C1/P1 schedules and existing native funding, margin intervention, costs and official-settlement accounting during shadow verification. Trading on axis events or fitting a model requires a separately frozen experiment. No parameter search to repair profitability.

## Causal event and data contract

Use one append-only event ledger consumed in availability order. Every row binds release, artifact hash, source row ID, event time, observed interval, historical available time or explicit unknown, ingestion time, revision identity, calendar pin and quality flags. Ingestion today does not establish historical availability. Equal-time inputs are excluded from predecision features unless a separately specified engine ordering proves availability; default requires availability strictly before decision.

Modes are explicit: fixture, staged sampled diagnostic, published sampled diagnostic, strict replay. No single `verified` Boolean promotes one mode to another. A receipt must attest the same release and artifact hashes, resolution, checks, coverage and publication state; matching the hash of a failed or unrelated receipt is insufficient. Native 60-second observations are mandatory; never upsample five-minute data. Retain genuine provider clocks when supplied, rather than overwriting them with nulls or interval labels.

Strict mode requires accepted Greek methodology and all market/input/availability clocks. Both strict and sampled modes reject any known clock later than the decision or contradictory clock ordering. Sampled mode may explicitly assume an unknown clock only for diagnostics, never overwrite a known future clock. Quote-event, Greek as-of and underlying Greek-input ages must each be at most 120 seconds. Require input <= Greek computation <= Greek availability < decision; quote event <= observation <= availability < decision. Missing strict evidence yields a reasoned exclusion.

Select the newest known market state per contract first, then validate spread, prices, freshness and provenance. A newer crossed/invalid state blocks that contract; do not revive an older convenient quote. This deliberately changes 0.8.8's latest-eligible policy. Resolve identical duplicate rows by identity; conflicting ties fail the affected contract. Apply the 30-second selected-leg event-time skew gate in the actual package selector, not merely a standalone utility. Persist candidate exclusions and selected-leg evidence. Dated quoted inventory alone is not point-in-time listing proof. Fixed-DTE Greeks cannot silently qualify as true expiry-time Greeks.

## Calendar, gaps and immutable decisions

Bind session labels to an exchange calendar with UTC intervals and New York dates. Verify open/close, holidays, early closes and DST; each decision must belong to a declared session and allowed decision interval. Expiry time comes from contract/calendar metadata. Report minutes to expiry and wall-clock duration explicitly. A 391-point snapshot grid including both endpoints is not 391 one-minute OHLC intervals; a regular session has 390 such intervals.

A missing expected minute creates a quality event at the time the gap becomes known. Invalidate the partial bar, reset the return anchor and increment segment ID. Once that event is known, features remain missing until a complete eligible bar in the new segment exists. Never backdate this invalidation into an already emitted decision. Include quality events even when no partial bar existed; completed bars alone cannot express this state. The feature API must accept the ledger/as-of state, not just a list of bars. Missing final minutes are recognized by the calendar close watermark. Do not bridge missing or overnight returns.

Late revisions are separate events. They cannot rewrite frozen decisions or already emitted bar identities. Reject them from the frozen online path and record exclusion; a corrected-history diagnostic needs a new data-run identity. Strict replay uses historical availability; sampled engine replay records actual slice-delivery time as well as assumed historical timing. A delayed slice is not available at its interval end merely because the bar says so.

## Axis and feature semantics

Freeze a threshold at the open using the median activity of the last 20 complete eligible prior sessions divided by 26. Bind calibration inputs to recipe, release, calendar and availability before open. Keep the existing inclusion of complete early-close sessions explicit for continuity; report their influence and event-count sensitivity, without refitting after inspection. Twenty-six is a target, not a guaranteed event count. Missing, incomplete, nonpositive or incompatible calibration observations cannot warm up the axis.

SPX variation activity is the sum of consecutive valid one-minute squared log close returns within a segment; the first valid close establishes the anchor. Dollar activity is verified traded notional in USD. Consume a whole minute, emit at most one bar on threshold crossing, record overshoot and reset accumulation to zero. Never split a minute into invented events. Time control is anchored to session open at 15-minute boundaries, threshold=15 and unit=minutes; activity recipes have their own units. Gap-contaminated time intervals cannot become valid complete controls. Tails remain incomplete and excluded.

Store each bar's start reference close separately from OHLC open. `last_return` is close-to-previous-completed-close in the same segment; it is missing without an eligible anchor. Multi-bar returns require their preceding anchor and all bars in the same segment. Preserve `open_to_close_return` as a separately named descriptive value. Store minute realized variation and event-return squared sums as different features; never call squared OHLC returns minute realized variation. Window length is explicit and missing windows remain missing. Age limit remains 30 minutes, with availability and segment gates applied first.

## State, output and adapter design

Checkpoint schema includes recipe/version, source and calendar pins, source cursor, session/segment, calibration history, partial bar, prior close, quality ledger cursor and emitted sequence. Validate full-state digest and semantic invariants before restore. Hashes detect accidental corruption; authenticity requires a trusted external manifest. Reject tampered state, incompatible recipes and duplicate cursors. Bound in-memory history to calibration and feature windows; stream immutable bar/decision shards with a final completion manifest. Failed/incomplete runs cannot look like complete bundles.

QC integration has explicit initialize, observe, decision and finish hooks. Finish is idempotent and called at algorithm end, so the last session is finalized without waiting for another session. Record actual engine receipt time. Observer-owned malformed data or telemetry errors mark the shadow invalid and write bounded diagnostics while preserving the original strategy callback exactly once. Do not catch or suppress errors from the native strategy, funding or margin subsystem. When features eventually control trading, invalid state must prevent the new feature-dependent entry under a separately specified policy; it cannot fall back silently.

The shadow must export event boundaries, feature provenance, errors and session completion, not only overwritten runtime counters. Python compilation and source-body similarity are preliminary checks, not QC execution parity. Require short cloud runtime, finalization, quota and source-readback checks followed by exact order/cash/expiry comparison before long runs.

## Acceptance and research gates

Run local requirements, calendar/restart/property tests, verified-provider replay, short QC shadow and then funded replay in order, as detailed in TEST_PLAN.md. Every output identifies mode and unresolved gates. A completed sampled pipeline cannot set economic acceptance true. Test changes in quality status as well as values.

Audit activity dispersion, durations, overshoot, counts, return tails and return/absolute/squared-return dependence on common eligible sessions after common warmup. Do not correlate returns across gaps or overnight. Use session-block uncertainty and chronological comparisons, not independent-trade bootstrap or random bar splits. Do not choose the recipe by highest historical profit. Data-quality failures block comparisons; otherwise report tradeoffs rather than retrospectively inventing a scoring rule.

The already examined 2022–2026 period is historical replication, not untouched holdout. Freeze recipes and record inspection cutoffs before prospective data accumulation. Future model labels include their expiry availability; purge split boundaries through label horizon and group by session. No model is authorized by this design alone.

Economic acceptance still needs realistic fills/fees, official settlement, marked drawdown, full admission/skips, capacity and native funding. C0 margin failures and P1 losses remain evidence. One-entry-per-day P1 must not inherit a 360/400 trades-per-year requirement. New axis version cannot erase those findings.

## Implementation order

1. Add versioned contracts, ledger and source/receipt validation under a new v089 namespace.
2. Implement gap-aware streaming state, calibrated axis, explicit return anchors and checkpoint validation.
3. Implement causal alignment and wire package-level gates; stream reproducible artifacts.
4. Implement isolated QC observer and finalization, then pass local and short cloud parity gates.
5. Run provider and statistical acceptance; only then preregister a funded comparison. Preserve v088 as the regression target throughout.
