"""Build Draft 0.65 only after both native tolerance runs pass accounting."""
from pathlib import Path
import json,html,textwrap,hashlib
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path(__file__).resolve().parents[4];P=Path(__file__).parent;BASE=ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024'
a=json.loads((BASE/'analysis/findings.json').read_text());comparison=pd.DataFrame(a['comparisons']).set_index('key')
assert {'condor_full_t02','condor_full_t05'}.issubset(comparison.index),'Do not publish pending native results as complete'
local=json.loads((BASE/'local/summary.json').read_text());diag=json.loads((BASE/'local/diagnostics.json').read_text());annual=pd.read_csv(BASE/'analysis/annual.csv')
sections=[]
def section(title,body):sections.append((title,body.strip()))
fmt=lambda v:f'${v:,.2f}'
t02=comparison.loc['condor_full_t02'];t05=comparison.loc['condor_full_t05'];v06=comparison.loc['v06']
section('Draft 0.65 — measured baseline and local alpha mini-PoC',f'''
2026-10-24 | Supersedes Draft 0.6 for delta admission and local feature scope.
SPXW 0DTE, 16 May 2022–13 July 2026. 2022 and 2026 are partial years.

The ±0.02 native run completed {int(t02.trades):,} whole condors and earned {fmt(t02.pnl)}; the ±0.05 run completed {int(t05.trades):,} and earned {fmt(t05.pnl)}. Minimum completed annual counts were {int(t02.min_annual):,} and {int(t05.min_annual):,}, respectively. Both satisfy the requested 360 trades in every included year without annualizing partial years.

Native CAGR / maximum drawdown / Calmar: ±0.02 = {t02.cagr:.3%} / {t02.native_mdd:.1%} / {t02.calmar:.3f}; ±0.05 = {t05.cagr:.3%} / {t05.native_mdd:.1%} / {t05.calmar:.3f}. These are separate funded accounts, not a combined portfolio.

Minimum sampled native margin remaining was {fmt(t02.min_margin_remaining)} for ±0.02 and {fmt(t05.min_margin_remaining)} for ±0.05. Completion does not prove continuously positive buying-power headroom; the native position-group margin behavior remains an engineering limitation. No custom margin override was used.

The audio display is {fmt(101790)} on 13,492 trades. Differences from that display are {fmt(t02.gap_to_oo)} and {fmt(t05.gap_to_oo)}, versus {fmt(v06.gap_to_oo)} for Draft 0.6. Closer ending profit alone does not prove reproduction. Prefer ±0.02 as the exposure-fidelity research baseline because it meets the declared annual gate; retain ±0.05 as sensitivity and 0.6 as the coverage control. No threshold was chosen to match the source ending profit.

The local PoC now materializes 211 fields per strategy schema, including 144 eligible alpha candidates and 20 separately flagged broker-IV fields. It evaluates 288 single-feature rules per baseline. This replaces the old 28-trade, five-feature fixture with full native SPX episode tapes and pinned provider inputs. Missing call/long-wing fields are deliberately null for strategies without those legs.

This is a reproducible development experiment. Exact Option Omega parity, independently verified settlement, untouched OOS performance and funded execution of the locally filtered strategies are not established.
''')
section('1. Native experiment contract and acceptance', '''
Fixed structure: sell put near −0.20 and call near +0.08, buy wings exactly 20 index points farther out, one contract per leg. Entry at 09:35, then every half hour 10:00–15:30 New York, only while index market is open. Hold to native cash settlement; no profit target, stop or roll. $100,000 initial capital, unchanged brokerage/margin model.

Quote admission remains non-fill-forward quotes no more than two minutes old, positive ask, nonnegative bid<=ask and spread<=3 index points. Same-day contracts only, shorts OTM, original broad delta bounds retained. QC uses Black-Scholes Greeks and a ±60-strike universe. Nearest shorts are retained if both exact wings pass; otherwise choose the nearest admissible exact-width pairs.

NEW: after selection, require abs(put_delta+0.20)<=tolerance AND abs(call_delta−0.08)<=tolerance, including originally admitted and recovered trades. Inclusive boundaries allow only 1e-12 numerical epsilon. Failure skips the slot; no widening/retry to chase trade count. Tested tolerances were predeclared as 0.02 and 0.05 absolute delta units (2 and 5 delta points), not relative percentages. At 0.02 the put must be between -0.22 and -0.18 and call between 0.06 and 0.10.

Costs: modeled midpoint, 0.05 index points adverse slippage per whole package, $1.18 per opening contract, zero modeled expiry commission. Native margin can reject a submission. European discretionary early assignment is disabled while native expiry remains active. Calendar half-days respect market closure.

Acceptance counts completed four-leg episodes, not orders. For each included year require >=360. Audit every native fill, fee, exercise reference, account cash and residual holding, preserve source hash and project/backtest IDs, and archive original paginated order responses. Full candidates followed an accounting smoke, serialized on the existing B2-8 node.

The 0.05 API first reported Completed with empty final statistics and stale interim holdings. The collector correctly stopped; a read-only refresh of the same native run supplied final statistics. Preserve that response and collection failure. The repaired readiness check requires final order statistics and native cash/ledger/count counters in addition to completion. No native run was duplicated.
''')
section('2. What explains the Option Omega P&L gap?',f'''
The measured Draft 0.6 cash identity is opening credit $3,157,347.50 minus fees $60,812.48 minus expiry cash $2,931,830.00 = net $164,705.02. The source displays $3,241,715 premium, but its exact premium/cost basis and trade population are unverified. Do not subtract those totals and label the difference a quote error.

The 3,054 recovered-wing filled episodes contributed $45,040.62 net. Original-admissible filled episodes contributed $119,664.40. This demonstrates that the admission expansion changed the sampled exposures and outcomes. The prior 0.5→0.6 comparison had 9,819 shared episodes with identical P&L; gains came from added/lost episodes rather than a changed ledger on shared trades.

A concrete exposure mismatch: the largest 0.6 winner was $810.28 on 2025-04-07 12:00, with a recovered put delta of -0.3774 instead of -0.20. The control had 12 wins above the source display's $550 maximum. Both proposed tolerance gates exclude all 12 on the saved control tape; its largest retained winner is $545.28. This is evidence of reduced exposure distortion, not proof that those retained trades match Option Omega.

Tolerance admission is regime-dependent on the saved 0.6 tape: ±0.02 retains 45.7% of episodes in the lowest prior-SPY-RV20 quintile versus 74.5% in the highest. These descriptive whole-period buckets are not a new alpha rule. The gate changes market-condition sampling as well as target precision; discrete strikes and quote availability are possible mechanisms requiring source data to separate.

For tighter runs, matched episode decompositions are saved in analysis/findings.json. They split P&L change into common-episode changes, additions and removals, including funding-path effects. Native reruns are necessary because filtering a funded tape cannot recover trades previously rejected by margin.

Current Option Omega documentation confirms nearest-delta selection, midpoint pricing, per-position slippage and per-contract commissions. Our ±0.02 gate is a fidelity constraint, not a verified Option Omega setting. Their exact historical Greek model, quote snapshot/admission, subscribed universe, expiry reference and expiry fees remain unverified.

A $5 extra charge on every Draft 0.6 episode would remove $64,420, numerically close to its $62,915 gap. This is NOT evidence of a missing $5 fee. The existing 0.05-point package entry slippage already deducts $5. Charging it twice to match the endpoint would corrupt the experiment. Fixed-tape extra-cost and ±1-point settlement-reference stresses are saved separately and never replace native results.

An algebraic bridge using the rounded source winner/loser averages attributes about -$4,617 to the smaller trade count, +$52,745 to the win-frequency difference, +$41,182 to average winners, and -$27,052 to average losers, plus $657 from source rounding. This is a sequential decomposition of different trade populations, NOT causal attribution. It shows why a small win-rate difference can move total P&L materially in a low-average-edge strategy.

Win/loss frequency and severity, yearly tails, selected deltas and trade coverage must agree before claiming parity. Rounded aggregate source metrics cannot identify a unique cause. Next exact-reproduction step is a source trade CSV/config joined on timestamp, expiration, strikes, premium, fees and settlement; report unmatched rows and component differences. Do not infer unavailable source rows.
''')
section('3. Local datafields and alpha families actually delivered', '''
Pinned provider release: see provider/release.json and immutable export manifests. Daily raw OHLCV covers SPY, QQQ, IWM, TLT and GLD for the source period plus lookback history. These are cross-market inputs to SPX outcomes; SPY is not relabeled SPX. No index volume is fabricated.

Per symbol: 5 prior completed OHLCV fields; returns over 1/2/5/10/20/60 sessions; trend distance from 5/10/20/60-session SMA; realized volatility over 5/10/20/60 sessions; RV5/RV20; daily range/close, close location, prior-day opening gap, candle body; volume/20-day mean, dollar volume, volume z-score, Amihud proxy; 60-session drawdown; 20-session return skew and downside volatility; simple 14-session RSI and ATR/close.

Cross-market alphas: QQQ−SPY, IWM−SPY, TLT−SPY and GLD−SPY 20-session return differences. These preserve instrument identity and are not survivor-universe market ranks. Total eligible price/volume candidates: 144.

Broker-IV sensitivity fields per symbol: 30-day broker IV level, 5-session IV change, 60-session IV rank and IV²−RV20² proxy. These 20 fields are materialized but excluded from primary alpha screening because historical publication clocks are not certified. They are not QQQ 0DTE ATM skew, option-derived 45-DTE IV, or the audio's unspecified VRP formula.

Native fields: short put/call deltas, decision spot, original anchor deltas, recovery flag, target errors, signed/absolute short-delta sums, anchor shifts, minutes since open and weekday. Contract geometry adds short/long put/call strike and strike distance from decision spot. These are chosen-contract inputs known before order, not a complete option-surface feature set.

Not delivered: current-session VIX gap, SPY opening/10-day-SMA signal, SPY VWAP distance, Hurst estimate, QQQ 0DTE skew, gamma/vega/theta surface, historical OI/NBBO panel. Source datasets inspected did not support complete entry-safe histories. Future acquisition must supply values, timestamps, definitions and coverage before these names enter a screen.
''')
section('4. Point-in-time, missingness and feature contracts', '''
The registry records source, formula, family, eligibility, applicability, release, dtype and availability convention. Provider daily observations are assigned to next New York midnight, then joined strictly before decision_at, with a maximum age of seven calendar days. Same-timestamp provider data is rejected unless event ordering is separately established. Warm-up NaNs are not silently filled. Native pre-order tags have explicit within-decision ordering.

This is a conservative completed-bar convention, not proof of original vendor publication or point-in-time vintages. Raw price basis avoids future adjustment factors but still reflects the currently published historical dataset. Broker IV has a stricter unresolved clock caveat and is not screened. Saved exports and checksums permit exact replay of the data actually used.

A field being unavailable by strategy is different from missing provider coverage: call/long-wing geometry is null for the put, long-wing geometry is null for the strangle. Never substitute zero. Per-dataset coverage CSVs expose both. Feature Parquet files exclude settlement spot, realized entry credit, fees, expiry cash and P&L; labels are physically separate. DuckDB research tables mirror those files.

Tests mutate future bars and later-period labels, reject equal/stale joins, check formulas and verify put-only null applicability. Future values must not affect earlier features; later labels must not affect training thresholds or selection. These checks test implementation leakage, not vendor vintage authenticity.
''')
section('5. Local research protocol and findings', '''
For each baseline: train on 2022–2023, evaluate 2024 separately, and report 2025–2026 as later-period evaluation. All these periods were already inspected during baseline development; none is an untouched holdout. Freeze feature formulas, split boundaries and screening procedure before viewing new screen results.

For each eligible feature take its training trade-weighted median, test >median and <=median, and retain all 288 trial results. Choose one candidate by highest training mean P&L subject to >=360 retained trades in both training years; deterministic name/side tie-breaking. Later annual counts are an acceptance report, not a means of tuning the chosen rule. A failing later count prevents promotion. Comparing several strategy tapes adds further multiplicity. Mean P&L is a deliberately simple PoC ranking criterion and can favor high-premium/high-risk environments; production promotion additionally needs tail risk, incremental daily performance and funded-account risk. Do not switch ranking metrics after inspecting these later outcomes.

The QQQ prior-day range candidate appears across the three original demos, which share SPX days and risks. These are correlated findings. Report per-period P&L/trades, all annual counts, training Spearman redundancy, and 40th/50th/60th training-quantile sensitivity without replacing the selected median using later results.

Use five-trading-day circular block bootstrap on daily outcomes, including zero-entry sessions. Report selected daily P&L and incremental P&L versus the unfiltered baseline. These intervals are descriptive and not selection-adjusted. A profitable filtered total can still underperform the baseline in later years. No rule is promoted solely because its full-period P&L looks attractive.

This local stage filters frozen completed episodes and preserves original outcome paths. It does not recompute buying power, reopen excluded opportunities or model different contracts/exits. Its count gate is necessary but not sufficient. Any chosen alpha requires a new native QC funded test with exact feature timing before it becomes a funded strategy baseline.
''')
for key,item in local['datasets'].items():
 r=item['selected_by_training_only'];d=diag[key]
 section('Local measured result — '+key,f'''
Episodes: {item['episodes']:,}. Materialized schema: {item['feature_fields']} fields. Eligible candidates: {item['eligible_features']}; tested rules: {item['screen_trials']}. Rules passing the all-year count gate: {item['rules_passing_all_year_count']} (not used to reselect after seeing later outcomes).
Training-only selection: {r['feature']} {r['side']} {r['threshold']:.8f}.
Training: {r['train_trades']:,} retained trades, {fmt(r['train_pnl'])}.
2024 validation: {r['validation_trades']:,} trades, {fmt(r['validation_pnl'])}.
2025–2026 later: {r['later_trades']:,} trades, {fmt(r['later_pnl'])}.
Annual counts: {', '.join(str(y)+': '+str(r['count_'+str(y)]) for y in range(2022,2027))}. All-year gate: {r['annual_pass']}.
Later average selected P&L per calendar trading session: {fmt(d['later_mean_daily_selected'])}; descriptive 95% block interval {d['block5_selected_mean_95']}.
Later incremental P&L per session versus baseline: {fmt(d['later_mean_daily_increment'])}; interval {d['block5_increment_mean_95']}.
Training candidate pairs with |Spearman rho|>0.95: {d['correlated_candidate_pairs_abs_rho_above_095']} of {d['candidate_pairs']}. Similar formulas are not independent discoveries.

Conditional outcomes only; no funded alpha-filtered performance claim. Null applicability is reflected in coverage files, so minimum schema coverage can be zero without a provider-data failure.
''')
section('6. Revised system design and next acceptance gates', '''
A. Baseline adapters: immutable strategy contract, capital, schedule, Greeks, quote rules, delta tolerance and execution/expiry assumptions. Keep condor, strangle and put adapters; do not conflate Tom-inspired 0DTE examples with the saved 45-DTE Tom source.

B. Admission ledger: record every scheduled opportunity, selected anchors/pairs, quote reason, target error, tolerance rejection, capital rejection and fill outcome. Current aggregate counters plus complete native orders establish the delivered funnel; a row-level ledger for every unfilled opportunity remains a design requirement, not a delivered artifact.

C. Provider admission: pin releases, validate instrument identity, raw/adjusted basis, sessions, timestamps and completeness. Build reusable feature packs with shared rolling dependencies. Separate unavailable, nonapplicable, stale and incomplete-warmup values. Add option surface/macro/event features only with justified availability contracts.

D. Local research: Parquet/DuckDB feature and label tables, reproducible formula registry, bounded array evaluation, training-only transforms, all-trial ledger, chronological evaluation and daily clustering. Jupyter and automated callers must use the same library. This PoC delivers 211 fields; the earlier 100,000-formula engine remains a scale objective, not 100,000 implemented independent alphas.

E. Local execution: preserve three modes—conditional frozen-tape filtering, funded replay on supported opportunity data, and regenerated paths for changed contracts/stops/exits. Pandas/DuckDB screen this PoC; the previous AKQuant accounting fixture remains separate. No independent quote-backed local SPX simulator is claimed here.

F. Final native validation: rerun the candidate alpha with native margin and fees, require >=360 completed episodes every year, reconcile all native cash, report tails and account marks, compare entry identities to local expectations. Follow with fresh prospective/untouched data. Do not combine the three tapes into a shared-capital portfolio by adding their P&L.

Remaining exact-parity gaps: source CSV/config; historical delta/quote and settlement agreement; complete skipped-opportunity export; independently admitted intraday and option feature data. Keep the 0.6 control and every 0.65 experiment, including failed local builds, with provenance. Report economic uncertainty separately from engineering audit success.
''')
section('7. Reproduction and source references', '''
Code: strategies/sstrangle/poc/v065/{campaign,run_campaign,local_features,local_diagnostics,analyze}.py.
Evidence: strategies/sstrangle/results/qc_delta_poc_20261024/.
Run local_features.py, local_diagnostics.py and analyze.py after native collection, then this build_report.py. Queueing is an explicit separate operation; report regeneration never submits cloud work.
Native IDs/source hashes live in each immutable trial manifest and evidence/queue_identity.json. Raw order pages, source files, terminal API responses, audit results and checksums are retained. Provider exports carry immutable manifests and the pinned release. All 288 local trials per dataset are saved, not only winners.

Option Omega primary references checked 2026-10-24:
https://docs.optionomega.com/backtesting-faq.md
https://docs.optionomega.com/backtesting/backtest-setup
Historical demo extraction:
strategies/sstrangle/research/design_20261023_v5/DEMO_STRATEGY_EXTRACTION.txt
Preceding design and native three-demo evidence:
strategies/sstrangle/research/design_20261023_v6/DESIGN_REPORT.pdf

The documentation supports current conventions; it does not retroactively establish the exact original backtest data/settings. Preserve source display metrics as reported, not audited.
''')
text='\n\n'.join(t+'\n'+b for t,b in sections);(P/'DESIGN_REPORT.txt').write_text(text)
plt.rcParams.update({'font.family':'DejaVu Sans','text.parse_math':False})
fig,axs=plt.subplots(1,2,figsize=(14,6));keys=['v05','v06','condor_full_t02','condor_full_t05'];labels=['0.5','0.6','±0.02','±0.05']
axs[0].bar(labels,comparison.loc[keys,'pnl'],color=['#9ca3af','#64748b','#2563eb','#0d9488']);axs[0].axhline(101790,color='#b91c1c',ls='--',label='OO displayed P&L');axs[0].set(title='Native P&L; differing episode sets',ylabel='USD');axs[0].legend()
for key,label in zip(keys,labels):
 x=annual[annual.key==key];axs[1].plot(x.year,x.trades,marker='o',label=label)
