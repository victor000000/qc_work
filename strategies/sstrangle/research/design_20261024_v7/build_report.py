"""Draft0.7: baseline reproduction, local optimization and funded QC closure."""
from pathlib import Path
import html,json,hashlib,textwrap,re
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path(__file__).resolve().parents[4];P=Path(__file__).parent;BASE=ROOT/'strategies/sstrangle/results/qc_final_poc_20261024'
findings=json.loads((BASE/'final_findings.json').read_text());table=pd.read_csv(BASE/'final_comparison.csv');annual=pd.read_csv(BASE/'final_annual.csv');rules=json.loads((BASE/'frozen_rules.json').read_text())
sections=[]
def add(title,text):
 text=text.strip()
 for old,new in [('Draft0.65','Draft 0.65'),('Draft0.7','Draft 0.7'),('Draft0.6','Draft 0.6'),('source interval:16','source interval: 16'),('tail.2022','tail. 2022'),(';16-delta','; 16-delta'),(';25-delta','; 25-delta'),('authorized0DTE','authorized 0DTE'),('saved45-DTE','saved 45-DTE'),('all3','all 3'),('Gate1','Gate 1'),('Gate2','Gate 2'),('Gate3','Gate 3'),('Gate4','Gate 4'),('Gate5','Gate 5'),('Gate6','Gate 6'),('StageA','Stage A'),('StageB','Stage B'),('StageC','Stage C'),('StageD','Stage D'),('StageE','Stage E'),('StageF','Stage F'),('budget:144','budget: 144'),('2,592','2,592'),('rules,2,592','rules, 2,592'),('quantiles(25th,50th,75th)','quantiles (25th, 50th, 75th)'),('quantiles(25th','quantiles (25th'),('days(ddof','days (ddof'),('dollars;','dollars;')]:text=text.replace(old,new)
 text=re.sub(r'([A-Za-z])(?=20[0-9]{2}(?![0-9]))',r'\1 ',text)
 text=re.sub(r'\b(from|of|the|below|within|with|over|those|at|before|after|only|saved)(?=[0-9])',r'\1 ',text)
 sections.append((title,text))
