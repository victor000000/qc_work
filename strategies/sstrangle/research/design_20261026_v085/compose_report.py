"""Compose findings only when the complete frozen campaign evidence exists."""
from pathlib import Path
import sys,json,hashlib,html
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];FOLDER=Path(__file__).parent
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v085'))
from campaign import OUT,ACTIVE_KINDS

def table(headers,rows):
 return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])+'\n'
def money(v):return f'-${abs(v):,.2f}' if v<0 else f'${v:,.2f}'
def chart(rows):
 width,height=1000,390;colors=['#356c9b','#cf732b'];lines=[]
 all_values=[];series=[]
 for kind in ACTIVE_KINDS:
  for stage in ['baseline','final']:
   f=pd.read_parquet(OUT/(kind+'_'+stage+'_evidence/episodes.parquet'))
   g=f.groupby('day').pnl.sum().cumsum()+100000;series.append((kind,stage,g));all_values.extend(g.tolist())
 low=min([100000]+all_values);high=max([100000]+all_values);span=max(high-low,1)
 start=pd.Timestamp('2022-05-16');end=pd.Timestamp('2026-10-22')
 for k,(kind,stage,g) in enumerate(series):
  panel=0 if kind=='condor' else 1;x0=65+panel*500
  points=' '.join(f'{x0+(pd.Timestamp(str(d))-start).days/(end-start).days*400:.1f},{310-(v-low)/span*230:.1f}' for d,v in g.items())
  color=colors[0 if stage=='baseline' else 1];dash=' stroke-dasharray="5 3"' if stage=='baseline' else ''
  lines.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
  if stage=='baseline':
   lines.append(f'<text x="{x0}" y="55" font-size="19">{html.escape(kind.replace("_"," ").title())}</text>')
   for i in range(5):
    val=low+span*i/4;y=310-230*i/4;lines.append(f'<line x1="{x0}" y1="{y}" x2="{x0+400}" y2="{y}" stroke="#ddd"/><text x="{x0-5}" y="{y}" text-anchor="end" font-size="10">{val/1000:.0f}k</text>')
   lines.append(f'<text x="{x0}" y="335" font-size="11">May 2022</text><text x="{x0+340}" y="335" font-size="11">Oct 2026</text>')
 lines.append('<text x="565" y="80" font-size="19">Put-spread POC rejected</text><text x="565" y="120" font-size="14">Native margin call: July 12, 2022</text><text x="565" y="150" font-size="14">No local selection or final candidate</text>')
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/><g font-family="Arial" fill="#183047"><text x="25" y="25" font-size="17">Realized daily cash equity — not native marked equity</text>'+''.join(lines)+'<text x="65" y="375" fill="#356c9b">Dashed blue: unfiltered baseline</text><text x="520" y="375" fill="#cf732b">Orange: frozen candidate</text></g></svg>'
 (FOLDER/'cash_equity.svg').write_text(svg)
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(1,2,figsize=(11,4),sharey=True)
 for kind,stage,g in series:
  ax=axes[0 if kind=='condor' else 1]
  ax.plot(pd.to_datetime(g.index),g.values,label=stage,color=colors[0 if stage=='baseline' else 1],linestyle='--' if stage=='baseline' else '-')
  ax.set_title(kind.replace('_',' ').title());ax.set_xlim(pd.Timestamp('2022-05-16'),pd.Timestamp('2026-10-22'));ax.grid(alpha=.2);ax.legend();ax.tick_params(axis='x',rotation=30)
 axes[1].axis('off');axes[1].text(.1,.65,'Put-spread POC rejected\n\nNative margin call: July 12, 2022\nNo local selection or final candidate',transform=axes[1].transAxes,fontsize=12,color='#8b4625')
 axes[0].set_ylabel('Cash equity ($)');fig.suptitle('Realized daily cash equity — not native marked equity');fig.tight_layout();fig.savefig(FOLDER/'cash_equity.png',dpi=150);plt.close(fig)
 fig,ax=plt.subplots(figsize=(11,2.5));ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis('off')
 labels=['QC baseline\nNative orders, fills\nand funded accounts','Local research\n13 executed trials\nFreeze predicates','QC verification\nNative funding rerun\nTrade-level bridge']
 for x,label in zip([.17,.5,.83],labels):
  ax.text(x,.68,label,ha='center',va='center',fontsize=12,bbox=dict(boxstyle='round,pad=.8',fc='#e6eff5',ec='#356c9b'))
 for x in [.31,.64]:ax.annotate('',xy=(x+.08,.68),xytext=(x,.68),arrowprops=dict(arrowstyle='->',lw=2,color='#356c9b'))
 ax.text(.5,.15,'Separate gates: accounting | frequency | economic comparison | margin | official settlement\nIndependent quote / opportunity / margin replay remains pending',ha='center',va='center',fontsize=11,color='#8b4625')
 fig.tight_layout();fig.savefig(FOLDER/'pipeline.png',dpi=150);plt.close(fig)


