"""Render current evidence without promoting pending or blocked work."""
from pathlib import Path
import json,hashlib,html
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_poc_20261027_v087'
d=json.loads((OUT/'results.json').read_text());cov=d['coverage_snapshot'];lines=['# 0.8.7 implementation and execution evidence','',f"Pinned provider release: `{cov['release']}`; audited {cov['checked_shanghai']}.",'','## Verdict','',d['verdict'],'',f"Native nine-account pipeline complete: **{d['native_pipeline_complete']}**. Full independent pipeline passed: **False**. Strict replay ready: **False**. Live ready: **False**.",'','## Native QC runs','','| Run | Status | Episodes | Net P&L | Native MDD | Minimum sampled margin |','|---|---|---:|---:|---|---:|']
for k,v in d['native'].items():
 lines.append(f"| {k} | {v['status']} | {v.get('episodes','—')} | {v.get('net_pnl','—')} | {v.get('drawdown','—')} | {v.get('min_margin','—')} |")
lines+=['','Smoke results cover July 8–15, 2022 and are engineering tests, not annual performance. Full baselines and verification cover May 16, 2022–October 22, 2026. Pending accounts have no claimed result. Every completed account has archived source readback, terminal response, paginated orders, logs, native-account reconciliation and independently recalculated expiry arithmetic. Native QC evidence does not establish independent provider replay.','','## Independent local attempt','','The local engine starts from provider contract/quote/Greek observations; QC trades are used only afterward for reconciliation. The preregistered predecision and strict modes have zero eligible joined observations in the pinned release. Their zero trades are an input failure, not zero strategy return. Equal-time snapshots are a separately labeled sensitivity.','','| Strategy | Fill assumption | Episodes | Diagnostic P&L | Covered sessions |','|---|---|---:|---:|---:|']
for r in d['local_summary']['results']:
 if r['mode']=='equal_time_sensitivity':lines.append(f"| {r['strategy']} | {r['fill']} | {r['episodes']} | ${r['net_pnl']:,.2f} | {r['covered_days']} |")
lines+=['','## Continuous QC diagnostic matrix','','These preregistered tests follow the primary baseline and verification accounts. Each changes only the recorded execution, reserve, or calendar condition; results are diagnostics, not a parameter selection contest.','','| Test | Question | Evidence status |','|---|---|---|']
validation={}
plans=json.loads((Path(__file__).parent/'cloud_test_plan.json').read_text())['tests']
if (Path(__file__).parent/'cloud_cost_funding_plan.json').exists():
 plans+=json.loads((Path(__file__).parent/'cloud_cost_funding_plan.json').read_text())['tests']
if (Path(__file__).parent/'cloud_capital_mechanism_plan.json').exists():
 plans+=json.loads((Path(__file__).parent/'cloud_capital_mechanism_plan.json').read_text())['tests']
for test in plans:
 key=test['key'];folder=OUT/(key+'_evidence');failure=OUT/(key+'_failure.json')
 record={'question':test['question'],'overrides':test['overrides'],'status':'queued'}
 if failure.exists():
  record.update(status='failed',failure=json.loads(failure.read_text()))
 elif (folder/'audit.json').exists():
  audit=json.loads((folder/'audit.json').read_text())
  record.update(status='audited_success' if audit.get('native_cloud_terminal_success') else 'audit_not_passed',audit=audit)
 elif (OUT/(key+'_progress.json')).exists():
  progress=json.loads((OUT/(key+'_progress.json')).read_text()).get('backtest',{})
  record.update(status='cloud_terminal_pending_audit' if progress.get('completed') else 'running',backtest_id=progress.get('backtestId'),progress=progress.get('progress'))
 validation[key]=record
 lines.append(f"| {key} | {test['question']} | {record['status']} |")
(OUT/'validation_status.json').write_text(json.dumps(validation,indent=2)+'\n')
if (OUT/'c0_half_reserve_review.json').exists():
 reserve_review=json.loads((OUT/'c0_half_reserve_review.json').read_text())
 lines+=['',reserve_review['interpretation']]
if (OUT/'settlement_clock_review.json').exists():
 clock_review=json.loads((OUT/'settlement_clock_review.json').read_text())
 lines+=['','## Native expiry-clock probes','',clock_review['conclusion'],'',clock_review['failed_probe']]
