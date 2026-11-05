"""emit_probes script tests."""
import ast as _ast
import qc_storage as storage


def _seed_one_field(tmp_db):
    with storage.connect(tmp_db) as con:
        con.execute(
            """INSERT INTO fundamental_fields
               (category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES ('valuation', 'pe_ratio', '_vr_z.pe_ratio',
                       'valuation_ratios', NULL,
                       '<', '15', 'decline > .10', 1.10, 'numeric', 'untested')""")
        con.execute("""INSERT OR REPLACE INTO settings
            (category, key, value, description, updated_at)
            VALUES ('strategy', 'current_bake_hash', 'test_bake', 't', CURRENT_TIMESTAMP)""")


def test_emit_probes_returns_specs(tmp_db):
    from s001.tools.emit_probes import emit_probes_for_db
    _seed_one_field(tmp_db)
    specs = emit_probes_for_db(db_path=tmp_db, round_n=999, k_new=1)
    assert len(specs) == 1
    name, body = specs[0]
    assert name.startswith('S001_R999_vr_pe_ratio_lt')
    assert '_v < 15' in body
    assert 'decline > .10' in body
    # body must parse standalone as the per-probe block.
    # It's a try/except — wrap to make it a complete statement context.
    wrapped = "def _f():\n  for sym in []:\n" + body + "\n   pass\n"
    _ast.parse(wrapped)


def test_emit_probes_pre_flight_skips_null_template(tmp_db):
    from s001.tools.emit_probes import emit_probes_for_db
    with storage.connect(tmp_db) as con:
        con.execute(
            """INSERT INTO fundamental_fields
               (category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES ('valuation', 'no_template', '_vr_z.no_template',
                       'valuation_ratios', NULL,
                       NULL, NULL, NULL, NULL, 'numeric', 'untested')""")
        con.execute("""INSERT OR REPLACE INTO settings
            (category, key, value, description, updated_at)
            VALUES ('strategy', 'current_bake_hash', 'test_bake', 't', CURRENT_TIMESTAMP)""")
    specs = emit_probes_for_db(db_path=tmp_db, round_n=999, k_new=5)
    assert specs == []


def test_emit_probes_includes_bind_block_when_requested(tmp_db):
    from s001.tools.emit_probes import emit_probes_for_db
    _seed_one_field(tmp_db)
    specs = emit_probes_for_db(db_path=tmp_db, round_n=999, k_new=1,
                               include_bind=True)
    name, body = specs[0]
    assert '_fz = self.securities[sym].fundamentals' in body
    assert '_v < 15' in body


def test_emit_includes_phase2_sweep_when_eligible(tmp_db):
    """If a field has sweep_phase=1 and field_universe_stats exists,
    emit_probes_for_db includes its 72-spec v3 coarse sweep (via k_sweep_fields alias)."""
    from s001.tools.emit_probes import emit_probes_for_db
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                       '>', '5', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        cur.execute(
            """INSERT INTO field_universe_stats
               (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
               VALUES (1, 'cur_bake', 1.0, 3.0, 5.0, 7.0, 9.0, 100, '2026-01-01')""")
        cur.execute(
            """INSERT INTO probe_results
               (field_id, experiment_name, round_n, bake_hash,
                noop_baseline, spec_car_mdd, delta, classification,
                applied_op, applied_threshold, applied_gate, applied_boost,
                recorded_at, is_sweep_variant)
               VALUES (1, 'S001_R1_vr_a_gt5', 1, 'cur_bake',
                       1.98, 1.9805, 0.0005, 'neutral',
                       '>', '5', 'decline > .12', 1.10, '2026-01-01', 0)""")
        con.execute("""INSERT OR REPLACE INTO settings
            (category, key, value, description, updated_at)
            VALUES ('strategy', 'current_bake_hash', 'cur_bake', 't', CURRENT_TIMESTAMP)""")
    specs = emit_probes_for_db(db_path=tmp_db, round_n=2,
                               k_new=0, k_sweep_fields=1)
    assert len(specs) == 72
    names = [n for n, _ in specs]
    for n in names:
        assert '_v3c_' in n


