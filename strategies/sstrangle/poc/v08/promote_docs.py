"""Promote Draft 0.8 only after complete native and artifact verification."""
import json
import pandas as pd
from campaign import ROOT,OUT
assert json.loads((OUT/'final_verification.json').read_text())['status']=='passed'
f=pd.read_csv(OUT/'final_comparison.csv');findings=json.loads((OUT/'final_findings.json').read_text());native=f[f.stage=='final'];summary='; '.join(f"{r.strategy}: {r.trades:,} trades, ${r.net_pnl:,.2f} net, {r.native_mdd:.1%} native MDD, {r.calmar:.3f} Calmar, minimum {r.minimum_annual}/year" for r in native.itertuples())
block='''## Current focus: Draft 0.8

[Draft 0.8 design and findings](../strategies/sstrangle/research/design_20261024_v8/DESIGN_REPORT.pdf) · [text](../strategies/sstrangle/research/design_20261024_v8/DESIGN_REPORT.txt) · [verification](../strategies/sstrangle/results/qc_sizing_poc_20261024/final_verification.json).

Latest scope: all equity available, no Tom sizing limits; original $100k condor/$2m put, 20-point wings and one-lot execution remain. Full allocation is a ceiling, not forced full margin usage. No capital-increase or narrow-wing variant was run.

The 150-feature, 1,802-rule local search freezes choices using historical walk-forward validation with increased costs. Six native runs (two smokes, two matched Draft 0.7 controls, two new candidates) cover execution parity and the extended period through October 22, 2026. Legacy control trades reproduce Draft 0.7; all full native runs pass >=360 episodes in every included year.

Final candidates: '''+summary+'''. [Comparison](../strategies/sstrangle/results/qc_sizing_poc_20261024/final_comparison.csv) · [Robustness evidence](../strategies/sstrangle/results/qc_sizing_poc_20261024/robustness.json).

Robustness is not established: historical bootstrap intervals include zero, repeated-search diagnostics are weak, and adaptive annual reoptimization fails some yearly frequency gates. The fixed candidates are separate from that failed adaptive process. The reserved July14–October22 interval is a short held historical test, not prospective live evidence.

'''+ '\n\n'.join(k+': '+v['verdict'] for k,v in findings['decisions'].items())+'\n\n'
p=ROOT/'docs/CURRENT_WORK.md';s=p.read_text()
if '## Current focus: Draft 0.8' not in s:s=s.replace('## Current focus: Draft 0.7',block+'## Previous Draft 0.7 evidence',1);p.write_text(s)
for rel,prefix in [('README.md','strategies/sstrangle/'),('docs/README.md','../strategies/sstrangle/'),('strategies/sstrangle/README.md',''),('strategies/sstrangle/poc/README.md','../')]:
 p=ROOT/rel;s=p.read_text();new=f'Current revision: **[Draft 0.8]({prefix}research/design_20261024_v8/DESIGN_REPORT.pdf)** — full-equity ceiling, historical robustness tests, matched controls and final funded QC verification. [Evidence]({prefix}results/qc_sizing_poc_20261024/final_verification.json). Robust alpha is not established.';p.write_text('\n'.join(new if x.startswith('Current revision:') else x for x in s.splitlines())+'\n')
p=ROOT/'docs/TODO.md';s=p.read_text();note='''
## Draft 0.8 completed and remaining (2026-10-24)

Completed: full-equity scope with no Tom caps, 150-feature search, historical walk-forward/cost/threshold/tail/bootstrap diagnostics, frozen rules, matched extended-period native controls/candidates, and a reserved July14–October22 historical interval. All fixed full native runs pass the annual 360 gate. See [report](../strategies/sstrangle/research/design_20261024_v8/DESIGN_REPORT.pdf).

Remaining: robust alpha evidence and prospective validation, stable adaptive frequency control without retrospective selection, independent option-market/margin simulation, and exact Option Omega parity. Passing execution verification is not deployment approval. Tom sizing is deferred at the user's request.
'''
if '## Draft 0.8 completed' not in s:p.write_text(s.replace('\n','\n'+note,1))
print(summary)
