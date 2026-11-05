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
ax.text(.35,10.02,'Draft 0.4 | Overall design -> detail design -> measured PoC -> review -> 1.0.0',fontsize=13,color='#516179')
colors=['#285ee8','#008b94','#c67a08','#7850b8','#16865d']
boxes=[('1  QC BASELINES','One ticker per baseline\nAudio demo + Tom templates\nBroad, simple trade samples\nDelta / exit variants\n\nActual orders, events, fees\nVersioned control records'),('2  WIDE PARQUET','All trade info + features\nPV / options / Brain formulas\nMultiple feature timeframes\nVectors / matrices / groups\n\nKnown-at-entry values only\nScalable feature packs'),('3  LOCAL RESEARCH','AKQuant + shared metrics\nAI scans + Jupyter notebooks\nTarget: 100k+ candidates\nCAR/MDD and drawdown first\n\nRecord every trial + failure\nConditional vs funded replay'),('4  ROBUSTNESS','Frozen OOS + cost stress\nParameters / timeframes / MC\nSingle / multi-ticker portfolios\nShared capital / correlation\n\nAll / Passed / Failed records\nTODO: detailed SQX tests'),('5  FINAL QC + YOU','Frozen strategies + portfolios\nThorough QC backtest / audit\nFinal evidence report\n\nUser review and decision\nIncubation / paper / live\nOnly after final QC gate')]
for i,(title,body) in enumerate(boxes):
 x=.3+i*3.98
 ax.add_patch(FancyBboxPatch((x,5.4),3.65,4.05,boxstyle='round,pad=.02,rounding_size=.1',facecolor='white',edgecolor=colors[i],linewidth=1.5))
 ax.add_patch(FancyBboxPatch((x,8.72),3.65,.73,boxstyle='round,pad=.02,rounding_size=.08',facecolor=colors[i],edgecolor=colors[i]))
 ax.text(x+.18,9.08,title,fontsize=15,weight='bold',color='white',va='center')
 ax.text(x+.18,8.4,body,fontsize=12.5,va='top',linespacing=1.65,color='#25374d')
 if i<4:ax.add_patch(FancyArrowPatch((x+3.68,7.5),(x+3.96,7.5),arrowstyle='-|>',mutation_scale=20,color='#667b9f',lw=2))
ax.add_patch(FancyBboxPatch((.3,2.9),7.45,1.95,boxstyle='round,pad=.02',facecolor='#e8f4f4',edgecolor='#008b94'))
ax.text(.5,4.45,'DATA PROVIDERS | TARGETED DELIVERY',fontsize=13,weight='bold',color='#007078')
ax.text(.5,4.05,'Core: multi-timeframe PV / options / VIX\nBenchmark: 5m / 15m / 30m / 1h; RAM / CPU / disk\nScope: US now; market adapters for future CN',fontsize=12,va='top',linespacing=1.6,color='#25374d')
ax.add_patch(FancyArrowPatch((5.8,4.86),(5.8,5.35),arrowstyle='-|>',mutation_scale=18,color='#008b94',lw=2))
ax.add_patch(FancyBboxPatch((8.15,2.9),11.4,1.95,boxstyle='round,pad=.02',facecolor='#fff4df',edgecolor='#c67a08'))
ax.text(8.4,4.45,'DESIGN GATES | DETAILS FOLLOW MEASURED PROOF',fontsize=13,weight='bold',color='#986000')
ax.text(8.4,4.05,'TODO / Detail design / Ref / Decision / PoC / Acceptance / Data gap\nReuse trade paths for filters; regenerate changed trade mechanics.\nVersion 1.0.0 follows measured PoC, revised detail design and review.',fontsize=12,va='top',linespacing=1.6,color='#25374d')
ax.add_patch(FancyBboxPatch((.3,.6),19.25,1.65,boxstyle='round,pad=.02',facecolor='#12233f',edgecolor='#12233f'))
ax.text(.6,1.82,'GOVERNANCE ACROSS EVERY STAGE',fontsize=14,weight='bold',color='white')
ax.text(.6,1.35,'As-of timestamps  |  No future-bar inputs  |  Source + policy versions  |  Labels excluded from alpha inputs',fontsize=13,color='#d3e5ff')
ax.text(.6,.92,'Preserve failures  |  Honest OOS status  |  Marked-risk coverage  |  No automatic paper trading or deployment',fontsize=13,color='#d3e5ff')
fig.savefig(P/'design_graph.png',dpi=160,bbox_inches='tight',facecolor=fig.get_facecolor());fig.savefig(P/'design_graph.svg',bbox_inches='tight',facecolor=fig.get_facecolor())
text=(P/'DESIGN_REPORT.txt').read_text()
with PdfPages(P/'DESIGN_REPORT.pdf') as pdf:
 pdf.savefig(fig,bbox_inches='tight',facecolor=fig.get_facecolor())
 lines=[]
 for line in text.splitlines():
  lines.extend(textwrap.wrap(line,width=88,replace_whitespace=False,drop_whitespace=True) or [''])
 for n,start in enumerate(range(0,len(lines),54),1):
  f=plt.figure(figsize=(8.27,11.69));f.patch.set_facecolor('white')
  f.text(.075,.96,'OPTIONS RESEARCH SYSTEM  |  OVERALL DESIGN 0.4',fontsize=10,color='#285ee8',weight='bold')
  f.text(.075,.925,'\n'.join(lines[start:start+54]),fontsize=9.1,family='DejaVu Sans Mono',va='top',linespacing=1.45)
  f.text(.075,.035,'21 October 2026  •  Proposed design — original baseline preserved',fontsize=8,color='#516179')
  f.text(.91,.035,str(n),fontsize=8,ha='right');pdf.savefig(f);plt.close(f)
plt.close(fig)
(P/'DESIGN_REPORT.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Options research design</title><style>body{max-width:1200px;margin:36px auto;padding:0 24px;font:16px/1.6 system-ui;color:#12233f}img{width:100%}pre{white-space:pre-wrap;font:15px/1.6 system-ui}a{color:#285ee8}</style><h1>Options research system</h1><p>Single-ticker baselines · AKQuant research · portfolio validation · human release gate</p><img src="design_graph.svg" alt="Five-stage research architecture"><pre>'+html.escape(text)+'</pre></html>')
files=['DESIGN_REPORT.txt','COMMENT_RESOLUTION.txt','DESIGN_REPORT.pdf','DESIGN_REPORT.html','design_graph.svg','design_graph.png']
(P/'manifest.json').write_text(json.dumps({'design_version':'0.4-review','date':'2026-10-21','strategy_code_changed':False,'cloud_jobs_submitted':False,'files':{n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in files}},indent=2)+'\n')
print('Created:',', '.join(files))
