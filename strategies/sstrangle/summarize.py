#!/usr/bin/env python3
"""Write a reviewable report using collected cloud results and audited cycles."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    p = args.folder.resolve()
    rows = json.loads((p/'summary.json').read_text())
    if len(rows) != 2:
        raise ValueError('Expected two completed comparison variants')
    rows.sort(key=lambda r: r['name'].endswith('no_roll'))
    labels = ['Managed rolls', 'No rolls']
    managed_return, control_return = [float(r['active_return']) for r in rows]
    outcome = (f'Managed rolls returned {100*managed_return:.2f}% versus '
               f'{100*control_return:.2f}% without rolls, a difference of '
               f'{100*(managed_return-control_return):+.2f} percentage points. ')
    if managed_return < 0 and control_return < 0:
        outcome += 'Both variants lost money under these assumptions.'
    lines = ['# Short strangle QuantConnect backtest results', '',
        'Trading period: 2024-01-02 through 2025-12-31. Initial capital: $250,000. '
        'SPY, GLD, and TLT; one strangle per eligible ETF. '
        '2022-12-01 through 2023 supplies IV and return history without trading.', '',
        'Both variants use the same supplied assumptions except that the control disables '
        'untested-side rolls. Full assumptions are in the [strategy README](../../README.md). '
        'This evaluates an implementation of the transcript guidelines, not a verified '
        'replication of the speaker’s discretionary trading.', '', outcome, '',
        '| Metric | Managed rolls | No rolls |', '|---|---:|---:|']
    for title, key, fmt in [
        ('Net return over trading period', 'active_return', 'pct'),
        ('Annualized return over trading period', 'active_cagr', 'pct'),
        ('Maximum drawdown at daily decision snapshots', 'active_daily_mdd', 'pct'),
        ('Daily Sharpe with zero risk free rate', 'active_sharpe_zero_rf', 'number'),
        ('Net closed cycle P&L', 'cycle_net_pnl', 'dollars'),
        ('Closed cycle win rate', 'cycle_win_rate', 'pct'),
        ('Closed cycles', 'closed_cycles', 'raw'), ('Untested side rolls', 'rolls', 'raw'),
        ('Profit target exits', 'PROFIT', 'raw'), ('21 DTE exits', 'TIME', 'raw'),
        ('Loss exits', 'STOP', 'raw'), ('End date exits', 'END', 'raw'),
        ('Assignments', 'assignments', 'raw'), ('Remaining open cycles', 'open_cycles', 'raw'),
        ('Actual fees', 'Fees', 'raw'), ('First entry', 'first_entry', 'raw')]:
        vals = []
        for r in rows:
            value = r[key]
            if fmt == 'pct': value = f'{100*float(value):.2f}%'
            elif fmt == 'dollars': value = f'${float(value):,.2f}'
            elif fmt == 'number': value = f'{float(value):.3f}' if value != 'n/a' else value
            vals.append(str(value))
        lines.append('| ' + ' | '.join([title, *vals]) + ' |')
    lines += ['', 'Returns use total account equity, including unallocated cash, with no interest '
        'added by this algorithm. Default QC headline annualized statistics include the idle '
        'initialization period; the table uses the custom trading-period statistics instead. '
        'The daily-snapshot drawdown can miss intraday extremes. The Sharpe measure assumes '
        'a zero risk free rate and is not an excess return over actual cash yields.', '',
        '## Cycle results by underlying', '',
        '| Variant | ETF | Closed cycles | Net P&L after fees | Win rate | Worst cycle |',
        '|---|---|---:|---:|---:|---:|']
    all_cycles = {}
    for label, r in zip(labels, rows):
        evidence = p/r['name']
        audit = json.loads((evidence/'audit.json').read_text())
        if audit.get('cycle_audit_skipped'):
            raise ValueError('Assignments require an expanded audit before this report')
        cycles = list(csv.DictReader((evidence/'cycles.csv').open()))
        all_cycles[label] = cycles
        buckets = defaultdict(list)
        for cycle in cycles:
            buckets[cycle['ticker']].append(float(cycle['pnl']))
        for ticker in ['SPY', 'GLD', 'TLT']:
            values = buckets[ticker]
            win_rate = f'{100*sum(v>0 for v in values)/len(values):.1f}%' if values else 'n/a'
            worst = f'${min(values):,.2f}' if values else 'n/a'
            lines.append(f'| {label} | {ticker} | {len(values)} | ${sum(values):,.2f} | {win_rate} | {worst} |')
    lines += ['', '## Largest realized cycle losses', '',
        '| Variant | ETF | Entry date UTC | Exit date UTC | Exit | Initial credit | Net P&L |',
        '|---|---|---|---|---|---:|---:|']
    for label in labels:
        for c in sorted(all_cycles[label], key=lambda x: float(x['pnl']))[:3]:
            lines.append(f'| {label} | {c["ticker"]} | {c["entry"][:10]} | {c["exit"][:10]} '
                f'| {c["reason"]} | ${float(c["initial_credit"]):,.2f} | ${float(c["pnl"]):,.2f} |')
    lines += ['', 'A stop trigger at a loss of twice opening credit is evaluated at the daily '
        'decision snapshot. Actual realized losses can exceed that threshold after market moves '
        'between checks and execution costs. Initial credit is not a loss bound.']
    lines += ['', '## Data coverage and execution checks', '',
        '| Check | Managed rolls | No rolls |', '|---|---:|---:|']
    for title, key in [('Downloaded orders', 'downloaded_orders'),
        ('Minimum final IV history length', 'min_iv_samples'),
        ('IV observations across ETFs', 'iv_observations'),
        ('Unavailable or low IVR entry rejections', 'ivr_rejected'),
        ('No qualifying delta and liquidity contract', 'no_delta_contract'),
        ('Correlation rejections', 'correlation_rejected'),
        ('Sizing rejections', 'size_rejected'), ('Margin rejections', 'margin_rejected'),
        ('Stale quote management skips', 'stale_management'),
        ('Roll checks without eligible replacement', 'roll_no_candidate'),
        ('Roll checks missing an existing leg in chain', 'roll_missing_contract'),
        ('Cycle P&L versus account equity difference', 'pnl_reconciliation_difference')]:
        lines.append('| ' + ' | '.join([title, *[str(r[key]) for r in rows]]) + ' |')
    lines += ['', 'Candidate-rejection counts are evaluated per ETF and day and are not a '
        'fraction of all market opportunities. A no-contract rejection may reflect strike '
        'spacing, the finite subscription range, liquidity thresholds, or the required '
        '16–20 delta band. A missing roll candidate is a documented skipped adjustment, '
        'not evidence that no economic adjustment was possible.', '',
        'Eight local regression tests passed for IV rank, correlation, exit and roll '
        'decisions, actual fill accounting, rejected orders, and independent cycle reconstruction. '
        'Downloaded fill events independently reconstruct the closed cycles, fees, rolls, '
        'and P&L; the collector rejects missing orders or disagreement with runtime accounting. '
        'QC may return no console logs, so execution evidence uses order fills and runtime statistics.', '',
        '## Interpretation limits', '',
        'The fixed ETF universe, IVR threshold 50, monthly expirations, 21 DTE exit, '
        'loss exit at twice original credit, correlation gate, and roll thresholds are supplied '
        'research assumptions. Fixed one-contract sizing leaves substantial idle capital. '
        'Default QC bid/ask fills include fees but no additional slippage overlay; liquidity '
        'and execution under stress can differ. Stops are checked once daily and do not cap '
        'gap losses. The comparison is a first historical test without a separate holdout or '
        'parameter-sensitivity campaign. High cycle win rates alone do not establish a '
        'positive long-term expected return.', '', '## Saved evidence', '']
    for label, r in zip(labels, rows):
        lines.append(f'- {label}: [cloud backtest]({r["url"]}); '
            f'[full cloud result]({r["name"]}/backtest.json), '
            f'[orders]({r["name"]}/orders.json), [cycles]({r["name"]}/cycles.csv), '
            f'[audit]({r["name"]}/audit.json).')
    lines += ['- [Summary CSV](summary.csv) and [summary JSON](summary.json).',
              '- Exact submitted sources: [managed.py](managed.py), [no_roll.py](no_roll.py), '
              '[bundled rules](extra_files.json), and [manifest](manifest.json).', '']
    (p/'RESULTS.md').write_text('\n'.join(lines))
    print(p/'RESULTS.md')


if __name__ == '__main__':
    main()
