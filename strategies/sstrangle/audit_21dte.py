#!/usr/bin/env python3
"""Audit calendar DTE at entry/exit from downloaded QC orders, not holding days."""
import argparse
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from audit import reconstruct
from qc_contracts import option_identity


def audit_dte(orders):
    cycles = reconstruct(orders)
    results = []
    for cycle in cycles:
        openings = [order for order in orders if order.get('tag', '').split(';')[0] == cycle['ticker']+':OPEN'
                    and order['time'] == cycle['entry']]
        expiries = set()
        for order in openings:
            if order['symbol'].get('id'):
                expiries.add(datetime.fromisoformat(option_identity(order['symbol'])['expiry']).date())
                continue
            symbol = order['symbol']['value'].replace(' ', '')
            match = re.fullmatch(r'[A-Z]+(\d{6})[CP]\d{8}', symbol)
            if not match:
                raise ValueError('Unsupported option identity: '+symbol)
            expiries.add(datetime.strptime(match[1], '%y%m%d').date())
        if len(expiries) != 1:
            raise ValueError('Cycle entry does not have a unique contract expiry')
        expiry = expiries.pop()
        entry = datetime.fromisoformat(cycle['entry'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date()
        exit = datetime.fromisoformat(cycle['exit'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date()
        dte = (expiry-exit).days
        results.append(dict(cycle, expiry=str(expiry), entry_dte=(expiry-entry).days,
                            exit_dte=dte, holding_calendar_days=(exit-entry).days,
                            calendar_21dte_date=str(expiry-timedelta(days=21)),
                            overdue_calendar_days=max(0,21-dte)))
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    args=parser.parse_args()
    orders=json.loads((args.folder/'orders.json').read_text())
    rows=audit_dte(orders)
    with (args.folder/'dte_audit.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['ticker','entry','exit','expiry','exit_dte'])
        writer.writeheader()
        writer.writerows(rows)
    summary=dict(cycles=len(rows),orders=len(orders),net_pnl=sum(row['pnl'] for row in rows),
                 time_exits=sum(row['reason']=='TIME' for row in rows),
                 time_exits_exactly_21dte=sum(row['reason']=='TIME' and row['exit_dte']==21 for row in rows),
                 exits_below_21dte=[row for row in rows if row['exit_dte']<21],
                 rule='Calendar days until contract expiry; once-daily decision at 15:30 NY on normal sessions. Holidays can move the first eligible session below 21 DTE.')
    (args.folder/'dte_audit.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
