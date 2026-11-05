"""next_round_s001.py — single-command S001 round generator.

Usage: python3 data/next_round_s001.py [RID]

Auto-rotates through proven design patterns based on round-pattern history:
  - 2-regime productive compounds × _qsneg/_qzero (R1897/R1898 pattern)
  - 3-regime productive compounds × _qsneg/_qzero (R1899 pattern)
  - sector × productive_regime × _qsneg/_qzero (untested compound)
  - parent-novel: _qsneg × productive × medium-decline
  - score-class on productive 2-regime compounds

Each invocation:
  1. Determines next RID from existing gen_s001_R*.py files
  2. Selects pattern based on round-mod-N rotation
  3. Picks 2-regime / 3-regime / sector cells avoiding recent rounds
  4. Calls build_128_round() + run_audit_and_queue()
  5. P6/P7/P8/P9/P10 + auto-trim enforce 128 ±10 meaningful specs

If a pattern produces <118 specs (P8 fail), tries the next pattern.
"""

from s001.paths import WORKSPACE_ROOT, DATA_DIR
import glob
import re
import sys
from pathlib import Path

from s001.gen_s001_strategies import (
    pretick_or_die, run_audit_and_queue, build_128_round,
    T128_WT_MAGS, T128_QUALITY_MAGS, T128_GATE_MAGS,
    T128_MTF_MAGS, T128_REGIME_MAGS, T128_SD,
)


PRODUCTIVE_REGIMES = ['_reg_haccel', '_reg_vxx_falling3',
                      '_reg_double_panic', '_reg_qqq_up3', '_reg_hyg_dn14']

# All 10 unordered pairs of 5 productive regimes:
TWO_REGIME_PAIRS = [(a, b) for i, a in enumerate(PRODUCTIVE_REGIMES)
                            for b in PRODUCTIVE_REGIMES[i+1:]]

# All 10 unordered triples of 5 productive regimes:
THREE_REGIME_TRIPLES = [
    (a, b, c)
    for i, a in enumerate(PRODUCTIVE_REGIMES)
    for j, b in enumerate(PRODUCTIVE_REGIMES[i+1:], start=i+1)
    for c in PRODUCTIVE_REGIMES[j+1:]
]


def _next_rid() -> int:
    """Find highest RID in queue OR gen scripts and add 1.

    Both sources matter: gen_s001_R*.py file scan misses rounds queued via
    this helper itself (which writes no file). Queue scan catches those.
    """
    import qc_storage as storage
    rids = []
    for p in glob.glob(str(WORKSPACE_ROOT / 'strategies/s001/**/gen_s001_R*.py'), recursive=True):
        m = re.search(r'_R(\d+)', Path(p).name)
        if m:
            rids.append(int(m.group(1)))
    db_path = DATA_DIR / 'S001.duckdb'
    if db_path.exists():
        with storage.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True) as con:
            for (name,) in con.execute(
                "SELECT name FROM backtest_queue WHERE name LIKE 'S001_R%' "
                "UNION SELECT name FROM experiments WHERE name LIKE 'S001_R%'"
            ):
                m = re.search(r'_R(\d+)_', name)
                if m:
                    rids.append(int(m.group(1)))
    return max(rids) + 1 if rids else 1900


def _short_tag(reg):
    return reg.replace('_reg_', '').upper()[:4]


def _pattern_2regime(rid: int):
    """Generate _qsneg/_qzero × 2-regime compound × small_dec blocks."""
    # Pick 5 pairs that haven't been used in last 2 rounds
    pairs = TWO_REGIME_PAIRS[(rid * 3) % len(TWO_REGIME_PAIRS):][:5] + \
            TWO_REGIME_PAIRS[:max(0, 5 - (len(TWO_REGIME_PAIRS) - (rid * 3) % len(TWO_REGIME_PAIRS)))]
    pairs = pairs[:5]
    blocks = []
    off = 0
    for parent in ['_qsneg', '_qzero']:
        for r1, r2 in pairs[:2]:
            t = f'{_short_tag(r1)}{_short_tag(r2)}'
            blocks.append((f'W_{parent[1:].upper()}_{t}', 'wt_tilt',
                           f'{parent} and {T128_SD} and self.{r1} and self.{r2} and _ngt({{acc}},1e6)',
                           off, T128_WT_MAGS, '*='))
            off += 3
    # 1 entry_score_gate + 1 entry_score_regime fillers
    r1, r2 = pairs[2]
    blocks.append((f'G_QSN_{_short_tag(r1)}{_short_tag(r2)}', 'entry_score_gate',
                   f'_qsneg and {T128_SD} and self.{r1} and self.{r2} and _ngt({{acc}},1e6)',
                   off, T128_GATE_MAGS, '+='))
    off += 3
    blocks.append((f'R_QZ_{_short_tag(r1)}{_short_tag(r2)}', 'entry_score_regime',
                   f'_qzero and {T128_SD} and self.{r1} and self.{r2} and _ngt({{acc}},1e6)',
                   off, T128_REGIME_MAGS, '+='))
    return blocks


def _pattern_3regime(rid: int):
    """Generate _qsneg/_qzero × 3-regime triple × small_dec blocks."""
    triples = THREE_REGIME_TRIPLES[(rid * 4) % len(THREE_REGIME_TRIPLES):][:5] + \
              THREE_REGIME_TRIPLES[:max(0, 5 - (len(THREE_REGIME_TRIPLES) - (rid * 4) % len(THREE_REGIME_TRIPLES)))]
    triples = triples[:5]
    blocks = []
    off = 0
    for parent in ['_qsneg', '_qzero']:
        for tri in triples[:4]:
            t = ''.join(_short_tag(r)[:2] for r in tri)
            blocks.append((f'W_{parent[1:].upper()}_{t}', 'wt_tilt',
                           f'{parent} and {T128_SD} and self.{tri[0]} and self.{tri[1]} and self.{tri[2]} and _ngt({{acc}},1e6)',
                           off, T128_WT_MAGS, '*='))
            off += 3
    return blocks[:10]


def main():
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else _next_rid()
    pretick_or_die()

    # Pattern rotation with fallback. If primary pattern fails (P8/quota/etc),
    # retry with the alternate pattern.
    primary = _pattern_2regime if rid % 2 == 0 else _pattern_3regime
    alternate = _pattern_3regime if rid % 2 == 0 else _pattern_2regime
    last_err = None
    for fn in (primary, alternate):
        blocks = fn(rid)
        print(f'  trying pattern: {fn.__name__}, rid: {rid}, blocks: {len(blocks)}')
        try:
            R = build_128_round(rid=rid, blocks=blocks)
            return run_audit_and_queue(R)
        except Exception as e:
            print(f'  pattern {fn.__name__} failed: {e}')
            last_err = e
    raise RuntimeError(f'All patterns failed for rid={rid}; last: {last_err}')


if __name__ == '__main__':
    main()
