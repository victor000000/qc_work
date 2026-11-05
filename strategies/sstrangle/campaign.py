#!/usr/bin/env python3
"""Collect predeclared discovery tests, freeze selection, and run untouched validation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def choose(rows, variants):
    eligible = [r for r in rows if int(r['closed_cycles']) >= 10]
    if not eligible:
        raise ValueError('No candidate has ten completed cycles; no qualifying improvement')
    eligible.sort(key=lambda r: (-float(r['cycle_net_pnl']), float(r['active_daily_mdd']), int(r['rolls'])))
    winner = eligible[0]
    label = next(label for label in variants if winner['name'].endswith('_'+label))
    return dict(candidate_label=label, candidate_config=variants[label], discovery_result=winner,
        eligible_candidates=[r['name'] for r in eligible],
        selected_at=time.strftime('%Y-%m-%d %H:%M:%S'),
        selection_rule='Highest net P&L with at least ten cycles, then lower drawdown, then fewer rolls')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('discovery', type=Path)
    args = parser.parse_args()
    folder = args.discovery.resolve()
    manifest = json.loads((folder/'manifest.json').read_text())
    expected = set(manifest['jobs'])
    deadline = time.monotonic() + 4000
    print(f'Waiting for {len(expected)} frozen discovery jobs', flush=True)
    while time.monotonic() < deadline:
        try:
            outcomes = json.loads((folder/'outcomes.json').read_text())
            if set(outcomes) == expected:
                break
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(10)
    else:
        raise TimeoutError('Discovery campaign deadline exceeded')
    subprocess.run([sys.executable, str(HERE/'collect.py'), str(folder)], check=True)
    rows = json.loads((folder/'summary.json').read_text())
    selected = choose(rows, manifest['variants'])
    selected['research_plan_sha256'] = hashlib.sha256((HERE/'research_plan.json').read_bytes()).hexdigest()
    selected['candidate_source_sha256'] = hashlib.sha256((folder/(selected['candidate_label']+'.py')).read_bytes()).hexdigest()
    selection = folder/'selection.json'
    selection.write_text(json.dumps(selected, indent=2))
    print('Frozen selection: '+json.dumps(selected), flush=True)
    # Collection takes place after the discovery driver has completed its final jobs.
    # The validation runner can reuse an existing shared server or start its own.
    before = set((HERE/'results').glob('strangle_validation_*'))
    subprocess.run([sys.executable, str(HERE/'run.py'), '--phase', 'validation', '--selection', str(selection)], check=True, cwd=ROOT)
    created = set((HERE/'results').glob('strangle_validation_*')) - before
    if len(created) != 1:
        raise RuntimeError('Cannot identify the validation result directory uniquely')
    validation = created.pop()
    (folder/'validation.json').write_text(json.dumps(dict(path=str(validation)), indent=2))
    subprocess.run([sys.executable, str(HERE/'collect.py'), str(validation)], check=True)
    print('Validation collected: '+str(validation), flush=True)


if __name__ == '__main__':
    main()
