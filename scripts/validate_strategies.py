#!/usr/bin/env python3
"""Validate S001/S002 baselines and SML01 train/infer through an isolated real server.

Run with .venv/bin/python scripts/validate_strategies.py --live. The default only
renders/validates files. Live mode owns a disposable project and UUID ObjectStore
namespace; production queues, models and strategy sources are never changed.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import signal
import qc_storage as storage
import subprocess
import sys
import tempfile
import time
import uuid
try:
    from .qc_api_check import ROOT, credentials, request
    from .cleanup_smoke_projects import cleanup_record
except ImportError:
    from qc_api_check import ROOT, credentials, request
    from cleanup_smoke_projects import cleanup_record


def baseline_specs(prefix):
    from lb.harness.orchestrator import render_train_config, render_infer_cell
    from lb.harness.psuf import cell_suffix
    cfg = {'ticker': 'GLD', 'axis': 'vol', 'labeler': 'tertile', 'sizing': 'binary',
           'thresh': 0.45, 'max_depth': 3, 'n_components': 20, 'reduce': 'correlation',
           'features': 'base', 'calibration': 'isotonic', 'permute_labels': False,
           'rebal_band': 0.01, 'horizons': None, 'train_purge': False}
    train, extra = render_train_config(cfg)
    cell = f"{cfg['axis']}_{cfg['labeler']}_{cfg['sizing']}_t45" + cell_suffix(cfg)
    specs = [
        ('s001', 'baseline_s001', (ROOT / 'strategies/s001/s001_20260628_base.py').read_text(), {}),
        ('s002', 'baseline_s002', (ROOT / 'strategies/s002/s002_20260628_ls_base.py').read_text(), {}),
        ('sml01', 'baseline_sml01_train', train, extra),
        ('sml01', 'baseline_sml01_infer', render_infer_cell('GLD', cell), {}),
    ]
    out = []
    for strategy, name, code, extras in specs:
        files = {'main.py': code, **extras}
        files = {filename: source.replace('autoresearch/', prefix) for filename, source in files.items()}
        for filename, source in files.items():
            ast.parse(source, filename=filename)
            if len(source.encode('utf-8')) > 128000:
                raise ValueError(f'{name}/{filename} exceeds QC file size')
        out.append((strategy, name, files.pop('main.py'), files))
    return out


def wait_result(data, strategy, name, server, timeout):
    path = data / f'{strategy.upper()}.duckdb'
    deadline, previous = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f'server exited with {server.returncode}')
        with storage.connect(path) as conn:
            row = conn.execute('SELECT status,error_message,result_json FROM backtest_queue WHERE name=?', (name,)).fetchone()
        if row[0] != previous:
            print(f'{name}: {row[0]}', flush=True)
            previous = row[0]
        if row[0] == 'failed':
            raise RuntimeError(row[1])
        if row[0] == 'done':
            result = json.loads(row[2])
            if 'Total Orders' not in result.get('statistics', {}):
                raise RuntimeError('completed result has no final statistics')
            return result
        time.sleep(1)
    raise TimeoutError(f'{name} exceeded {timeout}s')


def stop_server(server):
    if server and server.poll() is None:
        server.send_signal(signal.SIGTERM)
        try:
            server.wait(timeout=155)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
            raise RuntimeError('server did not complete bounded graceful shutdown')
        if server.returncode:
            raise RuntimeError(f'server exited with {server.returncode}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--strategies', default='s001,s002,sml01', help='Comma-separated strategy IDs')
    parser.add_argument('--timeout', type=int, default=900, help='Per-job deadline, seconds')
    args = parser.parse_args()
    nonce = uuid.uuid4().hex
    prefix = f'qcv/{nonce}/'
    selected = set(args.strategies.split(','))
    if not selected or not selected <= {'s001','s002','sml01'}:
        parser.error('--strategies accepts s001,s002,sml01')
    specs = [spec for spec in baseline_specs(prefix) if spec[0] in selected]
    if not args.live:
        print(json.dumps([{'strategy': s, 'name': n, 'files': ['main.py', *e]} for s,n,_,e in specs], indent=2))
        return
    binary = ROOT / 'target/release/qc-backtest-server'
    user, token = credentials(ROOT / 'data/S001.duckdb')
    with storage.connect((ROOT / 'data/S001.duckdb').as_uri() + '?mode=ro', uri=True) as conn:
        org = os.getenv('QC_ORGANIZATION_ID') or conn.execute("SELECT value FROM settings WHERE category='project' AND key='organization_id'").fetchone()[0]
    artifacts = ROOT / '.local/verification' / f'strategy-baselines-{nonce}'
    artifacts.mkdir(parents=True)
    outcomes, server, record = {}, None, None
    with tempfile.TemporaryDirectory(prefix='qc-baselines-') as folder:
        data = Path(folder)
        for strategy in ['s001','s002','sml01']:
            subprocess.run([str(binary),'--data-dir',folder,'init-strategy','--strategy',strategy], check=True, capture_output=True)
        with storage.connect(data / 'S001.duckdb') as conn:
            conn.executemany('INSERT OR REPLACE INTO settings(category,key,value) VALUES (?,?,?)',
                [('credentials','qc_user_id',user),('credentials','qc_api_token',token),('project','organization_id',org)])
        created = request(user,token,'/projects/create',{'name':f'qc-work-smoke-{nonce}','language':'Py','organizationId':org})['projects'][0]
        pid = created['projectId']
        record = ROOT / f'.local/verification/pending-cloud/{pid}.json'
        record.parent.mkdir(parents=True,exist_ok=True)
        owned = {'project_id':pid,'name':created['name']}
        if 'sml01' in selected:
            owned.update(object_store_prefix=prefix,organization_id=org)
        record.write_text(json.dumps(owned))
        print(f'Owned validation project {pid}; ObjectStore prefix {prefix}',flush=True)
        (data / 'projects.json').write_text(json.dumps({'projects':[pid]}))
        try:
            child_env = dict(os.environ)
            for key in ['QC_DATA_DIR','QC_USER_ID','QC_API_TOKEN','QC_ORGANIZATION_ID']:
                child_env.pop(key,None)
            with (artifacts / 'server.log').open('w') as log:
                server = subprocess.Popen([str(binary),'--data-dir',folder,'serve'],env=child_env,stdout=log,stderr=subprocess.STDOUT)
                for strategy,name,code,extras in specs:
                    try:
                        if name.endswith('_infer') and outcomes.get('baseline_sml01_train',{}).get('error'):
                            raise RuntimeError('training failed; inference cannot run')
                        main_path, extras_path = data / 'submit.py', data / 'extra.json'
                        main_path.write_text(code)
                        extras_path.write_text(json.dumps(extras))
                        subprocess.run([str(binary),'--data-dir',folder,'queue','--strategy',strategy,'--name',name,'--code-file',str(main_path),'--extra-files',str(extras_path)], check=True,capture_output=True)
                        result = wait_result(data,strategy,name,server,args.timeout)
                        outcomes[name] = result
                        if name.endswith('_train') and int(result.get('runtimeStatistics',{}).get('n_cells','0')) < 1:
                            raise RuntimeError('SML01 training produced no model cells')
                        if name.endswith('_infer'):
                            runtime = result.get('runtimeStatistics', {})
                            if min(int(runtime.get('n_predictions', '0')), int(runtime.get('n_replayed_predictions', '0'))) < 1:
                                raise RuntimeError('SML01 inference did not load and replay predictions')
                        outcomes[name] = result
                        print(f'{name}: validated',flush=True)
                    except Exception as error:
                        outcomes[name] = {**outcomes.get(name, {}), 'error':str(error)}
                        print(f'{name}: failed: {error}',flush=True)
        finally:
            try:
                stop_server(server)
            finally:
                for log_path in (data / 'logs').glob('*'):
                    if log_path.is_file():
                        shutil.copy2(log_path,artifacts / log_path.name)
                (artifacts / 'results.json').write_text(json.dumps(outcomes,indent=2))
                cleanup_record(record,user,token)
                print(f'Cleaned validation project {pid} and owned ObjectStore keys',flush=True)
    if any('error' in result for result in outcomes.values()):
        raise RuntimeError(f'Baseline validation failed; see {artifacts / "results.json"}')
    print(f'All strategy baselines validated; evidence: {artifacts}',flush=True)


if __name__ == '__main__':
    main()
