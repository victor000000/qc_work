# Draft 0.6: three native QC demos

This directory contains a versioned adapter and evidence tooling. The source in
`../optionomega_demo.py` and all Draft 0.5 evidence remain unchanged.

- Audio condor: SPXW 0DTE, -.20/+ .08 shorts, exact 20-point wings, one lot,
  $100,000. `paired_exact` selects the nearest eligible short with an admitted
  exact-width wing; it retains the original quote predicate.
- User-authorized Tom-inspired strangle: -.16/+ .16, one lot, $2,000,000.
- User-authorized Tom-inspired put: -.25, one lot, $2,000,000.

The two naked examples are explicit 0DTE adaptations. The saved Tom source
specifies a 45-DTE short put, not these complete intraday rules. Common entry
slots are 09:35, then every half hour 10:00–15:30 New York, subject to the
session being open. Hold to native cash expiry. Same source interval as 0.5.
Midpoint fills with .05 total position slippage, $1.18/opening contract, zero
native expiry commission. Native buying power is unchanged.

European SPXW uses `NullOptionAssignmentModel` to suppress discretionary
intraday assignment simulations; native expiry/delisting is preserved. A
stress test covering April 9, 2025 verifies this. A November 25, 2022 half-day
regression verifies that a market order is not submitted at the closed-session
boundary. The failed initial trials remain in the campaign ledger.

The episode audit checks 4/2/1 distinct native opening orders, actual combo
identity where applicable, signs, quantities, exact widths, same-day expiry,
model price/fee tags, settlement references, zero residuals and cash totals.
Whole episodes, not order or leg counts, must reach 360 in every included year.

## Rebuild the self-contained algorithm

From `/home/vic/qc_work`:

```bash
.venv/bin/python strategies/sstrangle/poc/v06/build_algorithm.py
.venv/bin/python strategies/sstrangle/poc/v06/add_pair_admission.py
.venv/bin/python strategies/sstrangle/poc/v06/add_expiry_calendar.py
.venv/bin/python strategies/sstrangle/poc/v06/add_bounded_runtime.py
```

Current condor defaults use `paired_exact`; pass `--wing-policy original`
only for an explicit historical-policy control. The frozen native primary
used an explicit `paired_exact` configuration and remains unchanged.

`campaign.py queue` freezes the submitted source, configuration and SHA256
under a unique immutable trial name. Do not submit a duplicate of a running
trial. Review actual queue/native identities before using the shared server.
`watch_campaign.py` only observes the three already submitted primary runs
and collects terminal evidence; it never creates or cancels backtests.

## Read and audit saved results

```bash
.venv/bin/python strategies/sstrangle/poc/v06/campaign.py status
.venv/bin/python -m pytest strategies/sstrangle/tests strategies/sstrangle/poc/test_demo_audit.py strategies/sstrangle/poc/v06 -q
```

The collector uses original API pages (99 orders each) with checksums and
resumable checkpoints. The read transport reuses one TLS session per worker,
keeps authentication in memory and never prints credentials. Local network
errors are not classified as native strategy failures. Uncertain create
outcomes require read-only discovery before any retry.

After completed native audits:

```bash
.venv/bin/python strategies/sstrangle/poc/v06/analyze_campaign.py --strangle strangle_full_v2 --put put_full_v3
.venv/bin/python strategies/sstrangle/poc/v06/fetch_charts.py
.venv/bin/python strategies/sstrangle/research/design_20261023_v6/build_report.py
.venv/bin/python strategies/sstrangle/research/design_20261023_v6/render_report.py
```

Analysis separates common/added/lost condor slots, actual yearly counts,
funded account statistics and conditional common-slot comparisons. A
five-day block resampling groups overlapping trades by day and is descriptive;
it is not untouched OOS. The native account charts are sampled and do not
replace QC engine marked drawdown. A shared-capital portfolio is future work.

The current template also bounds runtime telemetry to QC’s 50 custom fields
and 200-character field limits. This telemetry-only patch has local round-trip
and overflow tests; primary trading runs retain their earlier frozen source.
Their complete native-order audits remain authoritative. The condor exceeded
the runtime field quota, so absent optional counters stay unavailable and
complete original admission counts come from the separate no-order replay.
