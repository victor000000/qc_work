"""Emit per-round probe specs for gen_s001_R{N}.py to consume.

Usage:
  python -m scripts.emit_probes --round 407 --k-new 10 [--json]
  → prints specs as JSON list of {name, code} objects on stdout.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from s001.paths import WORKSPACE_ROOT, DATA_DIR
from s001.fundamental_probes import emit_probes_for_db  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--round', dest='round_n', type=int, required=True)
    p.add_argument('--k-new', type=int, default=10)
    p.add_argument('--db', default=str(DATA_DIR / 'S001.duckdb'))
    p.add_argument('--include-bind', action='store_true',
                   help='Prepend the BIND block to each spec body')
    p.add_argument('--json', action='store_true', help='Output JSON (default text)')
    args = p.parse_args()

    specs = emit_probes_for_db(
        db_path=args.db, round_n=args.round_n,
        k_new=args.k_new,
        include_bind=args.include_bind)

    if args.json:
        print(json.dumps([{'name': n, 'code': c} for n, c in specs], indent=2))
    else:
        for n, c in specs:
            print(f"# {n}")
            print(c)
            print()


if __name__ == '__main__':
    main()
