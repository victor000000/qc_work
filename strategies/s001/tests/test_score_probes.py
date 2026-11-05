"""score_probes script tests."""
import qc_storage as storage

import pytest

from s001.tools.score_probes import score_round


def _seed(tmp_db):
    """Seed one field, three NOOP experiments, two probe experiments."""
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES (1, 'valuation', 'pe_ratio', '_vr_z.pe_ratio',
                       'valuation_ratios', NULL,
                       '<', '15', 'decline > .10', 1.10, 'numeric', 'untested')""")
        # 3 NOOPs avg = 1.9000, spread = 0.0004 (within 0.0005 tolerance)
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R500_VBAKE40_NOOP_{i}', v))
        # Probe spec name matches the auto-naming pattern.
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R500_vr_pe_ratio_lt15', 1.9050))  # +0.0050 → hot
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R500_vr_pe_ratio_lt99', 1.8970))  # different threshold; field doesn't match exactly
                                                       # but we should still identify the field by name


def test_score_inserts_probe_results(tmp_db):
    _seed(tmp_db)
    out = score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')
    assert out['n_results'] >= 1

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM probe_results WHERE round_n = 500")
        rows = cur.fetchall()
        assert len(rows) >= 1
        cur.execute("SELECT classification, delta FROM probe_results WHERE experiment_name = 'S001_R500_vr_pe_ratio_lt15'")
        cl, delta = cur.fetchone()
    assert cl == 'hot'
    assert abs(delta - 0.005) < 1e-6


def test_score_rejects_round_with_no_noops(tmp_db):
    with storage.connect(tmp_db) as con:
        con.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES (1, 'v', 'p', '_vr_z.p', 'valuation_ratios', NULL,
                       '>', '5', NULL, 1.1, 'numeric', 'untested')""")
        con.execute("INSERT INTO experiments (name, status, car_mdd) VALUES ('S001_R501_vr_p_gt5', 'imported', 1.91)")
    with pytest.raises(AssertionError, match='NOOP'):
        score_round(db_path=tmp_db, round_n=501, bake_hash='c0ed7f31')


