"""Finish only this batch's native result/order receipts; never submit/restart jobs."""
import json,sys,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];P=Path(__file__).parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import qc_storage
from qc_api_check import credentials,request
u,t=credentials(ROOT/'data/S001.duckdb');last=None;end=time.monotonic()+2400
while time.monotonic()<end:
 with qc_storage.connect(f'file:{ROOT}/data/SS45DTE.duckdb?mode=ro',uri=True) as c:
  rows=c.execute("SELECT name,status,project_id,backtest_id,error_message FROM backtest_queue WHERE batch='ss45dte_funnel_20261026' ORDER BY id").fetchall()
 state=[(n,s,b) for n,s,p,b,e in rows]
 if state!=last:print('STATE',state,flush=True);last=state
 for name,status,pid,bid,error in rows:
  if status!='done' or not bid:continue
  rf=P/(name+'.reconciliation.json')
  if rf.exists():continue
  try:
   r=request(u,t,'/backtests/read',{'projectId':pid,'backtestId':bid});b=r['backtest']
   if not b.get('completed'):continue
   (P/(name+'.result.json')).write_text(json.dumps(r,indent=2)+'\n')
   orders=P/(name+'.orders.json')
   if not orders.exists():subprocess.run([str(ROOT/'target/release/qc-backtest-server'),'backtest-orders','--strategy','ss45dte','--name',name,'--out',str(orders)],cwd=ROOT,check=True,timeout=120)
   subprocess.run([sys.executable,str(P/'reconcile.py'),name],cwd=ROOT,check=True,timeout=30)
  except Exception as e:print(name,'READ_ERROR',str(e),flush=True)
 if all(s in ['done','failed','cancelled'] for n,s,p,b,e in rows):
  subprocess.run([sys.executable,str(P/'collect.py')],cwd=ROOT,stdout=(P/'collector_stdout.txt').open('w'),check=True,timeout=300)
  print('TERMINAL',flush=True);break
 time.sleep(20)
else:print('Receipt wait deadline reached; remote jobs unchanged.',flush=True)
