"""Audit frozen search, final native evidence and the published Draft 0.7."""
import ast,hashlib,json,subprocess,sys
import pandas as pd
from optimize import ROOT,OUT,OLD,BASES
from recheck_baselines import reconstruct
checks=[]
def check(ok,message):
 assert ok,message
 checks.append(message)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
rules=json.loads((OUT/'frozen_rules.json').read_text());provenance=json.loads((OUT/'optimizer_provenance.json').read_text())
check(sha(OUT/'frozen_rules.json')==provenance['rules_sha256'],'frozen optimizer rules unchanged')
check(sha(ROOT/'strategies/sstrangle/poc/v07/optimize.py')==provenance['source_sha256'],'frozen optimizer source unchanged')
for kind,rule in rules.items():
 trials=pd.read_csv(OUT/(kind+'_all_trials.csv'))
 check(len(trials)==864,kind+' complete 864-rule ledger')
 best=trials[trials.eligible].sort_values(['train_calmar','train_pnl','feature','quantile','side'],ascending=[False,False,True,True,True]).iloc[0]
 check(all(best[k]==rule[k] for k in ['feature','quantile','side']) and abs(best.threshold-rule['threshold'])<1e-12,kind+' deterministic frozen selection')
 local=pd.read_parquet(OUT/(kind+'_local_selected.parquet'))
 check(local.groupby('year').size().reindex(range(2022,2027),fill_value=0).ge(400).all(),kind+' local count feasibility')
 _,account=reconstruct(BASES[kind][1]);check(account['max_episode_error']<1e-5,kind+' independent baseline arithmetic')
for key in ['condor_alpha_smoke_readable','condor_control_full','condor_alpha_full','strangle_alpha_full','put_alpha_full']:
 folder=OUT/(key+'_evidence');a=json.loads((folder/'audit.json').read_text());m=json.loads((OUT/(key+'_manifest.json')).read_text());c=json.loads((OUT/(key+'_consistency.json')).read_text());ep=pd.read_parquet(folder/'episodes.parquet')
 check(a['native_cloud_terminal_success'] and a['residual_positions']==0,key+' native terminal and flat holdings')
 check(m['frozen_rules_sha256']==provenance['rules_sha256'],key+' native candidate uses frozen optimization decisions')
 check(sha(folder/'submitted_main.py')==sha(OUT/(key+'.py'))==m['source_sha256']==a['source_sha256'],key+' frozen main source')
 cloud={f['name']:f['content'] for f in json.loads((OUT/(key+'_cloud_source_files.json')).read_text())['files']}
 for name,digest in {'main.py':m['source_sha256'],**m.get('extra_files_sha256',{})}.items():check(hashlib.sha256(cloud[name].encode()).hexdigest()==digest,key+' cloud '+name)
 if c['alpha_enabled']:
  source=pd.read_parquet(OLD/'provider/us_prices/data.parquet');symbol=rules[c['kind']]['feature'].split('_')[0].upper();source=source[source.symbol==symbol].sort_values('date')
  expected=[[str(r.date),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in source.itertuples()]
  actual=[]
  for name in sorted(n for n in m['extra_files_sha256'] if n.startswith('daily_input_')):
   tree=ast.parse(cloud[name]);check(len(tree.body)==1 and isinstance(tree.body[0],ast.Assign),key+' readable raw rows '+name)
   actual.extend(ast.literal_eval(tree.body[0].value))
  check(actual==expected,key+' every uploaded raw row equals pinned provider export')

 for name,digest in json.loads((folder/'manifest.json').read_text())['files'].items():check(sha(folder/name)==digest,key+' evidence '+name)
 for name,digest in json.loads((folder/'raw_order_pages_manifest.json').read_text())['files'].items():check(sha(folder/'raw_order_pages'/name)==digest,key+' raw page '+name)
 check(c['max_common_pnl_difference']<1e-5 and not c['common_contract_mismatches'] and c['funding_differences_explained'],key+' contract/payoff/funding parity')
 if c['full']:check(a['annual_pass'] and ep.groupby('year').size().reindex(range(2022,2027),fill_value=0).ge(360).all(),key+' every year at least 360')
 _,account=reconstruct(folder);check(account['max_episode_error']<1e-5,key+' independent final payoff reconstruction')
 if c['alpha_enabled']:check(c['feature_max_error']<1e-10,key+' feature formula/source-day parity')
for path in (OLD/'provider').glob('*/manifest.json'):
 m=json.loads(path.read_text());check(sha(path.parent/'data.parquet')==m['sha256'],path.parent.name+' pinned provider input')
identity=json.loads((OUT/'native_launch_identity_audit.json').read_text());check(identity['status']=='passed' and identity['duplicate_runs']==0 and sum(bool(r['backtest_id']) for r in identity['experiments'])==5,'five unique successful native executions; no duplicate recovery launch')
report=ROOT/'strategies/sstrangle/research/design_20261024_v7'
for name,digest in json.loads((report/'manifest.json').read_text())['files'].items():check(sha(report/name)==digest,'report '+name)
result=subprocess.run([sys.executable,'-m','pytest','strategies/sstrangle/tests','strategies/sstrangle/poc/test_demo_audit.py','strategies/sstrangle/poc/v06','strategies/sstrangle/poc/v065','strategies/sstrangle/poc/v07','-q'],cwd=ROOT,capture_output=True,text=True)
(OUT/'tests.log').write_text(result.stdout+result.stderr);check(result.returncode==0,'regression suite')
(OUT/'final_verification.json').write_text(json.dumps(dict(status='passed',checks=len(checks),invariants=checks,tests=result.stdout.strip()),indent=2));print(len(checks),'checks passed')
