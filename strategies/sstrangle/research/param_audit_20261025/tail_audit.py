#!/usr/bin/env python3
"""Read-only tail audit of completed sstrangle QC runs.

Per-run daily P&L statistics from real backtested equity curves, reported as a distribution
across runs rather than pooled: pooling returns from different capital bases, periods and
overlapping parameter variants is not a valid sample.

Read-only. Does not queue, cancel, modify or re-run anything; touches no other strategy.
Writes tail_audit.json next to this file.
"""
import datetime as dt
import glob
import json
import os
import statistics as st

RESULTS = os.path.join(os.path.dirname(__file__), '..', '..', 'results')
OUT = os.path.dirname(os.path.abspath(__file__))


def daily(equity_json):
    try:
        values = json.load(open(equity_json))['chart']['series']['Equity']['values']
    except Exception:
        return None
    last = {}
    for row in values:
        ts = int(row[0])
        last[ts - ts % 86400] = float(row[4])
    days = sorted(last)
    if len(days) < 30:
        return None
    eq = [last[d] for d in days]
    rets = [(eq[i] - eq[i - 1]) / eq[i - 1] for i in range(1, len(eq))]
    live = [r for r in rets if r != 0.0]                 # flat marks are not observations
    if len(live) < 30:
        return None
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    live.sort()
    q = lambda p: live[min(int(p * len(live)), len(live) - 1)]
    mean = st.mean(live)
    return dict(days=len(eq), live=len(live), mean=mean, median=st.median(live),
                p5=q(0.05), p1=q(0.01), worst=live[0], best=live[-1],
                win_pct=100 * sum(1 for r in live if r > 0) / len(live),
                p5_over_mean=(abs(q(0.05)) / mean if mean > 0 else None), mdd=mdd)


def main():
    runs, skipped = [], 0
    for path in sorted(glob.glob(os.path.join(RESULTS, '*', '*', 'backtest.json'))):
        try:
            meta = json.load(open(path))['backtest']
        except Exception:
            skipped += 1
            continue
        if not meta.get('completed') or meta.get('error'):
            skipped += 1
            continue
        got = daily(os.path.join(os.path.dirname(path), 'strategy_equity.json'))
        if got:
            runs.append(dict(name=meta.get('name'), start=str(meta.get('backtestStart'))[:10],
                             end=str(meta.get('backtestEnd'))[:10], **got))
        else:
            skipped += 1

    def dist(key):
        v = sorted(r[key] for r in runs if r[key] is not None)
        if not v:
            return None
        q = lambda p: v[min(int(p * len(v)), len(v) - 1)]
        return dict(n=len(v), p10=q(.10), median=q(.50), p90=q(.90), worst=v[0], best=v[-1])

    ratios = sorted(r['p5_over_mean'] for r in runs if r['p5_over_mean'])
    worst = sorted(runs, key=lambda r: r['mdd'])[:6]
    doc = dict(
        generated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        source='completed QC runs under strategies/sstrangle/results',
        method=('collapse intraday equity points to one close per UTC date; simple daily returns; '
                'drop exact-zero days (flat mark, no position); statistics per run, then summarise '
                'the distribution across runs'),
        runs_used=len(runs), runs_skipped=skipped,
        caveat=('These runs are not independent strategies: several are the same strategy with small '
                'parameter changes over overlapping periods, so the cross-run distribution is narrower '
                'than the underlying uncertainty. The daily loss tail is also truncated by mandatory '
                'exits and does not include intraday excursion.'),
        drawdown=dist('mdd'),
        daily_p5=dist('p5'),
        daily_worst=dist('worst'),
        win_pct=dist('win_pct'),
        p5_over_mean=dict(n=len(ratios),
                          median=st.median(ratios) if ratios else None,
                          p10=ratios[int(.1 * len(ratios))] if ratios else None,
                          p90=ratios[int(.9 * len(ratios))] if ratios else None),
        insolvent=[dict(name=r['name'], mdd=r['mdd']) for r in runs if r['mdd'] <= -0.95],
        worst_drawdowns=[dict(name=r['name'], mdd=r['mdd'], days=r['days'], p5=r['p5']) for r in worst])
    json.dump(doc, open(os.path.join(OUT, 'tail_audit.json'), 'w'), indent=2)
    print(json.dumps({k: doc[k] for k in ('runs_used', 'runs_skipped', 'drawdown', 'p5_over_mean')}, indent=2))
    print('worst drawdowns:')
    for r in worst:
        print(f"  {r['mdd']*100:7.1f}%  p5/day {r['p5']*100:6.2f}%  {r['name']}")


if __name__ == '__main__':
    main()
