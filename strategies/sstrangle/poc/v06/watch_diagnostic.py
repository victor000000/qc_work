"""Read-only terminal collection and complete aggregate-counter validation."""
import hashlib,json,time
from campaign import rows,ROOT,OUT
from transport import request
from qc_api_check import credentials
u,t=credentials(ROOT/'data/S001.duckdb')
key='diag_full_v2';path=OUT/(key+'_terminal.json')
while not path.exists():
 row=next((r for r in rows() if r['name'].endswith('_'+key.upper())),None)
 if row and row['backtest_id']:
  try:
   r=request(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']))
   b=r['backtest'];print(b.get('status'),b.get('progress'),flush=True)
   if b['completed']:path.write_text(json.dumps(r,indent=2));break
  except Exception as exc:print(str(exc)[:200],flush=True)
 time.sleep(60)
b=json.loads(path.read_text())['backtest'];assert b['completed'] and not b.get('error')
rt=b['runtimeStatistics'];counts={}
for i in range(1,int(rt['admission_chunks'])+1):
 chunk=rt['admission_'+str(i).zfill(2)];assert len(chunk)<=180
 values=json.loads(chunk);assert not set(values)&set(counts);counts.update(values)
for key in ['scheduled_slots','skip_missing_20point_wing','diag_admitted_original','wing_recoverable_pair_search','skip_no_chain','skip_missing_delta_or_quotes']:
 assert counts[key]==int(rt[key])
assert counts['scheduled_slots']==13501 and counts['skip_missing_20point_wing']==3606
assert sum(v for k,v in counts.items() if k.startswith('wing_reason_'))==3606
assert int(b['statistics']['Total Orders'])==0
out=dict(project_id=b['projectId'],backtest_id=b['backtestId'],terminal_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),scope='Unfunded original admission replay; complete counts independently exported within QC quota',counts=counts)
(OUT/'admission_diagnostic.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
