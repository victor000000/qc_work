#!/usr/bin/env python3
"""Freeze a QC execution tape and read-only shared-provider exports for AKQuant."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'results/strangle_comparison_20261017_134629/SSTRANGLE_20261017_134629_managed'
OCC = re.compile(r'^([A-Z]+)(\d{6})([CP])(\d{8})$')


def executions(orders):
    rows, seen = [], set()
    for order in sorted(orders, key=lambda x: x['id']):
        if order['id'] in seen:
            raise ValueError('Duplicate QC order')
        seen.add(order['id'])
        symbol = order['symbol']['value'].replace(' ', '')
        match = OCC.fullmatch(symbol)
        if not match:
            raise ValueError('Unsupported OCC identity: '+symbol)
        root, expiry, cp, strike = match.groups()
        for event in order['events']:
            qty = float(event.get('fillQuantity', 0))
            if not qty:
                continue
            if event.get('isAssignment') or event.get('fillPriceCurrency') != 'USD':
                raise ValueError('Assignment or non-USD fill requires separate handling')
            rows.append(dict(order_id=order['id'], event_id=event['id'],
                timestamp=datetime.fromtimestamp(event['time'], timezone.utc).isoformat(),
                symbol=symbol, underlying=root,
                expiry=datetime.strptime(expiry, '%y%m%d').date().isoformat(),
                call_put=cp, strike=int(strike)/1000, multiplier=100,
                quantity=qty, qc_price=float(event['fillPrice']),
                fee=float(event.get('orderFeeAmount', 0)),
                group_id=order['groupOrderManager']['id'], tag=order['tag']))
    return rows


def write_csv(path, rows, fields=None):
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qc-source', type=Path, default=BASE)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    orders = json.loads((args.qc_source/'orders.json').read_text())
    rows = executions(orders)
    write_csv(out/'qc_executions.csv', rows)
    (out/'qc_orders.json').write_text(json.dumps(orders, indent=2))
    symbols = sorted({r['underlying'] for r in rows})
    start, end = min(r['timestamp'][:10] for r in rows), max(r['timestamp'][:10] for r in rows)
    from data_providers import MarketData
    m = MarketData()
    releases = {}
    for ds in ['us_option_bars','us_option_minutes','us_option_greeks','us_option_oi','us_iv','us_prices']:
        manifest = m.export(ds, out/ds, symbols=symbols, start=start, end=end)
        releases[ds] = manifest
        print(f'{ds}: {manifest["rows"]} rows', flush=True)
    net = sum(-r['quantity']*r['qc_price']*100-r['fee'] for r in rows)
    audit = json.loads((args.qc_source/'audit.json').read_text())
    if abs(net-audit['pnl']) > .001:
        raise ValueError('QC tape does not reconcile to the audited source')
    backtest_path = args.qc_source/'backtest.json'
    runtime = json.loads(backtest_path.read_text())['backtest']['runtimeStatistics'] if backtest_path.exists() else {}
    manifest = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        qc_source=str(args.qc_source.resolve()), provider_home=str(m.home),
        source_orders_sha256=hashlib.sha256((out/'qc_orders.json').read_bytes()).hexdigest(),
        execution_count=len(rows), contract_count=len({r['symbol'] for r in rows}),
        qc_net_pnl=net, initial_cash=float(runtime.get('initial_cash',250000)), start=start, end=end,
        datasets=releases, mode='frozen QC signal replay; not independent signal generation')
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(out, flush=True)


if __name__ == '__main__':
    main()