lines+=['','Adverse fills use native quote-side fills plus 0.05 index points per leg and $1.18 per opening contract. This is an execution stress assumption, not evidence of attainable live fills. Midpoint baselines instead charge 0.05 points per entire package. Native margin-call failures are failures of the requested account, not successful truncated backtests.','','| Diagnostic | Net P&L | Native MDD | Minimum sampled margin | Failure |','|---|---:|---|---:|---|']
for key,record in validation.items():
 folder=OUT/(key+'_evidence')
 if record['status']=='failed':
  reason=record['failure'].get('native_error') or record['failure'].get('error','unknown')
  lines.append(f"| {key} | Not accepted | — | — | {reason.splitlines()[0]} |")
 elif record['status']=='audited_success':
  b=json.loads((folder/'backtest.json').read_text())['backtest'];a=record['audit']
  lines.append(f"| {key} | {a.get('native_net_pnl')} | {b['statistics'].get('Drawdown')} | {b['runtimeStatistics'].get('min_margin_remaining_1m')} | None |")
if (OUT/'margin_runtime_review.json').exists():
 review=json.loads((OUT/'margin_runtime_review.json').read_text())
 next_status='The separate pre-call/post-fill diagnostic has been queued; see margin_events_submission_receipt.json. No result is claimed.' if (OUT/'margin_events_submission_receipt.json').exists() else 'Next diagnostic is preregistered in next_margin_and_settlement_preregistration.json and has not been submitted.'
 if (OUT/'margin_events_review.json').exists():
  next_status=json.loads((OUT/'margin_events_review.json').read_text())['conclusion']+' Evidence: margin_events_review.json; archive completion is recorded separately in c0_margin_events200k_evidence/audit.json.'
 lines+=['','## Margin intervention telemetry','',review['conclusion'],'','Evidence: margin_runtime_review.json; immutable terminal identity '+review['backtest_id']+'. '+next_status]
if (OUT/'official_settlement_model_gate_20261028.json').exists():
 lines+=['','The accounting implementation gate and short-probe requirements are recorded in official_settlement_model_gate_20261028.json; changing exercise fill price alone is insufficient.']
if (OUT/'accounting_probe_v2_plan.json').exists():
 lines+=['','The first native accounting probe ended before exercise processing (8 opens, 0 expiries, residual holdings), so it failed the lifecycle gate despite matching cash arithmetic. The preserved revision extends observation through October 4 without new entries; see accounting_probe_v2_plan.json and the separate accounting evidence folders. No settlement-model acceptance is inferred.']
if (OUT/'accounting_native_parity_review.json').exists():
 lines+=['','The extended native accounting pair passed its short engineering parity gate: identical opening trades, eight expiry events, zero residual holdings, cash/equity $100,080 and realized P&L $80 in both accounts within $0.01. Evidence: accounting_native_parity_review.json. Official-reference and synthetic boundary probes are separately preregistered in official_accounting_probe_plan.json; full-account status is listed below.']
if (OUT/'official_accounting_review.json').exists():
 lines+=['','Official-reference short accounting validation passed: the same eight positions settle to $98,856 cash/equity, $1,224 below the native-reference account. Both artificial boundary fixtures passed independently calculated cash and flat-holdings checks; these fixtures are not performance evidence. See official_accounting_review.json. Subsequent fee and strategy integration evidence is listed below.']
if (OUT/'accounting_fee_independent_review.json').exists():
 lines+=['','Nonzero-fee accounting verification passed: raw opening commissions total $14.16, exercise fees are zero, and cash/equity reconcile to $100,065.84 (native reference) and $98,841.84 (official reference). Opening trades match the zero-fee controls; gross realized P&L less commissions reconciles separately. Evidence: accounting_fee_independent_review.json. Short strategy integration is recorded in official_strategy_smoke_plan.json; full-account status is listed below.']
for integration_key in ['c0_official_integration','p1_official_integration']:
 audit_path=OUT/(integration_key+'_integration_archive/audit.json')
 if audit_path.exists():
  integration=json.loads(audit_path.read_text())
  lines+=['',f"Official strategy integration {integration_key}: passed={integration.get('integration_pass')}; episodes={integration.get('episodes')}; net cash={integration.get('raw_event_net_cash')}. These September 29–October 3 engineering tests do not establish full-period performance."]
