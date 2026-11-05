# Provider requirement: one-minute SPXW data for 0DTE custom-axis research

Request ID: QC_0DTE_CUSTOM_AXIS_1M_20261029. Consumer: `/home/vic/qc_work/strategies/sstrangle`. Requested by user on 2026-10-29 Asia/Shanghai. Priority: one-minute inputs replace five-minute inputs for the new primary research track; preserve all older source evidence and release pins. This requests data acquisition/verification/delivery, not provider-side strategy construction or trading.

## P0 scope

- SPXW PM-settled same-session expiry options, both calls and puts, **one-minute observations throughout the eligible trading session**, 2022-05-16 through 2026-10-22 for the frozen comparison. Keep later completed sessions in a distinct prospective release.
- Entire listed same-day chain, with all admissible OTM delta candidates and exact ±20-index-point hedges. Do not fetch only QC-selected contracts, crop to a profitable universe, use hindsight delta selection, or silently impose QC's ±60-strike subscription. If full-chain feasibility forces a boundary, deliver that explicit universe and missing-contract inventory first; it is not full-universe acceptance.
- One-minute SPX raw index price observations and SPY raw trade OHLCV, synchronized in UTC, including 60 trading sessions before the start for axis calibration. SPX volume is not required and must not be invented. SPY is an activity proxy; preserve its corporate-action/adjustment metadata.
- Preserve QQQ raw daily prices used by the frozen prior-session filter. QQQ option backfill is not on this request's critical path.
- Full-session one-minute coverage is necessary because custom-axis boundaries are endogenous. Sparse windows around 09:35/half-hours are insufficient for event alignment and intraday mark/risk reconstruction.

## Separate required data products

| Product | Required fields and semantics |
|---|---|
| NBBO or explicitly labeled quote source | Contract ID, interval start/end, snapshot observation time, bid/ask prices and sizes, venue/condition/status, real bid/ask event times if supplied, consolidated quote time, quote age, historical availability time and its definition, source/endpoint/receipt. Disclose if not NBBO. |
| One-minute Greeks | Delta, gamma, IV; theta/vega if available; calculation/as-of/availability timestamps, synchronized underlying price/time, quote input identifiers or input time, model/version and units, rate/dividend/forward conventions, quality and convergence status. Native vendor outputs and locally derived values must be separate. |
| Option trades/volume | Actual trade OHLCV and count where available, separate from quote snapshots. Do not label quote updates as trades or trade bars as NBBO. Useful for liquidity auditing; exact trade-derived option activity axes are deferred. |
| SPX/SPY underlying minutes | Raw OHLC, interval semantics, event/availability clocks, source receipts; SPY actual volume and turnover/trade count when supported. State whether turnover is actual or close×volume approximation. |
| Contract/calendar | Root, identifier mapping, listing/eligibility, expiry/trading cutoff, strike/right, multiplier, exercise/settlement style, actual session/early-close calendar and adjustment history. Distinguish no-listed-expiry from missing collection. |
| Official settlement | Official SPXW PM reference, expiry date/type, source, publication/revision times and raw evidence. Preserve separately from final-minute close. |

A one-minute bar must not be described as a contemporaneous executable quote merely because its interval label equals the decision minute. Distinguish point snapshot, last quote carried into a minute, bid/ask OHLC, and actual quote-event observations. Preserve stale/one-sided/crossed rows with quality flags and exclude them only through explicit consumer rules.

## Clocks and known gap

The separately verified release `20261028T110443Z_ea3a5193` contains 28,690,155 SPXW quote rows across 838 sessions and 19,639,832 Greek rows across 603 sessions. All historical availability values are null; Greek quote times are all null and quote times are null except four quote rows. Evidence: `/home/vic/qc_work/strategies/sstrangle/results/qc_poc_20261027_v087/provider_release_recheck_20261028T1157_corrected.json`. This is evidence for that release, not an assertion about every new delivery.

Provide a feasibility matrix for **interval resolution**, **actual event timestamp**, **historical availability**, **Greek input timing**, and **full-date/full-chain coverage** separately. Acquisition/received-at timestamps from a 2026 backfill do not establish what was known in 2022. If the vendor cannot supply historical availability or quote-event age, retain nulls and label the dataset sampled historical observations; document any conservative latency assumption separately. Do not synthesize clocks from interval labels.

Consumer strict mode requires quote_event ≤ available_at ≤ decision, quote age ≤120 seconds and cross-leg quote-event skew ≤30 seconds; Greeks and their inputs must be available by the decision. One-minute resolution does not automatically pass those gates. Provider delivery should expose values and failure counts, not silently relax them.

## Acquisition sequence

1. Confirm endpoint support, retained entitlements, storage/estimated rows and clocks before bulk acquisition. Reuse verified one-minute history where it exists. No new paid subscription, resource purchase or unauthorized feed activation.
2. Deliver a bounded full-chain pilot for 2022-09-30, 2024-01-08, 2024-09-11, 2025-03-10 and 2025-04-08, plus available sessions covering one actual early close and both DST transitions. Identify concrete dates through the instrument calendar. Include underlying calibration history for pilot threshold testing.
3. Prove raw-to-normalized parity, clock semantics, observed versus missing minutes and Greek/quote alignment. Publish the pilot with its own manifest and hash inventory; no consumer replay acceptance implied.
4. Resume full-period collection in checkpointed session/expiry batches only after the capability/pilot gate. Do not disturb unrelated active jobs or discard partial downloads. Publish immutable release IDs with the full completion and unresolved-gap matrix.

## Delivery and acceptance evidence

- Source capability/feasibility response and reason for every unsupported field, including whether genuine one-minute Greeks are vendor-provided or require a separately versioned calculation.
- Immutable Parquet release, schema version, source request parameters/resolution, raw receipts, per-partition hashes/row counts, primary keys and duplicate policy. Include `frequency_seconds=60` where relevant.
- Session × expiry × right × contract × minute coverage: expected eligible rows, actual rows, missing intervals, no-trade/stale intervals, excluded contracts and boundary policy. Give clock-null/age/skew/quality distributions separately.
- Validate bid/ask and Greek input joins by contract and time, not merely equal row counts. Bid/ask values should reconcile to retained raw response on sampled and full applicable key checks. Preserve failed rows/reasons.
- No forward/backward interpolation from 5m to 1m; no silent fill-forward; no deriving Greeks from later inputs; no mixing adjusted underlying prices with raw strikes without explicit consistent treatment.
- Independent consumer checks will compare batch/prefix availability, full candidate universes and cash/margin replay. Provider quality approval does not certify strategy returns or executable fills.

Please report what is deliverable now, what must be collected/calculated, and what is intrinsically unavailable. Keep this request separate from the earlier five-minute coverage completion. The consumer owns axis construction, threshold calibration, strategy features, selection and risk.