def test_emit_marks_sweep_phase_after_emission(tmp_db):
    """After emit_probes_for_db emits v3 coarse for a field, fundamental_fields
    row has sweep_phase = 2 (coarse in flight)."""
    from s001.tools.emit_probes import emit_probes_for_db
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                       '>', '5', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        cur.execute(
            """INSERT INTO field_universe_stats
               (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
               VALUES (1, 'cur_bake', 1.0, 3.0, 5.0, 7.0, 9.0, 100, '2026-01-01')""")
        cur.execute(
            """INSERT INTO probe_results
               (field_id, experiment_name, round_n, bake_hash,
                noop_baseline, spec_car_mdd, delta, classification,
                applied_op, applied_threshold, applied_gate, applied_boost,
                recorded_at, is_sweep_variant)
               VALUES (1, 'S001_R1_vr_a_gt5', 1, 'cur_bake',
                       1.98, 1.9805, 0.0005, 'neutral',
                       '>', '5', 'decline > .12', 1.10, '2026-01-01', 0)""")
        con.execute("""INSERT OR REPLACE INTO settings
            (category, key, value, description, updated_at)
            VALUES ('strategy', 'current_bake_hash', 'cur_bake', 't', CURRENT_TIMESTAMP)""")
    emit_probes_for_db(db_path=tmp_db, round_n=2,
                       k_new=0, k_sweep_fields=1)
    with storage.connect(tmp_db) as con:
        sweep_phase = con.execute(
            "SELECT sweep_phase FROM fundamental_fields WHERE id = 1"
        ).fetchone()[0]
    assert sweep_phase == 2


def test_emit_combines_phase1_and_phase2(tmp_db):
    """k_new=2 + k_sweep_fields=1 → 2 Phase 1 specs + 72 v3 coarse specs."""
    from s001.tools.emit_probes import emit_probes_for_db
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        for fid, name in [(2, 'b'), (3, 'c')]:
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint, sweep_phase)
                   VALUES (?, 'v', ?, ?, 'valuation_ratios', NULL,
                           '>', '5', 'decline > .12', 1.10, 'untested', 'numeric', 0)""",
                (fid, name, f'_vr_z.{name}'))
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                       '>', '5', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        cur.execute(
            """INSERT INTO field_universe_stats
               (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
               VALUES (1, 'cur_bake', 1.0, 3.0, 5.0, 7.0, 9.0, 100, '2026-01-01')""")
        cur.execute(
            """INSERT INTO probe_results
               (field_id, experiment_name, round_n, bake_hash,
                noop_baseline, spec_car_mdd, delta, classification,
                applied_op, applied_threshold, applied_gate, applied_boost,
                recorded_at, is_sweep_variant)
               VALUES (1, 'S001_R1_vr_a_gt5', 1, 'cur_bake',
                       1.98, 1.9810, 0.0010, 'neutral',
                       '>', '5', 'decline > .12', 1.10, '2026-01-01', 0)""")
        con.execute("""INSERT OR REPLACE INTO settings
            (category, key, value, description, updated_at)
            VALUES ('strategy', 'current_bake_hash', 'cur_bake', 't', CURRENT_TIMESTAMP)""")
    specs = emit_probes_for_db(db_path=tmp_db, round_n=3,
                               k_new=2, k_sweep_fields=1)
    assert len(specs) == 74
    coarse_count = sum(1 for n, _ in specs if '_v3c_' in n)
    assert coarse_count == 72


class TestEmitProbesV3:
    def _seed_for_v3(self, db_path):
        import qc_storage as storage
        with storage.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT OR REPLACE INTO settings
                (category, key, value, description)
                VALUES ('strategy', 'current_bake_hash', 'BAKE_TEST', 'test')""")
            # Coarse-eligible field
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 1)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            cur.execute("""INSERT INTO probe_results
                (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                 spec_car_mdd, delta, classification, applied_op, applied_threshold,
                 applied_boost, recorded_at)
                VALUES (1, 'F1_phase1', 500, 'BAKE_TEST', 2.0, 2.0005, 0.0005,
                        'neutral', '>', '1e9', 1.08, '2026-04-27')""")
            con.commit()

    def test_k_coarse_fields_emits_72_per_field(self, tmp_db):
        from s001.fundamental_probes import emit_probes_for_db
        self._seed_for_v3(tmp_db)
        results = emit_probes_for_db(
            db_path=tmp_db, round_n=501,
            k_new=0,
            k_coarse_fields=1, k_refine_fields=0)
        coarse_specs = [n for n, _ in results if '_v3c_' in n]
        assert len(coarse_specs) == 72

    def test_k_sweep_fields_alias_warns(self, tmp_db):
        import warnings
        from s001.fundamental_probes import emit_probes_for_db
        self._seed_for_v3(tmp_db)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            results = emit_probes_for_db(
                db_path=tmp_db, round_n=501,
                k_new=0, k_sweep_fields=1)
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)
        # Aliased to k_coarse_fields; should still emit coarse specs
        coarse_specs = [n for n, _ in results if '_v3c_' in n]
        assert len(coarse_specs) == 72
