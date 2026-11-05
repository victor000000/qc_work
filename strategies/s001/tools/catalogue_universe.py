"""Catalogue script: scan LEAN __init__.pyi and emit fundamental_fields rows.

Idempotent: existing rows preserved (templates not overwritten by default).
Backfills container/period/data_type_hint on legacy rows that have only an accessor.
"""

import argparse
import qc_storage as storage
import sys
from pathlib import Path

# Allow running as script or module.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from s001.paths import WORKSPACE_ROOT, DATA_DIR
from s001.fundamental_probes import (  # noqa: E402
    CONTAINER_ALIAS,
    extract_lean_universe,
    default_period,
    default_template,
)


# Map legacy accessor prefix (e.g. '_vr', '_bs') → container value.
PREFIX_TO_CONTAINER = {
    '_vr':  'valuation_ratios',
    '_ops': 'operation_ratios',
    '_ers': 'earning_ratios',
    '_er':  'earning_reports',
    '_ac':  'asset_classification',
    '_sr':  'security_reference',
    '_bs':  'balance_sheet',
    '_inc': 'income_statement',
    '_cfs': 'cash_flow_statement',
}


def _parse_legacy_accessor(accessor):
    """Parse a legacy-style accessor like '_bs.long_term_debt.twelve_months'.

    Returns (container, field_name, period) or (None, None, None) if unrecognized."""
    parts = accessor.split('.')
    if not parts:
        return None, None, None
    prefix = parts[0]
    cont = PREFIX_TO_CONTAINER.get(prefix)
    if cont is None:
        return None, None, None
    if len(parts) == 2:
        return cont, parts[1], None
    if len(parts) == 3:
        return cont, parts[1], parts[2]
    return None, None, None


def _build_canonical_accessor(container, field_name, period):
    alias = CONTAINER_ALIAS[container]
    base = f"{alias}.{field_name}"
    return f"{base}.{period}" if period else base


def main(db_path=str(DATA_DIR / 'S001.duckdb'), update_templates=False):
    universe = extract_lean_universe()
    with storage.connect(db_path) as con:
        cur = con.cursor()

        # --- Backfill legacy rows missing container/period ---
        # Also rewrite their accessor to canonical (`_vr_z.x` instead of `_vr.x`)
        # so the UNIQUE(accessor) constraint catches duplicates in the insert phase.
        cur.execute("""SELECT id, accessor FROM fundamental_fields
                       WHERE container IS NULL""")
        for fid, acc in list(cur.fetchall()):
            cont, fname, per = _parse_legacy_accessor(acc)
            if cont is None:
                continue
            tmpl = default_template(cont, fname)
            canonical = _build_canonical_accessor(cont, fname, per)
            try:
                cur.execute(
                    """UPDATE fundamental_fields
                       SET container = ?, period = ?, data_type_hint = ?,
                           accessor = ?
                       WHERE id = ?""",
                    (cont, per, tmpl['data_type_hint'], canonical, fid))
            except storage.IntegrityError:
                # Canonical accessor already exists (catalogue ran before
                # backfill on this row, or two legacy rows mapped to the same
                # canonical). Set container/period/hint without changing accessor.
                cur.execute(
                    """UPDATE fundamental_fields
                       SET container = ?, period = ?, data_type_hint = ?
                       WHERE id = ?""",
                    (cont, per, tmpl['data_type_hint'], fid))

        # --- Insert new rows for each LEAN field, skipping existing accessors ---
        inserted = 0
        for container, fields in universe.items():
            period = default_period(container)
            for field_name in fields:
                accessor = _build_canonical_accessor(container, field_name, period)
                tmpl = default_template(container, field_name)
                try:
                    cur.execute(
                        """INSERT INTO fundamental_fields
                           (category, field_name, accessor, container, period,
                            probe_op, probe_threshold, probe_gate, probe_boost,
                            data_type_hint, classification)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'untested')""",
                        (container, field_name, accessor, container, period,
                         tmpl['probe_op'], tmpl['probe_threshold'],
                         tmpl['probe_gate'], tmpl['probe_boost'],
                         tmpl['data_type_hint']))
                    inserted += 1
                except storage.IntegrityError:
                    # accessor already exists; preserve existing row.
                    if update_templates:
                        cur.execute(
                            """UPDATE fundamental_fields
                               SET probe_op = ?, probe_threshold = ?, probe_gate = ?,
                                   probe_boost = ?, data_type_hint = ?
                               WHERE accessor = ?""",
                            (tmpl['probe_op'], tmpl['probe_threshold'],
                             tmpl['probe_gate'], tmpl['probe_boost'],
                             tmpl['data_type_hint'], accessor))

        cur.execute("SELECT COUNT(*) FROM fundamental_fields")
        total = cur.fetchone()[0]
        return {'inserted': inserted, 'total': total}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--db', default=str(DATA_DIR / 'S001.duckdb'))
    p.add_argument('--update-templates', action='store_true')
    args = p.parse_args()
    res = main(db_path=args.db, update_templates=args.update_templates)
    print(f"Inserted {res['inserted']} new rows; total = {res['total']}")
