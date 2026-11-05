from pathlib import Path
import textwrap, html, hashlib, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.backends.backend_pdf import PdfPages
P=Path(__file__).resolve().parent
plt.rcParams['font.family']='DejaVu Sans'
plt.rcParams['text.parse_math']=False
fig,ax=plt.subplots(figsize=(20,11));fig.patch.set_facecolor('#f4f7fc');ax.set(xlim=(0,20),ylim=(0,11));ax.axis('off')
ax.text(.35,10.45,'OPTIONS RESEARCH | SINGLE-TICKER BASELINES TO PORTFOLIOS',fontsize=21,weight='bold',color='#12233f')
ax.text(.35,10.02,'Draft 0.5 | Audio demo in QC -> annual count + cash audit -> entry-safe local research',fontsize=13,color='#516179')
colors=['#285ee8','#008b94','#c67a08','#7850b8','#16865d']
boxes=[('1  QC BASELINES','One ticker per baseline\nSPX demo; native expiry\nAt least 360 episodes / year\n$100k, 13 slots, wings 20pt\n\nActual orders, events, fees\nVersioned control records'),('2  WIDE PARQUET','One row per native episode\n3 QC fields; 5 daily in fixture\nMultiple feature timeframes\nVectors / matrices / groups\n\nKnown-at-entry values only\nScalable feature packs'),('3  LOCAL RESEARCH','AKQuant + shared metrics\nAI scans + Jupyter notebooks\n100k+ fields remain a target\nCAR/MDD and drawdown first\n\nRecord every trial + failure\nConditional vs funded replay'),('4  ROBUSTNESS','Frozen OOS + cost stress\nParameters / timeframes / MC\nSingle / multi-ticker portfolios\nShared capital / correlation\n\nAll / Passed / Failed records\nTODO: detailed SQX tests'),('5  FINAL QC + YOU','Frozen strategies + portfolios\nThorough QC backtest / audit\nFinal evidence report\n\nUser review and decision\nIncubation / paper / live\nOnly after final QC gate')]
for i,(title,body) in enumerate(boxes):
 x=.3+i*3.98
 ax.add_patch(FancyBboxPatch((x,5.4),3.65,4.05,boxstyle='round,pad=.02,rounding_size=.1',facecolor='white',edgecolor=colors[i],linewidth=1.5))
 ax.add_patch(FancyBboxPatch((x,8.72),3.65,.73,boxstyle='round,pad=.02,rounding_size=.08',facecolor=colors[i],edgecolor=colors[i]))
 ax.text(x+.18,9.08,title,fontsize=15,weight='bold',color='white',va='center')
 ax.text(x+.18,8.4,body,fontsize=12.5,va='top',linespacing=1.65,color='#25374d')
 if i<4:ax.add_patch(FancyArrowPatch((x+3.68,7.5),(x+3.96,7.5),arrowstyle='-|>',mutation_scale=20,color='#667b9f',lw=2))