fmt=lambda x:f'${x:,.2f}'
add('Draft 0.7 — the local-to-QC verification loop', '''
2026-10-24. SPXW 0DTE source interval:16 May2022–13 July2026; four-day native settlement tail.2022 and2026 are partial years.

Draft0.65 stopped at conditional local screening. It had no funded QC rerun of those alpha filters. Draft0.7 closes that missing stage: independently recheck the saved baseline accounting and selected feature calculations, repeat the full unfiltered condor natively, freeze local optimizer decisions, implement the filters in QC, and audit the complete final native paths.

The three baselines remain: ±0.02-target-error iron condor with $100,000;16-delta naked short strangle with $2m;25-delta naked short put with $2m. The naked strategies are user-authorized0DTE Tom-inspired adaptations, not reproductions of the saved45-DTE Tom source. No sizing or cost changes are used to make a filter look better.

Engineering verification and economic improvement are separate outcomes. A verified native run can still reveal a poor optimized strategy. All periods were previously inspected, and later counts participate in feasibility screening; this is retrospective development, not untouched out-of-sample evidence.
''')
control=findings['fresh_control']
add('1. Baseline consistency — what was actually rechecked', f'''
A second local implementation parses native opening events and contract identities, calculates opening cash and fees, then applies the terminal intrinsic payoff to each leg. It reproduces every episode and the final account for all three saved baselines. Maximum per-episode discrepancies are floating-point rounding, below0.00001 dollars; residual contract quantities are zero. Fees and duplicate-event mutation tests deliberately break the fixture and confirm the checker rejects it.

This is arithmetic reproduction of native observations, not independent vendor option-price validation or a clone of QC's margin engine. Native expiry reference values are retained as source evidence; they are not silently relabeled independently verified official settlement values.

Fresh full-period unfiltered condor control: {control['native_episodes']:,} trades, net {fmt(control['native_pnl'])}. Common episode maximum P&L difference: {control['max_common_pnl_difference']:.10f}; changed contract identities: {len(control['common_contract_mismatches'])}; added: {control['added_episodes']}; missing: {control['missing_episodes']}. This directly checks repeatability of the baseline trading path under the revised adapter with the alpha gate disabled.

The saved strangle and put baselines are rechecked across all episodes locally; their filtered final QC runs additionally compare every shared native entry with those baselines. Only the condor receives a fresh full unfiltered rerun in this campaign. Do not describe all three original unfiltered accounts as newly rerun.
''')
add('2. Review findings and optimizer revision', '''
Prior missing stage: local filters were screened but never submitted as funded QC strategies. Previous local P&L could not be presented as a final verified strategy result. That omission is repaired by native implementations and final order-level reconciliation in this revision.

Prior ranking weakness: training mean profit per trade can favor high-premium/high-risk samples. The new declared ranking uses training daily realized-cash Calmar, with training total profit and stable feature/quantile/side tie breaks. This cash metric is a local search proxy, not QC marked drawdown. A high training Calmar across hundreds of tested rules is not an unbiased estimate of future performance.

Search budget:144 already-implemented eligible price/volume features ×three training quantiles(25th,50th,75th) ×both directions =864 rules per strategy,2,592 rules total. The20 uncertain-clock broker-IV fields remain excluded. Raw fields and native contract diagnostics are not mislabeled independent alpha tests. Every tested rule is retained, not just the winners.

Thresholds and risk ranking use2022–2023 only. Feasibility requires at least400 retained historical episodes in EVERY included year, providing a buffer for the final funded360 requirement. This uses later counts, not later P&L; it must be disclosed and precludes a pristine OOS claim.2024 and2025–2026 results are reported after selection. One rule per strategy is frozen with hashes before its final native run; native results do not trigger retrospective threshold changes.

The unfiltered baseline remains the comparison. These are simple single-feature candidates, not an exhaustive optimizer, predictive machine-learning model or proven deployment recommendation. Broader search must retain all failed experiments and obtain new prospective evidence.
''')
add('3. Identical feature inputs and timing in local and QC', '''
Use the pinned Draft0.65 daily provider export, including warmup from2021. The selected raw instrument rows are readable ordinary Python data modules, partitioned below32KB per file and uploaded alongside main.py through the existing Rust client. The code computes the frozen feature at each decision; it does not embed a list of winning trade dates or P&L labels.

Only rows with session date strictly BEFORE the decision's New York date enter calculation. Prior completed daily observations use the existing assumed next-midnight availability convention and seven-day maximum age; current/future rows cannot affect decisions. Tests mutate future rows and check same-day exclusion, stale data and threshold boundaries. Current-vintage raw bars are reproducible but not historically vintage-certified; exact publication clocks remain a provider requirement.

Range feature=(prior high−prior low)/prior close. Volume z-score=(latest completed volume−mean of20 completed daily volumes)/sample standard deviation over those20 volumes(ddof=1). Local reference pandas values and native pure-Python calculations agree within1e-10, with zero threshold-decision mismatches on the baseline tapes.

Every native entry records feature name, full-precision value and source session day before order submission. Recompute them independently from pinned raw inputs. Read back the actual QC project files and verify hashes of main.py and every input module before the project is reused. Feature consistency is checked on actual native entries, including any newly admitted funding-path trades.

A first compressed-data source upload was rejected by QC; it never created a backtest. The replacement uses fully readable plain-text modules in accordance with the platform's file rules. A local CLI extra-files argument error was also preserved and corrected to a JSON file path. Neither failure changes the frozen alpha rule. Intermittent API transport failures also interrupted a post-run source read; bounded read-only retries and resume from archived terminal/order evidence fixed the workflow without repeating a backtest. Completed project snapshots are retained because the cloud project can subsequently be reused. The final put upload exhausted Rust transport retries before any native run existed. After confirming an idle node and no matching backtest, the task-owned worker was stopped. The same frozen files were verified and submitted once through the existing authenticated Python transport; creation intent/response, native identity and recovery evidence are archived. No cloud run was cancelled or duplicated. No restricted QC quote history is exported through logging.
''')
add('4. Native execution and acceptance gates', '''
Preserve the baseline schedules, same-day PM SPXW series, one-lot legs, exact20-point condor wings, quote freshness/spread gates and Black-Scholes delta selection. Only the condor retains the ±0.02 delta-error gate; the original naked examples are not silently given that new tolerance. Daily alpha admission is applied before candidate selection and order submission.

Preserve $0.05 index points adverse slippage per whole package, $1.18 per opening contract and zero modeled native expiry commission. Native buying power remains active. European discretionary early assignment stays disabled; automatic cash expiry remains native. Market-open checks respect half-days and the final settlement tail.

Gate1: native terminal result must include final order statistics and cash/ledger/count fields; a Completed flag alone is insufficient. Gate2: every native fill/fee/expiry, source identity and residual holding reconciles. Gate3: >=360 completed logical episodes in each included year, without annualizing partial years. Gate4: actual feature values/source dates/pass decisions agree with local computation.

Gate5: on common entries, contract identities and whole-episode P&L must agree. Local/native differences are decomposed into common-trade changes, additions and missing entries. Every added/missing entry must have an actual native insufficient-buying-power explanation for acceptance in this campaign; otherwise stop and investigate. Native funding can recover opportunities missing from the original funded tape or reject some that tape retained. Do not force equality by discarding changed native trades.

Gate6: compare final native marked drawdown, CAGR and later-period outcomes against the baseline. Passing engineering/count gates does not automatically pass a performance criterion. Negative native margin headroom, if present, remains visible; completion is not proof of continuously positive buying power.
''')
for kind in ['condor','strangle','put']:
 r=rules[kind];x=findings['strategies'][kind];c=x['consistency'];b=table[(table.strategy==kind)&(table.stage=='baseline')].iloc[0];n=table[(table.strategy==kind)&(table.stage=='final_qc')].iloc[0];l=table[(table.strategy==kind)&(table.stage=='local_conditional')].iloc[0]
 counts=annual[(annual.strategy==kind)&(annual.stage=='final_qc')]
 add('Measured result — '+kind,f'''
Frozen rule: {r['feature']} {r['side']} {r['threshold']:.12g}; training quantile {r['quantile']:.0%}. Eligible rules: {r['eligible_trials']} of {r['trials']}. Training daily cash Calmar: {r['train_calmar']:.3f}; this is selected training performance, not a validated risk forecast.

Starting capital: {fmt(n.capital)}.
Baseline native: {int(b.trades):,} trades; net {fmt(b.net_pnl)}; CAGR {b.cagr:.3%}; marked maximum drawdown {b.native_mdd:.1%}; Calmar {b.calmar:.3f}.
Local conditional candidate: {int(l.trades):,} trades; net {fmt(l.net_pnl)}; daily cash maximum drawdown {l.daily_cash_mdd:.1%}; daily cash Calmar {l.daily_cash_calmar:.3f}. Local cash risk is not a native marked-risk result.
Final funded QC: {int(n.trades):,} trades; net {fmt(n.net_pnl)}; CAGR {n.cagr:.3%}; marked maximum drawdown {n.native_mdd:.1%}; Calmar {n.calmar:.3f}.
Native annual counts: {', '.join(str(int(row.year))+': '+str(int(row.trades)) for row in counts.itertuples())}. Minimum {int(n.min_annual)};360 gate passed.

Common entries: {c['common_episodes']:,}; changed contracts: {len(c['common_contract_mismatches'])}; maximum common P&L difference {c['max_common_pnl_difference']:.10f}. Added entries: {c['added_episodes']} with net {fmt(c['added_pnl'])}; missing entries: {c['missing_episodes']} with local net {fmt(c['missing_pnl'])}. Buying-power explanations verified: {c['funding_differences_explained']}. Maximum feature-value error: {c['feature_max_error']:.12g}; verified cloud source/input modules: {c['cloud_modules_verified']}.

2025–2026 native profit: baseline {fmt(b.later_pnl)}, filtered {fmt(n.later_pnl)}. Average daily increment {fmt(x['later_daily_increment'])}; descriptive five-day block95% interval {x['later_daily_increment_block5_95']}. This interval is not adjusted for optimizer selection.
Research decision: {x['research_decision']}

Full-period native Calmar improves: {x['full_native_calmar_improves']}. Full-period native total profit improves: {x['full_native_pnl_improves']}. Later-period total profit improves: {x['later_total_pnl_improves']}.
Minimum sampled native margin remaining: {fmt(n.min_margin_remaining)}. Performance findings above determine further research priority; a mechanically verified filter is not automatically promoted for trading.
''')
add('5. What is now final, and what remains unresolved', '''
The local-to-native loop is complete for the three frozen candidates: baseline accounting reproduction, feature parity, actual funded QC execution and native outcome reconciliation. This is the missing verification stage from0.65. All baseline and candidate identities, sources, input modules, raw native order pages and full trial records remain reviewable.

The conditional local tape is not an independent full opportunity simulator. It cannot reproduce native margin decisions on opportunities that were never filled, or independently price changed strikes, stops or exits. Where final funded trades differ, actual native rejection messages explain the difference. Claim consistency at the levels that were tested: accounting, feature decisions, common contracts/fills and audited funding differences.

Exact Option Omega parity is still separate. Original OO trade exports/configuration, historical Greek/quote conventions and independently verified expiry reference data remain missing. Passing local/QC consistency does not imply agreement with another vendor's backtest. The prior0.65 provider requirements remain the input roadmap; this revision does not purchase data or start a new backfill.

All tested periods are development evidence. A favorable full-period Calmar or profit does not establish a robust alpha; report later-period degradation and all tested rules. A selected rule that performs poorly is a valid failed research result, not grounds for concealing the trial or silently choosing a new winner.
''')
add('6. Revised research design', '''
StageA — freeze baseline and source contract: strategy, capital, quotes, deltas, costs, expiry, calendar and source versions. Require native accounting and yearly counts before producing a research tape.
StageB — baseline reproduction: independent local payoff/event arithmetic, exact per-episode/yearly reconciliation and a fresh native control for adapter changes. State which market/margin components are shared rather than independent.
StageC — feature admission: typed source/clock/formula registry, immutable raw inputs, no labels in feature modules, raw-versus-adjusted basis, warmup and missingness contracts. Require cross-engine formula tests and actual native feature tags.
StageD — local search: declare splits, search budget, objective, frequency constraint and tie breaks. Save every rule and freeze selected candidates with source/input hashes before QC. Distinguish full-period feasibility from untouched evaluation.
StageE — funded QC closure: implement the same predicate and input availability, preserve execution assumptions, verify final order/cash identities, and attribute changed entries to native funding. Readiness checks wait for complete native statistics; never duplicate a running experiment.
StageF — acceptance decision: engineering parity, >=360 annual trades, risk/performance comparison, later behavior, selection uncertainty and fresh prospective evidence. Retain/reject each candidate explicitly. Independent quote-backed local simulation, wider option features and shared-capital portfolio tests remain separate work.

Local conditional filtering is useful for cheap candidate screening; final QC is required before calling it a funded result. Any changed execution/contract rule must regenerate paths. A combined portfolio needs its own funding test; do not add the independent $100k/$2m/$2m accounts and call that a portfolio.
''')
add('7. Evidence and reproduction', '''
Code: strategies/sstrangle/poc/v07/. Run recheck_baselines.py, optimize.py only against the frozen inputs/rules contract, then the explicitly queued campaign. The report/analysis commands never submit cloud work.
Results: strategies/sstrangle/results/qc_final_poc_20261024/.
Key artifacts: baseline_recheck.json; frozen_rules.json and optimizer_provenance.json; all3 *_all_trials.csv; native *_manifest.json, *_extra_files.json, *_cloud_source_files.json; *_consistency.json and *_funding_messages.json; complete *_evidence raw orders/audits; final_comparison.csv, final_annual.csv and final_findings.json; final_verification.json.

Source-file format/reference: https://www.quantconnect.com/docs/v2/cloud-platform/projects/files
Platform file quotas and plain-text packaging are implementation constraints, not changes to strategy or data licensing. No compressed/obfuscated source is used by accepted runs.
Prior design: strategies/sstrangle/research/design_20261024_v065/DESIGN_REPORT.pdf.
Provider roadmap: /home/vic/data_providers/docs/requirements/QC_DRAFT_065_FEATURE_AND_PARITY_REQUIREMENTS_20261024.txt.
''')
text='\n\n'.join(t+'\n'+body for t,body in sections);(P/'DESIGN_REPORT.txt').write_text(text)
plt.rcParams.update({'font.family':'DejaVu Sans','text.parse_math':False});fig,axes=plt.subplots(1,2,figsize=(14,6))
keys=['condor','strangle','put'];x=list(range(3));w=.26
for i,(stage,color,label) in enumerate([('baseline','#94a3b8','Baseline native'),('local_conditional','#eab308','Local conditional'),('final_qc','#2563eb','Final funded QC')]):
 vals=[table[(table.strategy==k)&(table.stage==stage)].iloc[0].net_pnl for k in keys];axes[0].bar([j+(i-1)*w for j in x],vals,w,label=label,color=color)
