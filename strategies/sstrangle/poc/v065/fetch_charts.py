"""Fetch native sampled account marks after terminal success, never reconstruct prices."""
import json,sys,hashlib,time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v06'))
from transport import request
u,t=credentials(ROOT/'data/S001.duckdb');base=ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024'
keys=sys.argv[1:] or ['condor_full_t02','condor_full_t05']
for key in keys:
 p=base/(key+'_evidence');b=json.loads((p/'backtest.json').read_text())['backtest'];assert b['completed'] and not b.get('error')
 args=dict(projectId=b['projectId'],backtestId=b['backtestId'],name='Strategy Equity',start=int(datetime(2022,5,16,tzinfo=ZoneInfo('America/New_York')).timestamp()),end=int(datetime(2026,7,18,tzinfo=ZoneInfo('America/New_York')).timestamp()),count=5000)
 f=p/'strategy_equity.json'
 if not f.exists():
  for attempt in range(6):
   try:
    response=request(u,t,'/backtests/chart/read',args)
    if not isinstance(response.get('chart'),dict):raise RuntimeError('Native chart is loading or unavailable')
    f.write_text(json.dumps(response,indent=2));break
   except Exception:
    if attempt==5:raise
    time.sleep(min(2**attempt,8))
 r=json.loads(f.read_text());assert r['chart']['series']['Equity']['values']
 (p/'chart_request.json').write_text(json.dumps(args,indent=2))
 m=json.loads((p/'manifest.json').read_text())
 for name in ['strategy_equity.json','chart_request.json']:m['files'][name]=hashlib.sha256((p/name).read_bytes()).hexdigest()
 (p/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 print(key,len(r['chart']['series']['Equity']['values']),flush=True)