def compose():
 verify=json.loads((OUT/'final_verification.json').read_text());decisions=json.loads((OUT/'decision_record.json').read_text());local=json.loads((OUT/'local_research.json').read_text());official=json.loads((OUT/'official_settlement_audit.json').read_text());comparison=pd.read_csv(OUT/'final_comparison.csv');annual=pd.read_csv(OUT/'final_annual.csv');rules=json.loads((OUT/'frozen_rules.json').read_text())
 assert len(comparison)==2 and len(verify['runs'])==3
 text='# Version 0.8.5 — 0DTE strategy design and measured evidence\n\n26 October 2026 · SPXW iron condor + rejected put-spread POC · Research release\n\n'
 text+='The fresh native baseline → bounded local selection → funded native verification campaign has completed. This release delivers the full condor loop and rejects the additional put-spread POC after a full-baseline margin call. It preserves both successful and failed evidence. The engineering, frequency, margin, settlement and economic conclusions below are separate; no live deployment or robust-alpha claim is made.\n\n'
 text+='## Measured outcome\n\n'
 text+=table(['Check','Observed conclusion'],[
  ['Fresh native jobs','Three completed: spread smoke, condor baseline and frozen condor final; one failed spread baseline'],
  ['Engineering reconciliation',str(verify['engineering_pass'])],['Annual ≥360 gate',str(verify['frequency_pass'])],['All full runs have nonnegative sampled margin',str(verify['margin_headroom_pass'])],['Independent quote/funding replay','Not completed; provider admission remains blocked'],['Robust alpha / live readiness','Not established / not approved']])+'\n'
 text+=table(['Strategy / stage','Trades','Net P&L','Native MDD','Native Calmar'],[[r.strategy+' / '+r.stage,f'{r.trades:,}',money(r.net_pnl),f'{r.native_mdd:.1%}',f'{r.calmar:.3f}'] for r in comparison.itertuples()])+'\n'
 text+='The optional put-spread baseline failed on a native margin-call fill at 2022-07-12 15:37 New York. All 1,141 raw orders and the failed cloud identity are preserved. Its early-aborted return/CAGR is not reported as an accepted strategy result. No spread filter or final candidate was run. The scope amendment was saved before local selection, without changing the condor search.\n\n'
 text+='Each full account starts at $100,000 and uses one-lot entries. Native MDD is QC-reported marked drawdown; local cash plots and search scores are different measures. Net results use the native reference fill and settlement model. They are not results repriced at official Cboe settlement.\n\n'
 for kind,d in decisions.items():
  text+=f'**{kind.replace("_"," ").title()}: {d["verdict"]}.** Later-period native profit increment: {money(d["later_profit_increment"])}. The 20-session block interval for mean daily native uplift is [{money(d["native_block_bootstrap95"]["20"][0])}, {money(d["native_block_bootstrap95"]["20"][1])}]. Sampled margin headroom gate: {d["nonnegative_sampled_margin"]}.\n\n'
 text+='### Preserved cross-version comparison\n\n'
 versions=pd.read_csv(OUT/'cross_version_condor_comparison.csv')
 text+=table(['Frozen condor variant','Full net P&L','Native MDD','Native Calmar','2025–2026 P&L'],[[r.version,money(r.net_pnl),f'{r.native_mdd:.1%}',f'{r.calmar:.3f}',money(r.later_2025_2026_pnl)] for r in versions.itertuples()])+'\n'
 text+='These are separate funded historical accounts over the same extended interval and reference costs. The older two rows are preserved archived runs, not new 0.8.5 submissions. Version 0.8.5 improves full-period risk metrics, but its later profit lies between the older candidates and below the unfiltered baseline. This descriptive comparison does not replace the predeclared baseline test or certify robust alpha.\n\n'
 text+='### Frozen rules and local evidence\n\n'
 text+=table(['Strategy','Frozen predicate','2024 selection score','2025–2026 local P&L'],[[k,(r['feature']+' '+('>' if r['side']=='above' else '≤')+' '+format(r['threshold'],'.15g')) if r['feature']!='none' else 'No filter',f'{r["score"]:.3f}',money(local[k]['later']['pnl'])] for k,r in rules.items()])+'\n'
 text+='Selection score is daily realized-cash Calmar with $10 additional package cost. Thresholds are fitted only to unique baseline-filled 2022–2023 days; ranking and count feasibility stop at 2024. All 13 executed condor trials remain saved, including ineligible rules.\n\n'
 text+=table(['Strategy','Common episodes','Added / missing','Max common P&L error','Unexplained differences'],[[k,c['common_episodes'],f'{c["added"]} / {c["missing"]}',f'{c["common_max_pnl_error"]:.10f}',len(c['unexplained_differences'])] for k,c in verify['comparisons'].items()])+'\n'
 text+='Added/missing rows are the funded-account distinction between filtering a baseline tape and running the predicate natively. The saved bridge uses actual rejection messages; identical total profit alone would not establish parity.\n\n'
 text+='### Annual counts and observed profit\n\n'
 text+=table(['Strategy / stage','Year','Actual episodes','Net P&L','≥360'],[[r.strategy+' / '+r.stage,str(r.year)+(' (partial)' if r.partial_year else ''),r.trades,money(r.pnl),str(r.passed)] for r in annual.itertuples()])+'\n'
 text+='### Model validity: official settlement and native margin\n\n'
 sensitivity=json.loads((OUT/'settlement_rule_sensitivity.json').read_text())
 text+=table(['Frozen strategy on identical covered contracts','Native reference P&L','Official expiry sensitivity P&L'],[[k,money(v['covered_frozen_native']['pnl']),money(v['covered_frozen_official']['pnl'])] for k,v in sensitivity.items()])+'\n'
 text+='These covered-subset figures exclude the same unavailable settlement dates on both sides. They keep the already frozen entry predicate, contracts and fees. The diagnostic also retains scores for all original rules without choosing a replacement.\n\n'
 text+=table(['Run','Official covered / native days','Days differ >0.01','Official-minus-native expiry cash'],[[k,f'{v["official_covered_days"]} / {v["native_days"]}',v['days_differ_over_001'],money(v['sum_official_minus_native_expiry'])] for k,v in official.items()])+'\n'
 text+='This is an independently sourced outcome check on the same filled contracts, using the provider\'s saved official Cboe weekly year archives. Missing dates remain missing; third-Friday and month-end PM series must not be silently filled from AM settlement. The cash column is a fixed-contract sensitivity, not a corrected account or rerun. Settlement changes could alter subsequent funding, ranking and candidate choice. Native cash accounting can reconcile exactly while its expiry reference differs from the official value. Historical publication times are not known.\n\n'
 text+=table(['Run','Minimum sampled margin remaining','Maximum sampled margin used'],[[r.strategy+' / '+r.stage,money(r.minimum_margin_remaining),money(r.maximum_margin_used)] for r in comparison.itertuples()])+'\n'
 text+='Negative headroom is a failed readiness gate even when QC completes without an unexpected liquidation. These are minute-sampled extrema, not proof about every instant. Do not increase capital or narrow wings after seeing this result merely to hide the issue.\n\n'
 text+='### Cost, threshold and dependence diagnostics\n\n'
 text+=table(['Strategy','Extra package cost','Local net P&L','Cash Calmar'],[[k,'$'+c,money(v['pnl']),f'{v["calmar"]:.3f}'] for k,r in local.items() for c,v in r['cost_stress'].items()])+'\n'
 for k,r in local.items():
  text+=f'{k}: removing the five best days under the $10 stress leaves {money(r["remove_best_five_days"]["pnl"])}. The exploratory max-rule diagnostic has p={r["max_rule_diagnostic"]["p_value"]:.4f}. Selected exposure covers {r["independent_days"]} distinct days; these are not necessarily independent regimes.\n\n'
  text+=table(['Block length','Mean local daily uplift ($10 cost)','Descriptive 95% interval'],[[b,money(v['mean_daily_uplift']),f'[{money(v["ci95"][0])}, {money(v["ci95"][1])}]'] for b,v in r['block_bootstrap_uplift'].items()])+'\n'
  if r['threshold_neighbors']:text+=table(['Threshold multiplier','Local trades','Later net at +$10','Later cash Calmar'],[[v['scale'],v['trades'],money(v['later']['pnl']),f'{v["later"]["calmar"]:.3f}'] for v in r['threshold_neighbors']])+'\n'
 text+='All neighborhoods are diagnostics, not reranking candidates. Economic preference and interval signs do not override the settlement/margin/independent-replay limitations.\n\n'
 text+=(FOLDER/'DESIGN_BODY.md').read_text()+'\n\n## 10. Evidence index and acceptance decision\n\n'
 text+=table(['Evidence','Location relative to the v0.8.5 results directory'],[
 ['Predeclared scope and failure-driven amendment','experiment_contract.json; scope_amendment.json; put_spread_failure.json'],['Actual jobs and source identity','*_manifest.json; *_cloud_source_files.json; *_terminal.json'],['Original orders / audit','*_evidence/raw_order_pages/; orders.json; audit.json'],['All trial rules and frozen choice','*_trials.csv; frozen_rules.json; research_provenance.json'],['Features / labels','*_entry_features.parquet; *_labels.parquet; feature_registry.json'],['Baseline arithmetic and funded bridge','*_verification.json; *_local_qc_comparison.json; *_funding_messages.json'],['Robustness','local_research.json; decision_record.json'],['Official outcome comparison','official_settlement_audit.json; *_official_settlement.csv'],['Provider receipt and sources','provider_clock_snapshot.json; reviewed_source_manifest.json'],['Native table and gate summary','final_comparison.csv; final_annual.csv; final_verification.json'],['Tests','tests.log; inherited_admission_tests.log']])+'\n'
 text+='Results directory: `strategies/sstrangle/results/qc_poc_20261026_v085/`. Implementation: `strategies/sstrangle/poc/v085/`. This report and the contract are preserved under `strategies/sstrangle/research/design_20261026_v085/`.\n\n'
 text+='The accepted deliverable is a documented, reproducible research pipeline and a tested and rejected simple POC, with the full condor loop completed. Promotion to independent simulation or trading remains blocked until the corresponding data, settlement, funding and prospective gates pass. Keep unfavorable findings and the frozen rule; a version number is not evidence of improvement.\n'
 (FOLDER/'DESIGN_REPORT.md').write_text(text)
 current_design=dict(version='0.8.5',original_predeclared_experiment=json.loads((OUT/'experiment_contract.json').read_text()),scope_amendment=json.loads((OUT/'scope_amendment.json').read_text()),executed_scope=['SPXW condor full pipeline','SPXW put spread rejected at full baseline gate'],next_data_scope=['SPX/SPXW','SPY','QQQ','IWM','TSLA','NVDA','AAPL','AMZN','MSFT','GLD','TLT'],next_context=['VIX','VIX9D'],next_data_requirement='QC-0DTE-OO-5M-20261026: 17-date pilot plus one-minute slot windows; no new acquisition authorized',engineering_pass=verify['engineering_pass'],production_ready=False)
 (FOLDER/'design_contract.json').write_text(json.dumps(current_design,indent=2)+'\n')
 chart(comparison)
 (FOLDER/'findings.json').write_text(json.dumps(dict(verification=verify,decisions=decisions),indent=2)+'\n')
 print('Composed report from completed evidence')
if __name__=='__main__':compose()