axes[0].set(xticks=x,xticklabels=['Condor $100k','Strangle $2m','Put $2m'],ylabel='USD',title='Separate accounts: total net profit');axes[0].legend()
for i,stage in enumerate(['baseline','final_qc']):
 vals=[table[(table.strategy==k)&(table.stage==stage)].iloc[0].calmar for k in keys];axes[1].bar([j+(i-.5)*.32 for j in x],vals,.32,label=stage,color=['#94a3b8','#2563eb'][i])
axes[1].set(xticks=x,xticklabels=keys,title='Native CAGR / native marked drawdown');axes[1].legend();fig.tight_layout();fig.savefig(P/'final_comparison.png',dpi=160)
fig2,ax=plt.subplots(figsize=(14,5));ax.axis('off');ax.set_xlim(0,6);ax.set_ylim(0,2)
steps=['Freeze baseline','Reproduce locally','Freeze local rule','Run funded QC','Reconcile trades','Accept / reject']
for i,t in enumerate(steps):
 ax.text(i+.47,1.1,t,ha='center',va='center',bbox=dict(boxstyle='round,pad=.7',facecolor='#eff6ff',edgecolor='#2563eb'),fontsize=10)
 if i<5:ax.annotate('',xy=(i+1,.9),xytext=(i+.9,.9),arrowprops=dict(arrowstyle='->'))
