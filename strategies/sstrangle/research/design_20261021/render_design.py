from pathlib import Path
import textwrap, html, hashlib, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.backends.backend_pdf import PdfPages
P=Path(__file__).resolve().parent
plt.rcParams['font.family']='DejaVu Sans'
fig,ax=plt.subplots(figsize=(20,11));fig.patch.set_facecolor('#f4f7fc');ax.set(xlim=(0,20),ylim=(0,11));ax.axis('off')
ax.text(.35,10.45,'OPTIONS RESEARCH | MINUTE DECISIONS, COMPACT DATA',fontsize=24,weight='bold',color='#12233f')
ax.text(.35,10.02,'QC supplies mechanical trade paths. Local research learns entry filters. You control the final release.',fontsize=13,color='#516179')
colors=['#285ee8','#008b94','#c67a08','#7850b8','#16865d']
boxes=[('1  QC BASELINES','Tom strategy templates\nSimple, versioned mechanics\nTop 50 primary / top 100 test\nCompleted 1-minute decisions\n\nExport actual orders, fills,\nfees and account results'),('2  ENRICH TRADES','Reconcile cash + contracts\nJoin features known at entry\nPV + options + VIX regimes\nMinute and daily sidecars\n\nOne logical trade per row\nParquet + DuckDB'),('3  LOCAL ALPHAS','BRAIN-style field registry\nSingle-factor bins and shapes\nTrain-only rules / thresholds\nFixed-path trade filtering\n\nKeep exits / rolls unchanged\nRecord every trial + failure'),('4  VALIDATE','Frozen OOS / walk-forward\nSQX-style All / Passed banks\nCosts + parameter stability\nBlock Monte Carlo / portfolio\n\nFrozen finalists back to QC\nFresh minute portfolio test'),('5  YOUR DECISION','Report + reproducible bundle\nConditional vs funded results\nHuman-reserved Extra OOS\nExplicit review and approval\n\nReject / revise / paper / live\nQC incubation only if chosen')]
for i,(title,body) in enumerate(boxes):
 x=.3+i*3.98
 ax.add_patch(FancyBboxPatch((x,5.4),3.65,4.05,boxstyle='round,pad=.02,rounding_size=.1',facecolor='white',edgecolor=colors[i],linewidth=1.5))
 ax.add_patch(FancyBboxPatch((x,8.72),3.65,.73,boxstyle='round,pad=.02,rounding_size=.08',facecolor=colors[i],edgecolor=colors[i]))
 ax.text(x+.18,9.08,title,fontsize=15,weight='bold',color='white',va='center')
 ax.text(x+.18,8.4,body,fontsize=12.5,va='top',linespacing=1.65,color='#25374d')
 if i<4:ax.add_patch(FancyArrowPatch((x+3.68,7.5),(x+3.96,7.5),arrowstyle='-|>',mutation_scale=20,color='#667b9f',lw=2))
ax.add_patch(FancyBboxPatch((.3,2.9),7.45,1.95,boxstyle='round,pad=.02',facecolor='#e8f4f4',edgecolor='#008b94'))
ax.text(.5,4.45,'DATA PROVIDERS | TARGETED DELIVERY',fontsize=13,weight='bold',color='#007078')
ax.text(.5,4.05,'Core: minute PV + lagged daily / option / VIX features\nNext: held-contract minute marks for risk and reconciliation\nExpand: nearby contracts only for changed entry / exit / roll tests',fontsize=12,va='top',linespacing=1.6,color='#25374d')
ax.add_patch(FancyArrowPatch((5.8,4.86),(5.8,5.35),arrowstyle='-|>',mutation_scale=18,color='#008b94',lw=2))
ax.add_patch(FancyBboxPatch((8.15,2.9),11.4,1.95,boxstyle='round,pad=.02',facecolor='#fff4df',edgecolor='#c67a08'))
ax.text(8.4,4.45,'RESEARCH BOUNDARY | FILTER A PATH OR GENERATE A NEW ONE',fontsize=13,weight='bold',color='#986000')
ax.text(8.4,4.05,'Entry filters: reuse recorded trade paths for fast conditional research.\nNew timing, stops, rolls, replacements: regenerate in QC or targeted local simulation.\nEvery finalist: fresh QC run to recalculate sizing, capital and later opportunities.',fontsize=12,va='top',linespacing=1.6,color='#25374d')
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
  lines.extend(textwrap.wrap(line,width=94,replace_whitespace=False,drop_whitespace=True) or [''])
 for n,start in enumerate(range(0,len(lines),58),1):
  f=plt.figure(figsize=(8.27,11.69));f.patch.set_facecolor('white')
  f.text(.075,.96,'OPTIONS RESEARCH SYSTEM  |  DESIGN v2',fontsize=10,color='#285ee8',weight='bold')
  f.text(.075,.925,'\n'.join(lines[start:start+58]),fontsize=9.1,family='DejaVu Sans Mono',va='top',linespacing=1.45)
  f.text(.075,.035,'21 October 2026  •  Proposed design — original baseline preserved',fontsize=8,color='#516179')
  f.text(.91,.035,str(n),fontsize=8,ha='right');pdf.savefig(f);plt.close(f)
plt.close(fig)
(P/'DESIGN_REPORT.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Options research design</title><style>body{max-width:1200px;margin:36px auto;padding:0 24px;font:16px/1.6 system-ui;color:#12233f}img{width:100%}pre{white-space:pre-wrap;font:15px/1.6 system-ui}a{color:#285ee8}</style><h1>Options research system</h1><p>Minute decisions · compact trade research · human release gate</p><img src="design_graph.svg" alt="Five-stage research architecture"><pre>'+html.escape(text)+'</pre></html>')
files=['DESIGN_REPORT.txt','DESIGN_REPORT.pdf','DESIGN_REPORT.html','design_graph.svg','design_graph.png']
(P/'manifest.json').write_text(json.dumps({'design_version':2,'date':'2026-10-21','strategy_code_changed':False,'cloud_jobs_submitted':False,'files':{n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in files}},indent=2)+'\n')
print('Created:',', '.join(files))
