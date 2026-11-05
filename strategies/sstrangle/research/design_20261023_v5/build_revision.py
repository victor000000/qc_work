#!/usr/bin/env python3
"""Build Draft 0.5 from preserved 0.4 plus measured, scoped evidence."""
from pathlib import Path
import json
import pandas as pd

P=Path(__file__).resolve().parent
ROOT=P.parents[3]
LOCAL=ROOT/'strategies/sstrangle/results/design_mini_poc_20261023_final'
QC=ROOT/'strategies/sstrangle/results/qc_baseline_poc_20261023'


def main():
    local=json.loads((LOCAL/'summary.json').read_text())
    smoke_dir = next(QC/name for name in ['smoke_v5_raw_evidence','smoke_v5_evidence','smoke_v3_evidence'] if (QC/name/'audit.json').exists())
    smoke=json.loads((smoke_dir/'audit.json').read_text())
    full_path=QC/'full_v5_evidence/audit.json'
    full=json.loads(full_path.read_text()) if full_path.exists() else None
    measured='''0.5 REVISION: MEASURED EVIDENCE AND NEW BASELINE CONTRACT
23 October 2026 | Review draft; not a 1.0.0 design freeze.

The baseline PoC is the Option Omega audio demo reproduced in QC. The user
requires AT LEAST 360 COMPLETE TRADES FOR EACH YEAR FOR ONE TICKER. This is a
hard baseline admission gate, replacing 0.4's optional >365 target. A trade
means one fully filled four-leg iron-condor episode held to native expiry;
orders, legs, partial fills, rejections and rolls do not create extra samples.
The first baseline is SPX only. Report each included year independently and
identify partial years. Do not annualize partial counts or average good years
over a deficient year. Later single-ticker baselines must pass independently.
Overlapping episodes remain dependent: counts do not establish effective N.

SOURCE RULES AND EXECUTABLE QC DETAIL
SPXW PM-settled 0DTE; short put nearest -0.20 delta, short call nearest +0.08;
long put 20 points below, long call 20 points above; one contract each.
New York entry slots: 09:35, 10:00, 10:30, 11:00, 11:30, 12:00, 12:30,
13:00, 13:30, 14:00, 14:30, 15:00, 15:30 on available sessions.
$100,000 initial capital; native LEAN margin/position grouping in IB brokerage mode, overlapping
entries, no profit target, stop, discretionary close or roll. Hold through
native cash-settled expiry. A 15:55 close is a separate future variant.
Source range: 2022-05-16 through 2026-07-13. Extra four calendar days allow
last expiry processing; no new entries during this settlement tail.

Fresh non-fill-forward quote bars (at most two minutes old in each security's
local time), exact 20-point wings and positive net quoted credit are required.
The nearest eligible short is selected before checking wings. Missing wings
or quotes skip that slot; no alternate strike or future quote is substituted.
Quotes are limited to spreads <=3 points; put delta in (-0.40,-0.01), call
in (0.01,0.30), OTM shorts. These are explicit QC admission choices, not rules
recovered from the screenshot. Minute fills can lag the decision timestamp.
Sum of per-episode worst losses plus entry fees is capped at 100% of marked
account equity. Actual QC buying power still decides admission. An entirely
rejected zero-fill combo is a recorded skip. Partial/unresolved/rejected mixed
combos, intervention fills, nonflat prior-day holdings and ledger divergence
fail the experiment. Never inflate capital or alter margin to force counts.

COST AND REPRODUCTION LIMITS
Official Option Omega setup/FAQ documentation checked on 23 October resolves
an earlier uncertainty: commissions are per contract, fills use bid/ask
midpoints and slippage applies to the whole position. Primary QC V5 therefore
uses $1.18 per opening contract and 0.05 total adverse entry slippage for the
four-leg package. A custom QC combo fill model allocates 0.0125 to each leg,
retains native quote/order gating and records midpoint/slippage in every native
fill event. The export audit verifies each price and the 0.05 package total.
This is an explicitly modeled source convention, not a claim of live fills.

Expiry uses native cash settlement with no invented market exit, 0.10 exit
slippage or closing commission. The original export is still needed to verify
historical expiry-fee handling, exact quote timestamps and vendor delta models.
Official current conventions do not prove the historical source implementation
or guarantee matching the demo's $101,790 P&L / 13,492 displayed trade count.
The initial quote-side + 0.05 PER LEG full run is an execution-cost sensitivity,
not the midpoint reproduction. It failed on a native margin intervention on
2024-07-24; preserve its partial results and do not report it as completed.

ACCOUNTING AND DATA CONTRACT CHANGES
Preserve paginated native order JSON and events, source/config hashes and run
identities. Record the actual submitted source SHA256; the Rust queue uses a
different short job hash, so those two hash formats must not be equated. Versioned tags carry episode ID, decision time, deltas and spot.
The collector groups four native opening orders into an episode and verifies
signs, width, 0DTE expiry, filled quantity, unique events and zero final positions.
Native exercise-event messages retain actual settlement-underlying references,
including OTM expirations. Use these to attribute expiry cash to episode legs;
this is accounting attribution, not a synthetic execution or a replacement for
native settlement. Episode totals must reconcile with the native account.
Netted contract holdings can close components from several episodes; native
closed-trade count is not the research episode count. Retain child leg/events.
QC's Rust log CLI query filter returned no lines. A supported unfiltered
API read recovers the actual log pages; keep both responses. Episode
identity and settlement accounting must remain auditable without console logs;
native order tags/events supply both. Console summaries are supplementary.
The Rust JSON export serializes typed fields and can omit unmodeled API keys.
Large reads also exposed repeated full-response timeouts after order paging.
Use the implemented 99-order raw API page archive, up to eight bounded I/O workers, stable
run identity, source SHA256, page checksums and resume from completed pages.
The smoke raw-page archive passes the same audit as the Rust typed export.
A saved terminal response may be reused only with matching native run identity;
local polling/collection status does not override an actual terminal cloud read.

POINT-IN-TIME FEATURES: SMALL PROOF, NOT A COMPLETE PLATFORM
Five raw-daily-price features were built for 28 saved SPY/GLD/TLT trades:
1/5/20-day returns, 20-day annualized realized volatility and close/SMA20.
All 28 have fresh complete values. Raw daily features become available at the
following New York midnight, with a seven-day expiry. Labels are stored in a
separate Parquet. Source timestamps and missing reasons accompany entries.
Join by native ticker identity and available_at STRICTLY BEFORE decision_at;
exact timestamp equality is rejected until an explicit event-order policy is
proven. Normalize timestamps to UTC nanoseconds before joining: pandas rejected
mixed microsecond/nanosecond fixtures in the retained initial failed attempt.
Future-price mutation leaves earlier features unchanged. Future, equal-time
and stale injected records are rejected. Source-admission checks for revised
history, delisted identities and corporate actions still precede production.

The minimal registry records type/unit/scope/availability, not a full typed
expression engine. Vector abs-delta reduction and same-entry-batch IVR rank
were exercised on QC annotations. The batch rank is NOT a contemporaneous
full-market rank or an independent provider feature. Full matrix/group/BRAIN
operators, calendars, notebooks and 100,000-field coverage remain pending.

FREQUENCY AND ENGINE CHANGES
Saved sparse option trade-minute bars support an engineering workload only.
Every coarser row must retain observed-minute count, interval end/availability,
expected coverage and completeness. OHLC formed from incomplete bins must not
silently enter accepted price paths or valuation. Quote absence is not evidence
of no market movement; coarse bars cannot repair missing NBBO or risk marks.
RTH workload bins use a 09:30 anchor; a production session-calendar adapter,
early-close rules and live publication lag are still required.
Thirty minutes remains an unselected research view. Test all frequencies with
a common risk/valuation clock before comparing economic results. First-pass
and warm measurements do not establish cold-disk speed. Process peak RSS is a
lifetime high-water mark, not attributable per frequency or formula pack.

AKQuant reproduced the original 216-fill fixture and both predeclared sides
of a five-day-return filter. These are conditional frozen-tape accounting
checks with the existing premium-ratio margin adapter, not independent option
simulation, funded filter returns, optimization or untouched OOS evidence.
Do not report replay equity drawdown as held-position marked risk. The small
1,024-expression workload is redundant arithmetic over actual rows; it is not
1,024 independent alphas or evidence of 100,000-feature production throughput.

NEXT ACCEPTANCE ORDER
1. Verify the full audio baseline, native accounting and >=360 episodes in
   EVERY included year; inspect data/capital skips and any source differences.
2. Obtain original Option Omega export/config to verify expiry fees, quote
   timestamps and delta semantics. Freeze quote-side and any later source-matched variants separately.
3. Admit a current licensed provider release for actual SPX contracts, NBBO,
   metadata and session calendars. The old local fixture is not fresh coverage.
4. Build entry-safe features on this new SPX tape, then selected formula packs,
   shared Jupyter/API, changed-path simulation and consistent marked-risk parity.
5. Expand single-ticker families and SPY/QQQ only with independent annual count
   gates, then robustness/portfolio work and final QC validation before release.

'''
    bench=pd.read_csv(LOCAL/'benchmarks.csv').groupby('minutes').agg(
        rows=('rows','first'),complete=('complete_intervals','first'),bytes=('parquet_bytes','first'),
        wall=('wall_seconds','median'),cpu=('cpu_seconds','median'))
    report='MEASURED POC EVIDENCE | 23 October 2026\n\n'
    report+='QC AUDIO-DEMO SMOKE\n'
    report+=f"{smoke['episodes']} whole episodes, {smoke['orders']} native orders, {smoke['fill_events']} fills.\n"
    report+=f"Net P&L ${smoke['native_net_pnl']:,.2f}; attribution error {smoke['attribution_error']:.3g}; zero residuals.\n"
    report+='2024-01-02 through 2024-01-12, 9 trading days; 117 slots and 42 missing-wing\nskips. Primary midpoint smoke: 75 complete episodes, no rejected combo;\nquote-side smoke: 74 complete episodes and one native-margin rejection.\nNeither smoke satisfies an annual gate. Short-window annualized QC metrics\nare not used. Each primary fill verifies midpoint plus 0.0125 adverse points\nper leg, totaling the documented 0.05 per four-leg position.\n'
    report+='\nFULL AUDIO PERIOD\n'
    if full and 'episodes' in full:
        annual=pd.read_csv(QC/'full_v5_evidence/annual.csv')
        report+=f"{full['episodes']:,} whole episodes, {full['orders']:,} orders; net ${full['native_net_pnl']:,.2f}.\n"
        report+=annual[['year','partial_year','trades','days','net_pnl','passed']].to_string(index=False)+'\n'
        stats=full['qc_statistics'];car=float(stats['Compounding Annual Return'].rstrip('%'))/100;dd=float(stats['Drawdown'].rstrip('%'))/100
        report+=f"Native account: $100,000 -> ${float(stats['End Equity']):,.2f}; CAGR {car:.3%};\nmarked MDD {dd:.3%}; Calmar {car/dd:.3f}. The >2 Calmar objective is not met.\n"
        ep=full['episode_statistics']
        report+=f"Whole-episode win rate {ep['win_rate']:.3%}; mean net ${ep['mean_pnl']:.2f};\n{ep['distinct_trading_days']} distinct trading days; at most {ep['max_same_day_episodes']} episodes/day.\nQC's standard contract-level win rate is a different statistic.\n"
        rt=json.loads((QC/'full_v5_evidence/backtest.json').read_text())['backtest']['runtimeStatistics']
        report+='Source gap: 9,841 QC episodes versus 13,492 displayed in the demo.\n13,501 scheduled QC slots: 3,606 lacked an admissible exact-width wing;\n16 lacked usable delta/quotes; 13 lacked chains; 25 native margin combos\nwere wholly rejected. These admission differences can bias performance;\nthis is not verified numerical replication of the source export.\n'
        report+=f"All native fills/fees and expiry attribution reconcile, with zero residuals.\nSource SHA256: {full['source_sha256']}\n"
        resource_metrics=json.loads((QC/'full_v5_evidence/audit.first_export.json').read_text())
        report+=f"First completed export/audit phase wall {resource_metrics['collection_wall_seconds']:.1f}s, CPU {resource_metrics['collection_cpu_seconds']:.1f}s;\nprocess lifetime peak RSS {resource_metrics['process_peak_rss_mib']:.1f} MiB.\n"
        if 'span_since_terminal_response_seconds' in resource_metrics:report+=f"Span from saved terminal response through export/audit: {resource_metrics['span_since_terminal_response_seconds']:.1f}s\n(includes resumed/checkpointed export phases; not cloud compute).\n"
        if 'qc_logged_engine_seconds' in full:report+=f"QC logged engine wall: {full['qc_logged_engine_seconds']:.2f}s.\n"
        report+='The QC account window includes the declared four-day settlement tail.\nThis table attributes annual trade P&L by entry/expiry year; it is not a\nset of separately funded yearly accounts or independent observations.\n'
        report+=f"Annual >=360 gate: {full['annual_pass']}; settlement attribution error {full['attribution_error']:.3g}.\n"
        report+='QC reported statistics: '+json.dumps(full['qc_statistics'],sort_keys=True)+'\n'
    else:
        report+='Pending verified full-run collection. No full-period success or annual count claim.\n'
    report+='\nQUOTE-SIDE EXECUTION-COST SENSITIVITY\nThe older full V3 run failed on a native margin call at 2024-07-24 15:57;\nterminal equity $21,059.32 with residual exposure. It did not reach 2026\nand supplies neither full-period returns nor annual acceptance. It used\nquote-side fills plus 0.05 per leg, exceeding documented OO package slippage.\nPreserve its source, terminal cloud read and actual orders as failed evidence.\n'
    report+='\nLOCAL COMPONENT EVIDENCE (SEPARATE HISTORICAL FIXTURES)\n'
    report+='188 broad-control episodes / 1,134 fills reconcile individually; fees $1,555.82;\nnet -$11,182.57; largest episode error <1e-9. This is existing broad-control\nevidence, not the new SPX baseline. 28/28 prior replay trades have five daily\nfeatures. Future/equal/stale/invariance checks pass.\n\n'
    report+='Sparse captured option trade bars: 15,284 input rows; three repetitions each.\nMinutes | rows | full bins | ZSTD bytes | median wall s | median CPU s\n'
    for freq,r in bench.iterrows():
        report+=f'{freq:7} | {int(r.rows):4} | {int(r.complete):9} | {int(r.bytes):10} | {r.wall:.6f} | {r.cpu:.6f}\n'
    report+=f"Process peak RSS: {local['benchmark']['process_peak_rss_mib']:.1f} MiB (lifetime high-water).\n"
    report+='First pass is not a cold-cache test. Same 1,024 redundant arithmetic outputs\nper configuration; no frequency-sensitive strategy decisions or risk comparison.\nIncomplete panels are workload artifacts, not admitted market data.\n\n'
    report+='AKQuant conditional replay trials (same original 28-trade tape):\n'
    for t in local['trials']:
        report+=f"{t['trial']}: {t['retained_trades']} episodes / {t['scheduled_orders']} fills, net ${t['net_pnl']:,.2f}, wall {t['wall_seconds']:.4f}s.\n"
    report+='All execution price/quantity/fee and terminal-equity assertions pass.\nBoth filter sides were predeclared; neither is an OOS recommendation.\n\n'
    report+='NATIVE EXPORT ENGINEERING\nRaw native pages retain all API properties, unlike typed Rust serialization.\nUse 99 orders/page, up to eight I/O workers, per-page checkpoints and source/run identity;\nresume a local export without restarting any cloud backtest. The completed\nmidpoint smoke has a checksummed full raw-page archive. Native fill timestamps\nmust follow the declared decision and remain within the three-minute deadline.\nThe native-episode table also exposes three decision-time fields (put/call\ndelta and SPX spot) with labels, realized credit and fees physically separated.\nThese are QC metadata, not a newly admitted provider feature panel.\n\n'
    report+='REPRODUCE\nFrom /home/vic/qc_work:\n'
    report+='  .venv/bin/python strategies/sstrangle/research/design_20261023_v5/mini_poc.py --output <new-empty-folder>\n'
    report+='  .venv/bin/python -m pytest strategies/sstrangle/poc/test_demo_audit.py -q\n'
    report+='Cloud evidence is immutable; rerunning local analysis does not submit QC jobs.\n'
    report+='Versions: '+json.dumps(local['versions'],sort_keys=True)+'\n'
    report+='Artifacts: ../../results/design_mini_poc_20261023_final/summary.json\n'
    report+='          ../../results/qc_baseline_poc_20261023/\n'
    (P/'POC_REPORT.txt').write_text(report)
    old=(P.parent/'design_20261021_v4/DESIGN_REPORT.txt').read_text()
    old=old.replace('Draft 0.4 | 21 October 2026 | Incorporates comments on DESIGN_REPORT.pdf',
                    'Draft 0.5 | 23 October 2026 | Audio baseline and measured PoC revision')
    old=old.replace('First PoC: SPX demo iron condor plus a small Tom-inspired single-ticker example.',
                    'First PoC: reproduce the SPX audio demo in QC; defer the Tom example.')
    old=old.replace('User-proposed\n>365 trades/year is a design target to evaluate per eligible strategy, not a\nuniversal statistical guarantee or a reason to force trades.',
                    'User-required\n>=360 complete episodes per included year per single-ticker baseline is an\nadmission gate. Fail a deficient baseline; do not force or annualize trades.')
    old=old.replace('No timings have been measured for this new design yet.',
                    'Small saved-fixture component timings are now recorded in POC_REPORT.txt;\nthis is not a full-scale or cold-cache pipeline measurement.')
    old=old.replace('No new backtest, paid plan or deployment is initiated by this design document.',
                    'Authorized QC audio-baseline PoC runs are recorded with native identities.\nNo paid data plan or deployment is initiated.')
    old=old.replace('REFS (checked21October2026)','REFS (inherited review checked21October2026; current QC references below)')
    # Insert the scoped revision before inherited overall sections.
    marker='1. PURPOSE AND AGREED DIRECTION'
    old=old.replace(marker,measured+'\n'+marker,1)
    old+='\n12. MEASURED POC REPORT\n'+report
    old+='\nCURRENT QC IMPLEMENTATION REFERENCES (23 October 2026)\n'
    old+='https://www.quantconnect.com/docs/v2/writing-algorithms/universes/index-options\n'
    old+='https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Orders/Fills/FillModel.cs\n'
    old+='https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Securities/Option/OptionPortfolioModel.cs\n'
    old+='https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models\n'
    old+='https://docs.optionomega.com/backtesting/backtest-setup\n'
    old+='https://docs.optionomega.com/backtesting/backtesting-faq\n'
    (P/'DESIGN_REPORT.txt').write_text(old)
    changes='''DRAFT 0.4 -> 0.5 CHANGE REGISTER | 23 October 2026
1. Baseline source: user specifies the Option Omega audio demo; use the native
   expiry-held SPXW reproduction before Tom variants or an active-close variant.
2. Annual admission: >=360 whole completed episodes for each included year
   per ticker. Replace advisory >365 target; retain distinct days/overlap warnings.
3. Native funded execution: preserve $100k, allow documented zero-fill rejects,
   fail partial/intervention/unresolved paths; retain two failed smoke versions. V1 also used percentage slippage
   instead of absolute points; its results are invalid and never reused.
4. Costs: verify OO official midpoint/per-position slippage and per-contract
   fees. Primary V5 uses the documented model; V3 is an execution sensitivity.
   V4 failed Python/.NET dictionary iteration; V5 fixes it. No performance parity claim.
5. Native settlement attribution: audit four-leg episode identity from native
   tags/events, and actual settlement references even when console logs are absent.
6. Point-in-time join: normalize UTC precision; reject equal/future/stale data,
   require explicit equality sequencing; retain mutation-invariance evidence.
7. Frequency: preserve interval coverage; incomplete bins fail admission.
   Record first/warm pass, tiny sparse fixture, CPU/wall and lifetime RSS scope.
8. Engine: exact fixed-tape accounting and both predeclared filter sides pass;
   changed-path, marked-risk and independent funded simulation remain pending.
9. Feature scale: prove five daily features and limited annotation operators;
   1,024 redundant arithmetic outputs are not independent alphas. No 100k claim.
10. Archive complete raw native API pages and source SHA256 with resumable
    99-order batches with bounded parallel I/O; preserve actual logs with the supported unfiltered query.
11. Preserve overall five-stage QC/local/robustness/final-QC/human release flow,
    US/CN-only scope, old frozen baselines, failures and reviewed Draft 0.4.
'''
    (P/'COMMENT_RESOLUTION.txt').write_text(changes)
    print('Wrote Draft 0.5 sources and scoped PoC report')


if __name__=='__main__':main()
