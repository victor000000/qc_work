"""Promote the measured research release while preserving historical sections."""
from campaign import ROOT,OUT
import json,re
import pandas as pd

def main():
 proof=json.loads((OUT/'final_verification.json').read_text());assert proof['engineering_pass'] and proof['frequency_pass']
 assert (ROOT/'strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.pdf').exists()
 before=OUT/'documentation_before';before.mkdir(exist_ok=True)
 paths=['README.md','docs/README.md','docs/CURRENT_WORK.md','docs/TODO.md','strategies/sstrangle/README.md']
 for name in paths:
  p=ROOT/name;snapshot=before/name.replace('/','__')
  if not snapshot.exists():snapshot.write_bytes(p.read_bytes())
 for name,prefix in [('README.md',''),('docs/README.md','../')]:
  p=ROOT/name;s=p.read_text();summary=f'Current revision: **[Version 0.8.5]({prefix}strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.pdf)** — completed condor QC baseline → bounded local research → funded QC verification; optional put-spread add-on rejected on a native margin call. [Evidence]({prefix}strategies/sstrangle/results/qc_poc_20261026_v085/final_verification.json). Research release; robust alpha and official-settlement parity are not established.'
  s=re.sub(r'Current revision:.*',lambda m:summary,s,count=1)
  if name=='README.md':
   s=s.replace('Current options research has completed three native QC baseline PoCs and is reviewing [overall design Draft 0.6](strategies/sstrangle/research/design_20261023_v6/DESIGN_REPORT.pdf) for the QC → local research → final QC pipeline. Completed baseline results and pending data/implementation work are summarized in Current work.','The latest [0DTE design and measured findings](strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.md) review Tom’s three/eleven strategies, the audio demo, new native runs and data-admission limits. Current work separates completed research from remaining independent replay and prospective validation.')
  else:s=s.replace('[Options research design — Draft 0.6](../strategies/sstrangle/research/design_20261023_v6/DESIGN_REPORT.pdf): the overall design for review.','[0DTE design — Version 0.8.5](../strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.pdf): completed pipeline, full design, measured findings and failed add-on.')
  p.write_text(s)
 p=ROOT/'docs/CURRENT_WORK.md';s=p.read_text();heading='## Current focus: Version 0.8.5 completed research pipeline'
 section='''## Current focus: Version 0.8.5 completed research pipeline

[Full design PDF](../strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.pdf) · [readable design](../strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.md) · [implementation](../strategies/sstrangle/poc/v085/README.md) · [verification](../strategies/sstrangle/results/qc_poc_20261026_v085/final_verification.json) · [comparison](../strategies/sstrangle/results/qc_poc_20261026_v085/final_comparison.csv).

Completed fresh condor QC baseline → 13-rule local search → frozen funded QC verification, over 2022-05-16–2026-10-22. Re-audited ten inherited accounts / 73,819 episodes; all 7,753 original-period condor control trades reproduce exactly. The fixed filter uses prior QQQ daily range >0.016380462988098386, thresholds fitted on unique baseline-filled 2022–2023 days, selection on 2024 only. Later counts and outcomes do not choose the rule.

Final candidate: **3,510 trades, $251,600.30 native net profit, 16.2% native MDD, 2.019 Calmar**, minimum 434 trades/year and $9,762.96 minimum sampled margin remaining. The 3,506 shared local/native episodes match contracts and profit exactly; four extra funded trades add $216.62 and have actual baseline buying-power rejection explanations. Baseline: 8,358 trades, $158,166.74, 38.2% MDD, negative sampled margin headroom.

The candidate improves full-period risk metrics, but 2025–2026 profit is $41,454.74 versus the unfiltered $80,295.54; uplift intervals include zero. Official-settlement fixed-contract sensitivity is −$6,144 for the candidate and −$31,440 for the baseline, with missing PM dates retained. These are not corrected funded accounts. No robust-alpha, exact Option Omega parity, independent quote/funding simulator, or live-readiness claim.

The optional $100k/two-leg put-spread add-on passed its smoke but stopped at a native margin call on 2022-07-12. Its 1,141 orders and failure remain archived. A scope amendment excluded it before selection; no truncated-tape optimization, capital increase or replacement candidate was used.

The design incorporates the newer [eleven-underlying data requirement](OPTIONOMEGA_0DTE_5M_DATA_REQUIREMENTS_20261026.md), QQQ quote delivery and partial Greeks receipts as the next data stage. Completed trades remain SPXW-only. Historical availability/gamma/coverage gaps and independent 5m/finer parity remain gated. Frozen 0.7/0.8 and the 0.7.5 design remain preserved below.

'''
 if heading not in s:s=s.replace('## Current focus: Draft 0.7.5 design and data admission',section+'## Previous Draft 0.7.5 design and data admission',1)
 p.write_text(s)
 p=ROOT/'docs/TODO.md';s=p.read_text();section='''## Version 0.8.5 next gates (2026-10-26)

[Design and evidence](../strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.md). The condor baseline/local/final-QC loop is complete; the optional put-spread baseline is rejected on a native margin call. Preserve both outcomes.

1. Diagnose native buying-power/grouping behavior and actual margin-call fills before reconsidering the spread. Do not infer broker equivalence from an isolated maximum-loss formula.
2. Complete official SPXW PM settlement coverage, resolve native-reference differences and evaluate any corrected account path as a new frozen campaign.
3. Follow the [eleven-underlying requirement](OPTIONOMEGA_0DTE_5M_DATA_REQUIREMENTS_20261026.md): inventory, 17-date pilot, quote/availability clocks, gamma/Greek units, and decision-window timing. Current QQQ delivery is sampled and partly populated, not strict admission.
4. Build the complete opportunity ledger and independent quote/selection/funding replay; measure 5m-versus-finer discrepancies before broader research.
5. Preregister genuinely future evaluation and shared-capital portfolio rules. The historical Calmar above 2 is not evidence of robust alpha or deployment approval.

'''
 if '## Version 0.8.5 next gates' not in s:s=s.replace('# Next steps\n\n','# Next steps\n\n'+section,1).replace('## Draft 0.7.5 current sequence','## Previous Draft 0.7.5 sequence',1)
 p.write_text(s)
 p=ROOT/'strategies/sstrangle/README.md';s=p.read_text();s=re.sub(r'Current design:.*',lambda m:'Current design: **[Version 0.8.5](research/design_20261026_v085/DESIGN_REPORT.pdf)** — completed condor QC baseline → local research → funded QC verification, plus a rejected put-spread add-on. [Readable design](research/design_20261026_v085/DESIGN_REPORT.md) · [implementation](poc/v085/README.md) · [evidence](results/qc_poc_20261026_v085/final_verification.json). Native candidate: 3,510 trades, $251,600.30 net, 16.2% MDD, 2.019 Calmar. Research-only; later-period comparison and settlement/model gaps prevent an alpha/deployment claim.',s,count=1)
 s=s.replace('Start with [current work](../../docs/CURRENT_WORK.md), [next steps](../../docs/TODO.md), and [overall design Draft 0.6](research/design_20261023_v6/DESIGN_REPORT.pdf). Three audited','Start with [current work](../../docs/CURRENT_WORK.md), [next steps](../../docs/TODO.md), and [the 0.8.5 design](research/design_20261026_v085/DESIGN_REPORT.pdf). Historically, three audited')
 s=s.replace('| `research/design_20261023_v6/` | Current overall design for review, diagram and comment resolution |','| `research/design_20261026_v085/` | Current measured design, PDF, charts and findings |\n| `poc/v085/` | Native baseline, local search, frozen QC verification and failure audit |\n| `research/design_20261023_v6/` | Historical overall design and comment resolution |')
 p.write_text(s)
 print('Promoted five documentation entry points; prior snapshots retained')
if __name__=='__main__':main()