def test_score_rejects_high_noop_spread(tmp_db):
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES (1, 'v', 'p', '_vr_z.p', 'valuation_ratios', NULL,
                       '>', '5', NULL, 1.1, 'numeric', 'untested')""")
        # 3 NOOPs with spread > 0.0005
        for i, v in enumerate([1.8990, 1.9000, 1.9050]):  # spread = 0.006
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R502_VBAKE40_NOOP_{i}', v))
    with pytest.raises(AssertionError, match='spread'):
        score_round(db_path=tmp_db, round_n=502, bake_hash='c0ed7f31')


def test_score_idempotent(tmp_db):
    _seed(tmp_db)
    score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')
    with storage.connect(tmp_db) as con:
        n1 = con.execute("SELECT COUNT(*) FROM probe_results").fetchone()[0]
    score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')
    with storage.connect(tmp_db) as con:
        n2 = con.execute("SELECT COUNT(*) FROM probe_results").fetchone()[0]
    assert n1 == n2  # UNIQUE(experiment_name) prevents duplicates


def test_score_refreshes_field_classification(tmp_db):
    _seed(tmp_db)
    score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT classification FROM fundamental_fields WHERE id = 1")
        cl = cur.fetchone()[0]
    assert cl == 'hot'


def test_score_recognizes_sweep_name(tmp_db):
    """Sweep spec name → INSERT into probe_results with is_sweep_variant=1
    and reconstructed applied_* values."""
    from s001.tools.score_probes import score_round
    import qc_storage as storage
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL,
                       '<', '15', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R500_VBAKE40_NOOP_{i}', v))
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R500_sw_vr_pe_ratio_m106_g05', 1.9050))

    score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT is_sweep_variant, applied_boost, applied_gate, classification, delta "
            "FROM probe_results WHERE experiment_name = 'S001_R500_sw_vr_pe_ratio_m106_g05'")
        row = cur.fetchone()
    assert row is not None, 'sweep spec not scored'
    is_sweep, boost, gate, cls, delta = row
    assert is_sweep == 1
    assert abs(boost - 1.06) < 1e-6
    assert gate == 'decline > .05'
    assert cls == 'hot'  # delta=0.005 > 0.0015


def test_score_calls_update_sweep_winner_when_15_complete(tmp_db):
    """When all 15 sweep variants for a field are scored in one round,
    sweep_winner_* and sweep_phase=2 are populated."""
    from s001.tools.score_probes import score_round
    from s001.fundamental_probes import SWEEP_MAGS, SWEEP_GATES
    import qc_storage as storage
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL,
                       '<', '15', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R501_VBAKE40_NOOP_{i}', v))
        for mag in SWEEP_MAGS:
            for gate in SWEEP_GATES:
                if mag == '1.06' and gate == '.05':
                    car_mdd = 1.9050
                else:
                    car_mdd = 1.9005
                mag_short = mag.replace('.', '')
                gate_short = gate.replace('.', '').lstrip('-') or '0'
                cur.execute(
                    "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                    (f'S001_R501_sw_vr_pe_ratio_m{mag_short}_g{gate_short}', car_mdd))

    score_round(db_path=tmp_db, round_n=501, bake_hash='c0ed7f31')

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT sweep_phase, sweep_winner_boost, sweep_winner_gate, sweep_winner_delta "
            "FROM fundamental_fields WHERE id = 1")
        phase, boost, gate, delta = cur.fetchone()
    assert phase == 2
    assert abs(boost - 1.06) < 1e-6
    assert gate == 'decline > .05'
    assert abs(delta - 0.005) < 1e-6


def test_score_partial_sweep_no_winner(tmp_db):
    """If only some variants score (not all 15), sweep_winner stays NULL
    and sweep_phase stays at 1."""
    from s001.tools.score_probes import score_round
    import qc_storage as storage
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL,
                       '<', '15', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R502_VBAKE40_NOOP_{i}', v))
        for mag, gate in [('1.04', '.05'), ('1.06', '.05'), ('1.08', '.10'),
                           ('1.10', '.15'), ('1.13', '.10')]:
            mag_short = mag.replace('.', '')
            gate_short = gate.replace('.', '').lstrip('-') or '0'
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R502_sw_vr_pe_ratio_m{mag_short}_g{gate_short}', 1.9020))

    score_round(db_path=tmp_db, round_n=502, bake_hash='c0ed7f31')

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT sweep_phase, sweep_winner_boost FROM fundamental_fields WHERE id = 1")
        phase, boost = cur.fetchone()
    assert phase == 1
    assert boost is None


class TestV3ScoreRouting:
    def _seed_field_and_stats(self, db_path):
        import qc_storage as storage
        with storage.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT OR REPLACE INTO settings
                (category, key, value, description)
                VALUES ('strategy', 'current_bake_hash', 'BAKE_TEST', 'test')""")
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 2)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            con.commit()

    def test_v3_coarse_spec_inserted_with_sweep_stage_coarse(self, tmp_db):
        from s001.tools.score_probes import score_round
        import qc_storage as storage
        self._seed_field_and_stats(tmp_db)
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO experiments (name, status, car_mdd)
                VALUES ('S001_R501_VBAKE45_NOOP_0', 'imported', 2.0)""")
            cur.execute("""INSERT INTO experiments (name, status, car_mdd)
                VALUES ('S001_R501_v3c_bs_cash_ogt_m108_g10_t50', 'imported', 2.001)""")
            con.commit()

        score_round(db_path=tmp_db, round_n=501, bake_hash='BAKE_TEST')

        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("SELECT applied_op, applied_threshold, applied_gate, "
                        "applied_boost, sweep_stage FROM probe_results")
            row = cur.fetchone()
        assert row[0] == '>'      # applied_op
        assert row[1] == '5.000e+08'  # p50 threshold (.3e formatted)
        assert row[2] == 'decline > .10'
        assert row[3] == 1.08
        assert row[4] == 'coarse'

    def test_v3_refine_spec_inserted_with_sweep_stage_refine(self, tmp_db):
        from s001.tools.score_probes import score_round
        import qc_storage as storage
        self._seed_field_and_stats(tmp_db)
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO experiments (name, status, car_mdd)
                VALUES ('S001_R501_VBAKE45_NOOP_0', 'imported', 2.0)""")
            cur.execute("""INSERT INTO experiments (name, status, car_mdd)
                VALUES ('S001_R501_v3r_bs_cash_olt_m104_g05_t25', 'imported', 1.999)""")
            con.commit()

        score_round(db_path=tmp_db, round_n=501, bake_hash='BAKE_TEST')

        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("SELECT applied_op, applied_threshold, applied_gate, "
                        "applied_boost, sweep_stage FROM probe_results")
            row = cur.fetchone()
        assert row[0] == '<'
        assert row[1] == '1.000e+08'  # p25 threshold (.3e formatted)
        assert row[2] == 'decline > .05'
        assert row[3] == 1.04
        assert row[4] == 'refine'


