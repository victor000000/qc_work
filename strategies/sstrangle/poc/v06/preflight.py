import sys,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials
from transport import request
u,t=credentials(ROOT/'data/S001.duckdb')
pids=json.loads((ROOT/'data/projects.json').read_text())['projects']
def one(pid):
 r=request(u,t,'/backtests/list',{'projectId':pid})
 active=[b for b in r.get('backtests',[]) if not b.get('completed') and b.get('status') not in ('Completed.','Runtime Error','RuntimeError','Cancelled','Canceled')]
 return {'project_id':pid,'active':active,'total':len(r.get('backtests',[]))}
rows=list(ThreadPoolExecutor(max_workers=4).map(one,pids))
(ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/preflight.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
assert not any(r['active'] for r in rows)
