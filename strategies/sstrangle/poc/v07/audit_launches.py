"""Verify that every recorded experiment has exactly its intended native identity."""
import json,time
from campaign import ROOT,OUT,rows,credentials,request
u,t=credentials(ROOT/'data/S001.duckdb');records=rows();projects={r['project_id'] for r in records if r['project_id']};snapshots={}
for pid in projects:
 for attempt in range(6):
  try:snapshots[pid]=request(u,t,'/backtests/list',{'projectId':pid});break
  except RuntimeError:
   if attempt==5:raise
   time.sleep(min(2**attempt,15))
 (OUT/(str(pid)+'_native_backtests_list.json')).write_text(json.dumps(snapshots[pid],indent=2))
audit=[]
for row in records:
 matches=[b for b in snapshots.get(row['project_id'],{}).get('backtests',[]) if b.get('name')==row['name']]
 if row['backtest_id']:assert len(matches)==1 and matches[0]['backtestId']==row['backtest_id'],row['name']
 else:assert not matches,row['name']
 audit.append(dict(name=row['name'],backtest_id=row['backtest_id'],matching_native_executions=len(matches)))
(OUT/'native_launch_identity_audit.json').write_text(json.dumps(dict(status='passed',duplicate_runs=0,experiments=audit),indent=2));print('Native identities unique for',len(audit),'queue records')
