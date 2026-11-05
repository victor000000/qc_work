#!/usr/bin/env python3
"""Inspect (etf, lever) probe history — dead/alive/borderline pairs from recent rounds.

Usage:
  python3 strategies/s002/dead_pairs_cli.py
  python3 strategies/s002/dead_pairs_cli.py --rounds 10 --baked ewg --baked spdw
  python3 strategies/s002/dead_pairs_cli.py --show alive  # or 'dead' / 'borderline'
"""
from __future__ import annotations
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from round_lib import DB_PATH  # noqa: E402
from probe_history import (  # noqa: E402
    collect_recent_pair_stats, dead_pairs, alive_pair_stats, summary,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    ap.add_argument('--rounds', type=int, default=5)
    ap.add_argument('--baked', action='append', default=[],
                    help='ETFs whose observations are stale (just baked)')
    ap.add_argument('--show', choices=['summary', 'dead', 'alive', 'borderline'],
                    default='summary')
    args = ap.parse_args(argv)

    stats = collect_recent_pair_stats(DB_PATH, n_batches=args.rounds,
                                      recent_baked_etfs=set(args.baked))
    s = summary(stats)

    print(f'Probe-history summary (last {args.rounds} rounds):')
    print(f'  unique (etf, lever) pairs: {s["n_pairs"]}')
    print(f'  total observations:        {s["n_obs"]}')
    print(f'  DEAD       (max|lift| < 0.0001): {s["dead"]}')
    print(f'  ALIVE      (max|lift| ≥ 0.001):  {s["alive"]}')
    print(f'  BORDERLINE (in between):         {s["borderline"]}')

    if args.show == 'dead':
        print('\nDEAD pairs:')
        for etf, lever in sorted(s['dead_set']):
            n_obs = len(stats[(etf, lever)])
            print(f'  {etf:6s} {lever:10s}  (n={n_obs})')
    elif args.show == 'alive':
        print('\nALIVE pairs (top by max|lift|):')
        for p in alive_pair_stats(stats)[:30]:
            print(f'  {p.etf:6s} {p.lever:10s}  '
                  f'max|lift|={p.max_abs_lift:+.5f}  avg={p.avg_lift:+.5f}  n={p.n_probes}')
    elif args.show == 'borderline':
        print('\nBORDERLINE pairs:')
        for k, lifts in sorted(stats.items()):
            ml = max(abs(l) for l in lifts) if lifts else 0
            if 0.0001 <= ml < 0.001:
                print(f'  {k[0]:6s} {k[1]:10s}  max|lift|={ml:+.5f}  n={len(lifts)}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
