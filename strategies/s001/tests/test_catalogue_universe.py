"""Catalogue script tests."""
import qc_storage as storage

from s001.tools.catalogue_universe import main as catalogue_main


def _count_rows(db, table='fundamental_fields'):
    with storage.connect(db) as con:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _categorical_rows_present(db):
    with storage.connect(db) as con:
        n = con.execute(
            "SELECT COUNT(*) FROM fundamental_fields WHERE data_type_hint='categorical'"
        ).fetchone()[0]
    return n > 0


def test_catalogue_inserts_many(tmp_db):
    catalogue_main(db_path=tmp_db)
    n = _count_rows(tmp_db)
    assert n >= 600, f"expected >=600 rows, got {n}"


def test_catalogue_idempotent(tmp_db):
    catalogue_main(db_path=tmp_db)
    n1 = _count_rows(tmp_db)
    catalogue_main(db_path=tmp_db)
    n2 = _count_rows(tmp_db)
    assert n1 == n2


def test_catalogue_categorical_present(tmp_db):
    catalogue_main(db_path=tmp_db)
    assert _categorical_rows_present(tmp_db)


def test_catalogue_preserves_existing_template(tmp_db):
    # Pre-seed a row with a non-default template, then re-catalogue.
    with storage.connect(tmp_db) as con:
        con.execute(
            """INSERT INTO fundamental_fields
               (category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint)
               VALUES ('valuation', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL,
                       '<', '20', 'decline > .05', 1.20, 'numeric')""")

    catalogue_main(db_path=tmp_db)

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT probe_threshold, probe_boost, probe_gate FROM fundamental_fields WHERE field_name='pe_ratio'")
        thr, boost, gate = cur.fetchone()
    assert thr == '20'  # not overwritten
    assert boost == 1.20
    assert gate == 'decline > .05'


def test_catalogue_backfills_legacy_row(tmp_db):
    # Pre-seed a legacy-style row (no container/period populated).
    with storage.connect(tmp_db) as con:
        con.execute(
            """INSERT INTO fundamental_fields
               (category, field_name, accessor, container, period, data_type_hint)
               VALUES ('valuation', 'pe_ratio', '_vr.pe_ratio', NULL, NULL, NULL)""")

    catalogue_main(db_path=tmp_db)

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT container, period, data_type_hint FROM fundamental_fields WHERE field_name='pe_ratio'")
        container, period, hint = cur.fetchone()
    assert container == 'valuation_ratios'
    assert period is None
    assert hint == 'numeric'
