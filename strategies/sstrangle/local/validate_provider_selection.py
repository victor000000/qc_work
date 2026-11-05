#!/usr/bin/env python3
"""Stress frozen per-ticker selections on covered 2026 provider-price cycles."""
import argparse
import csv
import json
from pathlib import Path

from optimize_single import allowed
from replay import covered_rows, run_engine


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('batch',type=Path)
    args=p.parse_args()
    for local in sorted((args.batch/'local').iterdir()):
        source=local/'provider'
        selection_path=local/'optimization/selection.json'
        coverage=source/'price_coverage.csv'
        if not coverage.exists() or not selection_path.exists():
            continue
        out=local/'provider_selection_validation'
        out.mkdir(exist_ok=True)
        if (out/'summary.json').exists():
            continue
        selection=json.loads(selection_path.read_text())
        capital=json.loads((source/'manifest.json').read_text())['initial_cash']
        rows=list(csv.DictReader(coverage.open()))
        for r in rows:
            r['age_minutes']=float(r['age_minutes']) if r['age_minutes'] else None
            r['provider_price']=float(r['provider_price']) if r['provider_price'] else None
        valid_ids=set();selected_ids=set()
        for r in rows:
            if r['tag'].split(';')[0].endswith(':OPEN') and r['timestamp'][:10]>='2026-01-01':
                valid_ids.add(r['cycle_id'])
                f=dict(v.split('=',1) for v in r['tag'].split(';')[1:] if '=' in v)
                if allowed(f,selection['config']):
                    selected_ids.add(r['cycle_id'])
        summaries=[]
        for limit in [5,30,390]:
            for label,ids in [('baseline',valid_ids),('selected',selected_ids)]:
                subset=[r for r in covered_rows(rows,limit) if r['cycle_id'] in ids]
                name=f'{label}_{limit}min'
                if not subset:
                    summaries.append(dict(label=name,cycles=0,status='no complete covered cycles'))
                    continue
                prices={int(r['order_id']):r['provider_price'] for r in subset}
                if (out/name/'audit.json').exists():
                    audit=json.loads((out/name/'audit.json').read_text())
                else:
                    _,audit=run_engine(subset,prices,out/name,initial_cash=capital)
                audit.update(label=name,cycles=len({r['cycle_id'] for r in subset}),
                    stress_pnl=audit['engine_net_pnl']-10*len(subset),
                    matched_qc_pnl=sum(-float(r['quantity'])*float(r['qc_price'])*100-float(r['fee']) for r in subset))
                summaries.append(audit)
        (out/'summary.json').write_text(json.dumps(dict(ticker=local.name,
            selected_config=selection['config'],validation_only=True,runs=summaries,
            policy='Frozen selection; complete covered 2026 cycles only. Historical trade prints, not executable bid/ask; 390-minute scenario explicitly stale.'),indent=2))


if __name__=='__main__':
    main()