ax.text(3,.35,'Same raw features and timing | Native margin retained | Every year >=360 | All trials preserved',ha='center',fontsize=12);fig2.tight_layout();fig2.savefig(P/'verification_pipeline.png',dpi=160)
with PdfPages(P/'DESIGN_REPORT.pdf') as pdf:
 pdf.savefig(fig);pdf.savefig(fig2)
 for title,body in sections:
  lines=[]
  for paragraph in body.split('\n'):lines.extend(textwrap.wrap(paragraph,103,break_long_words=False) or [''])
  for offset in range(0,len(lines),49):
   page=plt.figure(figsize=(8.27,11.69));page.text(.07,.95,title+(' (continued)' if offset else ''),fontsize=14,weight='bold',va='top');page.text(.07,.90,'\n'.join(lines[offset:offset+49]),fontsize=9,va='top',linespacing=1.45);page.text(.07,.035,'Draft0.7 | Audited local-to-QC research | 2026-10-24',fontsize=8,color='#64748b');pdf.savefig(page)
   if title.startswith('Draft 0.7') and not offset:page.savefig(P/'overview_preview.png',dpi=120)
   plt.close(page)
plt.close('all')
body=''.join('<section><h2>'+html.escape(t)+'</h2>'+''.join('<p>'+html.escape(p).replace('\n','<br>')+'</p>' for p in b.split('\n\n'))+'</section>' for t,b in sections)
(P/'DESIGN_REPORT.html').write_text('<!doctype html><meta charset="utf-8"><title>Draft0.7</title><style>body{font:17px/1.65 system-ui;max-width:1050px;margin:40px auto;padding:20px;color:#192b44}img{width:100%}section{margin:40px 0}</style><h1>Draft0.7</h1><img src="final_comparison.png"><img src="verification_pipeline.png">'+body)
(P/'manifest.json').write_text(json.dumps({'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in P.iterdir() if f.is_file() and f.name!='manifest.json'}},indent=2));print(P/'DESIGN_REPORT.pdf')