ax.add_patch(FancyBboxPatch((.3,2.9),7.45,1.95,boxstyle='round,pad=.02',facecolor='#e8f4f4',edgecolor='#008b94'))
ax.text(.5,4.45,'DATA PROVIDERS | TARGETED DELIVERY',fontsize=13,weight='bold',color='#007078')
ax.text(.5,4.05,'Core: multi-timeframe PV / options / VIX\nMeasured sparse 5 / 15 / 30 / 60m; coverage flags\nScope: US now; market adapters for future CN',fontsize=12,va='top',linespacing=1.6,color='#25374d')
ax.add_patch(FancyArrowPatch((5.8,4.86),(5.8,5.35),arrowstyle='-|>',mutation_scale=18,color='#008b94',lw=2))
ax.add_patch(FancyBboxPatch((8.15,2.9),11.4,1.95,boxstyle='round,pad=.02',facecolor='#fff4df',edgecolor='#c67a08'))
ax.text(8.4,4.45,'DESIGN GATES | DETAILS FOLLOW MEASURED PROOF',fontsize=13,weight='bold',color='#986000')
ax.text(8.4,4.05,'Native episode accounting + annual counts before feature expansion\nIncomplete interval bars fail admission; changed mechanics need new paths.\nSmall component proof completed; provider/marked-risk/final QC gates remain.',fontsize=12,va='top',linespacing=1.6,color='#25374d')
ax.add_patch(FancyBboxPatch((.3,.6),19.25,1.65,boxstyle='round,pad=.02',facecolor='#12233f',edgecolor='#12233f'))
ax.text(.6,1.82,'GOVERNANCE ACROSS EVERY STAGE',fontsize=14,weight='bold',color='white')
ax.text(.6,1.35,'As-of timestamps  |  No future-bar inputs  |  Source + policy versions  |  Labels excluded from alpha inputs',fontsize=13,color='#d3e5ff')
ax.text(.6,.92,'Preserve failures  |  Honest OOS status  |  Marked-risk coverage  |  No automatic paper trading or deployment',fontsize=13,color='#d3e5ff')
fig.savefig(P/'design_graph.png',dpi=160,bbox_inches='tight',facecolor=fig.get_facecolor());fig.savefig(P/'design_graph.svg',bbox_inches='tight',facecolor=fig.get_facecolor())
baseline_fig=None
Q=(P/'../../results/qc_baseline_poc_20261023/full_v5_evidence').resolve()
if (Q/'audit.json').exists() and (Q/'strategy_equity.json').exists():
 import pandas as pd
 import matplotlib.dates as mdates
 audit=json.loads((Q/'audit.json').read_text())
 annual=pd.read_csv(Q/'annual.csv')
 points=json.loads((Q/'strategy_equity.json').read_text())['chart']['series']['Equity']['values']
 dates=pd.to_datetime([v[0] for v in points],unit='s',utc=True).tz_convert('America/New_York')
 closes=[float(v[-1])/1000 for v in points]
 baseline_fig,(left,right)=plt.subplots(1,2,figsize=(18,8),gridspec_kw={'width_ratios':[1.7,1]})
 baseline_fig.patch.set_facecolor('#f4f7fc')
 baseline_fig.suptitle('SPX AUDIO DEMO | QC MIDPOINT BASELINE',fontsize=22,weight='bold',color='#12233f',y=.97)
 left.plot(dates,closes,color='#285ee8',lw=1.3)
 left.axhline(100,color='#8292a8',ls='--',lw=1)
 left.set(title='Native account equity: sampled close marks',ylabel='USD thousands')
 left.xaxis.set_major_locator(mdates.YearLocator())
 left.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
 left.grid(axis='y',alpha=.2)
 stats=audit['qc_statistics']
 left.text(.02,.96,'End $'+format(float(stats['End Equity']),',.2f')+'  |  CAGR '+stats['Compounding Annual Return']+'\nQC engine MDD '+stats['Drawdown']+'; sampled chart is not the full marked path',transform=left.transAxes,va='top',fontsize=10,color='#12233f',bbox={'facecolor':'white','alpha':.85,'edgecolor':'none'})
 labels=[str(int(r.year))+('*' if r.partial_year else '') for r in annual.itertuples()]
 bars=right.bar(labels,annual.trades,color=['#80a0f2' if r.partial_year else '#285ee8' for r in annual.itertuples()])
 for bar,n in zip(bars,annual.trades):right.text(bar.get_x()+bar.get_width()/2,n+40,f'{n:,}',ha='center',fontsize=11)
 right.axhline(360,color='#c67a08',ls='--',label='Required: 360 per year')
 right.set(title='Audited whole four-leg episodes',ylabel='Completed episodes',ylim=(0,annual.trades.max()*1.18))
 right.legend(loc='upper left');right.grid(axis='y',alpha=.15)
 baseline_fig.text(.07,.105,'* Partial source years; counts are actual, not annualized. Overlapping intraday entries are dependent.',fontsize=10,color='#516179')
 baseline_fig.text(.07,.065,'SPXW 0DTE | 20-delta put / 8-delta call | 20-point wings | 13 slots | $100,000 | quote midpoint + 0.05 package slippage | native expiry',fontsize=10,color='#12233f')
 baseline_fig.text(.07,.025,'Quote/delta inputs and admission differ from the original demo; exact numerical parity remains open.',fontsize=10,color='#516179')
 baseline_fig.subplots_adjust(top=.85,bottom=.2,wspace=.25)
 baseline_fig.savefig(P/'baseline_evidence.png',dpi=150,bbox_inches='tight')
 baseline_fig.savefig(P/'baseline_evidence.svg',bbox_inches='tight')

