#!/usr/bin/env python3
"""Verify the SPX clock fix, retain the failed attempt and publish a corrected run."""
import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import qc_storage as storage

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BINARY=ROOT/'target/release/qc-backtest-server'


def read_job(name):
    with storage.connect(ROOT/'data/SSTRANGLE.duckdb') as c:
        c.row_factory=storage.Row
        row=c.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone()
        return dict(row) if row else None


def wait_job(name,server):
    last=None;deadline=time.monotonic()+7200
    while time.monotonic()<deadline:
        if server and server.poll() is not None:
            raise RuntimeError('Owned Rust server exited during SPX repair')
        row=read_job(name)
        if row and row['status']!=last:
            print(name,row['status'],row['project_id'],row['backtest_id'],flush=True)
            last=row['status']
        if row and row['status'] in ('done','failed'):
            if row['status']=='failed':
                raise RuntimeError(row['error_message'])
            return row
        time.sleep(10)
    raise TimeoutError('SPX repair deadline; queue and cloud identities retained')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('batch',type=Path)
    p.add_argument('--wait-pid',type=int)
    p.add_argument('--server-proxy',help='Optional scoped proxy for the Rust server only')
    p.add_argument('--backtest-timeout-secs',type=int,default=1800)
    args=p.parse_args()
    batch=args.batch.resolve()
    # The original batch runner owns its server and shuts it down at completion.
    # Wait for that lifecycle before starting another owned run.
    if args.wait_pid:
        print('Waiting for original batch runner',args.wait_pid,flush=True)
        while True:
            try:
                os.kill(args.wait_pid,0)
            except ProcessLookupError:
                break
            time.sleep(10)
    pid_file=ROOT/'data/qc-server.pid'
    existing=False
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text().strip()),0);existing=True
        except (ValueError,ProcessLookupError):
            pass
    server=None;log=None
    if not existing:
        log=(batch/'spx_repair_server.log').open('a')
        server_env=os.environ.copy()
        server_env['QC_BACKTEST_TIMEOUT_SECS']=str(args.backtest_timeout_secs)
        if args.server_proxy:
            for key in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:
                server_env[key]=args.server_proxy
        server=subprocess.Popen([str(BINARY),'--data-dir',str(ROOT/'data'),'serve'],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=server_env)
    try:
        smoke=wait_job('SSTRANGLE_20261017_SPX_CLOCK_SMOKE',server)
        result=json.loads(smoke['result_json'])
        rt=result['runtimeStatistics']
        if int(rt.get('entries',0))<1 or int(rt['open_cycles'])!=0 or abs(float(rt['pnl_reconciliation_difference']))>.05:
            raise RuntimeError('SPX clock smoke did not reconcile')
        (batch/'SPX_clock_smoke_result.json').write_text(json.dumps(dict(
            project_id=smoke['project_id'],backtest_id=smoke['backtest_id'],result=result),indent=2))
        manifest=json.loads((batch/'manifest.json').read_text())
        old_name=next(n for n in manifest['jobs'] if n.endswith('_SPX'))
        name=old_name.removesuffix('_SPX')+'_clockfix_SPX'
        source=(HERE/'project/main.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(manifest['variants']['SPX']),1)
        ast.parse(source)
        path=batch/'SPX_clock_corrected.py';path.write_text(source)
        if not read_job(name):
            subprocess.run([str(BINARY),'--data-dir',str(ROOT/'data'),'queue','--strategy','sstrangle',
                '--name',name,'--batch',manifest['batch']+'_spx_repair','--priority','0',
                '--code-file',str(path),'--extra-files',str(batch/'extra_files.json')],check=True)
        previous=read_job(name)
        if previous and previous['status']=='failed' and 'backtest_timeout' in (previous['error_message'] or ''):
            archived={k:previous[k] for k in ['name','status','error_message','project_id','backtest_id','runtime_seconds','code_hash']}
            archive=batch/('SPX_timeout_attempt_'+str(previous['backtest_id'])+'.json')
            if not archive.exists():
                archive.write_text(json.dumps(archived,indent=2))
            subprocess.run([str(BINARY),'--data-dir',str(ROOT/'data'),'retry','--strategy','sstrangle','--name',name],check=True)
        row=wait_job(name,server)
        record={k:row[k] for k in ['name','status','error_message','project_id','backtest_id','runtime_seconds','code_hash']}
        record['result']=json.loads(row['result_json'])
        outcomes=json.loads((batch/'outcomes.json').read_text())
        if old_name in outcomes:
            (batch/'SPX_initial_failed_outcome.json').write_text(json.dumps(outcomes[old_name],indent=2))
            outcomes.pop(old_name)
        outcomes[name]=record
        old_source=batch/'SPX.initial_failed.py'
        if not old_source.exists():
            old_source.write_bytes((batch/'SPX.py').read_bytes())
        (batch/'SPX.py').write_text(source)
        (batch/(name+'.json')).write_text(json.dumps(record,indent=2))
        manifest['jobs']=[name if n==old_name else n for n in manifest['jobs']]
        manifest.setdefault('source_amendments',[]).append(dict(ticker='SPX',
            reason='Quote timestamps compared to security.local_time; original run incorrectly compared Chicago to New York',
            failed_job=old_name,successful_job=name,original_source=old_source.name,
            smoke_backtest_id=smoke['backtest_id'],published_utc=datetime.now(timezone.utc).isoformat()))
        for filename,value in [('outcomes.json',outcomes),('manifest.json',manifest)]:
            temp=batch/(filename+'.tmp');temp.write_text(json.dumps(value,indent=2));temp.replace(batch/filename)
        print('Published corrected SPX identity',name,flush=True)
    finally:
        if server and server.poll() is None:
            server.send_signal(signal.SIGTERM)
            try:
                server.wait(timeout=155)
            except subprocess.TimeoutExpired:
                server.kill();server.wait()
        if log:
            log.close()
    # Use HTTP proxy settings for urllib-based result downloads; the Rust server
    # used its inherited SOCKS proxy during the cloud run.
    consumer_env=os.environ.copy()
    for key in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:
        value=consumer_env.get(key,'')
        if value.startswith('socks'):
            consumer_env.pop(key,None)
    for script in ['single_pipeline.py','single_features.py','local/validate_provider_selection.py','single_report.py']:
        subprocess.run([sys.executable,str(HERE/script),str(batch)],cwd=ROOT,env=consumer_env,check=True)


if __name__=='__main__':
    main()
