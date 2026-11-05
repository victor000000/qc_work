"""Publish evidence summaries after collection; no cloud submissions."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024';HERE=Path(__file__).parent
for key in ['condor_full_t02','condor_full_t05']:
 a=json.loads((OUT/(key+'_evidence/audit.json')).read_text());assert a['annual_pass'] and a['native_cloud_terminal_success']
for script in ['local_features.py','local_diagnostics.py','analyze.py']:
 with (OUT/(script.replace('.py','')+'_final.log')).open('w') as f:subprocess.run([sys.executable,str(HERE/script)],stdout=f,stderr=subprocess.STDOUT,check=True)
trials=[]
for p in sorted(OUT.glob('*_manifest.json')):
 key=p.name.removesuffix('_manifest.json');m=json.loads(p.read_text())
 if 'config' not in m:continue
 a=json.loads((OUT/(key+'_evidence/audit.json')).read_text())
 trials.append(dict(key=key,config=m['config'],source_sha256=m['source_sha256'],status='audited',native_pnl=a['native_net_pnl'],episodes=a['episodes'],annual_requirement_applied=a['annual_requirement_applied'],annual_pass=a['annual_pass']))
(OUT/'trial_ledger.json').write_text(json.dumps({'native':trials,'local_search':'288 rules per dataset; all rows saved in local/*_all_trials.csv','local_failure':{'initial_put_feature_build':'None-valued absent call delta could not take abs(); fixed with nullable numeric conversion, tested no invented call exposure; no cloud run affected'},'native_collection_recovery':{'trial':'condor_full_t05','failure':'QC completed flag arrived before final statistics; initial collector stopped on missing Total Orders','resolution':'Read-only refresh of same backtest; incomplete response and failed collection logs retained; no native resubmission','readiness_fix':'Require final statistics and native cash/ledger/count counters before terminal artifact acceptance'},'selection_policy':'Tightest predeclared tolerance passing annual gate; local rule selected on training only. No endpoint matching.'},indent=2))
subprocess.run([sys.executable,str(ROOT/'strategies/sstrangle/research/design_20261024_v065/build_report.py')],check=True)
subprocess.run([sys.executable,str(HERE/'verify.py')],check=True)
files={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for base in [OUT/'analysis',OUT/'local',OUT/'provider'] for p in base.rglob('*') if p.is_file()}
(OUT/'artifact_manifest.json').write_text(json.dumps({'files':files},indent=2))