axs[1].axhline(360,color='#b91c1c',ls='--',label='minimum');axs[1].set(title='Completed whole episodes per year',xticks=list(range(2022,2027)));axs[1].legend();fig.tight_layout();fig.savefig(P/'native_comparison.png',dpi=160)
fig2,ax=plt.subplots(figsize=(14,6));families=pd.Series([x['family'] for x in json.loads((BASE/'local/feature_registry.json').read_text()).values()]).value_counts();families.sort_values().plot.barh(ax=ax,color='#2563eb');ax.set(title='Delivered local feature schema by family',xlabel='Fields (not independent alphas)');fig2.tight_layout();fig2.savefig(P/'feature_inventory.png',dpi=160)
with PdfPages(P/'DESIGN_REPORT.pdf') as pdf:
 pdf.savefig(fig);pdf.savefig(fig2)
 for title,body in sections:
  lines=[]
  for paragraph in body.split('\n'):
   lines.extend(textwrap.wrap(paragraph,103,break_long_words=False) or [''])
  for start in range(0,len(lines),49):
   page=plt.figure(figsize=(8.27,11.69));page.text(.07,.95,title+(' (continued)' if start else ''),fontsize=14,weight='bold',va='top',wrap=True)
   page.text(.07,.90,'\n'.join(lines[start:start+49]),fontsize=9,va='top',linespacing=1.45)
   page.text(.07,.035,'Draft 0.65 | Research PoC | 2026-10-24',fontsize=8,color='#64748b');pdf.savefig(page)
   if title.startswith('Draft 0.65') and start==0:page.savefig(P/'overview_preview.png',dpi=120)
   plt.close(page)
plt.close('all')
body=''.join('<section><h2>'+html.escape(t)+'</h2>'+''.join('<p>'+html.escape(p).replace('\n','<br>')+'</p>' for p in b.split('\n\n'))+'</section>' for t,b in sections)
(P/'DESIGN_REPORT.html').write_text('<!doctype html><meta charset="utf-8"><title>Draft 0.65</title><style>body{font:17px/1.65 system-ui;max-width:1050px;margin:40px auto;color:#192b44;padding:20px}h2{line-height:1.3}img{width:100%}section{margin:45px 0}</style><h1>Draft 0.65</h1><img src="native_comparison.png"><img src="feature_inventory.png">'+body)
(P/'manifest.json').write_text(json.dumps({'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in P.iterdir() if f.is_file() and f.name!='manifest.json'}},indent=2))
print(P/'DESIGN_REPORT.pdf')
