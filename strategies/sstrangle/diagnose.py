#!/usr/bin/env python3
"""Describe observed baseline losses without treating hindsight exclusions as strategies."""
import csv
import json
from collections import defaultdict
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
BASE = HERE/'results/strangle_comparison_20261017_134629'


def main():
    out = HERE/'research'
    out.mkdir(exist_ok=True)
    findings = {}
    for variant in ['managed', 'no_roll']:
        folder = BASE/f'SSTRANGLE_20261017_134629_{variant}'
        cycles = list(csv.DictReader((folder/'cycles.csv').open()))
        orders = json.loads((folder/'orders.json').read_text())
        values = [float(c['pnl']) for c in cycles]
        winners, losers = [x for x in values if x > 0], [x for x in values if x <= 0]
        by_exit, by_asset = defaultdict(list), defaultdict(list)
        for c in cycles:
            by_exit[c['reason']].append(float(c['pnl']))
            by_asset[c['ticker']].append(float(c['pnl']))
        legs = defaultdict(float)
        midpoint_cost = 0.0
        for o in orders:
            ticker = o['tag'].split(':')[0]
            right = 'put' if 'P' in o['symbol']['value'].split()[-1] else 'call'
            quote = o.get('orderSubmissionData', {})
            bid, ask = quote.get('bidPrice', 0), quote.get('askPrice', 0)
            for e in o.get('events', []):
                quantity = float(e.get('fillQuantity', 0))
                if not quantity:
                    continue
                price, fee = float(e['fillPrice']), float(e.get('orderFeeAmount', 0))
                legs[ticker+'_'+right] -= quantity * price * 100 + fee
                if ask >= bid > 0:
                    midpoint_cost += quantity * (price - (bid + ask)/2) * 100
        avg_win, avg_loss = statistics.mean(winners), statistics.mean(losers)
        fees = sum(float(c['fees']) for c in cycles)
        findings[variant] = dict(cycles=len(values), wins=len(winners), losses=len(losers),
            net_pnl=sum(values), average_win=avg_win, average_loss=avg_loss,
            win_rate=len(winners)/len(values), empirical_break_even_win_rate=-avg_loss/(avg_win-avg_loss),
            gross_winning_pnl=sum(winners), gross_losing_pnl=sum(losers),
            profit_factor=sum(winners)/-sum(losers), worst_three_pnl=sum(sorted(values)[:3]),
            commissions=fees, pnl_before_commissions=sum(values)+fees,
            estimated_fill_cost_vs_submission_midpoint=midpoint_cost,
            by_exit={k:dict(cycles=len(v), net_pnl=sum(v)) for k,v in by_exit.items()},
            by_asset={k:dict(cycles=len(v), net_pnl=sum(v)) for k,v in by_asset.items()},
            leg_net_cash_attribution=dict(legs),
            worst_cycles=sorted(cycles, key=lambda c:float(c['pnl']))[:5])
        assert abs(sum(legs.values())-sum(values)) < .01
    (out/'baseline_diagnostics.json').write_text(json.dumps(findings, indent=2))
    m, n = findings['managed'], findings['no_roll']
    lines = ['# Why the short strangle baseline lost money', '',
        'The managed baseline lost $3,429 after costs in 2024–2025 because a few large '
        'losing cycles outweighed many small wins. The order-level attribution reconciles '
        'to the audited results; it describes this sample rather than proving a permanent '
        'market mechanism.', '',
        f'Of {m["cycles"]} managed cycles, {m["wins"]} won and {m["losses"]} lost. '
        f'Average winners were ${m["average_win"]:.2f}; average losers were '
        f'${abs(m["average_loss"]):.2f}. With those observed payoff sizes, the empirical '
        f'break-even win rate is {100*m["empirical_break_even_win_rate"]:.1f}%, versus '
        f'{100*m["win_rate"]:.1f}% observed. This break-even calculation assumes the same '
        'average win and loss sizes; it is not a forecast probability.', '',
        '| Exit reason | Managed cycles | Managed net P&L | No roll cycles | No roll net P&L |',
        '|---|---:|---:|---:|---:|']
    for reason in ['PROFIT','TIME','STOP']:
        a,b=m['by_exit'][reason],n['by_exit'][reason]
        lines.append(f'| {reason} | {a["cycles"]} | ${a["net_pnl"]:,.2f} | {b["cycles"]} | ${b["net_pnl"]:,.2f} |')
    lines += ['', 'The five managed stop exits lost $5,290; the other 23 cycles earned '
        '$1,861 net. The three largest losing cycles totaled $4,321. This concentration '
        'does not justify deleting those trades retrospectively; a usable improvement '
        'needs an observable rule available before entry or exit.', '',
        '| Managed leg attribution | Net cash P&L after fees |', '|---|---:|']
    for key,value in m['leg_net_cash_attribution'].items():
        lines.append(f'| {key} | ${value:,.2f} |')
    lines += ['', 'SPY put losses dominate the equity ETF result, while GLD calls lost money '
        'despite profitable GLD puts. That is consistent with exposure to large moves in '
        'both directions. This attribution is cumulative cash flow by option right, '
        'including rolled contracts, rather than a Greek-based decomposition.', '',
        f'Commissions were ${m["commissions"]:.2f}; excluding them still leaves a '
        f'${abs(m["pnl_before_commissions"]):,.2f} loss. Estimated fill cost against '
        f'contemporaneous submission midpoints was ${m["estimated_fill_cost_vs_submission_midpoint"]:.2f}. '
        'The midpoint figure is an execution diagnostic, not an attainable alternative '
        'backtest: market orders filled at the modeled bid/ask, and midpoint fills are not guaranteed.', '',
        'Daily checks let the realized loss exceed the nominal two-credit stop: the '
        'managed SPY cycle opened on 2025-03-31 for $753 and exited on 2025-04-04 '
        'with a $1,855 loss. A tighter daily stop can still overshoot after gaps. '
        'Intraday stop monitoring is not part of the three current experiments.', '',
        'Rolling improved the whole comparison by $849, while commissions rose from '
        '$108 to $216. The managed run had 28 cycles versus 27 without rolls, so that '
        '$849 includes changes in subsequent entry timing and is not a matched-trade '
        'estimate of the value of an individual roll.', '',
        'The IVR threshold of 50 is a comparison with past implied volatility. It '
        'does not establish that the option premium exceeds future realized volatility. '
        'The planned IV/RV filter uses trailing realized volatility as a causal proxy, '
        'not knowledge of future moves.', '',
        'Fourteen local tests pass after adding disabled-by-default entry filters and '
        'a configurable loss multiple. The baseline profit target, time exit, ETF '
        'universe, one-contract sizing, quotes, pricing model and roll rules remain unchanged. '
        'Original submitted source snapshots and results remain preserved.', '',
        '## Frozen improvement tests', '',
        'The [research plan](../research_plan.json) fixes three one-factor changes: '
        'one-credit loss exit; a symmetric one-sigma trailing 20-session trend gate; '
        'and ATM IV at least 1.2 times trailing 20-session realized volatility. '
        'The latter two features use the existing raw-price daily snapshots, so they '
        'include dividend-related price changes and are not total-return estimators.', '',
        'Selection uses highest discovery-period net P&L, then lower daily drawdown '
        'and fewer rolls, among candidates with at least ten completed cycles. '
        'The selected configuration is frozen before comparing it with the baseline '
        'over 2026-01-02 through 2026-09-30. No thresholds will be revised using '
        'validation results. Small samples or a failed improvement will be reported.', '',
        'Source evidence: [original results](../results/strangle_comparison_20261017_134629/RESULTS.md), '
        '[diagnostic calculations](baseline_diagnostics.json).', '']
    (out/'baseline_diagnostics.md').write_text('\n'.join(lines))
    print(out/'baseline_diagnostics.md')


if __name__ == '__main__':
    main()
