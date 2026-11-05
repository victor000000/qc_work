"""Build the evidence-backed Draft 0.8 report without submitting cloud work."""
from pathlib import Path
import json,hashlib,html,textwrap
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path(__file__).resolve().parents[4];P=Path(__file__).parent;OUT=ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024'
f=pd.read_csv(OUT/'final_comparison.csv');annual=pd.read_csv(OUT/'final_annual.csv');findings=json.loads((OUT/'final_findings.json').read_text());rules=json.loads((OUT/'frozen_rules.json').read_text());robust=findings['robustness'];sections=[]
def add(title,body):sections.append((title,body.strip()))
def money(n):return f'${n:,.2f}'
add('Draft 0.8 — robust testing and final QC verification', '''
2026-10-24. Scope: SPXW 0DTE iron condor and short put. The latest user instruction supersedes the initial Tom sizing experiment: all equity is available, and Tom's allocation limits are not applied. Preserve the $100,000 condor, $2,000,000 put, original 20-point condor wings, one-lot orders and native QC buying power. A 100% allocation ceiling does not mean forced full margin utilization at every entry. No 10-point-wing variant or $200,000 condor was run.

Draft 0.7 included execution/accounting tests, later-period comparisons and descriptive block bootstrap. It did not establish alpha robustness. Draft 0.8 adds historical walk-forward selection, threshold stability, cost/fee and tail sensitivity, block-length sensitivity and a repeated-search diagnostic, then verifies frozen candidates in funded QC.

All original dates have been inspected before. The additional July 14–October 22, 2026 interval was reserved before inspecting its new option outcomes. This is one short held historical interval, not prospective live evidence. No trading deployment is implied.
''')
add('1. Source, inputs and baseline contract', '''
Keep the saved Tom transcript as research context. Its per-position limits initially made the original $100k 20-point condor largely unaffordable; a feasibility inspection found only one filtered historical episode with net maximum loss below $1,500 at starting capital. The user then explicitly removed Tom sizing. The capital-increase and narrow-wing ideas were discarded before native submission.

The condor targets a 20-delta short put and 8-delta short call with a ±0.02 delta-error tolerance and exact 20-point wings. The naked put targets 25 delta. Both retain 13 daily New York entry slots, one-lot positions, the original fresh-quote/spread gates, midpoint fills with 0.05 index points adverse slippage per package, $1.18 opening fees per contract, and zero modeled expiry commission. Positions use native same-day PM cash expiry.

Native controls are the frozen Draft 0.7 GLD-range condor and QQQ-range short put. Both are rerun over the same extended interval as the new candidates. Their legacy episodes through July 13 must reproduce Draft 0.7 exactly. The local search uses the original funded baseline opportunity tapes; shared contracts and unit payoffs must reconcile, with additions/removals attributed to actual native funding messages.

Use the pinned provider daily raw OHLCV export for GLD, QQQ, SPY, IWM and TLT. Overlapping values match the previous provider export exactly. Cboe's archived VIX daily close adds six features: level, 252/60-session range rank, one/five-session changes, and level relative to its 20-session average. This is a named VIX regime proxy, not vendor option IV rank. No fictitious index volume is created.

Only completed earlier sessions are eligible. Next New York midnight is an assumed availability convention; raw bars are current vintage, not historically publication-certified. No feature labels or future settlement outcomes enter native inputs. Selected range formulas are checked independently against raw rows, and future-input mutation tests protect historical feature values.
''')
add('2. Local optimization and frozen decisions', '''
Search 150 eligible features × 3 quantiles × 2 directions plus a no-filter benchmark: 901 trials per strategy, 1,802 total. Preserve every trial. Broker-IV fields with uncertain clocks remain excluded.

The local engine is custom Python/pandas, not AKQuant. This is conditional replay and optimization of archived QC baseline trades and realized unit payoffs, not an independent local options backtest. It is sufficient for the fixed-contract, one-lot feature-filter POC when followed by frozen-rule native reruns and reconciliation. Trades absent from the funded baseline tape remain a coverage limitation; a different library alone would not supply missing option chains, quote/Greek timing or portfolio-margin simulation.

For each rule, fit a threshold on 2022 and evaluate 2023; fit on 2022–2023 and evaluate 2024. Rank the weaker validation daily cash Calmar after an extra $10 package cost, then total validation profit and stable identity. Fit the selected final threshold on 2022–2024 only. Require at least 400 locally retained episodes in every original included year; this later-count feasibility use is explicit and is not an untouched OOS design.

Freeze one rule per strategy before viewing new QC outcomes. Do not choose a replacement after an unfavorable native result. Native marked drawdown is the final risk measure; local daily realized-cash drawdown is only a search proxy.
''')
for kind in ['condor','put']:
 r=rules[kind];old=f[(f.strategy==kind)&(f.stage=='control')].iloc[0];new=f[(f.strategy==kind)&(f.stage=='final')].iloc[0];c=json.loads((OUT/(kind+'_final_consistency.json')).read_text());a=annual[(annual.strategy==kind)&(annual.stage=='final')]
 add('Measured native result — '+kind,f'''
Frozen filter: {r['feature']} {r['side']} {r['threshold']:.12g}. Training quantile {r['quantile']:.0%}. Worst historical validation cash Calmar under $10 extra cost: {r['score']:.3f}.

Matched Draft 0.7 control over the extended period: {int(old.trades):,} trades, net {money(old.net_pnl)}, CAGR {old.cagr:.3%}, native marked MDD {old.native_mdd:.1%}, Calmar {old.calmar:.3f}.
Draft 0.8 funded QC: {int(new.trades):,} trades, net {money(new.net_pnl)}, CAGR {new.cagr:.3%}, native marked MDD {new.native_mdd:.1%}, Calmar {new.calmar:.3f}.
Native annual counts: {', '.join(str(int(x.year))+': '+str(int(x.trades)) for x in a.itertuples())}. Minimum {int(new.minimum_annual)}; every included year passes 360, without annualizing partial years.

Original-period local conditional result: {money(r['full_local']['pnl'])}. Native original-period result: {money(new.legacy_pnl)}. Shared episodes {c['common_episodes']:,}; maximum shared P&L error {c['max_common_pnl_difference']:.10f}; added {c['added']} (net {money(c['added_pnl'])}); missing {c['missing']} (local net {money(c['missing_pnl'])}). All differences have native funding explanations: {c['funding_explained']}.

Reserved July 14–October 22 result: control {money(old.held_interval_pnl)} from {int(old.held_interval_trades)} trades; candidate {money(new.held_interval_pnl)} from {int(new.held_interval_trades)} trades. Increment {money(new.held_interval_pnl-old.held_interval_pnl)}. This interval follows the full simulated account path; it is not a separately reset account.
Minimum sampled native margin remaining {money(new.min_margin_remaining)}; maximum sampled margin used {money(new.max_margin_used)}. Any negative headroom remains visible despite successful completion.
Full native Calmar improves: {findings['decisions'][kind]['native_calmar_improved']}. Reserved-interval total profit improves: {findings['decisions'][kind]['held_interval_profit_improved']}. Robust alpha proven: False.
Reserved-interval daily increment block-5 descriptive 95% interval: {findings['decisions'][kind]['held_block5_interval95']}. One short interval cannot establish stable performance.
Research decision: {findings['decisions'][kind]['verdict']}
''')
 v=robust[kind]
 add('Robustness results — '+kind,'\n\n'.join([
 'Cost and tail scenarios (local conditional tape):\n'+'\n'.join(x['case']+': net '+money(x['pnl'])+', daily cash Calmar '+f"{x['calmar']:.3f}" for x in v['cost_and_tail_cases']),
 'Matched Draft 0.7 conditional control under identical stresses:\n'+'\n'.join(x['case']+': net '+money(x['pnl'])+', daily cash Calmar '+f"{x['calmar']:.3f}" for x in v['control_cost_and_tail_cases']),
 'Threshold neighborhoods, fitted on 2022–2024:\n'+'\n'.join(f"quantile {x['quantile']:.2f}: net {money(x['pnl'])}; minimum annual count {x['min_annual']}" for x in v['threshold_neighbors']),
 'Expanding annual reoptimization with $10 extra cost: 2023 uses training-only ranking because there is no inner validation year; later years rank the weakest available inner walk-forward validation fold. No current-year outcomes or counts enter selection:\n'+'\n'.join(f"{x['year']}: {x['feature']}, {x['trades']} trades, net {money(x['pnl'])}" for x in v['expanding_walk_forward']),
 'This adaptive process fails some annual 360-trade gates. It is not accepted as the final strategy; do not replace poor yearly rules using that same year’s outcomes.',
 'Paired daily profit increment against the Draft 0.7 filter during 2025–July 13, 2026:\n'+'\n'.join(f"block {x['block_days']} days: mean {money(x['mean_daily_increment'])}; 95% descriptive interval [{money(x['interval95'][0])}, {money(x['interval95'][1])}]" for x in v['later_paired_bootstrap']),
 f"Repeated-search diagnostic across {v['search_adjusted_diagnostic']['rules']} rules: centered 20-day block bootstrap, 1,000 replicates, max-mean-increment tail fraction {v['search_adjusted_diagnostic']['centered_max_search_tail_fraction']:.3f}. This does not establish a statistically robust advantage and is not a Calmar hypothesis test.",
 f"Worst rolling 63-session local profit: {money(v['rolling63_min_pnl'])}. Removal of good days and loss amplification are synthetic sensitivity cases, not forecasts."
 ]))
