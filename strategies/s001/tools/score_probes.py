"""Score probe specs from a completed round: compute deltas, classify, write
probe_results, refresh field classifications and sweep winners.

Usage:
  python -m scripts.score_probes --round 407 --bake-hash <md5>
"""

import argparse
import re
import qc_storage as storage
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from s001.paths import WORKSPACE_ROOT, DATA_DIR
from s001.fundamental_probes import (  # noqa: E402
    classify_delta, field_rollup, CONTAINER_SHORT, _threshold_short,
    update_sweep_winner, SWEEP_MAGS, SWEEP_GATES,
    update_v3_winner, _expected_coarse_count, _format_threshold,
    EXPECTED_COARSE_CELLS_NUMERIC,
)

CONTAINER_FROM_SHORT = {v: k for k, v in CONTAINER_SHORT.items()}


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# Default probe spec name pattern (existing v1 behavior).
SPEC_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)_'
    r'(?P<op>gt|gte|lt|lte|eq|in)(?P<thr>.+)$'
)

# v2: Phase 2 sweep spec name pattern.
SWEEP_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_sw_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_m(?P<mag>\d+)_g(?P<gate>\d+)$'
)

V3_COARSE_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_v3c_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_o(?P<op>gt|lt)_m(?P<mag>\d+)_g(?P<gate>\d+)_t(?P<thr>\d+)$')

V3_REFINE_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_v3r_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_o(?P<op>gt|lt)_m(?P<mag>\d+)_g(?P<gate>\d+)_t(?P<thr>\d+)$')

MEGA_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_mg_'
    r'(?P<mech>score|skip|stop|petgt|convg|convb)_'
    r'(?P<cs>[a-z]+)_(?P<field>.+)$'
)

OP_FROM_SHORT_V3 = {'gt': '>', 'lt': '<'}


def _parse_probe_spec_name(name):
    """Return (container, field_name, op_short, thr_short) for default probes,
    or None if name doesn't match."""
    m = SPEC_NAME_RE.match(name)
    if not m:
        return None
    cs = m.group('cs')
    cont = CONTAINER_FROM_SHORT.get(cs)
    if cont is None:
        return None
    return cont, m.group('field'), m.group('op'), m.group('thr')


def _parse_sweep_spec_name(name):
    """Return (container, field_name, mag, gate) for sweep specs, or None."""
    m = SWEEP_NAME_RE.match(name)
    if not m:
        return None
    cs = m.group('cs')
    cont = CONTAINER_FROM_SHORT.get(cs)
    if cont is None:
        return None
    mag_short = m.group('mag')
    gate_short = m.group('gate')
    mag_canonical = next((x for x in SWEEP_MAGS if x.replace('.', '') == mag_short), None)
    gate_canonical = next((x for x in SWEEP_GATES if x.replace('.', '').lstrip('-') == gate_short), None)
    if mag_canonical is None or gate_canonical is None:
        return None
    return cont, m.group('field'), mag_canonical, gate_canonical


def _parse_v3_spec_name(name):
    """Return (kind, container, field_name, op, mag, gate_str, thr_idx) for v3 coarse/refine specs.
    kind is 'coarse' or 'refine'. Returns None if no match."""
    for kind, regex in (('coarse', V3_COARSE_NAME_RE), ('refine', V3_REFINE_NAME_RE)):
        m = regex.match(name)
        if not m:
            continue
        cs = m.group('cs')
        cont = CONTAINER_FROM_SHORT.get(cs)
        if cont is None:
            return None
        op = OP_FROM_SHORT_V3[m.group('op')]
        mag = int(m.group('mag')) / 100.0
        gate_str = '.' + m.group('gate').zfill(2) if len(m.group('gate')) == 1 else '.' + m.group('gate')
        return kind, cont, m.group('field'), op, mag, gate_str, m.group('thr')
    return None


def _noop_baseline(cur, round_n):
    cur.execute(
        "SELECT car_mdd FROM experiments "
        "WHERE name LIKE ? AND status IN ('imported', 'success') AND car_mdd IS NOT NULL",
        (f'S001_R{round_n}_VBAKE%_NOOP_%',))
    vals = [r[0] for r in cur.fetchall()]
    assert len(vals) >= 1, f'Round {round_n} has no NOOP experiments'
    spread = max(vals) - min(vals)
    assert spread <= 0.0005, (
        f'Round {round_n} NOOP spread {spread:.5f} > 0.0005 — base nondeterministic')
    return sum(vals) / len(vals)


