"""Wait for a frozen basket run, download its evidence, audit and save the report."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path)
    parser.add_argument('--timeout',type=int,default=11400)
    args=parser.parse_args();campaign=args.campaign.resolve()
    manifest=json.loads((campaign/'manifest.json').read_text())
    if manifest['phase'] not in ('basket','basket-regression') or manifest['variants']['basket']['lookback']!=504:
        raise ValueError('Full baseline pipeline requires the frozen 504-observation basket phase')
    progress=campaign/'pipeline_progress.json'
    state={}
    def checkpoint(stage,**values):
        state.update(stage=stage,updated_utc=datetime.now(timezone.utc).isoformat(),**values)
        temp=progress.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2));temp.replace(progress)
        current=HERE/'research/CURRENT_BASELINE_PROGRESS.json'
        if current.exists():
            saved=json.loads(current.read_text())
            if saved.get('campaign')==str(campaign):
                saved.update(status=stage,pipeline_checkpoint=state,updated_at=state['updated_utc'])
                if stage in ('complete','failed'):
                    saved['performance_valid'] = stage=='complete' and not saved.get('engineering_only',True)
                current.write_text(json.dumps(saved,indent=2)+'\n')
        print(json.dumps(state),flush=True)
    checkpoint('waiting_for_cloud')
    try:
        deadline=time.monotonic()+args.timeout
        while True:
            try:
                outcomes=json.loads((campaign/'outcomes.json').read_text())
            except (FileNotFoundError,json.JSONDecodeError):
                outcomes={}
            if len(outcomes)==len(manifest['jobs']):break
            if time.monotonic()>deadline:raise TimeoutError('Cloud results are not ready; preserve and inspect the queued job')
            time.sleep(10)
        name,record=next(iter(outcomes.items()))
        checkpoint('downloading_results',backtest_id=record['backtest_id'],cloud_status=record['status'])
        for attempt in range(3):
            try:
                subprocess.run([sys.executable,str(HERE/'collect.py'),str(campaign),'--reuse-downloads'],check=True,cwd=ROOT)
                break
            except subprocess.CalledProcessError:
                if attempt==2:raise
                time.sleep(10)
        evidence=campaign/name
        checkpoint('downloading_rust_orders')
        subprocess.run([str(ROOT/'target/release/qc-backtest-server'),'--data-dir',str(ROOT/'data'),
            'backtest-orders','--strategy','sstrangle','--name',name,'--out',str(evidence/'orders.rust.json')],
            check=True,cwd=ROOT)
        if record['status']!='done':
            raise RuntimeError('Cloud run failed; orders/logs retained but no baseline can be published')
        checkpoint('auditing_results')
        report=campaign/'baseline_report/summary.json'
        if report.exists() and (report.parent/'REPORT.md').exists():
            summary=json.loads(report.read_text())
            if summary['backtest_id']!=record['backtest_id'] or not all(summary['audits'].values()):
                raise ValueError('Existing report does not match this verified baseline')
        else:
            if report.parent.exists():
                archived=report.parent.with_name(report.parent.name+'.incomplete.'+
                    datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
                report.parent.rename(archived)
            subprocess.run([sys.executable,str(HERE/'basket_report.py'),str(campaign)],check=True,cwd=ROOT)
        summary=json.loads(report.read_text())
        checkpoint('complete',report=str(campaign/'baseline_report/REPORT.md'),
            baseline_outcome=summary.get('baseline_outcome','period_complete'),
            requested_period_complete=summary.get('requested_period_complete',True),
            observed_end=summary.get('observed_end'))
    except Exception as exc:
        checkpoint('failed',error=f'{type(exc).__name__}: {exc}')
        raise


if __name__=='__main__':main()