add('3. Revised acceptance and research design', '''
Baseline gate: retain exact rules, raw input hashes, calendar, costs, capital and native evidence. Reproduce legacy controls before claiming a new result.
Feature gate: source/clock/formula registry; label separation; prior-session availability; numerical parity; future-input mutation; acknowledge current-vintage limitations.
Search gate: declare budget, chronological validation, cost proxy, annual frequency constraint and tie breaks; save every attempted rule; freeze decisions before native outcomes.
Robustness gate: threshold neighborhoods, expanding walk-forward process, costs/fees, clustered resampling, concentrated positive-day dependence and tail-loss sensitivity. Report failed frequency or uncertainty tests explicitly.
Native gate: same entry predicate/input convention, original contract selection and native margin; actual fills, fees, settlement and residual holdings; at least 360 completed episodes per year; source readback and unique cloud identities.
Economic gate: compare native marked risk and reserved-interval performance to the matched Draft 0.7 control. A candidate can be technically verified while economically inferior or insufficiently robust. Keep the better control where a new candidate loses its advantage. No automatic promotion based on training Calmar.

Exact Option Omega parity remains unverified without its trade/config export and independent quote/Greek/settlement reconciliation. Local filters still act on funded baseline tapes; they do not constitute an independent option-market or portfolio-margin simulator. No combined portfolio result is claimed.

Data expansion: an additional options provider is not required for the present fixed-trade filter search. Alternative deltas, widths and entry times require historical quotes/Greeks across eligible contracts, including skipped opportunities; intraday exits also require subsequent price paths. ThetaData is a candidate, not a mandatory dependency or an acquired dataset. Validate a small SPXW sample against QC first: contract/calendar coverage, timestamps and quote age, delta differences, package prices, and settlement. Provider-calculated Greeks need explicit reconciliation. A full local backtester still needs account state, execution and margin logic in addition to the data.
''')
add('4. Reproducible artifacts and source references', '''
Code: strategies/sstrangle/poc/v08/. Results: strategies/sstrangle/results/qc_sizing_poc_20261024/ (the folder name retains the initial sizing-request history; the revised contract explicitly removes sizing limits).
Key evidence: EXPERIMENT_CONTRACT.txt; provider_release.json; vix_source.json; feature_registry.json; frozen_rules.json; optimizer_provenance.json; both complete trial CSVs; robustness.json; native source/input manifests, launch intents, terminal results, raw order pages and consistency audits; final_comparison.csv; final_annual.csv; final_verification.json.

Tom source: research/tom_position_sizing_20261024/; user-provided transcript, video URL/publication date unknown.
Cboe VIX raw daily source: https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
QC buying-power reference: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power
QC option margin implementation inspected: https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Securities/Option/OptionMarginModel.cs
These sources inform input/model interpretation; the report's strategy performance comes from the archived native runs.
''')
(P/'DESIGN_REPORT.txt').write_text('\n\n'.join(t+'\n'+b for t,b in sections))
plt.rcParams.update({'font.family':'DejaVu Sans','text.parse_math':False});fig,axes=plt.subplots(1,3,figsize=(15,5));kinds=['condor','put']
for j,(field,title) in enumerate([('net_pnl','Full native net profit (USD)'),('calmar','Native CAGR / marked MDD'),('held_interval_pnl','Reserved interval profit (USD)')]):
 for i,stage in enumerate(['control','final']):axes[j].bar([n+(i-.5)*.32 for n in range(2)],[float(f[(f.strategy==k)&(f.stage==stage)].iloc[0][field]) for k in kinds],.32,label='Draft 0.7 control' if i==0 else 'Draft 0.8 candidate',color=['#94a3b8','#2563eb'][i])
 axes[j].set(xticks=[0,1],xticklabels=['Condor $100k','Put $2m'],title=title);axes[j].legend(fontsize=8)
