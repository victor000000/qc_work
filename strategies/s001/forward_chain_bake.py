"""Phase B: forward-chain bake — add one probe at a time, verify, keep if it lifts.

Algorithm:
  1. Start from PRE_BAKE_MD5 (clean base.py, NOOP car_mdd = 2.130).
  2. Sort candidates by delta DESC across all mechs.
  3. For each candidate:
     a. Apply (already-kept probes + candidate) to base.py.
     b. Queue verify spec, wait, read car_mdd.
     c. If new car_mdd >= prev_best + EPS: keep candidate, update prev_best.
        Else: candidate hurts (or doesn't help) → drop, continue with rest.
  4. After loop: leave base.py with only-kept probes baked.

Notes:
  - Probes baked as raw flat blocks (NOT mutex-grouped). Each kept probe is a
    standalone try/except. The chain naturally avoids stacking failures because
    only probes that MARGINALLY help when combined are kept.
  - Verify requires QC throughput ~1 backtest/min. With ~15 candidates that's
    ~15 min wall time. Driver script polls until each verify completes.
"""

from s001.paths import WORKSPACE_ROOT, DATA_DIR
import argparse
import ast
import hashlib
import json
import re
import qc_storage as storage
import sys
import time
from pathlib import Path

PRE_BAKE_MD5 = '7031d646104209b44816da09cf97051f'

ALIAS_SETUP = """\
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ers_z = getattr(_fz, 'earning_ratios', None) if _fz else None
    _er_z  = getattr(_fz, 'earning_reports', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _sr_z  = getattr(_fz, 'security_reference', None) if _fz else None
    _fs_z  = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z  = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _cfs_z = getattr(_fs_z, 'cash_flow_statement', None) if _fs_z else None
   except: _ops_z=_vr_z=_ers_z=_er_z=_ac_z=_sr_z=_fs_z=_bs_z=_inc_z=_cfs_z=None
"""

PROBE_RE = re.compile(
    r"=_cfs_z=None\n"
    r"(   try:\n    _v = f_\(.+?\n    if _v is not None and .+?\n   except: pass\n)",
    re.DOTALL,
)

ENTRY_MECHS = ('score', 'skip', 'convg', 'convb')
EXIT_MECHS = ('stop', 'petgt')


def fetch_candidates(db, top_n):
    con = storage.connect(db)
    cur = con.cursor()
    cur.execute("""
    WITH base AS (
      SELECT pr.field_id, pr.mechanism, pr.delta, pr.round_n, pr.experiment_name,
             e.total_orders, ROUND(pr.delta, 4) as d4, ff.field_name
      FROM probe_results pr
      JOIN experiments e ON e.name = pr.experiment_name
      JOIN fundamental_fields ff ON ff.id = pr.field_id
      WHERE pr.round_n IN (603, 604) AND pr.mechanism IS NOT NULL
        AND pr.delta > 0.001 AND e.total_orders > 10000
    ),
    clusters AS (SELECT mechanism, d4, COUNT(DISTINCT field_id) as n FROM base GROUP BY mechanism, d4)
    SELECT b.field_name, b.mechanism, b.delta, b.round_n, b.experiment_name
    FROM base b JOIN clusters c ON c.mechanism = b.mechanism AND c.d4 = b.d4
    WHERE c.n < 5
    ORDER BY b.delta DESC LIMIT ?
    """, (top_n,))
    rows = cur.fetchall()
    con.close()
    return rows