text=(P/'DESIGN_REPORT.txt').read_text()
with PdfPages(P/'DESIGN_REPORT.pdf') as pdf:
 pdf.savefig(fig,bbox_inches='tight',facecolor=fig.get_facecolor())
 if baseline_fig is not None:pdf.savefig(baseline_fig,bbox_inches='tight',facecolor=baseline_fig.get_facecolor())
 lines=[]
 for line in text.splitlines():
  lines.extend(textwrap.wrap(line,width=88,replace_whitespace=False,drop_whitespace=True) or [''])
 for n,start in enumerate(range(0,len(lines),54),1):
  f=plt.figure(figsize=(8.27,11.69));f.patch.set_facecolor('white')
  f.text(.075,.96,'OPTIONS RESEARCH SYSTEM  |  OVERALL DESIGN 0.5',fontsize=10,color='#285ee8',weight='bold')
  f.text(.075,.925,'\n'.join(lines[start:start+54]),fontsize=9.1,family='DejaVu Sans Mono',va='top',linespacing=1.45)
  f.text(.075,.035,'23 October 2026  •  Proposed design — original baseline preserved',fontsize=8,color='#516179')
  f.text(.91,.035,str(n),fontsize=8,ha='right');pdf.savefig(f);plt.close(f)
plt.close(fig)
if baseline_fig is not None:plt.close(baseline_fig)
(P/'DESIGN_REPORT.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Options research design</title><style>body{max-width:1200px;margin:36px auto;padding:0 24px;font:16px/1.6 system-ui;color:#12233f}img{width:100%}pre{white-space:pre-wrap;font:15px/1.6 system-ui}a{color:#285ee8}</style><h1>Options research system</h1><p>Single-ticker baselines · AKQuant research · portfolio validation · human release gate</p><img src="design_graph.svg" alt="Five-stage research architecture"><pre>'+html.escape(text)+'</pre>'+('<img src="baseline_evidence.svg" alt="Audited QC baseline and annual count gate">' if baseline_fig is not None else '')+'</html>')
files=['DESIGN_REPORT.txt','COMMENT_RESOLUTION.txt','DESIGN_REPORT.pdf','DESIGN_REPORT.html','design_graph.svg','design_graph.png','POC_REPORT.txt','mini_poc.py','build_revision.py','render_design.py','DEMO_STRATEGY_EXTRACTION.txt','../../poc/optionomega_demo.py','../../poc/collect_demo.py','../../poc/test_demo_audit.py','../../poc/README.md','../../poc/record_campaign.py','../../results/qc_baseline_poc_20261023/full_v5_manifest.json','../../results/qc_baseline_poc_20261023/smoke_v3_evidence/audit.json','../../results/qc_baseline_poc_20261023/smoke_v5_evidence/audit.json','../../poc/SOURCE_CONTRACT.txt','../../results/qc_baseline_poc_20261023/smoke_v5_raw_evidence/audit.json']
if (P/'../../results/qc_baseline_poc_20261023/full_v5_evidence/audit.json').exists():
 files.append('../../results/qc_baseline_poc_20261023/full_v5_evidence/audit.json')
if baseline_fig is not None:files.extend(['baseline_evidence.png','baseline_evidence.svg'])
(P/'manifest.json').write_text(json.dumps({'design_version':'0.5-measured-review','date':'2026-10-23','frozen_strategy_code_changed':False,'new_qc_poc_code_added':True,'cloud_jobs_submitted':True,'files':{n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in files}},indent=2)+'\n')
print('Created:',', '.join(files))
