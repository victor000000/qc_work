# Option Omega audio-demo QC PoC

Current revision: **[Draft 0.8](../research/design_20261024_v8/DESIGN_REPORT.pdf)** — full-equity ceiling, historical robustness tests, matched controls and final funded QC verification. [Evidence](../results/qc_sizing_poc_20261024/final_verification.json). Robust alpha is not established.


Current revision: **[Draft 0.8](../research/design_20261024_v8/DESIGN_REPORT.pdf)** — full-equity ceiling, historical robustness tests, matched controls and final funded QC verification. [Evidence](../results/qc_sizing_poc_20261024/final_verification.json). Robust alpha is not established.


This is a new SPX baseline for Draft 0.5. The older basket and monthly-strangle sources remain frozen.

`optionomega_demo.py` implements the [saved demo extraction](../research/design_20261021_v4/DEMO_STRATEGY_EXTRACTION.txt): SPXW PM-settled 0DTE iron condors, approximately −0.20 put/+0.08 call delta, exact 20-point wings, one lot, $100,000, 13 New York entry slots, held through native expiry. There are no profit targets, stops or rolls. Every entry goes through genuine QC combo orders and native buying-power checks.

Acceptance is **at least 360 completed whole episodes in every included year for each ticker**. An episode has four filled opening legs and a reconciled native expiry outcome. Legs, orders, rejected opportunities and annualized short-period counts do not satisfy the requirement. Partial years are identified and their actual counts are shown. Overlapping episodes are dependent observations.

The initial source-period run is `SSTRANGLE_OO05_20261023_FULL_V5`, May 16, 2022–July 13, 2026, followed by four calendar days without entries for expiry processing. Exact rendered sources and configuration hashes are in [campaign evidence](../results/qc_baseline_poc_20261023/). Inspect its recorded QC identity before any further execution; do not duplicate or restart a nonterminal run.

## Explicit adaptation assumptions

- Official Option Omega documentation specifies per-contract commissions, midpoint fills and per-position slippage. Primary V5 uses $1.18 per opening contract and 0.05 total adverse entry slippage across the four-leg package (0.0125 allocated per leg). Every native fill records its modeled midpoint and slippage; the collector verifies the convention. Native expiry has no fabricated exit fill or closing fee. The 0.10 exit slippage setting is inapplicable to this expiry-held execution path.
- Primary V5 uses an explicit midpoint QC fill model to match Option Omega's documented convention. This is modeled execution, not a claim of live midpoint fills. The V3 quote-side run is a separate execution-cost sensitivity; it failed on a native margin call on 2024-07-24 and is not a completed baseline.
- Require non-fill-forward quote bars at most two minutes old in the security's local time, noncrossed quotes with ask >0, spread <=3 points, OTM shorts, put delta between −0.40 and −0.01 and call delta between 0.01 and 0.30. Pick the nearest eligible short before checking the exact protective wing; a missing wing skips the slot.
- Require positive quoted credit after assumed slippage. Sum per-episode worst losses and fees against 100% of marked equity, in addition to native LEAN margin checks in IB brokerage mode. Real broker margin equivalence has not been established.
- A wholly rejected zero-fill native combo is a recorded skip. Mixed rejection, unresolved orders, unexpected intervention fills, residual prior-day positions or account-ledger mismatch fail the run.

All failures are preserved. V1 also used percentage slippage in error; it is invalid. V2 corrected absolute slippage but still treated a wholly rejected margin order as fatal. V3 records that rejection as a skipped opportunity without changing fills, account capital or margin models. Official documentation later resolved the source midpoint/package convention; V4 attempted that model but failed Python/.NET dictionary iteration, and V5 fixes the iteration. See [source contract](SOURCE_CONTRACT.txt).

## Export and audit

Run from `/home/vic/qc_work`, after the cloud run is terminal:

```bash
.venv/bin/python strategies/sstrangle/poc/collect_demo.py \
  --name SSTRANGLE_OO05_20261023_FULL_V5 \
  --output strategies/sstrangle/results/qc_baseline_poc_20261023/full_v5_evidence \
  --require-annual --expected-years 2022 2023 2024 2025 2026 --raw-pages --export-workers 8 \
  --terminal-json strategies/sstrangle/results/qc_baseline_poc_20261023/full_v5_terminal.json
```

The baseline runs through the shared Rust queue. The collector supports the Rust paginated order export and, with `--raw-pages`, a complete native API archive in 99-order checkpoints with up to eight bounded I/O workers. It verifies declared order totals and run identity, groups native opening tags into episodes, verifies four-leg signs/widths/expiry/quantity, checks native event uniqueness and zero residual contract positions, then reconciles attributed episode cash with the native account and standard QC end-equity/fee totals. It writes leg/event child tables, episode and annual Parquet/CSV, plus checksummed evidence.

Native exercise event messages provide the settlement underlying, including OTM expirations. The Rust CLI's query filter returns no lines for these runs; the collector archives that result and retrieves actual log pages with the supported unfiltered request. Accounting remains auditable from native events. Typed Rust serialization can omit API fields outside its schema, so use `--raw-pages` for full-field archival and resumable large exports. The smoke raw archive passes the same audit. A saved full terminal response is reused only after native identity/completion checks. Episode count is distinct from QC's netted contract closed-trade count.

```bash
.venv/bin/python -m pytest strategies/sstrangle/tests strategies/sstrangle/poc/test_demo_audit.py -q
```

The thirteen new regression cases exercise the frozen native smoke export: valid accounting, missing-year/360 gating, duplicate orders, missing legs, partial quantities, wrong widths and wrong cash totals, wrong ticker/combo identity, backdated fills, and missing/incorrect midpoint/package model metadata. Broader tests cover existing strategy, accounting and recovery behavior.
