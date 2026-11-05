"""Standalone scientific figures, readable PDF, and HTML for the audited revision."""
from pathlib import Path
import html,hashlib,json,textwrap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
import pandas as pd
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
BASE=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023'
findings=json.loads((BASE/'analysis/findings.json').read_text())
comparison=pd.read_csv(BASE/'analysis/comparison.csv');annual=pd.read_csv(BASE/'analysis/annual.csv')
plt.rcParams.update({'font.family':'DejaVu Sans','text.parse_math':False,'axes.spines.top':False,'axes.spines.right':False})
colors={'condor_v05':'#8391a6','condor':'#285ee8','strangle':'#b74a62','put':'#008b83'}
labels={'condor_v05':'Condor 0.5 control ($100k)','condor':'Condor 0.6 ($100k)','strangle':'16-delta strangle ($2m)','put':'25-delta put ($2m)'}
figures=[]
def save(fig,name):
 fig.savefig(P/(name+'.png'),dpi=150,bbox_inches='tight');fig.savefig(P/(name+'.svg'),bbox_inches='tight');figures.append((fig,name))

fig,ax=plt.subplots(figsize=(16,10));fig.patch.set_facecolor('#f4f7fc');ax.axis('off')
ax.text(.03,.94,'DRAFT 0.6 | THREE NATIVE QC BASELINES',fontsize=25,weight='bold',color='#12233f',transform=ax.transAxes)
ax.text(.03,.88,'SPXW 0DTE | 16 May 2022–13 July 2026 | 13 daily slots, with early closes respected',fontsize=13,color='#516179',transform=ax.transAxes)
rows=[]
for key in ['condor','strangle','put']:
 r=comparison.set_index('strategy').loc[key]
 rows.append([labels[key],f'{r.episodes:,}',f'${r.net_pnl:,.0f}',f'{r.cagr:.2%}',f'{r.native_mdd:.1%}',f'{r.calmar:.3f}'])
table=ax.table(cellText=rows,colLabels=['Funded baseline','Episodes','Net P&L','CAGR','QC MDD','Calmar'],colWidths=[.31,.13,.17,.13,.13,.13],bbox=[.03,.59,.94,.23],cellLoc='center')
table.auto_set_font_size(False);table.set_fontsize(13)
for (i,j),cell in table.get_celld().items():
 cell.set_edgecolor('#d6deec');cell.set_facecolor('#12233f' if i==0 else 'white')
 if i==0:cell.set_text_props(color='white',weight='bold')
d=findings['wing_diagnosis']
notes=[f"COVERAGE  All three exceed 360 completed whole episodes in every included year. 2022 and 2026 are partial.",
 f"WING FIX  9,841 → {d['new_count']:,} condors: {d['gap_closed_fraction']:.1%} of the gap to 13,492 closed; {d['new_gap']:,} remain.",
 "FIDELITY  Exact wings and quote gates stay fixed; deltas can shift. Count parity improves, but P&L parity does not.",
 "RISK  Naked examples were funded at $2m. None meets Calmar >2; no untouched OOS claim.",
 "ENGINEERING  Explicit European expiry, half-day admission, native 4/2/1-leg audits, complete failure ledger.",
 "NEXT  Source export comparison, delta-tolerance tests, native margin groups, provider features and chronological validation."]
for i,note in enumerate(notes):ax.text(.03,.50-i*.065,note,fontsize=12,color='#25374d',transform=ax.transAxes,va='top')
ax.text(.03,.06,'Tom examples are user-authorized 0DTE adaptations; the saved Tom source describes a 45-DTE short put.',fontsize=11,color='#516179',transform=ax.transAxes)
save(fig,'executive_summary')

fig,ax=plt.subplots(figsize=(16,8));fig.patch.set_facecolor('#f4f7fc');ax.axis('off');ax.set(xlim=(0,16),ylim=(0,8))
ax.text(.3,7.5,'OPTIONS RESEARCH | DRAFT 0.6',fontsize=23,weight='bold',color='#12233f')
ax.text(.3,7.05,'Three native QC baselines -> admission + funding + accounting -> research -> final QC',fontsize=12,color='#516179')
boxes=[('1. BASELINE LAB','Audio iron condor\nTom-inspired strangle / put\nNative orders + expiry\nExplicit capital and calendar'),('2. ADMISSION AUDIT','Missing wing reason funnel\nFeasible exact-width pairs\n>=360 whole trades / year\nNative fees / cash / residuals'),('3. RESEARCH TABLE','Entry-known metadata\nFeature packs + labels apart\nDaily clusters / tails\nAKQuant + Jupyter / API'),('4. VALIDATION','Frozen chronological tests\nCosts / parameter stress\nShared-capital portfolios\nFinal QC + user decision')]
for i,(title,body) in enumerate(boxes):
 x=.3+i*4
 ax.add_patch(FancyBboxPatch((x,3.35),3.55,2.9,boxstyle='round,pad=.02',facecolor='white',edgecolor='#285ee8'))
 ax.text(x+.18,5.9,title,fontsize=13,weight='bold',color='#285ee8')
 ax.text(x+.18,5.4,body,fontsize=11.5,va='top',linespacing=1.8,color='#25374d')
 if i<3:ax.add_patch(FancyArrowPatch((x+3.6,4.8),(x+3.95,4.8),arrowstyle='-|>',mutation_scale=18,color='#516179'))
