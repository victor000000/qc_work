#!/usr/bin/env python3
"""Report all predeclared discovery tests and the unchanged holdout comparison."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def details(folder, row):
    evidence = folder/row['name']
    cycles = list(csv.DictReader((evidence/'cycles.csv').open()))
    values = [float(c['pnl']) for c in cycles]
    wins, losses = [x for x in values if x > 0], [x for x in values if x < 0]
    return dict(cycles=cycles, average_win=sum(wins)/len(wins) if wins else 0,
        average_loss=sum(losses)/len(losses) if losses else 0,
        profit_factor=sum(wins)/-sum(losses) if losses else None,
        worst=min(values) if values else 0)


def metric_row(label, r, d):
    pf = f'{d["profit_factor"]:.2f}' if d['profit_factor'] is not None else 'n/a'
    win_rate = f'{100*float(r["cycle_win_rate"]):.1f}%' if r['cycle_win_rate'] != 'n/a' else 'n/a'
    return (f'| {label} | ${float(r["cycle_net_pnl"]):,.2f} | '
            f'{100*float(r["active_return"]):.2f}% | {100*float(r["active_daily_mdd"]):.2f}% | '
            f'{r["closed_cycles"]} | {win_rate} | {pf} | {r["Fees"]} |')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('discovery', type=Path)
    args = parser.parse_args()
    discovery = args.discovery.resolve()
    original = HERE/'results/strangle_comparison_20261017_134629'
    base = next(r for r in json.loads((original/'summary.json').read_text()) if r['name'].endswith('_managed'))
    candidates = json.loads((discovery/'summary.json').read_text())
    selected = json.loads((discovery/'selection.json').read_text())
    validation = Path(json.loads((discovery/'validation.json').read_text())['path'])
    holdout = json.loads((validation/'summary.json').read_text())
    hbase = next(r for r in holdout if r['name'].endswith('_baseline'))
    hselected = next(r for r in holdout if r['name'].endswith('_selected'))
    labels = dict(stop1='One credit stop', trend='Trend gate', edge='IV over RV gate')
    winner = labels[selected['candidate_label']]
    delta = float(hselected['cycle_net_pnl'])-float(hbase['cycle_net_pnl'])
    conclusion = (f'The frozen candidate was {winner}. Its 2026 validation net P&L was '
        f'${float(hselected["cycle_net_pnl"]):,.2f}, compared with '
        f'${float(hbase["cycle_net_pnl"]):,.2f} for the unchanged baseline, a difference '
        f'of ${delta:+,.2f} after fees. ')
    if int(hselected['closed_cycles']) == 0:
        conclusion += 'The candidate made no trades, so validation of its trading edge is inconclusive.'
    elif float(hselected['cycle_net_pnl']) <= 0:
        conclusion += 'It did not establish a profitable improvement in validation.'
    elif delta <= 0:
        conclusion += 'It was profitable in this sample but did not improve on the baseline.'
    else:
        conclusion += 'It improved on the baseline in this validation sample; durability remains unproven.'
    if 0 < int(hselected['closed_cycles']) < 10:
        conclusion += (f' Only {hselected["closed_cycles"]} candidate cycle(s) completed, '
            'so the result cannot establish a trading edge; lower exposure is a major limitation.')
    lines = ['# Short strangle loss analysis and improvement tests', '', conclusion, '',
        'All runs use SPY, GLD and TLT, $250,000 initial capital, fixed one-contract '
        'strangles, the original IVR threshold of 50 and the same QC pricing, quote, '
        'fee and fill models. Account returns include idle cash without added interest. '
        'Drawdown below is measured at the daily decision snapshots, not intraday. '
        'All five new jobs were scheduled, compiled and executed through the workspace '
        'Rust qc-backtest-server and data/SSTRANGLE.duckdb queue, using the existing QC '
        'project pool. Python rendered sources and collected evidence.', '',
        '## Why the baseline lost', '',
        'The 2024–2025 managed baseline had 17 profitable cycles out of 28, but '
        'average winners were $147.06 versus $539.00 average losses. Five stop exits '
        'lost $5,290, while the remaining cycles earned $1,861 net. The three largest '
        'losing cycles totaled $4,321. Costs contributed, but removing $216 in '
        'commissions still leaves a $3,213 loss.', '',
        'SPY put cash attribution was −$2,529 and GLD call attribution was −$1,673. '
        'The opposite directions matter: the strategy was exposed both to sharp falls '
        'and sustained rises. The daily two-credit stop did not bound losses; one '
        'SPY cycle collected $753 and lost $1,855 at exit. High IV rank alone did '
        'not prove that the premium compensated for subsequent price moves.', '',
        'See [baseline diagnostics](../../research/baseline_diagnostics.md) for '
        'exit-level and leg-level attribution and calculation limits.', '',
        '## Discovery on the already inspected period', '',
        'Trading period: 2024-01-02 through 2025-12-31, with prior IV and return '
        'history from 2022-12-01. The cached baseline is the original audited run. '
        'New entry filters are disabled by default and do not alter the '
        'baseline entry, exit, sizing or roll rules.', '',
        '| Variant | Net P&L | Return | Daily drawdown | Cycles | Win rate | Profit factor | Fees |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
        metric_row('Original managed baseline',base,details(original,base))]
    for label in ['stop1','trend','edge']:
        r = next((r for r in candidates if r['name'].endswith('_'+label)), None)
        if r:
            lines.append(metric_row(labels[label],r,details(discovery,r)))
        else:
            lines.append(f'| {labels[label]} | No completed usable result | | | | | | |')
    lines += ['', '## Discovery payoff and rejection diagnostics', '',
        '| Variant | Average winner | Average loser | Worst cycle | Stop exits | Stop exit net P&L | New filter rejections |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for label in ['stop1','trend','edge']:
        r = next((r for r in candidates if r['name'].endswith('_'+label)), None)
        if not r:
            continue
        d = details(discovery,r)
        stops = [float(c['pnl']) for c in d['cycles'] if c['reason']=='STOP']
        rejected = int(r.get('premium_rejected',0))+int(r.get('trend_rejected',0))
        lines.append(f'| {labels[label]} | ${d["average_win"]:.2f} | ${d["average_loss"]:.2f} '
            f'| ${d["worst"]:.2f} | {len(stops)} | ${sum(stops):,.2f} | {rejected} |')
    stop_row = next((r for r in candidates if r['name'].endswith('_stop1')), None)
    if stop_row:
        d = details(discovery,stop_row)
        spy = sum(float(c['pnl']) for c in d['cycles'] if c['ticker']=='SPY')
        lines += ['', f'The one-credit-stop run still lost ${abs(spy):,.2f} on SPY. '
            'Its two largest SPY stop exits occurred on the same dates with the same '
            'losses as the original managed run. A tighter daily trigger did not '
            'exit those positions before the large adverse moves.', '',
            'The following entry snapshots come from the audited one-credit-stop '
            'run, at entry times shared with the original SPY and GLD loss episodes. '
            'They provide context for the hypotheses; rejecting those entries is '
            'not equivalent to removing their losses because replacement entries '
            'and position paths also change.', '',
            '| ETF and entry date UTC | IV rank | ATM IV | Trailing RV | IV/RV | Trend displacement |',
            '|---|---:|---:|---:|---:|---:|']
        feature_file=discovery/stop_row['name']/'entry_features.csv'
        for e in csv.DictReader(feature_file.open()):
            if (e['ticker'],e['entry'][:10]) in [('SPY','2024-07-29'),('SPY','2025-03-31'),('GLD','2025-10-09')]:
                lines.append(f'| {e["ticker"]} {e["entry"][:10]} | {float(e["ivr"]):.1f} '
                    f'| {100*float(e["iv"]):.2f}% | {100*float(e["rv"]):.2f}% '
                    f'| {float(e["iv"])/float(e["rv"]):.2f} | {float(e["trend_z"]):.2f} |')
    lines += ['', 'The one-credit stop changes only the loss multiple from 2 to 1. '
        'The trend gate rejects entries when absolute trailing 20-session log-price '
        'displacement exceeds one realized-volatility-scaled 20-session move. '
        'The IV/RV gate requires ATM IV at least 1.2 times trailing 20-session '
        'realized volatility. These were separate tests; no untested combination '
        'is presented as a result.', '',
        'The thresholds were frozen before discovery results were collected. '
        'Selection required at least ten completed cycles and ranked by net P&L, '
        'then lower daily drawdown and fewer rolls. The chosen configuration is '
        f'`{json.dumps(selected["candidate_config"],sort_keys=True)}`. '
        'These tests were motivated by a period already examined, so discovery '
        'improvement is exploratory and subject to selection bias.', '',
        '## Frozen validation on subsequent data', '',
        'Trading period: 2026-01-02 through 2026-09-30, with initialization history '
        'from 2024-12-01. Both algorithms started with fresh capital and positions. '
        'The candidate was frozen before these validation runs. No validation '
        'result was used to change the threshold or select a different candidate.', '',
        '| Variant | Net P&L | Return | Daily drawdown | Cycles | Win rate | Profit factor | Fees |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
        metric_row('Unchanged baseline',hbase,details(validation,hbase)),
        metric_row(winner,hselected,details(validation,hselected)), '',
        f'Both validation runs recorded {hbase["active_snapshots"]} daily decision '
        f'snapshots and {hbase["active_iv_observations"]} active-period IV observations. '
        'The collector checked data coverage independently of trade counts. '
        'Both ended with zero open cycles and no assignments.', '',
        '## Validation trade attribution', '',
        '| Variant | ETF | Cycles | Net P&L after fees | Worst cycle |', '|---|---|---:|---:|---:|']
    for label,r in [('Baseline',hbase),(winner,hselected)]:
        buckets = defaultdict(list)
        for c in details(validation,r)['cycles']:
            buckets[c['ticker']].append(float(c['pnl']))
        for ticker in ['SPY','GLD','TLT']:
            values=buckets[ticker]
            worst=f'${min(values):,.2f}' if values else 'n/a'
            lines.append(f'| {label} | {ticker} | {len(values)} | ${sum(values):,.2f} | {worst} |')
    lines += ['', '## Evidence and limits', '',
        'Fourteen local regression tests cover calculations, selection, order accounting '
        'and cycle reconstruction. The collector downloads complete order histories and '
        'checks reconstructed P&L, cycle counts, rolls and fees against QC runtime '
        'statistics. Entry annotations preserve IVR, ATM IV, realized volatility, '
        'trend displacement, spot and selected deltas at the decision time.', '',
        'The filters use only trailing snapshot returns. They compare different '
        'horizons and use raw prices, including dividend effects; IV/RV is a '
        'heuristic entry condition, not a measured future volatility risk premium. '
        'Reduced losses can come partly from taking fewer trades. Do not infer '
        'improved expected return solely from lower exposure or a higher win rate. '
        'The fixed one-contract sizes are not volatility-balanced across ETFs.', '',
        'Daily stops can overshoot after gaps; no intraday monitoring or protective '
        'wings were tested. Monthly-only selection, finite strike subscriptions '
        'and modeled market-order fills constrain generalization. There is one '
        'subsequent validation window, not a multi-regime walk-forward study. '
        'Low counts, negative profit factors, or failed validation remain evidence '
        'against promoting a candidate; this research does not authorize live trading.', '',
        '- [Frozen plan](research_plan.json), [selection](selection.json), '
        '[discovery summary](summary.csv), [source manifest](manifest.json).',
        f'- [Validation summary]({validation.as_posix()}/summary.csv) and '
        f'[validation source manifest]({validation.as_posix()}/manifest.json).']
    total_orders=0
    for period, folder, rows in [('Discovery',discovery,candidates),('Validation',validation,holdout)]:
        for r in rows:
            total_orders+=int(r['downloaded_orders'])
            lines.append(f'- {period} {r["name"]}: [cloud result]({r["url"]}), '
                f'[audited cycles]({(folder/r["name"]/"cycles.csv").as_posix()}), '
                f'[entry features]({(folder/r["name"]/"entry_features.csv").as_posix()}), '
                f'[audit]({(folder/r["name"]/"audit.json").as_posix()}).')
    lines += ['', f'New experiment orders downloaded and audited: {total_orders}.', '']
    (discovery/'RESEARCH_RESULTS.md').write_text('\n'.join(lines))
    print(discovery/'RESEARCH_RESULTS.md')


if __name__ == '__main__':
    main()
