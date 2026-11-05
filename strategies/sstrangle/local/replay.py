#!/usr/bin/env python3
"""Replay frozen QC signals in AKQuant; separate price controls from provider proxies."""
import argparse
import csv
from datetime import datetime, timedelta
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import write_csv


def assign_cycles(rows):
    groups, active, number = {}, {}, 0
    for r in rows:
        groups.setdefault(r['group_id'], []).append(r)
    for group in groups.values():
        ticker, reason = group[0]['tag'].split(':', 1)
        reason = reason.split(';')[0]
        if reason == 'OPEN':
            if ticker in active:
                raise ValueError('Overlapping cycles')
            number += 1
            active[ticker] = number
        for r in group:
            r['cycle_id'] = active[ticker]
        if reason not in ['OPEN', 'ROLL']:
            del active[ticker]
    if active:
        raise ValueError('Unclosed signal cycles')


def price_rows(folder, rows):
    bars = {}
    capture = folder/'provider_capture'
    manifest = json.loads((capture/'manifest.json').read_text())
    if manifest['failures'] or manifest['completed_jobs'] != manifest['requested_jobs']:
        raise ValueError('Provider capture incomplete')
    for name, digest in manifest['files'].items():
        f = capture/name
        if hashlib.sha256(f.read_bytes()).hexdigest() != digest:
            raise ValueError('Provider capture checksum mismatch')
        if not name.startswith('minute_'):
            continue
        for page in json.loads(f.read_text())['pages']:
            for symbol, data in page.get('bars', {}).items():
                for b in data:
                    end = datetime.fromisoformat(b['t'].replace('Z', '+00:00'))+timedelta(minutes=1)
                    bars.setdefault((symbol, b['t'][:10]), []).append((end, b['c'], b['v']))
    output = []
    for original in rows:
        r = dict(original)
        t = datetime.fromisoformat(r['timestamp'])
        valid = [b for b in bars.get((r['symbol'], r['timestamp'][:10]), []) if b[0] <= t]
        if valid:
            last = max(valid, key=lambda b: b[0])
            r.update(provider_price=float(last[1]), provider_bar_end=last[0].isoformat(),
                age_minutes=(t-last[0]).total_seconds()/60, provider_bar_volume=float(last[2]))
        else:
            r.update(provider_price=None, provider_bar_end='', age_minutes=None, provider_bar_volume=0)
        output.append(r)
    return output


def covered_rows(rows, age_limit):
    cycles = {r['cycle_id'] for r in rows}
    if age_limit is not None:
        cycles -= {r['cycle_id'] for r in rows if r['age_minutes'] is None or r['age_minutes'] > age_limit}
    return [r for r in rows if r['cycle_id'] in cycles]


def validate_replay_inputs(rows, prices, initial_cash):
    if not rows or not math.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError('Replay requires executions and finite positive initial cash')
    seen = set()
    for row in rows:
        order_id = int(row['order_id'])
        if order_id in seen:
            raise ValueError('Partial fills require event-level price keys; duplicate order ID is unsupported')
        seen.add(order_id)
        price, quantity, fee = float(prices[order_id]), float(row['quantity']), float(row['fee'])
        if not math.isfinite(price) or price <= 0:
            raise ValueError('Replay price must be finite and positive')
        if not math.isfinite(quantity) or quantity == 0 or not math.isfinite(fee) or fee < 0:
            raise ValueError('Replay quantity or fee is invalid')


