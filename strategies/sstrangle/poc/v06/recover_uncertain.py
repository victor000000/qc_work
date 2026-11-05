"""Read-only discovery for create requests with an uncertain remote outcome."""
import sys,json,argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials
from transport import request
u,t=credentials(ROOT/'data/S001.duckdb')
def one(pid):
 r=request(u,t,'/backtests/list',{'projectId':pid})
 matches=[b for b in r['backtests'] if b.get('name','').startswith('SSTRANGLE_OO06_20261023_')]
 path=ROOT/f'strategies/sstrangle/results/qc_three_demo_poc_20261023/discovery_{pid}.json'
 path.write_text(json.dumps({'project_id':pid,'matches':matches},indent=2))
 print(pid,[(b['name'],b['backtestId'],b['completed'],b['status']) for b in matches],flush=True)
 return matches
p=argparse.ArgumentParser();p.add_argument('projects',nargs='*',type=int);a=p.parse_args()
with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(one,a.projects or [31338457,31338458]))
