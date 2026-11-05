"""Generate the universe scanner backtest spec.

The scanner runs once per bake. On the first OnData call it iterates every QQQ
symbol × every non-categorical fundamental field, collects values in-process,
computes {p10, p25, p50, p75, p90} per field, and logs one compact PCT line
per field. After the backtest completes, run `scripts/parse_scan_log.py` to
read those PCT lines into field_universe_stats.

Compact log format keeps the spec under QC's 128k char limit and the log
output under per-day budget. ~879 PCT lines per scan (one per non-categorical
field) instead of ~88k raw triples.

Usage:
    python -m s001.tools.gen_scan_spec --base strategies/s001/s001_*.py \\
        --bake-hash <md5> [--db data/S001.duckdb]
"""

import argparse
import hashlib
import qc_storage as storage
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from s001.paths import WORKSPACE_ROOT, DATA_DIR


# Algorithm-side scanner block. Reads field metadata from a list literal,
# walks every QQQ symbol × field, aggregates values, computes percentiles
# inline (linear interpolation matching numpy default), logs one PCT line
# per field with sample_size>=50.
SCAN_BLOCK_HEADER = """\
  # === SCANNER BLOCK ===
  if not getattr(self, '_scanner_done', False):
   self._scanner_done = True
"""

SCAN_BLOCK_BODY = """\
   _SF_DATA = {}
   for _ssym in equities:
    try:
     _ssec = self.securities.get(_ssym)
     if _ssec is None: continue
     _sfz = _ssec.fundamentals
     _sfs = getattr(_sfz, 'financial_statements', None) if _sfz else None
    except: continue
    for fid, _cont, _fname, _period in _SF_FIELDS:
     try:
      if _cont in ('balance_sheet','income_statement','cash_flow_statement'):
       _c = getattr(_sfs, _cont, None) if _sfs else None
      else:
       _c = getattr(_sfz, _cont, None) if _sfz else None
      _vv = getattr(_c, _fname, None) if _c else None
      if _period and _vv is not None: _vv = getattr(_vv, _period, None)
      if _vv is not None:
       _SF_DATA.setdefault(fid, []).append(float(_vv))
     except: pass
   for fid, values in _SF_DATA.items():
    n = len(values)
    if n < 50: continue
    values.sort()
    pcts = []
    for p in (10, 25, 50, 75, 90):
     h = (n-1) * (p/100.0)
     lo = int(h); up = lo+1
     if up >= n: pcts.append(values[lo])
     else: pcts.append((up-h)*values[lo] + (h-lo)*values[up])
    self.log(f'PCT,{fid},{pcts[0]:.6g},{pcts[1]:.6g},{pcts[2]:.6g},{pcts[3]:.6g},{pcts[4]:.6g},{n}')
  # === END SCANNER BLOCK ===
"""


def _build_field_list_literal(fields):
    """Render `_SF_FIELDS = [(field_id, container, field_name, period), ...]` as a string."""
    items = []
    for f in fields:
        period = f"'{f['period']}'" if f['period'] else 'None'
        items.append(f"({f['id']},'{f['container']}','{f['field_name']}',{period})")
    return "   _SF_FIELDS = [" + ",".join(items) + "]\n"


def generate_scan_spec(db_path, base_path, bake_hash):
    """Generate and queue the scanner backtest spec."""
    with storage.connect(db_path) as con:
        con.row_factory = storage.Row
        cur = con.cursor()
        cur.execute("""SELECT id, container, field_name, period, data_type_hint
                       FROM fundamental_fields
                       WHERE (data_type_hint IS NULL OR data_type_hint != 'categorical')
                         AND container IS NOT NULL
                         AND field_name IS NOT NULL
                       ORDER BY id""")
        fields = [dict(r) for r in cur.fetchall()]

    with open(base_path) as fh:
        base_code = fh.read()

    field_list = _build_field_list_literal(fields)
    scan_block = SCAN_BLOCK_HEADER + field_list + SCAN_BLOCK_BODY
    # Inject before the LAST occurrence (_scan_entries' loop, not _scan_exits'),
    # since the same `for sym in equities:` line appears in both methods.
    anchor = '  for sym in equities:'
    last_idx = base_code.rfind(anchor)
    if last_idx == -1:
        raise SystemExit(f'anchor {anchor!r} not found in {base_path}')
    code = base_code[:last_idx] + scan_block + base_code[last_idx:]
    name = f'S001_SCAN_FUNDAMENTALS_{bake_hash}'
    h = hashlib.md5(code.encode()).hexdigest()

    with storage.connect(db_path) as con:
        cur = con.cursor()
        try:
            cur.execute(
                "INSERT INTO backtest_queue "
                "(name, code, status, priority, submitted_at, code_hash, project_id) "
                "VALUES (?, ?, 'queued', 0, datetime('now'), ?, NULL)",
                (name, code, h))
            con.commit()
            return name, len(code), len(fields)
        except storage.IntegrityError as e:
            print(f'Skip {name}: {e}', file=sys.stderr)
            return None, 0, 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', required=True, help='Path to s001_*_base.py')
    p.add_argument('--bake-hash', required=True)
    p.add_argument('--db', default=str(DATA_DIR / 'S001.duckdb'))
    args = p.parse_args()
    name, code_size, field_count = generate_scan_spec(args.db, args.base, args.bake_hash)
    if name:
        print(f'Queued scan spec: {name}')
        print(f'Code size: {code_size} chars (limit 128000)')
        print(f'Fields covered: {field_count}')


if __name__ == '__main__':
    main()
