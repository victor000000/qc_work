"""Read-only cloud result recovery; never creates, restarts or cancels QC work."""
import json,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import qc_storage
from qc_api_check import credentials,request
OUT=Path(__file__).parent
user,token=credentials(ROOT/'data/S001.duckdb')
with qc_storage.connect(f'file:{ROOT}/data/SS45DTE.duckdb?mode=ro',uri=True) as c:
 rows=c.execute("SELECT name,status,project_id,backtest_id,code,error_message FROM backtest_queue WHERE batch='ss45dte_funnel_20261026' ORDER BY id").fetchall()
summary=[]
for name,status,pid,bid,code,error in rows:
 item={'name':name,'local_status':status,'project_id':pid,'backtest_id':bid,'source_sha256':hashlib.sha256(code.encode()).hexdigest(),'local_error':error}
 if bid:
  try:
   response=request(user,token,'/backtests/read',{'projectId':pid,'backtestId':bid})
   bt=response.get('backtest',{})
   item.update(remote_status=bt.get('status'),progress=bt.get('progress'),runtime=bt.get('runtimeStatistics'),statistics=bt.get('statistics'),error=bt.get('error'),completed=bt.get('completed'))
   (OUT/(name+'.result.json')).write_text(json.dumps(response,indent=2)+'\n')
  except Exception as e:item['read_error']=str(e)
 summary.append(item)
(OUT/'latest.json').write_text(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),'runs':summary},indent=2)+'\n')
for r in summary: print(json.dumps(r))
