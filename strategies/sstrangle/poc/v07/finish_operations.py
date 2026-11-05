"""Stop only the task-owned idle server, then reconcile proven terminal local rows."""
import argparse,hashlib,json,os,signal,sys,time
from pathlib import Path
from datetime import datetime,timezone
from campaign import ROOT,OUT,storage
from qc_api_check import credentials
from transport import request
sys.path.insert(0,str(ROOT/'strategies/sstrangle/optimization'))
from recover_terminal_research import terminal_values,apply_terminal,active_owners
p=argparse.ArgumentParser();p.add_argument('--owned-server-pid',type=int,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
known={}
for path in OUT.glob('*_terminal.json'):
 b=json.loads(path.read_text())['backtest']
 assert b['completed']
 known[(int(b['projectId']),b['backtestId'])]=path
pending=[]
for db in (ROOT/'data').glob('S*.duckdb'):
 with storage.connect(f'file:{db}?mode=ro',uri=True) as c:
  c.row_factory=storage.Row
  for row in c.execute("SELECT name,status,project_id,backtest_id FROM backtest_queue WHERE status IN ('queued','running')"):
   row=dict(row)
   assert row['name'].startswith('SSTRANGLE_OO07_20261024_'), 'Unrelated active work: leave server untouched'
   assert (row['project_id'],row['backtest_id']) in known, 'Missing full terminal proof: leave server untouched'
   pending.append(row)
with storage.connect(f'file:{ROOT}/data/S001.duckdb?mode=ro',uri=True) as c:
 org=os.getenv('QC_ORGANIZATION_ID') or c.execute("SELECT value FROM settings WHERE category='project' AND key='organization_id'").fetchone()[0]
u,t=credentials(ROOT/'data/S001.duckdb');nodes=request(u,t,'/nodes/read',{'organizationId':org})
(OUT/'nodes_final.json').write_text(json.dumps(nodes,indent=2))
assert nodes.get('backtest') and all(not n['busy'] for n in nodes['backtest']), 'Native compute remains busy'
proc=Path('/proc')/str(a.owned_server_pid)
if proc.exists():
 cmd=(proc/'cmdline').read_bytes().decode().split('\0')
 assert Path(cmd[0]).name=='qc-backtest-server' and 'serve' in cmd and (proc/'cwd').resolve()==ROOT
 if a.apply:
  os.kill(a.owned_server_pid,signal.SIGINT)
  for i in range(60):
   if not proc.exists():break
   time.sleep(1)
  assert not proc.exists(),'Server still owns local queue; recovery not applied'
if a.apply:assert not active_owners()
receipts=[]
for row in pending:
 with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as c:
  c.row_factory=storage.Row;fullrow=dict(c.execute('SELECT * FROM backtest_queue WHERE name=?',(row['name'],)).fetchone())
 key=row['name'].removeprefix('SSTRANGLE_OO07_20261024_').lower()
 manifest=json.loads((OUT/(key+'_manifest.json')).read_text())
 assert hashlib.sha256(fullrow['code'].encode()).hexdigest()==manifest['source_sha256']
 path=known[(row['project_id'],row['backtest_id'])];values=terminal_values(fullrow,json.loads(path.read_text()))
 prior=OUT/(key+'_queue_before_recovery.json')
 if a.apply:
  if not prior.exists():prior.write_text(json.dumps(fullrow,indent=2))
  with storage.connect(str(ROOT/'data/SSTRANGLE.duckdb')) as c:
   c.row_factory=storage.Row;apply_terminal(c,fullrow,values)
 receipts.append(dict(name=row['name'],previous_status=row['status'],native_status=values['status'],source_sha256=manifest['source_sha256'],terminal_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),applied=a.apply))
receipt=dict(utc=datetime.now(timezone.utc).isoformat(),owned_server_pid=a.owned_server_pid,server_stopped=a.apply,cloud_runs_cancelled_or_submitted=False,rows=receipts)
(OUT/'terminal_queue_recovery.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
