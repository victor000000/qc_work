"""Attribute genuine closed-cycle economics; no counterfactual or full-period claim."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import duckdb
from report import write_tables

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'guard21_failure_results_20261019'
OUT = HERE / 'guarded21_loss_attribution_20261019'
ORDERS = HERE.parent / 'results/strangle_basket-calmar_20261019_163122/SSTRANGLE_20261019_163122_cap20_stop1_guard_exit21/orders.json'


def main():
    with duckdb.connect(str(SOURCE / 'research.duckdb'), read_only=True) as conn:
        cycles = conn.execute('select * from closed_cycles').fetchdf().to_dict('records')
        fills = conn.execute('select * from executions').fetchdf().to_dict('records')
    by_order = defaultdict(list)
    orders = {row['id']: row for row in json.loads(ORDERS.read_text())}
    for fill in fills:
        by_order[int(fill['order_id'])].append(fill)
    rows = []
    for cycle in cycles:
        ids = json.loads(cycle['order_ids'])
        native = [f for order_id in ids for f in by_order[order_id]]
        if not native or any(f['strategy_key'] != cycle['key'] for f in native):
            raise ValueError('Cycle/order identity mismatch')
        pnl = sum(-f['quantity'] * f['qc_price'] * f['multiplier'] - f['fee'] for f in native)
        if abs(pnl - cycle['net_pnl']) > 1e-7:
            raise ValueError('Cycle economics differ from actual native fills')
        legs = {side: sum(-f['quantity'] * f['qc_price'] * f['multiplier'] - f['fee']
                         for f in native if f['call_put'] == side) for side in ['P', 'C']}
        if abs(sum(legs.values()) - pnl) > 1e-7:
            raise ValueError('Put/call attribution does not reconcile')
        opening = [f for f in native if f['reason'] == 'OPEN']
        credit = sum(-f['quantity'] * f['qc_price'] * f['multiplier'] for f in opening)
        if len(opening) != 2 or credit <= 0 or abs(credit - cycle['opening_credit']) > 1e-7:
            raise ValueError('Actual opening-credit reconciliation failed')
        spreads = []
        for fill in native:
            if fill['reason'] in ('OPEN', 'ROLL'):
                continue
            quote = orders[int(fill['order_id'])]['orderSubmissionData']
            bid, ask = float(quote['bidPrice']), float(quote['askPrice'])
            if bid < 0 or ask <= 0 or ask < bid:
                raise ValueError('Invalid actual exit submission quote')
            spreads.append(2 * (ask - bid) / (ask + bid))
        if len(spreads) != 2:
            raise ValueError('Missing two actual closing submission quotes')
        rows.append(dict(cycle, asset_class='futures_options' if cycle['key'].startswith('FUT_')
                         else 'equity_etf_options', net_credit_multiple=pnl / credit,
                         put_net_pnl=legs['P'], call_net_pnl=legs['C'],
                         exit_max_spread_to_mid=max(spreads),
                         exit_relative_spread_above_25pct=any(s > .25 for s in spreads),
                         stop_loss_above_110pct_credit=cycle['reason'] == 'STOP' and pnl < -1.1 * credit))
    groups = []
    for field in ['asset_class', 'reason', 'rolls']:
        for value in sorted({r[field] for r in rows}, key=str):
            subset = [r for r in rows if r[field] == value]
            groups.append(dict(dimension=field, group=str(value), closed_cycles=len(subset),
                               net_pnl=sum(r['net_pnl'] for r in subset),
                               fees=sum(r['fees'] for r in subset),
                               put_net_pnl=sum(r['put_net_pnl'] for r in subset),
                               call_net_pnl=sum(r['call_net_pnl'] for r in subset),
                               wins=sum(r['net_pnl'] > 0 for r in subset),
                               relative_wide_exit_cycles=sum(r['exit_relative_spread_above_25pct'] for r in subset),
                               stop_overshoots=sum(r['stop_loss_above_110pct_credit'] for r in subset)))
    if len(rows) != 157 or abs(sum(r['net_pnl'] for r in rows) - (-8477.89)) > .005:
        raise ValueError('Wrong preserved guarded-run scope')
    OUT.mkdir(exist_ok=True)
    write_tables(OUT, dict(closed_cycle_attribution=rows, aggregate_attribution=groups))
    result = dict(scope='Failed partial guarded21 run, closed cycles only, all before2020',
                  source_sha256=hashlib.sha256((SOURCE / 'research.duckdb').read_bytes()).hexdigest(),
                  actual_orders_sha256=hashlib.sha256(ORDERS.read_bytes()).hexdigest(),
                  closed_cycles=len(rows), closed_net_pnl=sum(r['net_pnl'] for r in rows),
                  closed_fees=sum(r['fees'] for r in rows), actual_all_fees=sum(f['fee'] for f in fills),
                  aggregate_attribution=groups,
                  worst_closed_cycles=sorted(rows, key=lambda r: r['net_pnl'])[:10],
                  full_period_calmar=None, counterfactual_backtest=False,
                  next_research_implication='The equity-only RV gate does not directly address the dominant observed futures losses. Keep its already-submitted full path unchanged. Independently investigate futures stop overshoot and a declared, valid all-root volatility/risk feature; no posthoc root exclusions.',
                  limitations=['One unresolved WBA cycle remains outside closed-cycle economics.',
                               'Entry filters and risk changes alter subsequent baskets; these group totals are not optimized backtests.',
                               'Roll-count and exit-reason groups are outcomes, not ex-ante filters or causal effects.',
                               'Relative spread >25% of midpoint is a submission-quote diagnostic, not a complete proposed guard decision; the actual guard also uses native ticks, current bar side, clock and fill-forward status.',
                               'A realized STOP loss above its trigger threshold does not identify gaps, quote latency or execution slippage without native decision evidence.'])
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: result[k] for k in ['closed_cycles', 'closed_net_pnl', 'closed_fees', 'actual_all_fees', 'aggregate_attribution']}, indent=2))


if __name__ == '__main__':
    main()