def run_engine(rows, prices, output, initial_cash=250000):
    validate_replay_inputs(rows, prices, initial_cash)
    import akquant as aq
    from akquant import BacktestConfig, InstrumentConfig, StrategyConfig
    from akquant.config import RiskConfig
    from akquant import CurrentClose
    output.mkdir(exist_ok=False)
    schedule, data, metadata = {}, {}, {}
    expected = 0
    for r in rows:
        symbol, timestamp = r['symbol'], pd.Timestamp(r['timestamp'])
        key = (symbol, timestamp.value)
        if key in schedule:
            raise ValueError('Two orders for the same contract at one timestamp require sequencing')
        schedule[key] = r
        price = prices[int(r['order_id'])]
        qty, fee = float(r['quantity']), float(r['fee'])
        expected -= qty*price*100+fee
        data.setdefault(symbol, []).append(dict(datetime=timestamp, open=price, high=price,
            low=price, close=price, volume=1000000))
        metadata[symbol] = r
    for symbol, bars in data.items():
        frame = pd.DataFrame(bars).set_index('datetime').sort_index()
        data[symbol] = frame

    class Replay(aq.Strategy):
        def on_bar(self, bar):
            r = schedule.get((bar.symbol, int(bar.timestamp)))
            if r is None:
                return
            qty = float(r['quantity'])
            method = self.buy if qty > 0 else self.sell
            method(symbol=bar.symbol, quantity=abs(qty), tag=str(r['order_id']),
                   commission={'type':'fixed', 'value':float(r['fee'])})

    instruments = [InstrumentConfig(symbol=s, asset_type='OPTION', multiplier=100,
        option_type='CALL' if r['call_put']=='C' else 'PUT', strike_price=float(r['strike']),
        expiry_date=datetime.fromisoformat(r['expiry']).date(),
        underlying_symbol=r['underlying'], option_margin_model='RATIO', margin_ratio=1.0,
        tick_size=.000001, lot_size=1, sellable_after_days=0,
        commission_rate=0, min_commission=0, stamp_tax_rate=0, transfer_fee_rate=0)
        for s,r in metadata.items()]
    config = BacktestConfig(strategy_config=StrategyConfig(initial_cash=initial_cash,
        commission_rate=0, min_commission=0, stamp_tax_rate=0, transfer_fee_rate=0,
        volume_limit_pct=1, round_fill_price=False, exit_on_last_bar=False,
        risk=RiskConfig(account_mode='margin', enable_short_sell=True,
            financing_rate_annual=0, borrow_rate_annual=0, allow_force_liquidation=False)),
        instruments_config=instruments, timezone='America/New_York', show_progress=False,
        bootstrap_samples=0)
    result = aq.run_backtest(data=data, strategy=Replay, config=config,
        fill_policy=CurrentClose())
    for attr in ['executions_df','orders_df','trades_df','equity_curve']:
        value = getattr(result, attr, None)
        if isinstance(value, (pd.Series,pd.DataFrame)):
            value.to_csv(output/(attr+'.csv'))
    fills = result.executions_df
    fills.to_csv(output/'executions.csv', index=False)
    actual_net, residual, matched = 0.0, {}, set()
    for fill in fills.to_dict('records'):
        key = (fill['symbol'], pd.Timestamp(fill['timestamp']).value)
        if key not in schedule or key in matched:
            raise ValueError('Unexpected or duplicate engine fill')
        matched.add(key)
        r = schedule[key]
        sign = 1 if str(fill['side']).lower()=='buy' else -1
        quantity = sign*float(fill['quantity'])
        if abs(quantity-float(r['quantity'])) > 1e-8:
            raise ValueError('Engine fill quantity differs from requested QC quantity')
        if abs(float(fill['price'])-prices[int(r['order_id'])]) > 1e-8:
            raise ValueError('Engine fill price differs from scenario price')
        if abs(float(fill['commission'])-float(r['fee'])) > 1e-8:
            raise ValueError('Engine fee differs from the explicit QC fee schedule')
        residual[fill['symbol']] = residual.get(fill['symbol'], 0)+quantity
        actual_net -= quantity*float(fill['price'])*100+float(fill['commission'])
    if len(matched) != len(schedule) or any(abs(q)>1e-8 for q in residual.values()):
        raise ValueError('Missing engine executions or residual positions')
    final_equity = float(result.equity_curve.iloc[-1])
    if abs(actual_net-expected)>1e-6 or abs(final_equity-initial_cash-expected)>1e-6:
        raise ValueError('AKQuant ledger/equity does not reconcile')
    summary = dict(expected_net_pnl=expected, scheduled_orders=len(rows),
        engine_executions=len(fills), akquant_version=version('akquant'),
        engine_net_pnl=actual_net, final_equity=final_equity, initial_cash=initial_cash,
        fill_price_quantity_fee_audit=True, residual_positions=0,
        maximum_observed_age_minutes=max((r['age_minutes'] or 0 for r in rows), default=0))
    (output/'audit.json').write_text(json.dumps(summary, indent=2))
    print(f'{output.name}: {len(fills)} executions, net P&L={actual_net:.2f}', flush=True)
    return result, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    args = p.parse_args()
    folder = args.folder.resolve()
    rows = list(csv.DictReader((folder/'qc_executions.csv').open()))
    assign_cycles(rows)
    rows = price_rows(folder, rows)
    write_csv(folder/'price_coverage.csv', rows)
    # The maximum-age run is explicitly a stale-trade sensitivity, not a
    # bid/ask execution simulation. No missing provider price uses a QC fallback.
    scenarios = [('qc_control', None), ('provider_5min',5),
                 ('provider_30min',30), ('provider_same_day_stale',390)]
    summaries = []
    for label, age_limit in scenarios:
        selected = covered_rows(rows, age_limit)
        cycles = {r['cycle_id'] for r in selected}
        if not selected:
            summaries.append(dict(label=label, cycles=0, status='no complete covered cycles'))
            continue
        prices = {int(r['order_id']):float(r['qc_price'] if age_limit is None else r['provider_price'])
                  for r in selected}
        initial_cash = json.loads((folder/'manifest.json').read_text()).get('initial_cash',250000)
        _, summary = run_engine(selected, prices, folder/label, initial_cash=initial_cash)
        summary.update(label=label, cycles=len(cycles), max_age_minutes=age_limit,
            matched_qc_pnl=sum(-float(r['quantity'])*float(r['qc_price'])*100-float(r['fee']) for r in selected))
        summaries.append(summary)
        (folder/'replay_summary.json').write_text(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
