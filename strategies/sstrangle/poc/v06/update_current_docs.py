"""Promote the verified Draft 0.6 artifacts while retaining historical evidence."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[4]
B=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023'
r=json.loads((B/'analysis/findings.json').read_text())
assert (B/'final_verification.json').exists()
summaries={x['strategy']:x for x in r['summaries']}
d=r['wing_diagnosis']
lines=['Review **[overall design Draft 0.6](../strategies/sstrangle/research/design_20261023_v6/DESIGN_REPORT.pdf)**: three native QC baselines, the 3,606 wing-admission skips, and the revised research architecture. [Design text](../strategies/sstrangle/research/design_20261023_v6/DESIGN_REPORT.txt) · [diagram](../strategies/sstrangle/research/design_20261023_v6/design_graph.svg) · [verified evidence](../strategies/sstrangle/results/qc_three_demo_poc_20261023/final_verification.json).','',
'Source interval **2022-05-16–2026-07-13**, SPXW 0DTE. All three pass **>=360 completed whole episodes in every included year**; 2022 and 2026 are partial actual counts. Tom-inspired 16-delta strangle and 25-delta put are user-authorized 0DTE adaptations, not reproductions of the saved 45-DTE source.','',
'| Baseline | Episodes | Capital | Net P&L | CAGR | Native MDD | Calmar |','|---|---:|---:|---:|---:|---:|---:|']
for k in ['condor','strangle','put']:
 x=summaries[k];lines.append(f"| {k} | {x['episodes']:,} | ${x['capital']:,.0f} | ${x['net_pnl']:,.2f} | {x['cagr']:.3%} | {x['native_mdd']:.1%} | {x['calmar']:.3f} |")
lines += ['',f"Condor coverage increased from 9,841 to {d['new_count']:,}, closing {d['gap_closed_fraction']:.1%} of the gap to 13,492. Exact-width feasible-pair search retains the original quote gates but can materially change delta exposure. A separate no-order diagnostic recovers the complete original 3,606 skip breakdown. Source contract/fill parity remains unverified.",'',
'Native 4/2/1-leg orders, expiry cash, fees and zero residuals reconcile. The condor sampled minimum margin remaining was negative; completion does not prove continuously positive buying power. Separate $2m naked accounts must not be compared with the $100k condor without acknowledging capital. No result is untouched OOS or a shared-capital portfolio.','',
'[Annual counts](../strategies/sstrangle/results/qc_three_demo_poc_20261023/analysis/annual.csv) · [trial ledger, including failures](../strategies/sstrangle/results/qc_three_demo_poc_20261023/trial_ledger.json) · [implementation](../strategies/sstrangle/poc/v06/README.md). The [Draft 0.5 control](../strategies/sstrangle/research/design_20261023_v5/DESIGN_REPORT.pdf) remains frozen.','',
'The proposed workflow is:','',
'**Single-ticker QC baseline → genuine orders and opportunity audit → native accounting + entry-safe features → Parquet/DuckDB research → AKQuant simulation + robustness → funded final QC individual/portfolio validation → user decision.**','',
'Full provider coverage, 100,000+ feature expressions, independent option paths, chronological validation and shared-capital portfolios remain future deliverables. Existing local fixtures are not a delivered SPX feature platform.','']
p=ROOT/'docs/CURRENT_WORK.md';s=p.read_text();a=s.index('## Current focus');b=s.index('## What is actually completed',a);s=s[:a]+'## Current focus\n\n'+'\n'.join(lines)+'\n'+s[b:];s=s.replace('Draft 0.5 needs a consolidated provider contract','Draft 0.6 needs a consolidated provider contract');p.write_text(s)
for name in ['README.md','docs/README.md','docs/TODO.md','strategies/sstrangle/README.md']:
 p=ROOT/name;s=p.read_text().replace('overall design Draft 0.5','overall design Draft 0.6').replace('design — Draft 0.5','design — Draft 0.6').replace('Review Draft 0.5','Review Draft 0.6')
 s=s.replace('design_20261023_v5/DESIGN_REPORT.pdf','design_20261023_v6/DESIGN_REPORT.pdf').replace('design_20261023_v5/COMMENT_RESOLUTION.txt','design_20261023_v6/COMMENT_RESOLUTION.txt')
 if name=='README.md':s=s.replace('has completed the audio-demo QC baseline PoC','has completed three native QC baseline PoCs')
 if name=='strategies/sstrangle/README.md':
  start=s.find(' The native QC audio-demo PoC');end=s.find('\n',start)
  if start>=0:s=s[:start]+f" Three audited SPX baselines exceed 360 whole episodes in every included year. The revised condor has {d['new_count']:,} episodes; Draft 0.6 records admission recovery, naked-strategy funding, expiry/calendar fixes and source-parity limits."+s[end:]
  s=s.replace('- **Audio-demo QC PoC:**','- **Frozen Draft 0.5 audio-demo QC control:**')
  marker='## Results and implementation\n\n'
  if '**Draft 0.6 three-demo PoC:**' not in s:s=s.replace(marker,marker+'- **Draft 0.6 three-demo PoC:** [comparison](results/qc_three_demo_poc_20261023/analysis/comparison.csv) · [annual gate](results/qc_three_demo_poc_20261023/analysis/annual.csv) · [native audit verification](results/qc_three_demo_poc_20261023/final_verification.json) · [adapter](poc/v06/README.md).\n\n')
  s=s.replace('`research/design_20261023_v5/` | Current','`research/design_20261023_v6/` | Current')
 if name=='docs/TODO.md':
  s=s.replace('Audio-demo SPX baseline, then parameter neighborhoods','Three SPX baselines, then predeclared parameter neighborhoods')
  s=s.replace('- Diagnose the 3,606 rejected admissible-wing slots without substituting future or stale quotes; compare source quote/delta definitions and verify historical expiry fees from the original demo export.','- Draft 0.6 diagnoses the 3,606 wing skips and tests feasible exact-width recovery. Next: predeclare delta-tolerance sensitivities, resolve residual chain gaps, audit native margin groups, and compare source quote/delta definitions and historical expiry fees against the original demo export.')
  if '- Draft 0.6: all three full SPX baselines' not in s:s=s.replace('## Measured PoC evidence — 2026-10-23\n','## Measured PoC evidence — 2026-10-23\n\n- Draft 0.6: all three full SPX baselines pass the annual gate and native accounting. [Verified evidence](../strategies/sstrangle/results/qc_three_demo_poc_20261023/final_verification.json) · [findings](../strategies/sstrangle/research/design_20261023_v6/POC_REPORT.txt). Remaining work includes source parity, delta tolerances, margin portability, provider features and OOS validation.\n')
  s=s.replace('- Native QC full source-period baseline: 9,841','- Frozen Draft 0.5 control: 9,841')
 p.write_text(s)
print('Current documentation promoted to verified Draft 0.6')