def _seed_mega_round(tmp_db):
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES (1, 'ops', 'revenue_growth', '_ops_z.revenue_growth.one_year',
                       'operation_ratios', 'one_year',
                       '>', '0.10', 'decline > .12', 1.10, 'numeric', 'untested')""")
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R603_VBAKEMG_NOOP_{i}', v))
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R603_mg_score_ops_revenue_growth', 1.9050))
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R603_mg_skip_ops_revenue_growth', 1.9020))
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R603_mg_petgt_ops_revenue_growth', 1.8990))


def test_score_routes_mega_specs(tmp_db):
    _seed_mega_round(tmp_db)
    out = score_round(db_path=tmp_db, round_n=603, bake_hash='b4619')
    assert out['n_results'] == 3

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT mechanism, applied_op, classification "
                    "FROM probe_results WHERE experiment_name = ?",
                    ('S001_R603_mg_score_ops_revenue_growth',))
        mech, op_used, cls = cur.fetchone()
        assert mech == 'score'
        assert op_used == '>'
        assert cls == 'hot'

        cur.execute("SELECT mechanism, applied_op FROM probe_results "
                    "WHERE experiment_name = ?",
                    ('S001_R603_mg_skip_ops_revenue_growth',))
        mech, op_used = cur.fetchone()
        assert mech == 'skip'
        assert op_used == '<'

        cur.execute("SELECT mechanism, applied_op FROM probe_results "
                    "WHERE experiment_name = ?",
                    ('S001_R603_mg_petgt_ops_revenue_growth',))
        mech, op_used = cur.fetchone()
        assert mech == 'petgt'
        assert op_used == '>'


def test_mega_name_re_matches_underscore_heavy_field():
    from s001.tools.score_probes import MEGA_NAME_RE
    m = MEGA_NAME_RE.match('S001_R603_mg_score_cfs_change_in_account_payable')
    assert m
    assert m.group('mech') == 'score'
    assert m.group('cs') == 'cfs'
    assert m.group('field') == 'change_in_account_payable'


def test_mega_name_re_does_not_match_v1_specs():
    from s001.tools.score_probes import MEGA_NAME_RE
    assert MEGA_NAME_RE.match('S001_R500_vr_pe_ratio_lt15') is None
    assert MEGA_NAME_RE.match('S001_R500_sw_ops_revenue_growth_m110_g05') is None
    assert MEGA_NAME_RE.match('S001_R500_v3c_ops_revenue_growth_ogt_m110_g05_t50') is None


def test_field_rollup_ignores_non_score_mechanisms(tmp_db):
    """A 'harmful' skip cell must NOT poison the field's rollup — rollup is
    score-only so v3 pickup isn't disrupted."""
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES (1, 'ops', 'rg', '_ops_z.rg.one_year',
                       'operation_ratios', 'one_year',
                       '>', '0.10', 'decline > .12', 1.10, 'numeric', 'untested')""")
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R604_VBAKEMG_NOOP_{i}', v))
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R604_mg_score_ops_rg', 1.9005))
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R604_mg_skip_ops_rg', 1.8950))

    score_round(db_path=tmp_db, round_n=604, bake_hash='b4619')
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT classification FROM fundamental_fields WHERE id = 1")
        rollup = cur.fetchone()[0]
    assert rollup == 'neutral', f'rollup got poisoned by skip cell: {rollup!r}'
