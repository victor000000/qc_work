"""Repair an orphaned local queue row from pinned genuine terminal QC evidence.

Does not submit/cancel backtests or start a server. A missing runner is never
proof of cloud completion. Run report.py first to collect a full terminal read.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import report as shared


def terminal_values(row, payload):
    if payload.get('success') is False or payload.get('errors'):
        raise ValueError('API-error response cannot repair queue state')
    full = payload['backtest']
    shared.validate_identity(full,row)
    status = shared.terminal_status(full)
    if full.get('completed') is not True or status not in ('done','failed'):
        raise ValueError('A nonterminal cloud execution must remain untouched')
    old = row.get('result_json')
    if old:
        stored = json.loads(old) if isinstance(old,str) else old
        stored = stored.get('backtest',stored)
        for remote,local in [('projectId','project_id'),('backtestId','backtest_id')]:
            if remote in stored and str(stored[remote])!=str(row[local]):
                raise ValueError('Existing result has a conflicting cloud identity; preserve and investigate')
    return dict(status=status,error_message=full.get('error') or
                ('Cloud terminal state: '+str(full.get('status')) if status=='failed' else None),
                result_json=json.dumps(full,allow_nan=False))


def apply_terminal(conn,row,values):
    # The storage context holds the transaction. A changed identity/hash fails
    # the update and rolls back rather than touching a replacement execution.
    changed = conn.execute('UPDATE backtest_queue SET status=?,error_message=?,result_json=? '
        'WHERE name=? AND project_id=? AND backtest_id=? AND code_hash=?',
        (values['status'],values['error_message'],values['result_json'],row['name'],
         row['project_id'],row['backtest_id'],row['code_hash']))
    if changed.rowcount!=1:
        raise ValueError('Frozen queue identity/source changed before recovery')
    actual=dict(conn.execute('SELECT * FROM backtest_queue WHERE name=?',(row['name'],)).fetchone())
    if any(actual[k]!=values[k] for k in values):
        raise ValueError('Terminal queue repair did not read back exactly')


def active_owners():
    result=[]
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        server=bool(args and Path(args[0]).name=='qc-backtest-server' and 'serve' in args)
        owner=any(a=='strategies/sstrangle/run.py' or a.endswith('/strategies/sstrangle/run.py') for a in args)
        if server or owner:result.append(int(proc.name))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path)
    p.add_argument('--apply',action='store_true',help='Apply verified terminal state only; preserve IDs/source and previous local evidence')
    args=p.parse_args();c=args.campaign.resolve();m=json.loads((c/'manifest.json').read_text())
    if m['phase']!='basket-calmar':raise ValueError('Only existing basket-calmar campaigns are supported')
    lock=(c/'terminal_queue_recovery.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Another terminal recovery owns this campaign');return
    owners=active_owners()
    if args.apply and owners:raise ValueError('A local run/server owner remains live; wait for natural completion: '+repr(owners))
    results=[]
    for name in m['jobs']:
        key,cfg=shared.config_for(name,m)
        with shared.storage.connect(f'file:{shared.ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as conn:
            conn.row_factory=shared.storage.Row;saved=conn.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone()
        if saved is None:raise ValueError('Existing research queue job is missing')
        row=dict(saved);source=shared.verify_frozen_source(c,key,cfg,row)
        payload=shared.verified_terminal_cache(c/name,row)
        if payload is None:
            results.append(dict(name=name,applied=False,reason='No trusted full terminal cache; collect same cloud execution with report.py. No completion inferred.'))
            continue
        values=terminal_values(row,payload)
        unchanged=all(row.get(k)==values[k] for k in values)
        r=dict(name=name,project_id=row['project_id'],backtest_id=row['backtest_id'],
               previous_status=row['status'],confirmed_cloud_status=values['status'],
               applied=False,already_matches=unchanged,source_proof=source,
               terminal_evidence_sha256=hashlib.sha256((c/name/'backtest.json').read_bytes()).hexdigest(),
               research_qualification_not_set=True)
        if args.apply and not unchanged:
            before={k:row.get(k) for k in ('name','status','error_message','result_json','project_id','backtest_id','code_hash')}
            digest=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
            prior=c/name/('queue_before_recovery_'+digest[:16]+'.json')
            if not prior.exists():shared.atomic_json(prior,before)
            with shared.storage.connect(str(shared.ROOT/'data/SSTRANGLE.duckdb')) as conn:
                conn.row_factory=shared.storage.Row;apply_terminal(conn,row,values)
            r.update(applied=True,preserved_previous_queue_state=str(prior))
        results.append(r)
    receipt=dict(utc=datetime.now(timezone.utc).isoformat(),mode='apply' if args.apply else 'preview',
                 campaign=str(c),active_local_owners=owners,results=results,
                 cloud_execution_submitted_or_cancelled=False,server_started=False,
                 strategy_calmar_proven=False)
    shared.atomic_json(c/'terminal_queue_recovery.json',receipt)
    with (c/'terminal_queue_recovery_history.jsonl').open('a') as history:history.write(json.dumps(receipt)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