def fetch_probe_block(db, spec_name):
    con = storage.connect(db)
    cur = con.cursor()
    cur.execute("SELECT code FROM backtest_queue WHERE name=?", (spec_name,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    m = PROBE_RE.search(row[0])
    return m.group(1) if m else None


def get_base_path():
    return Path(str(WORKSPACE_ROOT / 'strategies/s001/s001_20260425_base.py'))


def reset_base_to_clean():
    """Use git to restore base.py to the pre-bake commit."""
    import subprocess
    subprocess.run(['git', 'checkout', PRE_BAKE_MD5[:8], '--', 's001/s001_20260425_base.py'],
                   cwd=str(WORKSPACE_ROOT / 'strategies/s001'), check=False)
    # Verify
    h = hashlib.md5(get_base_path().read_bytes()).hexdigest()
    if h != PRE_BAKE_MD5:
        # fallback: use git show
        out = subprocess.check_output(['git', 'show', 'HEAD~3:data/s001/s001_20260425_base.py'],
                                       cwd=str(WORKSPACE_ROOT / '')).decode()
        get_base_path().write_text(out)
        h = hashlib.md5(get_base_path().read_bytes()).hexdigest()
    return h


def apply_probes(base_src, entry_probes, exit_probes):
    """Inject given probe blocks at the inject points, with shared alias setup."""
    new_src = base_src
    if entry_probes:
        payload = '   # === FWD-CHAIN BATCH === START\n' + ALIAS_SETUP + ''.join(entry_probes) + '   # === END ===\n'
        new_src = new_src.replace('   # --- ENTRY INJECT POINT ---',
                                   payload + '   # --- ENTRY INJECT POINT ---', 1)
    if exit_probes:
        payload = '   # === FWD-CHAIN BATCH === START\n' + ALIAS_SETUP + ''.join(exit_probes) + '   # === END ===\n'
        new_src = new_src.replace('   # --- EXIT INJECT POINT ---',
                                   payload + '   # --- EXIT INJECT POINT ---', 1)
    return new_src


def queue_verify(db, code, name):
    h = hashlib.md5(code.encode()).hexdigest()
    con = storage.connect(db)
    cur = con.cursor()
    try:
        cur.execute("INSERT INTO backtest_queue (name, code, status, priority, submitted_at, code_hash, project_id) "
                    "VALUES (?, ?, 'queued', 1, datetime('now'), ?, NULL)", (name, code, h))
    except storage.IntegrityError as e:
        con.close()
        return False, str(e)
    con.commit()
    con.close()
    return True, None


def wait_done(db, name, timeout_s=900):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        con = storage.connect(db)
        cur = con.cursor()
        cur.execute("SELECT status FROM backtest_queue WHERE name=?", (name,))
        row = cur.fetchone()
        con.close()
        if not row: return None
        if row[0] in ('done', 'failed'):
            return row[0]
        time.sleep(20)
    return 'timeout'


def fetch_result(db, name):
    con = storage.connect(db)
    cur = con.cursor()
    cur.execute("SELECT car_mdd, cagr, dd, total_orders FROM experiments WHERE name=?", (name,))
    row = cur.fetchone()
    con.close()
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default=str(DATA_DIR / 'S001.duckdb'))
    p.add_argument('--top-n', type=int, default=15)
    p.add_argument('--baseline', type=float, default=2.1299)
    p.add_argument('--epsilon', type=float, default=0.0005, help='min lift to keep candidate')
    p.add_argument('--state-file', default=str(WORKSPACE_ROOT / 'strategies/s001/research/forward_chain_state.json'))
    p.add_argument('--start-step', type=int, default=0, help='resume from this step')
    args = p.parse_args()

    state = {'baseline': args.baseline, 'history': []}
    if Path(args.state_file).exists():
        state = json.loads(Path(args.state_file).read_text())
        print(f'resumed: {len(state["history"])} prior steps')

    cands = fetch_candidates(args.db, args.top_n)
    print(f'top-{args.top_n} candidates by Δ:')
    for i, c in enumerate(cands):
        print(f'  {i:2d}. {c[1]:6s} Δ{c[2]:+.4f}  {c[0]}')

    base_path = get_base_path()
    base_md5 = hashlib.md5(base_path.read_bytes()).hexdigest()
    if base_md5 != PRE_BAKE_MD5:
        print(f'ERROR: base.py md5 {base_md5} != PRE_BAKE_MD5 {PRE_BAKE_MD5}')
        print('Reset base.py first via `git checkout 7839202 -- s001/s001_20260425_base.py` then retry')
        sys.exit(1)
    base_src = base_path.read_text()

    # Build state: kept probes from history
    kept = []
    prev_best = state.get('prev_best', args.baseline)
    for h in state['history']:
        if h.get('kept'):
            kept.append(h['probe_block'])

    for step, (field_name, mech, delta, round_n, spec_name) in enumerate(cands):
        if step < args.start_step: continue
        print(f'\n=== step {step}: try {mech} {field_name} (Δ{delta:+.4f}) ===')
        probe_block = fetch_probe_block(args.db, spec_name)
        if not probe_block:
            print('  (skip: no probe block)')
            continue

        # Build candidate base
        is_entry = mech in ENTRY_MECHS
        entry_probes = [p for p in kept if _classify_probe(p) == 'entry']
        exit_probes = [p for p in kept if _classify_probe(p) == 'exit']
        if is_entry: entry_probes.append(probe_block)
        else: exit_probes.append(probe_block)

        candidate_src = apply_probes(base_src, entry_probes, exit_probes)
        try:
            ast.parse(candidate_src)
        except SyntaxError as e:
            print(f'  SYNTAX ERROR: {e}'); break

        # Mutate code with unique comment so QC sees a fresh hash
        unique_code = candidate_src.replace('   # --- ENTRY INJECT POINT ---',
                                            f'   # fwd_chain_step_{step}\n   # --- ENTRY INJECT POINT ---', 1)
        verify_name = f'S001_R607_FWD_S{step:02d}_{mech}_{field_name[:30]}'.replace('.', '_')[:80]
        ok, err = queue_verify(args.db, unique_code, verify_name)
        if not ok:
            print(f'  queue failed: {err}'); continue
        print(f'  queued {verify_name}')
        status = wait_done(args.db, verify_name)
        print(f'  {verify_name} → {status}')
        if status != 'done':
            print('  candidate run failed; treat as no lift'); continue
        result = fetch_result(args.db, verify_name)
        if not result:
            print('  no result row; skip'); continue
        car_mdd, cagr, dd, orders = result
        lift = car_mdd - prev_best
        keep = lift >= args.epsilon
        print(f'  car_mdd={car_mdd:.4f} (Δvs_prev={lift:+.4f}, vs_NOOP={car_mdd - args.baseline:+.4f})  cagr={cagr} dd={dd} ord={orders}')
        print(f'  decision: {"KEEP" if keep else "DROP"}')

        state['history'].append({
            'step': step, 'mech': mech, 'field': field_name, 'delta': delta,
            'verify_name': verify_name, 'car_mdd': car_mdd, 'cagr': cagr, 'dd': dd, 'orders': orders,
            'lift_vs_prev': lift, 'lift_vs_noop': car_mdd - args.baseline,
            'kept': keep, 'probe_block': probe_block,
        })
        if keep:
            kept.append(probe_block)
            prev_best = car_mdd
            state['prev_best'] = prev_best
        Path(args.state_file).write_text(json.dumps(state, indent=2))

    # Final apply
    entry_kept = [p for p in kept if _classify_probe(p) == 'entry']
    exit_kept = [p for p in kept if _classify_probe(p) == 'exit']
    final_src = apply_probes(base_src, entry_kept, exit_kept)
    ast.parse(final_src)
    base_path.write_text(final_src)
    new_hash = hashlib.md5(final_src.encode()).hexdigest()

    # Update settings
    con = storage.connect(args.db)
    cur = con.cursor()
    cur.execute("UPDATE settings SET value=? WHERE category='strategy' AND key='current_bake_hash'", (new_hash,))
    con.commit()
    con.close()
    print(f'\n=== FINAL ===')
    print(f'kept {len(kept)} probes; new md5: {new_hash}')
    print(f'final car_mdd: {prev_best:.4f}  vs NOOP {args.baseline:.4f}  Δ={prev_best - args.baseline:+.4f}')


def _is_entry_block(block):
    """deprecated — kept for back-compat"""
    return _classify_probe(block) == 'entry'


def _classify_probe(probe_block):
    """Determine if a probe block is entry-side or exit-side based on its action."""
    if 'continue' in probe_block: return 'entry'  # skip
    if 'score *=' in probe_block: return 'entry'
    if 'conv *=' in probe_block: return 'entry'
    if 'stop *=' in probe_block: return 'exit'
    if 'petgt *=' in probe_block: return 'exit'
    return 'entry'  # default


if __name__ == '__main__':
    main()
