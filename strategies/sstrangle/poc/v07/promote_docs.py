"""Publish only the audited Draft 0.7, keeping older revisions as controls."""
import json
import pandas as pd
from optimize import ROOT,OUT
assert json.loads((OUT/'final_verification.json').read_text())['status']=='passed'
f=pd.read_csv(OUT/'final_comparison.csv');native=f[f.stage=='final_qc']
summary='; '.join(f"{r.strategy}: {r.trades:,} trades, ${r.net_pnl:,.2f} net, {r.native_mdd:.1%} native MDD, {r.calmar:.3f} Calmar, minimum {r.min_annual:.0f}/year" for r in native.itertuples())
block='''## Current focus: Draft 0.7

[Draft 0.7 design and findings](../strategies/sstrangle/research/design_20261024_v7/DESIGN_REPORT.pdf) · [text](../strategies/sstrangle/research/design_20261024_v7/DESIGN_REPORT.txt) · [verification](../strategies/sstrangle/results/qc_final_poc_20261024/final_verification.json).

The missing funded QC stage is complete for all three frozen local alpha candidates. All three baseline tapes reproduce locally at episode/account level; a fresh full unfiltered condor reproduces the original 7,753 trades and $138,586.34 net exactly. Local reproduction uses native observations, not independent option quotes or a cloned native margin engine.

Final funded results: '''+summary+'''. Each passes at least 360 completed trades in every included year (2022 and 2026 partial). [Baseline/local/final comparison](../strategies/sstrangle/results/qc_final_poc_20261024/final_comparison.csv) · [Annual counts](../strategies/sstrangle/results/qc_final_poc_20261024/final_annual.csv).

Search: 144 eligible daily price/volume features, 864 rules per strategy, training 2022–2023 cash Calmar, full-period count feasibility >=400, immutable selection before native results. Selected rules use prior GLD range, IWM volume z-score and QQQ range. Common native/local trades match contracts and P&L; changed entries must reconcile to actual native buying-power messages. Engineering verification does not imply economic improvement. All periods remain development evidence; original Option Omega trade-level parity and fresh prospective evaluation remain unresolved.

'''
p=ROOT/'docs/CURRENT_WORK.md';s=p.read_text()
if '## Current focus: Draft 0.7' not in s:s=s.replace('## Current focus: Draft 0.65',block+'## Previous Draft 0.65 evidence',1);p.write_text(s)
for rel,prefix in [('README.md','strategies/sstrangle/'),('docs/README.md','../strategies/sstrangle/'),('strategies/sstrangle/README.md',''),('strategies/sstrangle/poc/README.md','../')]:
 p=ROOT/rel;s=p.read_text();new=f'Current revision: **[Draft 0.7]({prefix}research/design_20261024_v7/DESIGN_REPORT.pdf)** — baseline reproduction, frozen local optimization and final funded QC validation of all three candidates. [Evidence]({prefix}results/qc_final_poc_20261024/final_verification.json). Performance conclusions are distinct from engineering verification.'
 lines=s.splitlines();lines=[new if x.startswith('Current revision:') else x for x in lines];p.write_text('\n'.join(lines)+'\n')
p=ROOT/'docs/TODO.md';s=p.read_text();note='''
## Draft 0.7 completed and remaining (2026-10-24)

Completed: independent baseline payoff arithmetic, fresh unfiltered condor control, 2,592-rule local search, frozen feature inputs/predicates, three final funded QC candidates, annual >=360 gate, exact common-trade parity and native funding attribution. See [audited report](../strategies/sstrangle/research/design_20261024_v7/DESIGN_REPORT.pdf).

Remaining: exact Option Omega trade export/config parity, independently sourced option paths and official settlement verification, certified historical feature availability, full unfilled-opportunity local simulator, and fresh prospective evaluation. Older entries below describe historical gaps; the three Draft 0.7 candidates now have final funded QC verification.
'''
if '## Draft 0.7 completed' not in s:s=s.replace('\n','\n'+note,1);p.write_text(s)
print(summary)
