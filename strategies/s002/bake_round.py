#!/usr/bin/env python3
"""Apply a confirmed bake to the s002 base file.

Usage:
  python3 strategies/s002/bake_round.py ewc tp=0.15 --label tp
  python3 strategies/s002/bake_round.py rwo tp=0.06 --label tp
  python3 strategies/s002/bake_round.py vo tp=0.12 sl=0.015 --label tp_sl

Backs up the base file before modifying. Rejects no-op edits.
"""
from __future__ import annotations
import argparse
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from round_lib import apply_bake, ROOT  # noqa: E402

DEFAULT_BASE = f'{ROOT}/strategies/s002/s002_20260628_ls_base.py'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('etf')
    ap.add_argument('changes', nargs='+',
                    help='key=value pairs, e.g. tp=0.15 sl=0.025')
    ap.add_argument('--base', default=DEFAULT_BASE)
    ap.add_argument('--label', default='bake',
                    help='Backup filename suffix label')
    args = ap.parse_args(argv)

    ch: dict = {}
    for kv in args.changes:
        k, v = kv.split('=')
        try:
            ch[k.strip()] = float(v) if '.' in v else int(v)
        except ValueError:
            ch[k.strip()] = v.strip()

    bak = apply_bake(args.base, args.etf, ch, args.label)
    print(f'Baked {args.etf} {ch} into {os.path.basename(args.base)}')
    print(f'Backup: {bak}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