ax.add_patch(FancyBboxPatch((.3,.65),15.5,2.1,boxstyle='round,pad=.02',facecolor='#12233f',edgecolor='#12233f'))
ax.text(.6,2.3,'NEW DESIGN REQUIREMENTS FROM ACTUAL FAILURES',fontsize=14,weight='bold',color='white')
ax.text(.6,1.85,'Quote admission is part of the strategy.  Capital changes frequency.  European expiry and half-days need explicit models.',fontsize=11.5,color='#d3e5ff')
ax.text(.6,1.35,'Native 4 / 2 / 1-leg episode audit  |  Preserve failures and source hashes  |  Separate coverage from performance',fontsize=11.5,color='#d3e5ff')
ax.text(.6,.9,'Current scope: measured SPX PoC.  Provider panel, full feature engine, independent OOS and shared-capital portfolio remain next.',fontsize=11,color='#d3e5ff')
save(fig,'design_graph')

fig,(left,right)=plt.subplots(1,2,figsize=(16,7),gridspec_kw={'width_ratios':[1.8,1]});fig.suptitle('FUNDED NATIVE QC ACCOUNTS | SOURCE PERIOD',fontsize=19,weight='bold',color='#12233f')
paths={'condor_v05':ROOT/'strategies/sstrangle/results/qc_baseline_poc_20261023/full_v5_evidence',**{k:BASE/(v+'_evidence') for k,v in [('condor','condor_full_v1'),('strangle','strangle_full_v2'),('put','put_full_v3')]}}
native_curves=all((folder/'strategy_equity.json').exists() for folder in paths.values())
curve_title='Sampled native account close marks; start = 100' if native_curves else 'Daily settled equity from audited cash; initial = 100'
for key,folder in paths.items():
 initial=float(comparison.loc[comparison.strategy==key,'capital'].iloc[0])
 if native_curves:
  points=json.loads((folder/'strategy_equity.json').read_text())['chart']['series']['Equity']['values']
  dates=pd.to_datetime([v[0] for v in points],unit='s',utc=True).tz_convert('America/New_York')
  values=[100*float(v[-1])/initial for v in points]
 else:
  daily=pd.read_csv(BASE/'analysis/daily_pnl.csv',index_col='day')[key]
  dates=pd.to_datetime([str(d)+' 16:00' for d in daily.index]).tz_localize('America/New_York')
  dates=dates.insert(0,pd.Timestamp('2022-05-16 09:30',tz='America/New_York'))
  values=[100,*((initial+daily.cumsum())/initial*100).tolist()]
 left.plot(dates,values,lw=1.2,color=colors[key],label=labels[key])
(P/'chart_basis.json').write_text(json.dumps({'basis':'native sampled account chart' if native_curves else 'Cumulative audited native expiry cash by day, with opening costs; excludes intraday unrealized marks','mdd_source':'QC standard native Drawdown statistic; not recalculated from plotted curves'},indent=2)+'\n')
left.set(title=curve_title,ylabel='Equity / initial capital x 100');left.grid(axis='y',alpha=.2);left.legend(fontsize=9);left.xaxis.set_major_locator(mdates.YearLocator());left.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
selected=comparison.set_index('strategy').loc[['condor_v05','condor','strangle','put']]
right.barh(range(4),selected.native_mdd*100,color=[colors[k] for k in selected.index]);right.set_yticks(range(4),['Condor 0.5','Condor 0.6','Strangle','Put']);right.invert_yaxis();right.set(title='QC engine marked maximum drawdown',xlabel='Drawdown (%)')
for i,v in enumerate(selected.native_mdd):right.text(v*100+.4,i,f'{v:.1%}',va='center',fontsize=10)
right.set_xlim(0,max(selected.native_mdd)*115);right.grid(axis='x',alpha=.15)
fig.text(.07,.035,'Separate funded accounts. Larger naked-strategy capital reduces percentage risk. Curves omit intraday extremes; MDD comes from QC.',fontsize=10,color='#516179')
fig.subplots_adjust(bottom=.14,top=.86,wspace=.3);save(fig,'account_comparison')