def score_round(db_path, round_n, bake_hash):
    with storage.connect(db_path) as con:
        con.row_factory = storage.Row
        cur = con.cursor()

        baseline = _noop_baseline(cur, round_n)
        now = _now_iso()

        cur.execute(
            "SELECT name, car_mdd FROM experiments "
            "WHERE name LIKE ? AND status IN ('imported', 'success') AND car_mdd IS NOT NULL",
            (f'S001_R{round_n}_%',))
        touched_field_ids = set()
        sweep_field_ids = set()
        n_results = 0
        for row in cur.fetchall():
            # Mega-round routing (anchored prefix — try first)
            mega = MEGA_NAME_RE.match(row['name'])
            if mega:
                mech = mega.group('mech')
                cs = mega.group('cs')
                field_name = mega.group('field')
                container = CONTAINER_FROM_SHORT.get(cs)
                if container is None:
                    continue
                cur.execute(
                    "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
                    (container, field_name))
                f = cur.fetchone()
                if f is None:
                    continue
                from s001.fundamental_probes import MECH_DEFAULTS, flip_op
                defaults = MECH_DEFAULTS[mech]
                op_used = (f['probe_op'] if defaults['side'] == 'good'
                           else flip_op(f['probe_op']))
                delta = row['car_mdd'] - baseline
                cls = classify_delta(delta)
                applied_gate = defaults['gate'] if defaults['gate'] is not None else ''
                applied_boost = defaults['mag'] if defaults['mag'] is not None else 0.0
                try:
                    cur.execute(
                        """INSERT INTO probe_results
                           (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                            spec_car_mdd, delta, classification, applied_op,
                            applied_threshold, applied_gate, applied_boost,
                            recorded_at, is_sweep_variant, sweep_stage, mechanism)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)""",
                        (f['id'], row['name'], round_n, bake_hash, baseline,
                         row['car_mdd'], delta, cls, op_used, f['probe_threshold'],
                         applied_gate, applied_boost, now, mech))
                    n_results += 1
                except storage.IntegrityError:
                    pass
                touched_field_ids.add(f['id'])
                continue

            # v3 coarse / refine routing (most specific — try first)
            v3_parsed = _parse_v3_spec_name(row['name'])
            if v3_parsed is not None:
                kind, container, field_name, op, mag, gate_str, thr_idx = v3_parsed
                cur.execute(
                    "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
                    (container, field_name))
                f = cur.fetchone()
                if f is None:
                    continue
                # Look up the threshold value from field_universe_stats by percentile slot
                cur.execute(
                    "SELECT p25, p50, p75 FROM field_universe_stats "
                    "WHERE field_id = ? AND bake_hash = ?",
                    (f['id'], bake_hash))
                stats = cur.fetchone()
                if stats is None:
                    continue
                pct_to_col = {'25': 'p25', '50': 'p50', '75': 'p75'}
                col = pct_to_col.get(thr_idx)
                if col is None:
                    continue
                hint = f['data_type_hint'] or 'numeric'
                applied_threshold = _format_threshold(stats[col], hint)
                applied_gate = f'decline > {gate_str}'
                applied_boost = mag
                delta = row['car_mdd'] - baseline
                cls = classify_delta(delta)
                try:
                    cur.execute(
                        """INSERT INTO probe_results
                           (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                            spec_car_mdd, delta, classification, applied_op,
                            applied_threshold, applied_gate, applied_boost,
                            recorded_at, is_sweep_variant, sweep_stage)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                        (f['id'], row['name'], round_n, bake_hash, baseline,
                         row['car_mdd'], delta, cls, op, applied_threshold,
                         applied_gate, applied_boost, now, kind))
                    n_results += 1
                except storage.IntegrityError:
                    pass
                touched_field_ids.add(f['id'])
                if kind == 'coarse':
                    sweep_field_ids.add(('v3_coarse', f['id']))
                else:
                    sweep_field_ids.add(('v3_refine', f['id']))
                continue

            # Try sweep regex first (more specific — '_sw_' anchor)
            sweep_parsed = _parse_sweep_spec_name(row['name'])
            if sweep_parsed is not None:
                container, field_name, mag, gate = sweep_parsed
                cur.execute(
                    "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
                    (container, field_name))
                f = cur.fetchone()
                if f is None:
                    continue
                delta = row['car_mdd'] - baseline
                cls = classify_delta(delta)
                applied_op = f['probe_op']
                applied_threshold = f['probe_threshold']
                applied_gate = f'decline > {gate}'
                applied_boost = float(mag)
                try:
                    cur.execute(
                        """INSERT INTO probe_results
                           (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                            spec_car_mdd, delta, classification, applied_op,
                            applied_threshold, applied_gate, applied_boost,
                            recorded_at, is_sweep_variant)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                        (f['id'], row['name'], round_n, bake_hash, baseline,
                         row['car_mdd'], delta, cls, applied_op,
                         applied_threshold, applied_gate, applied_boost, now))
                    n_results += 1
                except storage.IntegrityError:
                    pass
                touched_field_ids.add(f['id'])
                sweep_field_ids.add(('v2', f['id']))
                continue

            # Default probe regex (existing v1 behavior)
            parsed = _parse_probe_spec_name(row['name'])
            if parsed is None:
                continue
            container, field_name, op_short, thr_short = parsed
            cur.execute(
                "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
                (container, field_name))
            f = cur.fetchone()
            if f is None:
                continue
            if f['probe_threshold'] is not None:
                expected_thr = _threshold_short(f['probe_threshold'], f['probe_op'])
                if thr_short != expected_thr:
                    continue
            delta = row['car_mdd'] - baseline
            cls = classify_delta(delta)
            try:
                cur.execute(
                    """INSERT INTO probe_results
                       (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                        spec_car_mdd, delta, classification, applied_op,
                        applied_threshold, applied_gate, applied_boost,
                        recorded_at, is_sweep_variant)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (f['id'], row['name'], round_n, bake_hash, baseline,
                     row['car_mdd'], delta, cls, f['probe_op'],
                     f['probe_threshold'], f['probe_gate'], f['probe_boost'], now))
                n_results += 1
            except storage.IntegrityError:
                pass
            touched_field_ids.add(f['id'])

        # Refresh field-row classification for each touched field
        # (score-only — non-score mega cells must not poison v3 pickup)
        for fid in touched_field_ids:
            cur.execute(
                "SELECT classification FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? "
                "AND (mechanism IS NULL OR mechanism = 'score')",
                (fid, bake_hash))
            results = [{'classification': r[0]} for r in cur.fetchall()]
            rollup = field_rollup(results)
            cur.execute(
                "UPDATE fundamental_fields SET classification = ?, "
                "last_classified_at = ? WHERE id = ?", (rollup, now, fid))

        # v2 sweep winner update (legacy specs only — sweep_stage IS NULL but
        # is_sweep_variant=1)
        v2_field_ids = {fid for kind, fid in sweep_field_ids if kind == 'v2'}
        for fid in v2_field_ids:
            cur.execute(
                "SELECT COUNT(*) FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? AND is_sweep_variant = 1 "
                "AND sweep_stage IS NULL",
                (fid, bake_hash))
            count = cur.fetchone()[0]
            if count >= len(SWEEP_MAGS) * len(SWEEP_GATES):
                update_sweep_winner(con, fid, bake_hash)

        # v3 refine completion check — when refine done, seal as final winner
        v3_refine_field_ids = {fid for kind, fid in sweep_field_ids if kind == 'v3_refine'}
        for fid in v3_refine_field_ids:
            cur.execute("SELECT * FROM fundamental_fields WHERE id = ?", (fid,))
            f = cur.fetchone()
            if f['sweep_phase'] != 3:
                continue
            from s001.fundamental_probes import refine_grid
            import json as _json
            try:
                refine_sets = {
                    'op': set(_json.loads(f['refine_op_set'])),
                    'mag': set(_json.loads(f['refine_mag_set'])),
                    'gate': set(_json.loads(f['refine_gate_set'])),
                    'threshold': set(_json.loads(f['refine_threshold_set'])),
                }
            except (TypeError, _json.JSONDecodeError):
                continue
            coarse_winner = {
                'op': f['coarse_winner_op'], 'mag': f['coarse_winner_mag'],
                'gate': f['coarse_winner_gate'], 'threshold': f['coarse_winner_threshold'],
            }
            expected = len(refine_grid(coarse_winner, refine_sets))
            cur.execute(
                "SELECT COUNT(*) FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? AND sweep_stage = 'refine'",
                (fid, bake_hash))
            count = cur.fetchone()[0]
            if count >= expected:
                update_v3_winner(con, fid, bake_hash)

        return {'n_results': n_results, 'baseline': baseline,
                'fields_touched': len(touched_field_ids),
                'sweep_fields': len(sweep_field_ids)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--round', dest='round_n', type=int, required=True)
    p.add_argument('--bake-hash', required=True)
    p.add_argument('--db', default=str(DATA_DIR / 'S001.duckdb'))
    args = p.parse_args()
    out = score_round(db_path=args.db, round_n=args.round_n, bake_hash=args.bake_hash)
    print(f"Round {args.round_n}: scored {out['n_results']} probes, "
          f"baseline={out['baseline']:.4f}, "
          f"fields_touched={out['fields_touched']}, "
          f"sweep_fields={out['sweep_fields']}")


if __name__ == '__main__':
    main()
