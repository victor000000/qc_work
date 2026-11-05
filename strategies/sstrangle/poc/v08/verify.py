"""Final offline integrity checks; no cloud writes or reruns."""
import ast,hashlib,json,subprocess,sys
import pandas as pd
from campaign import ROOT,OUT
checks=[]
def check(ok,msg):
 assert ok,msg
 checks.append(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
provenance=json.loads((OUT/'optimizer_provenance.json').read_text());check(sha(OUT/'frozen_rules.json')==provenance['rules_sha256'],'Frozen decisions unchanged');check(sha(ROOT/'strategies/sstrangle/poc/v08/optimize.py')==provenance['source_sha256'],'Optimizer source unchanged after freeze');check(sha(OUT/'EXPERIMENT_CONTRACT.txt')==provenance['contract_sha256'],'Revised full-equity contract unchanged')
rules=json.loads((OUT/'frozen_rules.json').read_text());robust=json.loads((OUT/'robustness.json').read_text())
for kind,rule in rules.items():
 t=pd.read_csv(OUT/(kind+'_all_trials.csv'));check(len(t)==901,kind+' all901 trials retained');best=t[t.eligible].sort_values(['score','validation_pnl','feature','quantile','side'],ascending=[False,False,True,True,True]).iloc[0]
 check(best.feature==rule['feature'] and best.side==rule['side'] and abs(best.threshold-rule['threshold'])<1e-12,kind+' declared rank reproduces frozen choice')
 check(len(robust[kind]['cost_and_tail_cases'])==7 and len(robust[kind]['expanding_walk_forward'])==4 and len(robust[kind]['later_paired_bootstrap'])==3,kind+' complete robustness cases')
 check(robust[kind]['search_adjusted_diagnostic']['rules']==901,kind+' repeated-search diagnostic covers all rules')
for key in ['condor_smoke','put_smoke','condor_control','condor_final','put_control','put_final']:
 p=OUT/(key+'_evidence');m=json.loads((OUT/(key+'_manifest.json')).read_text());a=json.loads((p/'audit.json').read_text());c=json.loads((OUT/(key+'_consistency.json')).read_text());ep=pd.read_parquet(p/'episodes.parquet')
 check(a['native_cloud_terminal_success'] and a['residual_positions']==0,key+' terminal and flat holdings')
 check(m['config']['capital_fraction']==1 and m['config']['start_capital']==(100000 if m['config']['strategy_kind']=='condor' else 2000000),key+' full equity ceiling and unchanged starting capital')
 check(m['frozen_rules_sha256']==provenance['rules_sha256'],key+' rule freeze identity')
 check(sha(p/'submitted_main.py')==m['source_sha256']==a['source_sha256'],key+' frozen main identity')
 cloud={r['name']:r['content'] for r in json.loads((OUT/(key+'_cloud_source_files.json')).read_text())['files']}
 for n,digest in {'main.py':m['source_sha256'],**m['extra_files_sha256']}.items():check(hashlib.sha256(cloud[n].encode()).hexdigest()==digest,key+' cloud '+n)
 if m['config']['alpha_enabled']:
  prices=pd.read_parquet(OUT/'provider/us_prices_full/data.parquet');g=prices[prices.symbol==m['config']['alpha_feature'].split('_')[0].upper()].sort_values('date');expected=[[str(r.date),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in g.itertuples()];actual=[]
  for n in sorted(x for x in m['extra_files_sha256'] if x.startswith('daily_input_')):actual.extend(ast.literal_eval(ast.parse(cloud[n]).body[0].value))
  check(actual==expected,key+' every uploaded raw row equals pinned provider data')

 for n,digest in json.loads((p/'manifest.json').read_text())['files'].items():check(sha(p/n)==digest,key+' evidence '+n)
 for n,digest in json.loads((p/'raw_order_pages_manifest.json').read_text())['files'].items():check(sha(p/'raw_order_pages'/n)==digest,key+' raw '+n)
 check(c['funding_explained'] and c['max_common_pnl_difference']<1e-5 and c['feature_max_error']<1e-10 and c['independent_payoff']['max_episode_error']<1e-5,key+' trade/feature/accounting parity')
 if not m['smoke']:check(ep.groupby('year').size().reindex(range(2022,2027),fill_value=0).ge(360).all(),key+' every year>=360')
for name in ['us_prices','us_prices_full']:
 p=OUT/'provider'/name;m=json.loads((p/'manifest.json').read_text());check(sha(p/'data.parquet')==m['sha256'],name+' pinned raw inputs')
check(sha(OUT/'VIX_History.csv')==json.loads((OUT/'vix_source.json').read_text())['sha256'],'Cboe raw source hash')
r=json.loads((OUT/'terminal_queue_recovery.json').read_text());check(r['status']=='passed' and len(r['rows'])==6 and all(x['native_instances']==1 for x in r['rows']),'six unique native executions; queue reconciled; no duplicate runs')
report=ROOT/'strategies/sstrangle/research/design_20261024_v8'
for n,digest in json.loads((report/'manifest.json').read_text())['files'].items():check(sha(report/n)==digest,'report '+n)
cmd=[sys.executable,'-m','pytest','strategies/sstrangle/tests','strategies/sstrangle/poc/test_demo_audit.py','strategies/sstrangle/poc/v06','strategies/sstrangle/poc/v065','strategies/sstrangle/poc/v07','strategies/sstrangle/poc/v08','-q']
r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True);(OUT/'tests.log').write_text(r.stdout+r.stderr);check(r.returncode==0,'regression suite')
(OUT/'final_verification.json').write_text(json.dumps(dict(status='passed',checks=len(checks),invariants=checks,tests=r.stdout.strip()),indent=2));print(len(checks),'checks passed')