if (OUT/'official_funded_plan.json').exists():
 lines+=['','Full-period official-settlement replays are preregistered in official_funded_plan.json using 1,114 pinned expiry values. The serial controller covers C0/C1/P1 at $100k and C1 at $200k against existing native quote-side controls. Each new account retains native margin intervention; results are pending until archived and audited.']
 for test in json.loads((OUT/'official_funded_plan.json').read_text())['tests']:
  archive=OUT/(test['key']+'_funded_archive');audit_path=archive/'audit.json'
  if audit_path.exists():
   result=json.loads(audit_path.read_text())
   detail=('audited net P&L '+str(result.get('native_net_pnl'))) if result.get('funded_pass') else ('FAILED: '+result.get('error','audit did not pass').splitlines()[0])
   lines+=['',test['key']+': '+detail+'. Evidence: '+str(audit_path.relative_to(OUT))+'.']
  if (archive/'backtest.json').exists():
   terminal=json.loads((archive/'backtest.json').read_text())['backtest'];runtime=terminal.get('runtimeStatistics',{})
   minimum=runtime.get('min_margin_remaining_1m')
   if minimum is not None:
    lines+=['',test['key']+': terminal reported net='+str(runtime.get('native_net_pnl'))+', drawdown='+str(terminal.get('statistics',{}).get('Drawdown'))+', minimum margin remaining='+str(minimum)+'. '+('Funding acceptance fails: negative margin headroom.' if float(minimum)<0 else 'Nonnegative sampled margin headroom; other acceptance gates remain.')+(' Raw-order audit pending.' if not audit_path.exists() else ' Archive accounting audit is distinct from funding acceptance.')]
if (OUT/'official_funded_comparison.json').exists():
 comparison=json.loads((OUT/'official_funded_comparison.json').read_text())
 lines+=['','## Consolidated official-settlement funded results','','All four preregistered accounts are terminal and archived. C0 at $100k failed native margin intervention on September 11, 2024; its partial-period return is not an accepted result. The completed accounts below use quote-side fills, commissions and official expiry cash with native buying power.','','| Account | Net P&L | Drawdown | Minimum margin remaining | Episodes | Assessment |','|---|---:|---:|---:|---:|---|']
 for key,v in comparison['runs'].items():
  lines.append(f"| {key} | {v['net_pnl']:,.2f} | {v['drawdown']} | {v['minimum_margin_remaining']:,.2f} | {v['episodes']} | {v['acceptance']} |")
 lines+=['','Both C1 accounts retained exactly the native-control opening contracts, quantities, prices and fees, with no admission changes. Official settlement reduced each account by $11,631. C1 at $100k fails the nonnegative margin gate; C1 at $200k retains positive sampled headroom but is not independently accepted.','','P1 admitted 474 episodes versus 852 under native settlement. All common openings match exactly. The $4,017.92 deterioration comprises $908 of settlement differences on common episodes plus $3,109.92 native P&L from 378 omitted episodes. This is an actual account-path difference, unlike fixed-trade attribution. P1 also fails the annual episode gate and remains loss-making.','','Raw cash, episode P&L and flat holdings reconcile. The controller field funded_pass denotes accounting checks only; it does not certify margin headroom, profitability or independent economic acceptance. Evidence: official_funded_comparison.json and each funded archive.','','Remaining gates: full independent predecision data/replay, historical availability and coverage, and the unexplained C0 native position-group margin requirement. No new cloud test is implied by these results.']
if (OUT/'provider_release_recheck_20261028T1157_corrected.json').exists():
 lines+=['','Latest provider release recheck (20261028T110443Z_ea3a5193): quote/Greek partition hashes match. SPXW coverage is 838 quote sessions and 603 Greek sessions, but availability timestamps are absent throughout and quote-event timestamps are absent for all Greek rows and all but four quote rows. Strict predecision acceptance remains blocked. This separate data-run identity preserves the original pin. The corrected-root scan supersedes the initial underlying=SPXW zero-count scan; actual underlying is SPX. Evidence: provider_release_recheck_20261028T1157_corrected.json.']