fig.tight_layout();fig.savefig(P/'comparison.png',dpi=150)
with PdfPages(P/'DESIGN_REPORT.pdf') as pdf:
 pdf.savefig(fig)
 for title,body in sections:
  lines=[]
  for paragraph in body.split('\n'):lines.extend(textwrap.wrap(paragraph,103,break_long_words=False) or [''])
  for offset in range(0,len(lines),49):
   page=plt.figure(figsize=(8.27,11.69));page.text(.07,.95,title+(' (continued)' if offset else ''),fontsize=13,weight='bold',va='top');page.text(.07,.90,'\n'.join(lines[offset:offset+49]),fontsize=9,va='top',linespacing=1.45);page.text(.07,.035,'Draft 0.8 | Audited research | 2026-10-24',fontsize=8,color='#64748b');pdf.savefig(page)
   if title.startswith('Draft 0.8') and not offset:page.savefig(P/'overview_preview.png',dpi=120)
   plt.close(page)
plt.close(fig)
body=''.join('<section><h2>'+html.escape(t)+'</h2>'+''.join('<p>'+html.escape(p).replace('\n','<br>')+'</p>' for p in b.split('\n\n'))+'</section>' for t,b in sections)
(P/'DESIGN_REPORT.html').write_text('<!doctype html><meta charset="utf-8"><title>Draft 0.8</title><style>body{font:17px/1.65 system-ui;max-width:1050px;margin:40px auto;padding:20px;color:#192b44}img{width:100%}section{margin:40px 0}</style><h1>Draft 0.8</h1><img src="comparison.png">'+body)
(P/'manifest.json').write_text(json.dumps({'files':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in P.iterdir() if x.is_file() and x.name!='manifest.json'}},indent=2));print(P/'DESIGN_REPORT.pdf')
