#!/usr/bin/env python3
"""Incrementally collect single-ticker QC evidence and run local research stages."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


STAGES = ('optimization', 'provider_export', 'provider_capture', 'provider_replay')


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)


def stage_complete(record):
    return all(record.get('stages', {}).get(stage) == 'complete' for stage in STAGES)


def preserve_partial_output(path):
    """Retain failed evidence while allowing exclusive-create stages to restart."""
    if path.exists():
        archived = path.with_name(path.name + '.incomplete.' + str(time.time_ns()))
        path.rename(archived)
        return archived


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    p.add_argument('--timeout',type=int,default=14400)
    args=p.parse_args()
    folder=args.folder.resolve()
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest.get('research_scope', '').startswith('Historical baseline') and not (folder/'research_plan.json').exists():
        raise ValueError('Historical campaign needs a frozen local optimization plan matching its dates')
    progress_path=folder/'local_progress.json'
    progress=json.loads(progress_path.read_text()) if progress_path.exists() else {}
    deadline=time.monotonic()+args.timeout
    last_collected=set()

    def run(command,log):
        with log.open('a') as f:
            subprocess.run([sys.executable,*map(str,command)],cwd=ROOT,
                           stdout=f,stderr=subprocess.STDOUT,check=True,timeout=2400)

    while time.monotonic()<deadline:
        outcome_path=folder/'outcomes.json'
        try:
            outcomes=json.loads(outcome_path.read_text()) if outcome_path.exists() else {}
        except json.JSONDecodeError:
            # The cloud runner may still be publishing its next snapshot.
            time.sleep(1)
            continue
        done={n for n,r in outcomes.items() if r['status']=='done'}
        if done-last_collected:
            try:
                run([HERE/'collect.py',folder,'--reuse-downloads'],folder/'collection.log')
                last_collected=done
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
                print('Collection incomplete; retrying cached downloads:',type(exc).__name__,flush=True)
                time.sleep(20)
                continue
        for name in sorted(done):
            ticker=name.rsplit('_',1)[1]
            source=folder/name
            if ticker in progress and progress[ticker].get('qc_source') != str(source):
                raise ValueError('Progress belongs to a different QC source; use a fresh local output folder')
            if ticker in progress and (stage_complete(progress[ticker]) or
                    progress[ticker].get('status', '').startswith('no complete audited')):
                continue
            local=folder/'local'/ticker
            local.mkdir(parents=True,exist_ok=True)
            record=progress.get(ticker, {'ticker':ticker,'qc_source':str(source),'stages':{}})
            if record['qc_source'] != str(source):
                raise ValueError('Progress belongs to a different QC source; use a fresh local output folder')
            progress[ticker]=record
            audit=json.loads((source/'audit.json').read_text())
            if audit.get('cycle_audit_skipped') or not audit.get('cycles'):
                record['status']='no complete audited option-only cycles; local optimization unavailable'
                progress[ticker]=record
                atomic_json(progress_path, progress)
                continue
            stages=[('optimization',[HERE/'local/optimize_single.py',source,'--output',local/'optimization'])]
            for stage,command in stages:
                if record['stages'].get(stage) == 'complete':
                    continue
                preserve_partial_output(local/'optimization')
                try:
                    run(command,local/(stage+'.log'))
                    record['stages'][stage]='complete'
                except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
                    record['stages'][stage]=type(exc).__name__+'; inspect preserved log'
                atomic_json(progress_path, progress)
            provider=local/'provider'
            for stage,command in [
                ('provider_export',[HERE/'local/prepare.py','--qc-source',source,'--output',provider]),
                ('provider_capture',[HERE/'local/capture.py',provider]),
                ('provider_replay',[HERE/'local/replay.py',provider])]:
                if record['stages'].get(stage) == 'complete':
                    continue
                if stage == 'provider_export':
                    preserve_partial_output(provider)
                    # A new export invalidates completion markers for its dependents.
                    for dependent in ('provider_capture', 'provider_replay'):
                        record['stages'].pop(dependent, None)
                elif stage == 'provider_replay':
                    for label in ('qc_control', 'provider_5min', 'provider_30min', 'provider_same_day_stale'):
                        preserve_partial_output(provider/label)
                try:
                    run(command,local/(stage+'.log'))
                    record['stages'][stage]='complete'
                except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
                    record['stages'][stage]=type(exc).__name__+'; inspect preserved log'
                    atomic_json(progress_path, progress)
                    break
                atomic_json(progress_path, progress)
            record['status']='complete' if stage_complete(record) else 'failed; rerun to resume incomplete stages'
            progress[ticker]=record
            atomic_json(progress_path, progress)
            print(ticker,record['stages'],flush=True)
        if len(outcomes)==len(manifest['jobs']) and all(r['status'] in ('done','failed') for r in outcomes.values()):
            break
        time.sleep(20)
    else:
        raise TimeoutError('Cloud/local pipeline deadline; evidence and progress retained')
    report=[]
    for label in manifest['variants']:
        record=progress.get(label,{'ticker':label,'status':'cloud failed or not collected'})
        summary=folder/'local'/label/'optimization/summary.json'
        if summary.exists():
            record['optimization']=json.loads(summary.read_text())
        provider=folder/'local'/label/'provider/replay_summary.json'
        if provider.exists():
            record['provider_replays']=json.loads(provider.read_text())
        report.append(record)
    atomic_json(folder/'local_summary.json', report)
    if any(record.get('status', '').startswith('failed;') for record in progress.values()):
        raise RuntimeError('Local stages failed; inspect local_progress.json and rerun to resume')
    print('Finished local processing:',folder,flush=True)


if __name__=='__main__':
    main()
