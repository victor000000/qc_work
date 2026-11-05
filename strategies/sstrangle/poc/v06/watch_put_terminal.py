"""Read-only terminal observer, independent of potentially slow order exports."""
import json,time
from campaign import rows,ROOT,OUT
from transport import request
from qc_api_check import credentials
u,t=credentials(ROOT/'data/S001.duckdb');p=OUT/'put_full_v3_terminal.json'
while not p.exists():
 row=next(r for r in rows() if r['name'].endswith('_PUT_FULL_V3'))
 if row['backtest_id']:
  try:
   result=request(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']))
   b=result['backtest'];print(b['status'],b['progress'],flush=True)
   if b['completed']:
    p.write_text(json.dumps(result,indent=2));break
  except Exception as exc:print(str(exc)[:200],flush=True)
 time.sleep(60)
print('Native terminal evidence saved; no execution submitted or cancelled',flush=True)
