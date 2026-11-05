"""Resume collection of an existing QC basket without restarting or cancelling it."""
import argparse
from datetime import datetime,timezone
import fcntl
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import qc_storage as storage
from qc_api_check import credentials,request


def atomic_json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n')
    temporary.replace(path)


def terminal_status(backtest):
    if backtest.get('error'):
        return 'failed'
    if not backtest.get('completed'):
        return None
    return 'done' if backtest.get('status','').rstrip('.')=='Completed' else 'failed'


def validate_identity(backtest,row):
    for remote,local in [('projectId','project_id'),('backtestId','backtest_id')]:
        if str(backtest.get(remote))!=str(row[local]):
            raise ValueError('Cloud response identity differs from frozen execution: '+remote)


def read_existing_backtest(user, token, row):
    """Read this execution directly; fall back only to verified live listing metadata.

    List responses can lag actual progress and contain thousands of old jobs.
    During initialization a direct read can time out, so a matching nonterminal
    listing still establishes a live execution. A terminal listing is never a
    substitute for the complete read required to collect/audit results.
    """
    ids = dict(projectId=row['project_id'], backtestId=row['backtest_id'])
    try:
        response = request(user, token, '/backtests/read', ids)
    except (OSError, TimeoutError, ConnectionError) as read_error:
        # Transport failure alone says nothing about the cloud execution state.
        listing = request(user, token, '/backtests/list', dict(projectId=row['project_id']))
        if 'backtests' not in listing:
            raise ValueError('Fallback listing omitted backtests; cannot infer execution state') from read_error
        candidates = [b for b in listing['backtests']
            if str(b.get('backtestId')) == str(row['backtest_id'])]
        if len(candidates) > 1:
            raise ValueError('Duplicate cloud execution identity in listing') from read_error
        if candidates:
            b = candidates[0]
            validate_identity(b, row)
            if not b.get('completed') and not b.get('error'):
                return dict(backtest=b, status_source='backtests/list after read transport failure; existing nonterminal execution unchanged',
                    read_issue=type(read_error).__name__)
        raise RuntimeError('Full backtest read unavailable; terminal/missing listing cannot replace complete result evidence; retry same execution') from read_error
    validate_identity(response['backtest'], row)
    return response


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path)
    args=parser.parse_args();campaign=args.campaign.resolve()
    manifest=json.loads((campaign/'manifest.json').read_text())
    if manifest['phase']!='basket' or len(manifest['jobs'])!=1:
        raise ValueError('Resume requires one existing full basket job')
    lock=(campaign/'resume.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another collector already owns this campaign');return
    name=manifest['jobs'][0]
    with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as connection:
        connection.row_factory=storage.Row
        record=connection.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone()
        if record is None:raise ValueError('Frozen job is missing from Rust queue')
        row=dict(record)
    if not row['project_id'] or not row['backtest_id']:
        raise ValueError('No existing cloud execution to resume; never submit a replacement here')
    user,token=credentials(ROOT/'data/S001.duckdb')
    response=read_existing_backtest(user,token,row)
    backtest=response['backtest'];validate_identity(backtest,row)
    now=datetime.now(timezone.utc).isoformat();status=terminal_status(backtest)
    snapshot=dict(utc=now,backtest_id=row['backtest_id'],status=backtest.get('status'),
        progress=backtest.get('progress'),completed=backtest.get('completed'),error=backtest.get('error'),
        runtime_statistics=backtest.get('runtimeStatistics'),performance_valid=False)
    atomic_json(campaign/'cloud_progress.json',snapshot)
    atomic_json(campaign/'resumed_cloud_response.json',response)
    current=HERE/'research/CURRENT_BASELINE_PROGRESS.json'
    if current.exists():
        saved=json.loads(current.read_text())
        if saved.get('campaign')==str(campaign):
            saved.update(updated_at=now,backtest_id=row['backtest_id'],latest_cloud_snapshot=snapshot,
                status='cloud completed; collecting' if status=='done' else
                'cloud failed; preserving evidence' if status=='failed' else 'existing cloud backtest: '+str(backtest.get('status')),
                performance_valid=False,pipeline_log=str(ROOT/'.local/verification/basket_full_corrected_pipeline_20261018.log'))
            atomic_json(current,saved)
    print(json.dumps(snapshot),flush=True)
    if status is None:
        return
    if row['status'] not in ('running','done','failed'):
        raise ValueError('Unexpected queue state for the existing cloud execution')
    outcome={key:row.get(key) for key in ('name','project_id','backtest_id','runtime_seconds','code_hash')}
    outcome.update(status=status,error_message=backtest.get('error') or
        (None if status=='done' else 'Cloud terminal state: '+str(backtest.get('status'))),
        result=backtest,recovered_from_cloud_api=True)
    previous=campaign/'outcomes.json'
    if previous.exists():
        old=json.loads(previous.read_text()).get(name)
        if old and old.get('backtest_id')!=row['backtest_id']:
            raise ValueError('Existing outcome belongs to a different execution')
    with storage.connect(str(ROOT/'data/SSTRANGLE.duckdb')) as connection:
        connection.execute('UPDATE backtest_queue SET status=?,error_message=?,result_json=? '
            'WHERE name=? AND backtest_id=?',
            (status,outcome['error_message'],json.dumps(backtest),name,row['backtest_id']))
    atomic_json(campaign/(name+'.json'),outcome)
    atomic_json(previous,{name:outcome})
    subprocess.run([sys.executable,str(HERE/'basket_pipeline.py'),str(campaign)],check=True,cwd=ROOT)


if __name__=='__main__':main()