if (OUT/'official_settlement_fixed_tapes.json').exists():
 settlement=json.loads((OUT/'official_settlement_fixed_tapes.json').read_text())
 lines+=['','## Official settlement attribution','',''+settlement['scope'],'','| Native account | Matched episodes | Native P&L | Official settlement on fixed trades | Difference |','|---|---:|---:|---:|---:|']
 for key,v in settlement['runs'].items():
  if 'smoke' in key or 'verify' in key:continue
  lines.append(f"| {key} | {v['matched_episodes']}/{v['native_episodes']} | {v['native_pnl_matched']:,.2f} | {v['official_fixed_tape_pnl']:,.2f} | {v['settlement_difference']:,.2f} |")
 lines+=['','Provider provenance checks found raw/publication parity for the initial 194-day comparison. The clock probe excludes an hour-offset explanation; the cross-date vendor cause remains unresolved. These adjusted figures do not recalculate subsequent sizing, admissions or margin, and must not be treated as a corrected backtest. Evidence: official_settlement_fixed_tapes.parquet and evidence/provider_settlement_validation_20261027T233909Z.json.']
lines+=['','These results omit unavailable dates. The paths are conditional on incomplete, noncontiguous coverage, not funded full-history strategy results. Additional $10/$25/$50 costs in local_summary.json are fixed-trade-count diagnostics; capital/selection reflow is not certified. No annualized return or marked drawdown is inferred from this sample.','', '## Controls and reconciliation','']
for k,v in d['baseline_verification'].items():lines.append(f'- {k} baseline vs fresh verification: `{json.dumps(v)}`')
for k,v in d['legacy_native_control'].items():lines.append(f'- {k} vs frozen 0.8.5: `{json.dumps(v)}`')
for k,v in d['independent_comparison'].items():lines.append(f'- {k} provider/native comparison: `{json.dumps(v)}`')
if (OUT/'fixed_contract_bridge.json').exists():
 lines+=['','Fixed-contract bridge separates official settlement, source fill prices and independent selection on joint filled slots. It does not explain all funding/admission differences.']
 for k,v in json.loads((OUT/'fixed_contract_bridge.json').read_text()).items():lines.append(f'- {k}: `{json.dumps(v)}`')
if (OUT/'diagnostics.json').exists():
 diag=json.loads((OUT/'diagnostics.json').read_text());lines+=['',f"Prior-session QQQ filter parity: {diag['equal_filter_decisions']}/{diag['feature_days']} decisions agree; maximum feature difference {diag['max_absolute_feature_difference']}. This is value parity, not historical availability proof."]
lines+=['','## Remaining acceptance gates','','- Full-period SPXW data and exact expiry/listing coverage.','- Synchronized predecision quotes and delta inputs; strict quote-event/availability clocks.','- Gamma/model/units, mark-equity coverage and independent funding equivalence.','- Complete missing/admitted trade attribution and preregistered robustness on accepted coverage.','- Final native accounts if marked pending above.','','## Reproduction and files','','Implementation: strategies/sstrangle/poc/v087. Immutable design: research/design_20261027_v087. Results: results/qc_poc_20261027_v087.','', 'Run `campaign.py smoke`, then `continue_pipeline.py`; the latter resumes baselines and verification with existing queue identities. Run `research.py` against the already pinned coverage snapshot, then `diagnostics.py`, `analyze.py`, `bridge.py`, and `report.py`. Do not overwrite the snapshot to hide missing data; admit a later release under an explicit new data-run identity.','', 'Evidence: coverage_snapshot.json, local_input_manifest.json, local_slots.parquet, local_episodes.parquet, local_summary.json, feature_parity.parquet, diagnostics.json, tests.txt, results.json, fixed_contract_bridge.json and the per-account evidence folders.','', 'The runtime dependency exchange-calendars 4.13.2 supplies a calendar baseline. XNYS is used for RTH sessions and early closes; independent SPXW calendar/eligibility acceptance remains outstanding. No subscriptions or trades were initiated.']
text='\n'.join(lines)+'\n';(OUT/'RESULTS.md').write_text(text)
(OUT/'RESULTS.html').write_text('<!doctype html><meta charset="utf-8"><title>0.8.7 evidence</title><style>body{max-width:1100px;margin:40px auto;font:15px/1.6 system-ui}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>')
manifest={'version':'0.8.7','status':'native_complete_independent_blocked' if d['native_pipeline_complete'] else 'native_running_independent_blocked','files':{str(f.relative_to(OUT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in OUT.rglob('*') if f.is_file() and f.suffix in ['.json','.parquet','.md','.txt'] and f.name not in ['release_manifest.json'] and not f.name.endswith('_progress.json')},'implementation':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.glob('*.py')}}
(OUT/'release_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(OUT/'RESULTS.md')
