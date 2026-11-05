"""Reconcile only proven terminal jobs after the serial manual campaign."""
import json,hashlib,sys
from datetime import datetime,timezone
from campaign import ROOT,OUT,PROJECT,PREFIX,storage,credentials,read,rows
sys.path.insert(0,str(ROOT/'strategies/sstrangle/optimization'))
from recover_terminal_research import terminal_values,apply_terminal,active_owners
assert not active_owners(),'A queue server owns recovery; leave it untouched'
u,t=credentials(ROOT/'data/S001.duckdb');nodes=read(u,t,'/projects/nodes/read',{'projectId':PROJECT});assert all(not n['busy'] for n in nodes['nodes']['backtest']);(OUT/'nodes_final.json').write_text(json.dumps(nodes,indent=2))
listing=read(u,t,'/backtests/list',{'projectId':PROJECT});(OUT/'native_backtests_list_final.json').write_text(json.dumps(listing,indent=2));receipts=[]
for row in rows():
 key=row['name'].removeprefix(PREFIX).lower();matches=[b for b in listing['backtests'] if b['name']==row['name']];assert len(matches)==1 and matches[0]['backtestId']==row['backtest_id']
 terminal=json.loads((OUT/(key+'_terminal.json')).read_text());assert terminal['backtest']['completed'] and not terminal['backtest'].get('error');assert (OUT/(key+'_consistency.json')).exists()
 with storage.connect(str(ROOT/'data/SSTRANGLE.duckdb')) as db:
  db.row_factory=storage.Row;full=dict(db.execute('SELECT * FROM backtest_queue WHERE name=?',(row['name'],)).fetchone());m=json.loads((OUT/(key+'_manifest.json')).read_text());assert hashlib.sha256(full['code'].encode()).hexdigest()==m['source_sha256']
  snapshot=OUT/(key+'_queue_before_recovery.json')
  if not snapshot.exists():snapshot.write_text(json.dumps(full,indent=2))
  values=terminal_values(full,terminal);apply_terminal(db,full,values)
 receipts.append(dict(name=row['name'],backtest_id=row['backtest_id'],native_status=values['status'],native_instances=len(matches)))
(OUT/'terminal_queue_recovery.json').write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),status='passed',worker_started=False,cloud_runs_cancelled_or_submitted=False,rows=receipts),indent=2));print('Reconciled',len(receipts),'unique terminal native jobs; node idle')
