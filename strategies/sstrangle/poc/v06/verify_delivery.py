"""Verify the completed three-demo deliverable and save provenance without cloud writes."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,subprocess,sys
import pandas as pd
from campaign import rows,ROOT,OUT,storage
P=ROOT/'strategies/sstrangle/research/design_20261023_v6'
findings=json.loads((OUT/'analysis/findings.json').read_text())
checks=0
for row in rows():
 key=row['name'].removeprefix('SSTRANGLE_OO06_20261023_').lower()
 source=OUT/(key+'.py');manifest=OUT/(key+'_manifest.json')
 if source.exists() and manifest.exists():
  frozen=json.loads(manifest.read_text());assert hashlib.sha256(source.read_bytes()).hexdigest()==frozen['source_sha256']
  with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as c:
   submitted=c.execute('SELECT code FROM backtest_queue WHERE name=?',(row['name'],)).fetchone()[0]
  assert hashlib.sha256(submitted.encode()).hexdigest()==frozen['source_sha256'];checks+=2
for folder in sorted(OUT.glob('*_evidence')):
 if not (folder/'audit.json').exists():continue
 audit=json.loads((folder/'audit.json').read_text())
 if (folder/'raw_order_pages_manifest.json').exists():
  raw=json.loads((folder/'raw_order_pages_manifest.json').read_text())
  for name,digest in raw['files'].items():assert hashlib.sha256((folder/'raw_order_pages'/name).read_bytes()).hexdigest()==digest;checks+=1
 if audit.get('native_cloud_terminal_success'):
  episodes=pd.read_parquet(folder/'episodes.parquet');features=pd.read_parquet(folder/'entry_features.parquet');labels=pd.read_parquet(folder/'labels.parquet')
  assert episodes.episode.is_unique and features.episode.is_unique and labels.episode.is_unique
  assert set(episodes.episode)==set(features.episode)==set(labels.episode)
  assert set(features.columns).isdisjoint(set(labels.columns)-{'episode'})
  assert abs(audit['attribution_error'])<.05 and audit['residual_positions']==0
  b=json.loads((folder/'backtest.json').read_text())['backtest'];assert b['completed'] and not b.get('error')
  identity=json.loads((folder/'queue_identity.json').read_text());assert b['backtestId']==identity['backtest_id'] and b['projectId']==identity['project_id']
  assert hashlib.sha256((folder/'submitted_main.py').read_bytes()).hexdigest()==audit['source_sha256'];checks+=8
 # Include newly derived views in the evidence manifest; original raw page hashes were checked above.
 files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file() and p.name!='manifest.json'}
 (folder/'manifest.json').write_text(json.dumps({'files':files},indent=2)+'\n')
for kind in ['condor','strangle','put']:
 identity=findings['identities'][kind];match=None
 for folder in OUT.glob('*_evidence'):
  if (folder/'queue_identity.json').exists() and json.loads((folder/'queue_identity.json').read_text())['backtest_id']==identity['backtest_id']:match=folder;break
 assert match is not None
 annual=pd.read_csv(match/'annual.csv');assert annual.year.tolist()==[2022,2023,2024,2025,2026] and annual.passed.all() and (annual.trades>=360).all()
 assert annual.partial_year.tolist()==[True,False,False,False,True]
 rt=json.loads((match/'backtest.json').read_text())['backtest']['runtimeStatistics']
 assert rt['assignment_policy']=='european_no_discretionary_early_assignment_native_expiry'
 assert rt['session_policy']=='index_open_at_submission';checks+=4
diagnostic=json.loads((OUT/'admission_diagnostic.json').read_text())
assert diagnostic['counts']['skip_missing_20point_wing']==3606
assert sum(v for k,v in diagnostic['counts'].items() if k.startswith('wing_reason_'))==3606
assert hashlib.sha256((OUT/'diag_full_v2_terminal.json').read_bytes()).hexdigest()==diagnostic['terminal_sha256'];checks+=3
ledger=[]
for row in rows():
 key=row['name'].removeprefix('SSTRANGLE_OO06_20261023_').lower();row.pop('result_json',None)
 m=OUT/(key+'_manifest.json')
 if m.exists():row.update(json.loads(m.read_text()))
 terminal=OUT/(key+'_terminal.json')
 if terminal.exists():
  native=json.loads(terminal.read_text())['backtest']
  row['native_terminal']={k:native.get(k) for k in ['completed','status','error']}
 row['primary']=row.get('backtest_id') in {x['backtest_id'] for k,x in findings['identities'].items() if k!='condor_v05'}
 ledger.append(row)
(OUT/'trial_ledger.json').write_text(json.dumps({'observed_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'trials':ledger},indent=2)+'\n')
result=subprocess.run([sys.executable,'-m','pytest','strategies/sstrangle/tests','strategies/sstrangle/poc/test_demo_audit.py','strategies/sstrangle/poc/v06','-q'],cwd=ROOT,capture_output=True,text=True)
(OUT/'final_tests.txt').write_text(result.stdout+result.stderr);assert result.returncode==0
for name,digest in json.loads((P/'manifest.json').read_text())['files'].items():assert hashlib.sha256((P/name).read_bytes()).hexdigest()==digest;checks+=1
record=dict(observed_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),passed=True,checked_invariants_and_hashes=checks,
 primary_identities=findings['identities'],annual_gate='all three revised baselines: >=360 actual completed episodes for each included year',
 test_output=result.stdout.strip(),scope='Native cash reconciliation, raw archive checksums, source identity, feature-label separation, annual coverage, PDF/report manifest. Not OOS or production certification.')
(OUT/'final_verification.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