fig,ax=plt.subplots(figsize=(15,7));fig.suptitle('ACTUAL WHOLE EPISODES PER YEAR | REQUIRED >=360',fontsize=19,weight='bold',color='#12233f')
years=sorted(annual.year.unique());width=.2
for i,key in enumerate(['condor_v05','condor','strangle','put']):
 data=annual[annual.strategy==key].set_index('year').loc[years]
 bars=ax.bar([j+(i-1.5)*width for j in range(len(years))],data.trades,width=width,color=colors[key],label=labels[key])
 for b,n in zip(bars,data.trades):ax.text(b.get_x()+b.get_width()/2,n+35,f'{n:,}',ha='center',va='bottom',fontsize=8,rotation=90)
ax.axhline(360,color='#b87914',ls='--',lw=1.6);ax.set_xticks(range(len(years)),[str(y)+('*' if y in [2022,2026] else '') for y in years]);ax.set(ylabel='Completed episodes',ylim=(0,annual.trades.max()*1.2));ax.legend(fontsize=10,loc='upper left');ax.grid(axis='y',alpha=.15)
fig.text(.08,.025,'* Partial source years. Counts are actual, not annualized. Overlapping intraday trades are dependent observations.',fontsize=10,color='#516179');fig.subplots_adjust(bottom=.12,top=.88);save(fig,'annual_counts')

reasons=findings['wing_diagnosis']['reasons'];combined={k.removeprefix('wing_reason_'):v for k,v in reasons.items() if k.startswith('wing_reason_')};combined=dict(sorted(combined.items(),key=lambda kv:kv[1],reverse=True))
fig,(left,right)=plt.subplots(1,2,figsize=(16,8),gridspec_kw={'width_ratios':[1.5,1]});fig.suptitle('WHY THE ORIGINAL WING POLICY SKIPPED SLOTS',fontsize=19,weight='bold',color='#12233f')
left.barh(list(combined),list(combined.values()),color='#285ee8');left.invert_yaxis();left.set(xlabel='Skipped scheduled slots (mutually exclusive reasons)');left.tick_params(axis='y',labelsize=9)
for i,v in enumerate(combined.values()):left.text(v+max(combined.values())*.01,i,str(v),va='center',fontsize=9)
left.set_xlim(0,max(combined.values())*1.15);left.grid(axis='x',alpha=.15)
d=findings['wing_diagnosis'];vals=[d['old_count'],d['new_count'],d['source_trade_count']];bars=right.bar(['QC 0.5','QC 0.6','OO display'],vals,color=['#8391a6','#285ee8','#b87914'])
for b,n in zip(bars,vals):right.text(b.get_x()+b.get_width()/2,n+100,f'{n:,}',ha='center',fontsize=11)
right.set(title='Closer count does not establish exact parity',ylabel='Whole episodes / displayed source trades',ylim=(0,max(vals)*1.15));right.grid(axis='y',alpha=.15)
fig.text(.08,.025,'Exact 20-point width and original quote checks retained. Recovery changes feasible short-strike selection; final native margin still applies.',fontsize=10,color='#516179');fig.subplots_adjust(left=.23,right=.97,wspace=.45,bottom=.12,top=.87);save(fig,'wing_diagnosis')

text=(P/'DESIGN_REPORT.txt').read_text()
with PdfPages(P/'DESIGN_REPORT.pdf') as pdf:
 for fig,name in figures:pdf.savefig(fig,bbox_inches='tight')
 lines=[]
 for line in text.splitlines():lines.extend(textwrap.wrap(line,width=91,replace_whitespace=False,drop_whitespace=True) or [''])
 for number,start in enumerate(range(0,len(lines),54),1):
  f=plt.figure(figsize=(8.27,11.69));f.text(.07,.96,'OPTIONS RESEARCH | DRAFT 0.6 | NATIVE QC EVIDENCE',fontsize=10,weight='bold',color='#285ee8')
  f.text(.07,.925,'\n'.join(lines[start:start+54]),fontsize=8.6,family='DejaVu Sans Mono',va='top',linespacing=1.5)
  f.text(.07,.035,'23 October 2026 | Review draft; all attempts preserved',fontsize=8,color='#516179');f.text(.93,.035,str(number),ha='right',fontsize=8);pdf.savefig(f);plt.close(f)
for fig,name in figures:plt.close(fig)
images=''.join(f'<img src="{name}.svg" alt="{name.replace("_"," ")}">' for _,name in figures)
(P/'DESIGN_REPORT.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Options research — Draft 0.6</title><style>body{max-width:1250px;margin:32px auto;padding:0 24px;font:16px/1.6 system-ui;color:#12233f}img{width:100%;margin:20px 0}pre{white-space:pre-wrap;font:15px/1.6 system-ui}</style><h1>Options research — Draft 0.6</h1>'+images+'<pre>'+html.escape(text)+'</pre></html>')
files=[p for p in P.iterdir() if p.is_file() and p.name!='manifest.json']
manifest={'design_version':'0.6','files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'evidence':str(BASE/'analysis/findings.json')}
(P/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(P/'DESIGN_REPORT.pdf')
