"""Recover the same ZW cloud regression; never cancel, queue or duplicate a job."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime,timezone
from resume_basket import atomic_json,read_existing_backtest,terminal_status,validate_identity
import qc_storage as storage

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path)
    args=parser.parse_args();campaign=args.campaign.resolve()
    manifest=json.loads((campaign/'manifest.json').read_text())
    if manifest['phase']!='basket-zw-regression' or len(manifest['jobs'])!=1:
        raise ValueError('Expected one frozen ZW regression')
    name=manifest['jobs'][0]
    with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as c:
        c.row_factory=storage.Row
        row=dict(c.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone())
    if not row.get('backtest_id'):raise ValueError('No existing cloud execution; never submit here')
    u,t=credentials(ROOT/'data/S001.duckdb');response=read_existing_backtest(u,t,row)
    b=response['backtest'];validate_identity(b,row);status=terminal_status(b)
    snapshot=dict(utc=datetime.now(timezone.utc).isoformat(),backtest_id=row['backtest_id'],
        status=b.get('status'),completed=b.get('completed'),progress=b.get('progress'),error=b.get('error'))
    atomic_json(campaign/'cloud_progress.json',snapshot)
    print(json.dumps(snapshot),flush=True)
    if status is None:return
    # The old poller was stopped solely to prevent its automatic deletion
    # after a local timeout. Stop that *local process* only after the cloud
    # is confirmed terminal; never resume its obsolete cleanup callback.
    protected=campaign/'local_poll_protected.json'
    if protected.exists():
        protection=json.loads(protected.read_text())
        if protection['cloud']['backtestId']!=row['backtest_id']:
            raise ValueError('Protection belongs to another execution')
        pid=int(protection['server_pid']);proc=Path('/proc')/str(pid)
        if proc.exists():
            command=(proc/'cmdline').read_bytes()
            if b'qc-backtest-server' not in command or b'serve' not in command:
                raise ValueError('Protected PID was reused')
            state=(proc/'status').read_text().split('State:',1)[1].splitlines()[0]
            if 'T' not in state:raise ValueError('Expected the protected stopped poller')
            os.kill(pid,signal.SIGKILL)
            deadline=time.monotonic()+20
            while proc.exists() and time.monotonic()<deadline:time.sleep(.25)
            if proc.exists():raise RuntimeError('Old local poller has not been reaped')
        protection.update(cloud_terminal=True,local_poller_stopped_after_cloud_terminal=True)
        atomic_json(protected,protection)
    outcome={k:row.get(k) for k in ('name','project_id','backtest_id','runtime_seconds','code_hash')}
    outcome.update(status=status,error_message=b.get('error'),result=b,recovered_from_cloud_api=True)
    with storage.connect(str(ROOT/'data/SSTRANGLE.duckdb')) as c:
        c.execute('UPDATE backtest_queue SET status=?,error_message=?,result_json=? WHERE name=? AND backtest_id=?',
            (status,b.get('error'),json.dumps(b),name,row['backtest_id']))
    atomic_json(campaign/(name+'.json'),outcome);atomic_json(campaign/'outcomes.json',{name:outcome})
    command=[sys.executable,str(HERE/'zw_regression_report.py'),str(campaign)]
    if name.endswith('_zw_control'):command.append('--control')
    subprocess.run(command,check=True,cwd=ROOT)


if __name__=='__main__':main()
