"""Promote only audited Draft 0.65; preserve the historical 0.6 evidence."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024'
assert json.loads((OUT/'final_verification.json').read_text())['status']=='passed'
a=json.loads((OUT/'analysis/findings.json').read_text());rows={r['key']:r for r in a['comparisons']};x=rows['condor_full_t02'];y=rows['condor_full_t05']
p=ROOT/'docs/CURRENT_WORK.md';s=p.read_text();s=s.replace('Updated: 2026-10-23.','Updated: 2026-10-24.')
start=s.index('## Current focus');s=s[:start]+f'''## Current focus: Draft 0.65

[Draft 0.65 design and findings](../strategies/sstrangle/research/design_20261024_v065/DESIGN_REPORT.pdf) · [text](../strategies/sstrangle/research/design_20261024_v065/DESIGN_REPORT.txt) · [verification](../strategies/sstrangle/results/qc_delta_poc_20261024/final_verification.json).

Native condor delta tolerances ±0.02 and ±0.05 completed {x['trades']:,} and {y['trades']:,} episodes, respectively; minimum annual counts {x['min_annual']:,} and {y['min_annual']:,}. Both pass >=360 in every included year. Native net P&L: ${x['pnl']:,.2f} and ${y['pnl']:,.2f}. Exact Option Omega parity remains unverified; tighter exposure trades off coverage.

Local PoC now has **211 fields / 144 eligible alpha candidates / 288 rules per baseline**, with pinned daily provider exports and strict as-of joins on all three 0.6 baselines and both tighter condors. The 20 broker-IV fields are sensitivity-only. Conditional filters do not recompute native funding; all periods are development evidence, not untouched OOS. [Local results](../strategies/sstrangle/results/qc_delta_poc_20261024/local/summary.json) · [feature registry](../strategies/sstrangle/results/qc_delta_poc_20261024/local/feature_registry.json) · [implementation](../strategies/sstrangle/poc/v065/README.md).

## Previous Draft 0.6 evidence

'''+s[start+len('## Current focus'):].lstrip()
s=s.replace('Full provider coverage, 100,000+ feature expressions, independent option paths, chronological validation and shared-capital portfolios remain future deliverables. Existing local fixtures are not a delivered SPX feature platform.','Full intraday/options provider coverage, 100,000+ feature expressions, independent option paths and shared-capital portfolios remain future deliverables. Draft 0.65 now supplies daily cross-market feature packs and retrospective chronological screening; it is not a complete feature platform.')
p.write_text(s)
for rel,prefix in [('README.md','strategies/sstrangle/'),('docs/README.md','../strategies/sstrangle/'),('strategies/sstrangle/README.md',''),('strategies/sstrangle/poc/README.md','../')]:
 p=ROOT/rel;s=p.read_text();lines=s.splitlines();block=f'\nCurrent revision: **[Draft 0.65]({prefix}research/design_20261024_v065/DESIGN_REPORT.pdf)** — native delta-tolerance tests with >=360 completed trades/year, P&L-gap attribution, and a 211-field local feature PoC. [Evidence]({prefix}results/qc_delta_poc_20261024/final_verification.json). Earlier reports below remain historical controls.\n'
 if 'Current revision: **[Draft 0.65]' not in s:lines.insert(1,block);p.write_text('\n'.join(lines)+'\n')
p=ROOT/'docs/TODO.md';s=p.read_text();block='''
## Draft 0.65 follow-up (2026-10-24)

Completed: two funded native delta-tolerance tests; annual 360 gate; local 211-field packs and 288-rule screens per baseline; later-period/cluster diagnostics. See [verified design](../strategies/sstrangle/research/design_20261024_v065/DESIGN_REPORT.pdf).

Remaining: original Option Omega trade CSV/config reconciliation; certified intraday/options feature availability; row-level unfilled opportunity ledger; native funded validation before promoting a local alpha; fresh prospective/untouched evaluation. Existing retrospective filters are not validated funded strategies.
'''
if '## Draft 0.65 follow-up' not in s:s=s.replace('\n','\n'+block,1);p.write_text(s)
