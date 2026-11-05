"""Tests for s001.fundamental_probes library."""
import pytest

import pytest as _pytest_for_bake
from s001.fundamental_probes import accessor_for


class TestAccessorFor:
    def test_valuation_ratios_no_period(self):
        row = {'container': 'valuation_ratios', 'field_name': 'pe_ratio', 'period': None}
        assert accessor_for(row) == '_vr_z.pe_ratio'

    def test_balance_sheet_with_period(self):
        row = {'container': 'balance_sheet', 'field_name': 'long_term_debt', 'period': 'twelve_months'}
        assert accessor_for(row) == '_bs_z.long_term_debt.twelve_months'

    def test_operation_ratios_one_year(self):
        row = {'container': 'operation_ratios', 'field_name': 'roe', 'period': 'one_year'}
        assert accessor_for(row) == '_ops_z.roe.one_year'

    def test_cash_flow_statement(self):
        row = {'container': 'cash_flow_statement', 'field_name': 'free_cash_flow', 'period': 'twelve_months'}
        assert accessor_for(row) == '_cfs_z.free_cash_flow.twelve_months'

    def test_income_statement(self):
        row = {'container': 'income_statement', 'field_name': 'net_income', 'period': 'twelve_months'}
        assert accessor_for(row) == '_inc_z.net_income.twelve_months'

    def test_earning_ratios(self):
        row = {'container': 'earning_ratios', 'field_name': 'diluted_eps_growth', 'period': 'one_year'}
        assert accessor_for(row) == '_ers_z.diluted_eps_growth.one_year'

    def test_earning_reports(self):
        row = {'container': 'earning_reports', 'field_name': 'basic_eps', 'period': 'twelve_months'}
        assert accessor_for(row) == '_er_z.basic_eps.twelve_months'

    def test_asset_classification_no_period(self):
        row = {'container': 'asset_classification', 'field_name': 'financial_health_grade', 'period': None}
        assert accessor_for(row) == '_ac_z.financial_health_grade'

    def test_security_reference_no_period(self):
        row = {'container': 'security_reference', 'field_name': 'ipo_date', 'period': None}
        assert accessor_for(row) == '_sr_z.ipo_date'

    def test_unknown_container_raises(self):
        row = {'container': 'mystery', 'field_name': 'foo', 'period': None}
        with pytest.raises(KeyError):
            accessor_for(row)


from s001.fundamental_probes import classify_delta


class TestClassifyDelta:
    def test_clearly_hot(self):
        assert classify_delta(0.0030) == 'hot'

    def test_clearly_harmful(self):
        assert classify_delta(-0.0030) == 'harmful'

    def test_neutral_positive(self):
        assert classify_delta(0.0010) == 'neutral'

    def test_neutral_negative(self):
        assert classify_delta(-0.0010) == 'neutral'

    def test_zero(self):
        assert classify_delta(0.0) == 'neutral'

    def test_exact_positive_boundary_neutral(self):
        # delta > +0.0015 → 'hot'; exactly +0.0015 stays 'neutral'.
        assert classify_delta(0.0015) == 'neutral'

    def test_exact_negative_boundary_neutral(self):
        # delta < -0.0015 → 'harmful'; exactly -0.0015 stays 'neutral'.
        assert classify_delta(-0.0015) == 'neutral'

    def test_just_above_positive_boundary(self):
        assert classify_delta(0.00151) == 'hot'

    def test_just_below_negative_boundary(self):
        assert classify_delta(-0.00151) == 'harmful'


from s001.fundamental_probes import field_rollup


class TestFieldRollup:
    def test_empty_results_untested(self):
        assert field_rollup([]) == 'untested'

    def test_single_hot(self):
        assert field_rollup([{'classification': 'hot'}]) == 'hot'

    def test_single_neutral(self):
        assert field_rollup([{'classification': 'neutral'}]) == 'neutral'

    def test_single_harmful(self):
        assert field_rollup([{'classification': 'harmful'}]) == 'harmful'

    def test_mixed_hot_and_harmful_poisons(self):
        # One harmful poisons even with hot present.
        results = [{'classification': 'hot'}, {'classification': 'harmful'}]
        assert field_rollup(results) == 'harmful'

    def test_mixed_hot_and_neutral_is_hot(self):
        results = [{'classification': 'hot'}, {'classification': 'neutral'}, {'classification': 'neutral'}]
        assert field_rollup(results) == 'hot'

    def test_all_neutral_is_neutral(self):
        results = [{'classification': 'neutral'}] * 3
        assert field_rollup(results) == 'neutral'

    def test_three_hot_is_hot(self):
        results = [{'classification': 'hot'}] * 3
        assert field_rollup(results) == 'hot'

    def test_harmful_alone(self):
        assert field_rollup([{'classification': 'harmful'}, {'classification': 'harmful'}]) == 'harmful'


from s001.fundamental_probes import build_condition


class TestBuildConditionGt:
    def test_numeric_gt(self):
        row = {'probe_op': '>', 'probe_threshold': '15', 'data_type_hint': 'numeric'}
        assert build_condition(row, '_v') == '_v is not None and _v > 15'

    def test_signed_ratio_gt(self):
        row = {'probe_op': '>', 'probe_threshold': '0.10', 'data_type_hint': 'signed_ratio'}
        assert build_condition(row, '_v') == '_v is not None and _v > 0.10'

    def test_absolute_amount_gt(self):
        # `>` does not need 0<_v guard (we want positive amounts above threshold).
        row = {'probe_op': '>', 'probe_threshold': '1e9', 'data_type_hint': 'absolute_amount'}
        assert build_condition(row, '_v') == '_v is not None and _v > 1e9'

    def test_gte(self):
        row = {'probe_op': '>=', 'probe_threshold': '15', 'data_type_hint': 'numeric'}
        assert build_condition(row, '_v') == '_v is not None and _v >= 15'

    def test_threshold_can_be_negative(self):
        row = {'probe_op': '>', 'probe_threshold': '-0.05', 'data_type_hint': 'signed_ratio'}
        assert build_condition(row, '_v') == '_v is not None and _v > -0.05'


class TestBuildConditionLt:
    def test_numeric_lt(self):
        # numeric: bare `<`, no special guard
        row = {'probe_op': '<', 'probe_threshold': '15', 'data_type_hint': 'numeric'}
        assert build_condition(row, '_v') == '_v is not None and _v < 15'

    def test_signed_ratio_lt(self):
        # signed_ratio: bare `<`, allows negatives like -0.05
        row = {'probe_op': '<', 'probe_threshold': '-0.05', 'data_type_hint': 'signed_ratio'}
        assert build_condition(row, '_v') == '_v is not None and _v < -0.05'

    def test_absolute_amount_lt_adds_zero_guard(self):
        # absolute_amount: must filter out 0/missing values via 0 < _v
        row = {'probe_op': '<', 'probe_threshold': '5e8', 'data_type_hint': 'absolute_amount'}
        assert build_condition(row, '_v') == '_v is not None and 0 < _v < 5e8'

    def test_absolute_amount_signed_lt_uses_abs(self):
        # absolute_amount_signed: BS/CFS sign-tolerant flavor
        row = {'probe_op': '<', 'probe_threshold': '1e8', 'data_type_hint': 'absolute_amount_signed'}
        assert build_condition(row, '_v') == '_v is not None and abs(_v) < 1e8'

    def test_lte_signed_ratio(self):
        row = {'probe_op': '<=', 'probe_threshold': '0', 'data_type_hint': 'signed_ratio'}
        assert build_condition(row, '_v') == '_v is not None and _v <= 0'

    def test_lte_absolute_amount(self):
        row = {'probe_op': '<=', 'probe_threshold': '1e9', 'data_type_hint': 'absolute_amount'}
        assert build_condition(row, '_v') == '_v is not None and 0 < _v <= 1e9'


class TestBuildConditionCategorical:
    def test_eq_string(self):
        row = {'probe_op': 'eq', 'probe_threshold': '"A"', 'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v == 'A'"

    def test_eq_int(self):
        row = {'probe_op': 'eq', 'probe_threshold': '207', 'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == '_v == 207'

    def test_in_strings(self):
        row = {'probe_op': 'in', 'probe_threshold': '["A","B+","B"]', 'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v in ('A', 'B+', 'B')"

    def test_in_ints(self):
        row = {'probe_op': 'in', 'probe_threshold': '[205, 206, 207]', 'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == '_v in (205, 206, 207)'

    def test_in_single_value(self):
        row = {'probe_op': 'in', 'probe_threshold': '["A"]', 'data_type_hint': 'categorical'}
        # tuple comma needed for 1-element to avoid Python eval ambiguity
        assert build_condition(row, '_v') == "_v in ('A',)"

    def test_categorical_op_on_numeric_hint_raises(self):
        # Bad combo: 'in' with numeric hint should fail loud.
        row = {'probe_op': 'in', 'probe_threshold': '[1,2]', 'data_type_hint': 'numeric'}
        with pytest.raises(ValueError, match='categorical'):
            build_condition(row, '_v')

    def test_in_non_json_raises(self):
        row = {'probe_op': 'in', 'probe_threshold': 'A,B,C', 'data_type_hint': 'categorical'}
        with pytest.raises(ValueError):
            build_condition(row, '_v')


import ast as _ast

from s001.fundamental_probes import render_probe, BIND


class TestRenderProbe:
    def test_numeric_gt_with_gate(self):
        row = {
            'container': 'valuation_ratios', 'field_name': 'book_value_per_share',
            'period': None, 'probe_op': '>', 'probe_threshold': '15',
            'probe_gate': 'decline > .10', 'probe_boost': 1.12,
            'data_type_hint': 'numeric',
        }
        out = render_probe(row)
        assert '_v = f_(_vr_z.book_value_per_share)' in out
        assert '_v > 15' in out
        assert 'decline > .10' in out
        assert 'score *= 1.12' in out
        # Output is indented for injection at a 3-space anchor; wrap to parse.
        _ast.parse("def _f():\n  for sym in []:\n" + out + "\n   pass\n")

    def test_numeric_no_gate(self):
        row = {
            'container': 'operation_ratios', 'field_name': 'roe', 'period': 'one_year',
            'probe_op': '>', 'probe_threshold': '0.15',
            'probe_gate': None, 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        out = render_probe(row)
        assert ' and (' not in out  # no gate fragment
        assert '_v > 0.15: score *= 1.1' in out
        _ast.parse("def _f():\n  for sym in []:\n" + out + "\n   pass\n")

    def test_categorical_in(self):
        row = {
            'container': 'asset_classification', 'field_name': 'financial_health_grade',
            'period': None, 'probe_op': 'in', 'probe_threshold': '["A","B+","B"]',
            'probe_gate': 'decline > .10', 'probe_boost': 1.06,
            'data_type_hint': 'categorical',
        }
        out = render_probe(row)
        # Categorical path: no f_(...) coerce
        assert '_v = _ac_z.financial_health_grade' in out
        assert "'A'" in out and "'B+'" in out
        assert 'decline > .10' in out
        assert 'score *= 1.06' in out
        _ast.parse("def _f():\n  for sym in []:\n" + out + "\n   pass\n")

    def test_absolute_amount_lt_with_zero_guard(self):
        row = {
            'container': 'income_statement', 'field_name': 'interest_expense',
            'period': 'twelve_months', 'probe_op': '<', 'probe_threshold': '5e7',
            'probe_gate': 'decline > .10', 'probe_boost': 1.08,
            'data_type_hint': 'absolute_amount',
        }
        out = render_probe(row)
        assert '0 < _v < 5e7' in out
        _ast.parse("def _f():\n  for sym in []:\n" + out + "\n   pass\n")

    def test_signed_ratio_negative_threshold(self):
        row = {
            'container': 'earning_ratios', 'field_name': 'diluted_eps_growth',
            'period': 'one_year', 'probe_op': '<', 'probe_threshold': '-0.10',
            'probe_gate': None, 'probe_boost': 0.85,
            'data_type_hint': 'signed_ratio',
        }
        out = render_probe(row)
        assert '_v < -0.10' in out
        assert 'score *= 0.85' in out
        _ast.parse("def _f():\n  for sym in []:\n" + out + "\n   pass\n")

    def test_null_threshold_raises(self):
        row = {
            'container': 'valuation_ratios', 'field_name': 'pe_ratio', 'period': None,
            'probe_op': '>', 'probe_threshold': None,
            'probe_gate': None, 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        with pytest.raises(ValueError, match='probe_threshold'):
            render_probe(row)

    def test_bind_block_constant_parses(self):
        # The shared BIND block must itself parse standalone (after dedent of the leading 3-space indent).
        # We wrap it in a function to test parseability.
        wrapped = "def _f():\n  for sym in []:\n" + BIND + "   pass\n"
        _ast.parse(wrapped)


from s001.fundamental_probes import spec_name


class TestSpecName:
    def test_numeric_gt(self):
        row = {
            'container': 'valuation_ratios', 'field_name': 'book_value_per_share',
            'probe_op': '>', 'probe_threshold': '15',
        }
        assert spec_name(row, 406) == 'S001_R406_vr_book_value_per_share_gt15'

    def test_numeric_lt(self):
        row = {
            'container': 'income_statement', 'field_name': 'interest_expense',
            'probe_op': '<', 'probe_threshold': '5e7',
        }
        assert spec_name(row, 406) == 'S001_R406_inc_interest_expense_lt5e7'

    def test_categorical_in(self):
        row = {
            'container': 'asset_classification', 'field_name': 'financial_health_grade',
            'probe_op': 'in', 'probe_threshold': '["A","B+","B"]',
        }
        # Categorical short form: 'in_AB' (concat of values, stripped to alphanumeric)
        assert spec_name(row, 406) == 'S001_R406_ac_financial_health_grade_in_ABplusB'

    def test_balance_sheet(self):
        row = {
            'container': 'balance_sheet', 'field_name': 'long_term_debt',
            'probe_op': '<', 'probe_threshold': '5e8',
        }
        assert spec_name(row, 406) == 'S001_R406_bs_long_term_debt_lt5e8'

    def test_truncates_long_name(self):
        row = {
            'container': 'income_statement',
            'field_name': 'continuing_and_discontinued_basic_earnings_per_share_x',
            'probe_op': '>', 'probe_threshold': '2',
        }
        out = spec_name(row, 406)
        assert len(out) <= 100
        assert out.startswith('S001_R406_inc_')


from s001.fundamental_probes import pick_fields, CONTAINER_CYCLE


class TestPickFields:
    @staticmethod
    def _seed_fields(tmp_db, rows):
        import qc_storage as storage
        con = storage.connect(tmp_db)
        cur = con.cursor()
        for r in rows:
            cur.execute(
                """INSERT INTO fundamental_fields
                   (category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r['container'], r['field_name'], r['accessor'], r['container'],
                 r.get('period'), r.get('probe_op'), r.get('probe_threshold'),
                 r.get('probe_gate'), r.get('probe_boost'),
                 r.get('classification', 'untested'), r.get('data_type_hint', 'numeric')))
        con.commit()
        con.close()

    def test_picks_in_container_cycle(self, tmp_db):
        # Seed 2 each in vr, ops, ac (the first 3 in CONTAINER_CYCLE).
        rows = [
            {'container': 'valuation_ratios', 'field_name': 'a', 'accessor': '_vr.a',
             'probe_op': '>', 'probe_threshold': '1', 'probe_boost': 1.1},
            {'container': 'valuation_ratios', 'field_name': 'b', 'accessor': '_vr.b',
             'probe_op': '>', 'probe_threshold': '2', 'probe_boost': 1.1},
            {'container': 'operation_ratios', 'field_name': 'c', 'accessor': '_ops.c.one_year',
             'period': 'one_year', 'probe_op': '>', 'probe_threshold': '3', 'probe_boost': 1.1},
            {'container': 'operation_ratios', 'field_name': 'd', 'accessor': '_ops.d.one_year',
             'period': 'one_year', 'probe_op': '>', 'probe_threshold': '4', 'probe_boost': 1.1},
            {'container': 'asset_classification', 'field_name': 'e', 'accessor': '_ac.e',
             'probe_op': 'in', 'probe_threshold': '["A"]', 'probe_boost': 1.1, 'data_type_hint': 'categorical'},
        ]
        self._seed_fields(tmp_db, rows)
        picked = pick_fields(tmp_db, k=3, classification='untested', bake_hash='test_bake')
        # Cycle: vr → ops → ac → vr → ... so first 3 = (vr.a, ops.c, ac.e)
        assert [p['field_name'] for p in picked] == ['a', 'c', 'e']

    def test_skips_null_threshold(self, tmp_db):
        rows = [
            {'container': 'valuation_ratios', 'field_name': 'has_template',
             'accessor': '_vr.has_template', 'probe_op': '>', 'probe_threshold': '1', 'probe_boost': 1.1},
            {'container': 'valuation_ratios', 'field_name': 'no_template',
             'accessor': '_vr.no_template', 'probe_op': None, 'probe_threshold': None, 'probe_boost': None},
        ]
        self._seed_fields(tmp_db, rows)
        picked = pick_fields(tmp_db, k=5, classification='untested', bake_hash='test_bake')
        assert [p['field_name'] for p in picked] == ['has_template']

    def test_filters_by_classification(self, tmp_db):
        # v2: classification filter joins through probe_results.bake_hash.
        # Field with a 'hot' result on test_bake is picked when classification='hot'.
        # Field with no result on test_bake is picked when classification='untested'.
        rows = [
            {'container': 'valuation_ratios', 'field_name': 'untested_a',
             'accessor': '_vr.untested_a', 'probe_op': '>', 'probe_threshold': '1', 'probe_boost': 1.1},
            {'container': 'valuation_ratios', 'field_name': 'hot_b',
             'accessor': '_vr.hot_b', 'probe_op': '>', 'probe_threshold': '1', 'probe_boost': 1.1},
        ]
        self._seed_fields(tmp_db, rows)
        # Seed a hot probe_result on test_bake for hot_b
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("SELECT id FROM fundamental_fields WHERE field_name = 'hot_b'")
            hot_b_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO probe_results
                   (field_id, experiment_name, round_n, bake_hash,
                    noop_baseline, spec_car_mdd, delta, classification,
                    applied_op, applied_threshold, applied_gate, applied_boost, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (hot_b_id, 'S001_R1_vr_hot_b_gt1', 1, 'test_bake',
                 1.98, 1.985, 0.005, 'hot', '>', '1', None, 1.1, '2026-01-01'))
        untested = pick_fields(tmp_db, k=10, classification='untested', bake_hash='test_bake')
        hot = pick_fields(tmp_db, k=10, classification='hot', bake_hash='test_bake')
        assert [p['field_name'] for p in untested] == ['untested_a']
        assert [p['field_name'] for p in hot] == ['hot_b']

    def test_deterministic(self, tmp_db):
        rows = [{'container': 'valuation_ratios', 'field_name': f'f{i}',
                 'accessor': f'_vr.f{i}', 'probe_op': '>', 'probe_threshold': str(i),
                 'probe_boost': 1.1} for i in range(5)]
        self._seed_fields(tmp_db, rows)
        a = [p['field_name'] for p in pick_fields(tmp_db, k=3, classification='untested', bake_hash='test_bake')]
        b = [p['field_name'] for p in pick_fields(tmp_db, k=3, classification='untested', bake_hash='test_bake')]
        assert a == b

    def test_container_cycle_constant_order(self):
        # Spec §7.3 declares this exact order.
        assert CONTAINER_CYCLE == [
            'valuation_ratios', 'operation_ratios', 'asset_classification',
            'balance_sheet', 'cash_flow_statement', 'income_statement',
            'earning_ratios', 'earning_reports', 'security_reference',
        ]


from s001.fundamental_probes import extract_lean_universe, EXCLUDE_FIELD_PATTERNS


class TestExtractLeanUniverse:
    def test_returns_dict_per_container(self):
        # Run against the actually installed LEAN __init__.pyi
        out = extract_lean_universe()
        assert isinstance(out, dict)
        # Required containers must all be present
        for c in ('balance_sheet', 'cash_flow_statement', 'income_statement',
                  'operation_ratios', 'valuation_ratios', 'earning_ratios',
                  'earning_reports', 'asset_classification', 'security_reference'):
            assert c in out, f"missing {c}"

    def test_field_counts_meet_minimums(self):
        out = extract_lean_universe()
        # Lower bounds — actual counts may exceed these as LEAN evolves.
        assert len(out['valuation_ratios']) >= 50
        assert len(out['operation_ratios']) >= 40
        assert len(out['balance_sheet']) >= 100
        assert len(out['income_statement']) >= 80
        assert len(out['cash_flow_statement']) >= 80
        assert len(out['earning_ratios']) >= 5
        assert len(out['asset_classification']) >= 10

    def test_known_field_present(self):
        out = extract_lean_universe()
        # Sanity: known field that has been used in production rounds.
        assert 'pe_ratio' in out['valuation_ratios']
        assert 'roe' in out['operation_ratios']
        assert 'free_cash_flow' in out['cash_flow_statement']

    def test_metadata_excluded(self):
        out = extract_lean_universe()
        # These appear in the .pyi but should be filtered.
        for excluded in ('file_date', 'accession_number', 'form_type',
                         'period_type', 'period_ending_date'):
            for cont in out.values():
                assert excluded not in cont, f"{excluded} should be excluded"

    def test_categorical_fields_present(self):
        out = extract_lean_universe()
        # AssetClassification has these categorical signals
        assert 'financial_health_grade' in out['asset_classification']
        assert 'morningstar_sector_code' in out['asset_classification']


from s001.fundamental_probes import default_template, default_period


class TestDefaultPeriod:
    def test_balance_sheet_twelve_months(self):
        assert default_period('balance_sheet') == 'twelve_months'

    def test_cash_flow_twelve_months(self):
        assert default_period('cash_flow_statement') == 'twelve_months'

    def test_income_twelve_months(self):
        assert default_period('income_statement') == 'twelve_months'

    def test_earning_reports_twelve_months(self):
        assert default_period('earning_reports') == 'twelve_months'

    def test_operation_ratios_one_year(self):
        assert default_period('operation_ratios') == 'one_year'

    def test_earning_ratios_one_year(self):
        assert default_period('earning_ratios') == 'one_year'

    def test_valuation_ratios_none(self):
        assert default_period('valuation_ratios') is None

    def test_asset_classification_none(self):
        assert default_period('asset_classification') is None

    def test_security_reference_none(self):
        assert default_period('security_reference') is None


class TestDefaultTemplate:
    def test_valuation_ratios_pe(self):
        # PE-style ratios get '<' op (low = undervalued).
        out = default_template('valuation_ratios', 'pe_ratio')
        assert out['probe_op'] == '<'
        assert out['probe_threshold'] == '15'
        assert out['data_type_hint'] == 'numeric'
        assert 'decline' in out['probe_gate']
        assert out['probe_boost'] >= 1.05

    def test_valuation_ratios_default_high(self):
        # Generic vr field gets '>' op (high = good).
        out = default_template('valuation_ratios', 'book_value_per_share')
        assert out['probe_op'] == '>'
        assert out['data_type_hint'] == 'numeric'

    def test_operation_ratios_margin(self):
        out = default_template('operation_ratios', 'gross_margin')
        assert out['probe_op'] == '>'
        assert out['data_type_hint'] == 'numeric'

    def test_operation_ratios_leverage(self):
        out = default_template('operation_ratios', 'financial_leverage')
        assert out['probe_op'] == '<'

    def test_balance_sheet_total_assets(self):
        out = default_template('balance_sheet', 'total_assets')
        assert out['probe_op'] == '>'
        assert out['data_type_hint'] == 'absolute_amount'
        assert float(out['probe_threshold']) >= 1e9

    def test_balance_sheet_long_term_debt(self):
        out = default_template('balance_sheet', 'long_term_debt')
        assert out['probe_op'] == '<'
        assert out['data_type_hint'] == 'absolute_amount'

    def test_earning_ratios_growth(self):
        out = default_template('earning_ratios', 'diluted_eps_growth')
        assert out['probe_op'] == '>'
        assert out['data_type_hint'] == 'signed_ratio'

    def test_asset_classification_grade(self):
        out = default_template('asset_classification', 'financial_health_grade')
        assert out['probe_op'] == 'in'
        assert out['data_type_hint'] == 'categorical'
        # JSON list of A-tier grades
        import json
        assert json.loads(out['probe_threshold']) == ['A', 'A+', 'A-']

    def test_asset_classification_sector_code(self):
        out = default_template('asset_classification', 'morningstar_sector_code')
        assert out['probe_op'] == 'in'
        assert out['data_type_hint'] == 'categorical'


from s001.fundamental_probes import current_bake_hash


class TestCurrentBakeHash:
    def test_reads_value(self, tmp_db):
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            con.execute("""INSERT OR REPLACE INTO settings
                (category, key, value, description, updated_at)
                VALUES ('strategy', 'current_bake_hash',
                        'abc123def456', 'test', CURRENT_TIMESTAMP)""")
        assert current_bake_hash(tmp_db) == 'abc123def456'

    def test_raises_when_unset(self, tmp_db):
        with _pytest_for_bake.raises(RuntimeError, match='current_bake_hash'):
            current_bake_hash(tmp_db)


class TestPickFieldsBakeAware:
    @staticmethod
    def _seed(tmp_db):
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint)
                   VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                           '>', '5', NULL, 1.10, 'untested', 'numeric')""")
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint)
                   VALUES (2, 'v', 'b', '_vr_z.b', 'valuation_ratios', NULL,
                           '>', '5', NULL, 1.10, 'untested', 'numeric')""")
            cur.execute(
                """INSERT INTO probe_results
                   (field_id, experiment_name, round_n, bake_hash,
                    noop_baseline, spec_car_mdd, delta, classification,
                    applied_op, applied_threshold, applied_gate, applied_boost, recorded_at)
                   VALUES (1, 'S001_R100_vr_a_gt5', 100, 'old_bake',
                           1.98, 1.98, 0, 'neutral', '>', '5', NULL, 1.10, '2026-01-01')""")
            con.execute("""INSERT OR REPLACE INTO settings
                (category, key, value, description, updated_at)
                VALUES ('strategy', 'current_bake_hash', 'new_bake', 't', CURRENT_TIMESTAMP)""")

    def test_pick_fields_untested_excludes_current_bake_results(self, tmp_db):
        from s001.fundamental_probes import pick_fields
        self._seed(tmp_db)
        picked = pick_fields(tmp_db, k=10, classification='untested')
        names = sorted(p['field_name'] for p in picked)
        assert names == ['a', 'b']

    def test_pick_fields_untested_filters_when_current_bake_results_exist(self, tmp_db):
        from s001.fundamental_probes import pick_fields
        self._seed(tmp_db)
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            con.execute(
                """INSERT INTO probe_results
                   (field_id, experiment_name, round_n, bake_hash,
                    noop_baseline, spec_car_mdd, delta, classification,
                    applied_op, applied_threshold, applied_gate, applied_boost, recorded_at)
                   VALUES (2, 'S001_R200_vr_b_gt5', 200, 'new_bake',
                           1.99, 1.99, 0, 'neutral', '>', '5', NULL, 1.10, '2026-02-01')""")
        picked = pick_fields(tmp_db, k=10, classification='untested')
        names = [p['field_name'] for p in picked]
        assert names == ['a']

    def test_pick_fields_explicit_bake_hash_arg(self, tmp_db):
        from s001.fundamental_probes import pick_fields
        self._seed(tmp_db)
        picked = pick_fields(tmp_db, k=10, classification='untested', bake_hash='old_bake')
        names = [p['field_name'] for p in picked]
        assert names == ['b']


class TestEmitPhase2Sweep:
    def test_returns_15_specs(self):
        from s001.fundamental_probes import emit_phase2_sweep
        row = {
            'id': 7,
            'container': 'cash_flow_statement',
            'field_name': 'change_in_account_payable',
            'period': 'twelve_months',
            'probe_op': '>',
            'probe_threshold': '1e9',
            'probe_gate': 'decline > .12',
            'probe_boost': 1.08,
            'data_type_hint': 'absolute_amount',
        }
        out = emit_phase2_sweep(row, round_n=475)
        assert len(out) == 15
        names = [n for n, _ in out]
        for n in names:
            assert n.startswith('S001_R475_sw_cfs_change_in_account_payable_m')
        assert len(set(names)) == 15

    def test_grid_covers_expected_mags_and_gates(self):
        from s001.fundamental_probes import emit_phase2_sweep, SWEEP_MAGS, SWEEP_GATES
        assert SWEEP_MAGS == ['1.04', '1.06', '1.08', '1.10', '1.13']
        assert SWEEP_GATES == ['.05', '.10', '.15']

        row = {
            'id': 1, 'container': 'valuation_ratios', 'field_name': 'pe_ratio',
            'period': None, 'probe_op': '<', 'probe_threshold': '15',
            'probe_gate': 'decline > .12', 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        out = emit_phase2_sweep(row, round_n=999)
        suffixes = sorted(n.rsplit('_', 2)[-2] + '_' + n.rsplit('_', 1)[-1] for n, _ in out)
        expected = sorted(f'm{m.replace(".","")}_g{g.replace(".","")}' for m in SWEEP_MAGS for g in SWEEP_GATES)
        assert suffixes == expected

    def test_bodies_parse_as_python(self):
        import ast as _ast
        from s001.fundamental_probes import emit_phase2_sweep
        row = {
            'id': 1, 'container': 'valuation_ratios', 'field_name': 'pe_ratio',
            'period': None, 'probe_op': '<', 'probe_threshold': '15',
            'probe_gate': 'decline > .12', 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        for name, body in emit_phase2_sweep(row, round_n=999):
            wrapped = "def _f():\n  for sym in []:\n" + body + "\n   pass\n"
            _ast.parse(wrapped)

    def test_variant_overrides_mag_and_gate(self):
        from s001.fundamental_probes import emit_phase2_sweep
        row = {
            'id': 1, 'container': 'valuation_ratios', 'field_name': 'pe_ratio',
            'period': None, 'probe_op': '<', 'probe_threshold': '15',
            'probe_gate': 'decline > .12', 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        out = dict(emit_phase2_sweep(row, round_n=999))
        body = out['S001_R999_sw_vr_pe_ratio_m106_g05']
        assert 'score *= 1.06' in body
        assert 'decline > .05' in body
        assert 'score *= 1.1' not in body


class TestPickSweepCandidates:
    @staticmethod
    def _seed(tmp_db):
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            for fid, name in [(1, 'a'), (2, 'b'), (3, 'c')]:
                cur.execute(
                    """INSERT INTO fundamental_fields
                       (id, category, field_name, accessor, container, period,
                        probe_op, probe_threshold, probe_gate, probe_boost,
                        classification, data_type_hint, sweep_phase)
                       VALUES (?, 'v', ?, ?, 'valuation_ratios', NULL,
                               '>', '5', NULL, 1.10, 'untested', 'numeric', 0)""",
                    (fid, name, f'_vr_z.{name}'))
            for fid, delta in [(1, 0.0008), (2, 0.00005), (3, 0.0020)]:
                cur.execute(
                    """INSERT INTO probe_results
                       (field_id, experiment_name, round_n, bake_hash,
                        noop_baseline, spec_car_mdd, delta, classification,
                        applied_op, applied_threshold, applied_gate, applied_boost,
                        recorded_at, is_sweep_variant)
                       VALUES (?, ?, 1, 'cur_bake',
                               1.98, ?, ?, 'neutral',
                               '>', '5', NULL, 1.10, '2026-01-01', 0)""",
                    (fid, f'S001_R1_x_{fid}', 1.98 + delta, delta))

    def test_returns_only_above_trigger_threshold(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        ids = [r['id'] for r in out]
        assert 2 not in ids
        assert set(ids) == {1, 3}

    def test_sorted_by_max_abs_delta_desc(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        ids = [r['id'] for r in out]
        assert ids == [3, 1]

    def test_respects_k_limit(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        out = pick_sweep_candidates(tmp_db, k=1, bake_hash='cur_bake')
        assert len(out) == 1
        assert out[0]['id'] == 3

    def test_skips_fields_with_sweep_phase_nonzero(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            con.execute("UPDATE fundamental_fields SET sweep_phase = 1 WHERE id = 3")
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        ids = [r['id'] for r in out]
        assert 3 not in ids
        assert ids == [1]

    def test_empty_when_no_eligible_fields(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        assert out == []

    def test_uses_default_min_abs_delta_0001(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        assert {r['id'] for r in out} == {1, 3}
        out2 = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake', min_abs_delta=0.0010)
        assert {r['id'] for r in out2} == {3}


class TestUpdateSweepWinner:
    def test_writes_max_delta_variant(self, tmp_db):
        from s001.fundamental_probes import update_sweep_winner
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint, sweep_phase)
                   VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                           '>', '5', NULL, 1.10, 'untested', 'numeric', 1)""")
            for mag, gate, delta in [(1.04, '.10', 0.0010),
                                      (1.06, '.05', 0.0035),
                                      (1.08, '.15', 0.0008)]:
                cur.execute(
                    """INSERT INTO probe_results
                       (field_id, experiment_name, round_n, bake_hash,
                        noop_baseline, spec_car_mdd, delta, classification,
                        applied_op, applied_threshold, applied_gate, applied_boost,
                        recorded_at, is_sweep_variant)
                       VALUES (1, ?, 1, 'cur_bake',
                               1.98, ?, ?, 'hot',
                               '>', '5', ?, ?, '2026-01-01', 1)""",
                    (f'S001_R1_sw_vr_a_m{int(mag*100)}_g{gate.replace(".","")}',
                     1.98 + delta, delta, f'decline > {gate}', mag))
            update_sweep_winner(con, 1, 'cur_bake')
            cur.execute(
                """SELECT sweep_winner_op, sweep_winner_threshold,
                          sweep_winner_gate, sweep_winner_boost,
                          sweep_winner_delta, sweep_phase
                   FROM fundamental_fields WHERE id = 1""")
            op, thr, gate, boost, delta, phase = cur.fetchone()
        assert op == '>'
        assert thr == '5'
        assert gate == 'decline > .05'
        assert abs(boost - 1.06) < 1e-6
        assert abs(delta - 0.0035) < 1e-6
        assert phase == 2

    def test_no_variants_no_update(self, tmp_db):
        from s001.fundamental_probes import update_sweep_winner
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint, sweep_phase)
                   VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                           '>', '5', NULL, 1.10, 'untested', 'numeric', 1)""")
            update_sweep_winner(con, 1, 'cur_bake')
            cur.execute(
                "SELECT sweep_winner_op, sweep_phase FROM fundamental_fields WHERE id = 1")
            op, phase = cur.fetchone()
        assert op is None
        assert phase == 1


class TestFormatThreshold:
    def test_zero_returns_zero_string(self):
        from s001.fundamental_probes import _format_threshold
        assert _format_threshold(0, 'absolute_amount') == '0'

    def test_large_amounts_use_scientific(self):
        from s001.fundamental_probes import _format_threshold
        # Bumped from .1e to .3e to avoid p25/p50/p75 collisions when clustered.
        assert _format_threshold(1.5e9, 'absolute_amount') == '1.500e+09'
        assert _format_threshold(7.2e8, 'absolute_amount') == '7.200e+08'

    def test_small_ratios_use_four_sigfigs(self):
        from s001.fundamental_probes import _format_threshold
        # Bumped from .2g to .4g for higher precision.
        assert _format_threshold(0.10, 'ratio') == '0.1'
        assert _format_threshold(0.123, 'ratio') == '0.123'

    def test_tiny_values_use_scientific(self):
        from s001.fundamental_probes import _format_threshold
        assert _format_threshold(0.0005, 'ratio') == '5.000e-04'

    def test_modest_integer_no_scientific(self):
        from s001.fundamental_probes import _format_threshold
        # 120 < 1e6 falls under .4g now, which prints '120' (no scientific).
        assert _format_threshold(120, 'count') == '120'
        assert _format_threshold(15, 'ratio') == '15'

    def test_close_ratios_distinct_after_format(self):
        from s001.fundamental_probes import _format_threshold
        # C2 regression: 0.103 and 0.108 used to both → '0.1' under .2g.
        # With .4g they stay distinct.
        a = _format_threshold(0.103, 'ratio')
        b = _format_threshold(0.108, 'ratio')
        assert a != b


class TestCoarseGrid:
    def _seed_field_and_stats(self, db_path, hint='absolute_amount'):
        import qc_storage as storage
        with storage.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, ?)""", (hint,))
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            con.commit()

    def test_returns_72_cells_for_numeric(self, tmp_db):
        from s001.fundamental_probes import coarse_grid
        self._seed_field_and_stats(tmp_db)
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        # 2 ops × 4 mags × 3 gates × 3 thresholds = 72
        assert len(cells) == 72

    def test_returns_none_when_no_universe_stats(self, tmp_db):
        from s001.fundamental_probes import coarse_grid
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount')""")
            con.commit()
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        assert cells is None

    def test_categorical_uses_15_cell_fallback(self, tmp_db):
        from s001.fundamental_probes import coarse_grid
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'ac', 'fin_health', '_ac_z.fin_health', 'asset_classification',
                        'eq', '"A"', 1.08, 'categorical')""")
            con.commit()
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        assert len(cells) == 15  # 5 mags × 3 gates, no inversion or threshold sweep
        # All cells have op == 'eq' (no inversion)
        assert {c[0] for c in cells} == {'eq'}

    def test_thresholds_drawn_from_p25_p50_p75(self, tmp_db):
        from s001.fundamental_probes import coarse_grid
        self._seed_field_and_stats(tmp_db)
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        thresholds = {c[3] for c in cells}
        # .3e formatted: p25=1e8, p50=5e8, p75=1e9
        assert thresholds == {'1.000e+08', '5.000e+08', '1.000e+09'}

    def test_returns_none_when_thresholds_collide(self, tmp_db):
        """C2 regression: if p25/p50/p75 collapse to <3 unique formatted strings,
        coarse_grid returns None (skip this bake) rather than emitting a broken grid."""
        from s001.fundamental_probes import coarse_grid
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount')""")
            # All three percentiles equal — must format to a single string.
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 5e8, 5e8, 5e8, 5e9, 100, '2026-04-27')""")
            con.commit()
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        assert cells is None


class TestEmitV3Coarse:
    def _seed(self, db_path):
        import qc_storage as storage
        with storage.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount')""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            con.commit()

    def test_emit_categorical_field_does_not_crash(self, tmp_db):
        """Categorical fields should produce 15 cells with op='eq' encoded as 'eq'."""
        from s001.fundamental_probes import emit_v3_coarse
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'ac', 'fin_health', '_ac_z.fin_health', 'asset_classification',
                        'eq', '"A"', 1.08, 'categorical')""")
            con.commit()
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_coarse(row, round_n=500, bake_hash='BAKE_TEST', db_path=tmp_db)
        assert len(specs) == 15
        # All names use _oeq_ since categorical doesn't invert
        assert all('_oeq_' in name for name, _ in specs)
        for name, _ in specs:
            assert name.startswith('S001_R500_v3c_ac_fin_health_')
            assert len(name) <= 100

    def test_emit_returns_72_named_specs(self, tmp_db):
        from s001.fundamental_probes import emit_v3_coarse
        self._seed(tmp_db)
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_coarse(row, round_n=500, bake_hash='BAKE_TEST', db_path=tmp_db)
        assert len(specs) == 72
        # Names follow the v3c format
        for name, body in specs:
            assert name.startswith('S001_R500_v3c_bs_cash_')
            assert '_o' in name
            assert '_m' in name
            assert '_g' in name
            assert '_t' in name
            assert len(name) <= 100
            # Body uses the standard try/except shape
            assert '_v = f_(_bs_z.cash)' in body
            assert 'except: pass' in body

    def test_emit_uses_inverse_op(self, tmp_db):
        from s001.fundamental_probes import emit_v3_coarse
        self._seed(tmp_db)
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_coarse(row, round_n=500, bake_hash='BAKE_TEST', db_path=tmp_db)
        # Names with _ogt and _olt should both be present
        ops_seen = set()
        for name, _ in specs:
            if '_ogt_' in name:
                ops_seen.add('gt')
            if '_olt_' in name:
                ops_seen.add('lt')
        assert ops_seen == {'gt', 'lt'}

    def test_emit_returns_empty_when_no_stats(self, tmp_db):
        from s001.fundamental_probes import emit_v3_coarse
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount')""")
            con.commit()
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_coarse(row, round_n=500, bake_hash='BAKE_TEST', db_path=tmp_db)
        assert specs == []


class TestPickV3CoarseCandidates:
    def _seed(self, db_path):
        import qc_storage as storage
        with storage.connect(db_path) as con:
            cur = con.cursor()
            # Field 1: phase=1, has Phase 1 delta of +0.0005, has stats — eligible
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

            # Field 2: phase=1, has Phase 1 delta below threshold (+0.00005) — ineligible
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (2, 'bs', 'debt', '_bs_z.debt', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 1)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (2, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            cur.execute("""INSERT INTO probe_results
                (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                 spec_car_mdd, delta, classification, applied_op, applied_threshold,
                 applied_boost, recorded_at)
                VALUES (2, 'F2_phase1', 500, 'BAKE_TEST', 2.0, 2.00005, 0.00005,
                        'neutral', '>', '1e9', 1.08, '2026-04-27')""")

            # Field 3: phase=1, has delta but NO universe stats — ineligible
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (3, 'bs', 'rev', '_bs_z.rev', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 1)""")
            cur.execute("""INSERT INTO probe_results
                (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                 spec_car_mdd, delta, classification, applied_op, applied_threshold,
                 applied_boost, recorded_at)
                VALUES (3, 'F3_phase1', 500, 'BAKE_TEST', 2.0, 2.0005, 0.0005,
                        'neutral', '>', '1e9', 1.08, '2026-04-27')""")
            con.commit()

    def test_picks_only_eligible_field(self, tmp_db):
        from s001.fundamental_probes import pick_v3_coarse_candidates
        self._seed(tmp_db)
        picked = pick_v3_coarse_candidates(tmp_db, k=10, bake_hash='BAKE_TEST')
        assert len(picked) == 1
        assert picked[0]['id'] == 1

    def test_picking_bumps_phase_to_2(self, tmp_db):
        from s001.fundamental_probes import pick_v3_coarse_candidates
        self._seed(tmp_db)
        pick_v3_coarse_candidates(tmp_db, k=10, bake_hash='BAKE_TEST')
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            phase = con.execute(
                "SELECT sweep_phase FROM fundamental_fields WHERE id=1").fetchone()[0]
        assert phase == 2

    def test_returns_empty_when_k_zero(self, tmp_db):
        from s001.fundamental_probes import pick_v3_coarse_candidates
        self._seed(tmp_db)
        picked = pick_v3_coarse_candidates(tmp_db, k=0, bake_hash='BAKE_TEST')
        assert picked == []


class TestNeighbors:
    def test_returns_value_and_one_above_one_below(self):
        from s001.fundamental_probes import _neighbors
        assert _neighbors(0.10, [0.05, 0.10, 0.15], k=1) == [0.05, 0.10, 0.15]

    def test_at_lower_boundary(self):
        from s001.fundamental_probes import _neighbors
        assert _neighbors(1.04, [1.04, 1.08, 1.13, 1.20], k=1) == [1.04, 1.08]

    def test_at_upper_boundary(self):
        from s001.fundamental_probes import _neighbors
        assert _neighbors(1.20, [1.04, 1.08, 1.13, 1.20], k=1) == [1.13, 1.20]

    def test_value_not_in_set_returns_nearest(self):
        from s001.fundamental_probes import _neighbors
        # 1.10 isn't in the set; nearest below is 1.08, nearest above is 1.13
        assert _neighbors(1.10, [1.04, 1.08, 1.13, 1.20], k=1) == [1.08, 1.13]


class TestDimensionPrune:
    def test_drops_bottom_half_of_3plus_value_dimension(self):
        from s001.fundamental_probes import dimension_prune
        # Synthetic results: mag=1.04 wins, 1.08 ties, 1.13 loses, 1.20 loses
        results = []
        for mag, delta in [(1.04, 0.001), (1.08, 0.000), (1.13, -0.005), (1.20, -0.005)]:
            for op in ['>', '<']:
                for gate in ['.05', '.10', '.15']:
                    for thr in ['p25', 'p50', 'p75']:
                        results.append({
                            'op': op, 'mag': mag, 'gate': gate, 'threshold': thr,
                            'delta': delta + (0.0001 if op == '>' else 0.0)})
        survivors = dimension_prune(results)
        # Bottom-half mags should be dropped
        assert 1.04 in survivors['mag']
        assert 1.08 in survivors['mag']
        assert 1.13 not in survivors['mag']
        assert 1.20 not in survivors['mag']

    def test_two_value_dim_drops_loser_only_when_dominance_threshold_met(self):
        from s001.fundamental_probes import dimension_prune
        # `>` median = 0.001, `<` median = -0.0001 → diff = 0.0011 ≥ 0.001 → drop `<`
        results = []
        for op, op_delta in [('>', 0.001), ('<', -0.0001)]:
            for mag in [1.04, 1.08]:
                for gate in ['.05']:
                    for thr in ['p25']:
                        results.append({'op': op, 'mag': mag, 'gate': gate,
                                        'threshold': thr, 'delta': op_delta})
        survivors = dimension_prune(results)
        assert survivors['op'] == {'>'}

    def test_two_value_dim_keeps_both_when_close(self):
        from s001.fundamental_probes import dimension_prune
        # `>` median = 0.001, `<` median = 0.0005 → diff = 0.0005 < 0.001 → keep both
        results = []
        for op, op_delta in [('>', 0.001), ('<', 0.0005)]:
            for mag in [1.04, 1.08]:
                for gate in ['.05']:
                    for thr in ['p25']:
                        results.append({'op': op, 'mag': mag, 'gate': gate,
                                        'threshold': thr, 'delta': op_delta})
        survivors = dimension_prune(results)
        assert survivors['op'] == {'>', '<'}


class TestRefineGrid:
    def test_uses_neighbors_within_survivors(self):
        from s001.fundamental_probes import refine_grid
        coarse_winner = {'op': '>', 'mag': 1.08, 'gate': '.10',
                         'threshold': '5.0e+08'}
        refine_sets = {
            'op': {'>'},
            'mag': {1.04, 1.08, 1.13, 1.20},
            'gate': {'.05', '.10', '.15'},
            'threshold': {'1.0e+08', '5.0e+08', '1.0e+09'},
        }
        cells = refine_grid(coarse_winner, refine_sets)
        # 1 op × 3 mag (1.04, 1.08, 1.13) × 3 gate × 3 thr = 27 - 1 (winner) = 26
        assert len(cells) == 26
        # Coarse winner not in refine cells
        assert ('>', 1.08, '.10', '5.0e+08') not in cells

    def test_handles_singleton_survivor(self):
        from s001.fundamental_probes import refine_grid
        coarse_winner = {'op': '>', 'mag': 1.08, 'gate': '.10',
                         'threshold': '5.0e+08'}
        refine_sets = {
            'op': {'>'}, 'mag': {1.08}, 'gate': {'.10'},
            'threshold': {'5.0e+08'},
        }
        cells = refine_grid(coarse_winner, refine_sets)
        # Only one cell exists and it's the winner; refine excludes it → empty
        assert cells == []


class TestEmitV3Refine:
    def _seed(self, db_path):
        import qc_storage as storage, json
        with storage.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase,
                 coarse_winner_op, coarse_winner_mag, coarse_winner_gate,
                 coarse_winner_threshold, coarse_winner_delta,
                 refine_op_set, refine_mag_set, refine_gate_set, refine_threshold_set)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 3,
                        '>', 1.08, '.10', '5.0e+08', 0.0008,
                        ?, ?, ?, ?)""",
                (json.dumps(['>']),
                 json.dumps([1.04, 1.08, 1.13]),
                 json.dumps(['.05', '.10', '.15']),
                 json.dumps(['1.0e+08', '5.0e+08', '1.0e+09'])))
            con.commit()

    def test_emit_returns_26_named_specs(self, tmp_db):
        from s001.fundamental_probes import emit_v3_refine
        self._seed(tmp_db)
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_refine(row, round_n=501)
        assert len(specs) == 26
        for name, body in specs:
            assert name.startswith('S001_R501_v3r_bs_cash_')
            assert len(name) <= 100

    def test_emit_canonical_percentile_when_p25_pruned(self, tmp_db):
        """C1 regression: if dimension_prune drops p25, refine cells using p50/p75
        must still get _t50/_t75 in their spec names — not _t25/_t50 from the old
        positional relabeling. Canonical mapping reads field_universe_stats."""
        from s001.fundamental_probes import emit_v3_refine, _format_threshold
        import qc_storage as storage, json
        # Use canonical formatted values that match what the universe stats produce.
        p25_str = _format_threshold(1e8, 'absolute_amount')
        p50_str = _format_threshold(5e8, 'absolute_amount')
        p75_str = _format_threshold(1e9, 'absolute_amount')
        with storage.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase,
                 coarse_winner_op, coarse_winner_mag, coarse_winner_gate,
                 coarse_winner_threshold, coarse_winner_delta,
                 refine_op_set, refine_mag_set, refine_gate_set, refine_threshold_set)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 3,
                        '>', 1.08, '.10', ?, 0.0008,
                        ?, ?, ?, ?)""",
                (p50_str,
                 json.dumps(['>']),
                 json.dumps([1.04, 1.08, 1.13]),
                 json.dumps(['.05', '.10', '.15']),
                 # p25 pruned — only p50 and p75 survive
                 json.dumps([p50_str, p75_str])))
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            con.commit()
            con.row_factory = storage.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_refine(row, round_n=501, bake_hash='BAKE_TEST', db_path=tmp_db)
        # Spec names with _t50 must use the p50 threshold (5e8)
        # Spec names with _t75 must use the p75 threshold (1e9)
        # No spec name should use _t25 — p25 was pruned
        for name, body in specs:
            assert '_t25' not in name, f'p25 was pruned but {name} uses _t25'
        # Confirm canonical labels appear correctly when p50/p75 thresholds are emitted
        for name, body in specs:
            if '_t50' in name:
                assert p50_str in body, f'{name} labeled _t50 but body lacks {p50_str}'
            elif '_t75' in name:
                assert p75_str in body, f'{name} labeled _t75 but body lacks {p75_str}'


class TestPickV3RefineCandidates:
    def _seed(self, db_path):
        import qc_storage as storage
        with storage.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 2)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            # Insert all 72 coarse results with synthetic deltas
            for i, op in enumerate(['>', '<']):
                for j, mag in enumerate([1.04, 1.08, 1.13, 1.20]):
                    for k, gate in enumerate(['.05', '.10', '.15']):
                        for m, thr in enumerate(['1.0e+08', '5.0e+08', '1.0e+09']):
                            # Best at op=>, mag=1.08, gate=.10, thr=5.0e+08
                            best = (op == '>' and mag == 1.08 and gate == '.10'
                                    and thr == '5.0e+08')
                            delta = 0.001 if best else -0.001
                            uniq = i * 1000 + j * 100 + k * 10 + m
                            cur.execute("""INSERT INTO probe_results
                                (field_id, experiment_name, round_n, bake_hash,
                                 noop_baseline, spec_car_mdd, delta, classification,
                                 applied_op, applied_threshold, applied_gate,
                                 applied_boost, recorded_at, sweep_stage)
                                VALUES (?, ?, 500, 'BAKE_TEST', 2.0, ?, ?, 'neutral',
                                        ?, ?, ?, ?, '2026-04-27', 'coarse')""",
                                (1, f'F1_coarse_{uniq}', 2.0 + delta, delta,
                                 op, thr, f'decline > {gate}', mag))
            con.commit()

    def test_picks_field_with_72_coarse_done(self, tmp_db):
        from s001.fundamental_probes import pick_v3_refine_candidates
        self._seed(tmp_db)
        picked = pick_v3_refine_candidates(tmp_db, k=10, bake_hash='BAKE_TEST')
        assert len(picked) == 1
        assert picked[0]['id'] == 1

    def test_persists_refine_sets_and_coarse_winner(self, tmp_db):
        from s001.fundamental_probes import pick_v3_refine_candidates
        self._seed(tmp_db)
        pick_v3_refine_candidates(tmp_db, k=10, bake_hash='BAKE_TEST')
        import qc_storage as storage, json
        with storage.connect(tmp_db) as con:
            con.row_factory = storage.Row
            row = con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone()
        assert row['sweep_phase'] == 3
        assert row['coarse_winner_op'] == '>'
        assert row['coarse_winner_mag'] == 1.08
        assert row['coarse_winner_gate'] == '.10'
        assert row['coarse_winner_threshold'] == '5.0e+08'
        assert row['coarse_winner_delta'] == 0.001
        # JSON-encoded sets are populated
        assert row['refine_op_set'] is not None
        assert row['refine_mag_set'] is not None


class TestUpdateV3Winner:
    def _seed(self, db_path):
        import qc_storage as storage, json
        with storage.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase,
                 coarse_winner_op, coarse_winner_mag, coarse_winner_gate,
                 coarse_winner_threshold, coarse_winner_delta,
                 refine_op_set, refine_mag_set, refine_gate_set, refine_threshold_set)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 3,
                        '>', 1.08, '.10', '5.0e+08', 0.0008,
                        ?, ?, ?, ?)""",
                (json.dumps(['>']),
                 json.dumps([1.04, 1.08, 1.13]),
                 json.dumps(['.05', '.10', '.15']),
                 json.dumps(['1.0e+08', '5.0e+08', '1.0e+09'])))
            # Insert refine results — best is mag=1.13, delta=0.0015
            for mag in [1.04, 1.08, 1.13]:
                for gate in ['.05', '.10', '.15']:
                    for thr in ['1.0e+08', '5.0e+08', '1.0e+09']:
                        if (mag, gate, thr) == (1.08, '.10', '5.0e+08'):
                            continue  # skip coarse winner
                        delta = 0.0015 if mag == 1.13 and gate == '.10' and thr == '5.0e+08' else 0.0005
                        cur.execute("""INSERT INTO probe_results
                            (field_id, experiment_name, round_n, bake_hash,
                             noop_baseline, spec_car_mdd, delta, classification,
                             applied_op, applied_threshold, applied_gate,
                             applied_boost, recorded_at, sweep_stage)
                            VALUES (?, ?, 501, 'BAKE_TEST', 2.0, ?, ?, 'neutral',
                                    '>', ?, ?, ?, '2026-04-27', 'refine')""",
                            (1, f'F1_refine_{mag}_{gate}_{thr}', 2.0 + delta, delta,
                             thr, f'decline > {gate}', mag))
            con.commit()

    def test_writes_sweep_winner_and_phase4_version3(self, tmp_db):
        from s001.fundamental_probes import update_v3_winner
        self._seed(tmp_db)
        import qc_storage as storage
        with storage.connect(tmp_db) as con:
            update_v3_winner(con, field_id=1, bake_hash='BAKE_TEST')
            con.commit()
            row = con.execute(
                "SELECT sweep_phase, sweep_version, sweep_winner_op, "
                "sweep_winner_threshold, sweep_winner_gate, sweep_winner_boost, "
                "sweep_winner_delta FROM fundamental_fields WHERE id=1").fetchone()
        phase, version, op, thr, gate, boost, delta = row
        assert phase == 4
        assert version == 3
        assert op == '>'
        assert boost == 1.13
        assert gate == 'decline > .10'
        assert thr == '5.0e+08'
        assert abs(delta - 0.0015) < 1e-9


# === Mega-round helpers ===

from s001.fundamental_probes import flip_op


class TestFlipOp:
    def test_gt_to_lt(self):
        assert flip_op('>') == '<'

    def test_lt_to_gt(self):
        assert flip_op('<') == '>'

    def test_gte_to_lte(self):
        assert flip_op('>=') == '<='

    def test_lte_to_gte(self):
        assert flip_op('<=') == '>='

    def test_eq_to_neq(self):
        assert flip_op('eq') == 'neq'

    def test_in_to_notin(self):
        assert flip_op('in') == 'notin'

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            flip_op('between')


from s001.fundamental_probes import build_condition


class TestBuildConditionInverse:
    def test_neq_string(self):
        row = {'probe_op': 'neq', 'probe_threshold': '"A"',
               'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v != 'A'"

    def test_neq_number(self):
        row = {'probe_op': 'neq', 'probe_threshold': '207',
               'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v != 207"

    def test_notin_array(self):
        row = {'probe_op': 'notin', 'probe_threshold': '[205, 206, 207]',
               'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v not in (205, 206, 207)"

    def test_notin_single_element(self):
        row = {'probe_op': 'notin', 'probe_threshold': '["A"]',
               'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v not in ('A',)"

    def test_neq_requires_categorical(self):
        row = {'probe_op': 'neq', 'probe_threshold': '"A"',
               'data_type_hint': 'numeric'}
        with pytest.raises(ValueError, match='categorical'):
            build_condition(row, '_v')

    def test_notin_requires_array(self):
        row = {'probe_op': 'notin', 'probe_threshold': '"single"',
               'data_type_hint': 'categorical'}
        with pytest.raises(ValueError, match='array'):
            build_condition(row, '_v')


from s001.fundamental_probes import MECHANISMS, MECH_DEFAULTS


class TestMechanismDefaults:
    def test_six_mechanisms(self):
        assert MECHANISMS == ('score', 'skip', 'stop', 'petgt', 'convg', 'convb')

    def test_each_has_required_keys(self):
        required = {'action', 'mag', 'gate', 'side', 'location'}
        for m in MECHANISMS:
            assert required <= set(MECH_DEFAULTS[m].keys()), f'{m} missing keys'

    def test_score_defaults(self):
        d = MECH_DEFAULTS['score']
        assert d['action'] == 'score *= {mag}'
        assert d['mag'] == 1.10
        assert d['gate'] == 'decline > .05'
        assert d['side'] == 'good'
        assert d['location'] == 'entry'

    def test_skip_defaults(self):
        d = MECH_DEFAULTS['skip']
        assert d['action'] == 'continue'
        assert d['mag'] is None
        assert d['gate'] == 'decline > .10'
        assert d['side'] == 'bad'
        assert d['location'] == 'entry'

    def test_stop_defaults(self):
        d = MECH_DEFAULTS['stop']
        assert d['action'] == 'stop *= {mag}'
        assert d['mag'] == 0.85
        assert d['gate'] is None
        assert d['side'] == 'bad'
        assert d['location'] == 'exit'

    def test_petgt_defaults(self):
        d = MECH_DEFAULTS['petgt']
        assert d['action'] == 'petgt *= {mag}'
        assert d['mag'] == 1.15
        assert d['gate'] is None
        assert d['side'] == 'good'
        assert d['location'] == 'exit'

    def test_convg_defaults(self):
        d = MECH_DEFAULTS['convg']
        assert d['action'] == 'conv *= {mag}'
        assert d['mag'] == 1.15
        assert d['gate'] == 'decline > .05'
        assert d['side'] == 'good'
        assert d['location'] == 'entry'

    def test_convb_defaults(self):
        d = MECH_DEFAULTS['convb']
        assert d['action'] == 'conv *= {mag}'
        assert d['mag'] == 0.70
        assert d['gate'] == 'decline > .05'
        assert d['side'] == 'bad'
        assert d['location'] == 'entry'


from s001.fundamental_probes import ENTRY_BIND, EXIT_BIND, BIND


class TestBinds:
    def test_entry_bind_equals_bind(self):
        assert ENTRY_BIND == BIND

    def test_exit_bind_equals_bind(self):
        assert EXIT_BIND == BIND

    def test_binds_contain_alias_block(self):
        assert '_ops_z' in ENTRY_BIND
        assert '_vr_z' in ENTRY_BIND
        assert '_bs_z' in ENTRY_BIND


from s001.fundamental_probes import mega_spec_name


class TestMegaSpecName:
    def test_score_ops(self):
        row = {'container': 'operation_ratios', 'field_name': 'revenue_growth'}
        assert mega_spec_name(603, 'score', row) == 'S001_R603_mg_score_ops_revenue_growth'

    def test_skip_ers(self):
        row = {'container': 'earning_ratios', 'field_name': 'diluted_eps_growth'}
        assert mega_spec_name(603, 'skip', row) == 'S001_R603_mg_skip_ers_diluted_eps_growth'

    def test_petgt_vr(self):
        row = {'container': 'valuation_ratios', 'field_name': 'pe_ratio'}
        assert mega_spec_name(603, 'petgt', row) == 'S001_R603_mg_petgt_vr_pe_ratio'

    def test_convb_bs(self):
        row = {'container': 'balance_sheet', 'field_name': 'long_term_debt'}
        assert mega_spec_name(603, 'convb', row) == 'S001_R603_mg_convb_bs_long_term_debt'

    def test_handles_underscore_heavy_field_name(self):
        row = {'container': 'cash_flow_statement',
               'field_name': 'change_in_account_payable'}
        assert mega_spec_name(603, 'score', row) == 'S001_R603_mg_score_cfs_change_in_account_payable'

    def test_unknown_mech_raises(self):
        row = {'container': 'operation_ratios', 'field_name': 'roe'}
        with pytest.raises(KeyError):
            mega_spec_name(603, 'bogus', row)

    def test_unknown_container_raises(self):
        row = {'container': 'mystery', 'field_name': 'x'}
        with pytest.raises(KeyError):
            mega_spec_name(603, 'score', row)


from s001.fundamental_probes import render_cell


def _row_score_template():
    """A score-template field: revenue_growth > 0.10 → score *= 1.10, gated decline > .12."""
    return {
        'id': 1, 'container': 'operation_ratios', 'field_name': 'revenue_growth',
        'period': 'one_year',
        'probe_op': '>', 'probe_threshold': '0.10', 'probe_gate': 'decline > .12',
        'probe_boost': 1.10, 'data_type_hint': 'numeric',
    }


def _row_categorical_in():
    return {
        'id': 2, 'container': 'asset_classification',
        'field_name': 'morningstar_sector_code', 'period': None,
        'probe_op': 'in', 'probe_threshold': '[205, 206, 207]',
        'probe_gate': 'decline > .10', 'probe_boost': 1.08,
        'data_type_hint': 'categorical',
    }


class TestRenderCell:
    def test_score_good_side(self):
        out = render_cell(_row_score_template(), 'score', 603)
        assert out is not None
        name, body, location = out
        assert name == 'S001_R603_mg_score_ops_revenue_growth'
        assert location == 'entry'
        assert '_ops_z.revenue_growth.one_year' in body
        assert '_v > 0.10' in body
        assert 'decline > .05' in body
        assert 'score *= 1.1' in body

    def test_skip_bad_side(self):
        out = render_cell(_row_score_template(), 'skip', 603)
        assert out is not None
        name, body, location = out
        assert name == 'S001_R603_mg_skip_ops_revenue_growth'
        assert location == 'entry'
        assert '_v < 0.10' in body
        assert 'continue' in body
        assert 'decline > .10' in body

    def test_stop_bad_side(self):
        out = render_cell(_row_score_template(), 'stop', 603)
        assert out is not None
        name, body, location = out
        assert location == 'exit'
        assert '_v < 0.10' in body
        assert 'stop *= 0.85' in body
        assert 'decline >' not in body

    def test_petgt_good_side(self):
        out = render_cell(_row_score_template(), 'petgt', 603)
        assert out is not None
        name, body, location = out
        assert location == 'exit'
        assert '_v > 0.10' in body
        assert 'petgt *= 1.15' in body
        assert 'decline >' not in body

    def test_convg_good_side(self):
        out = render_cell(_row_score_template(), 'convg', 603)
        assert out is not None
        name, body, location = out
        assert location == 'entry'
        assert '_v > 0.10' in body
        assert 'conv *= 1.15' in body
        assert 'decline > .05' in body

    def test_convb_bad_side(self):
        out = render_cell(_row_score_template(), 'convb', 603)
        assert out is not None
        name, body, location = out
        assert location == 'entry'
        assert '_v < 0.10' in body
        assert 'conv *= 0.7' in body
        assert 'decline > .05' in body

    def test_categorical_in_good_renders(self):
        out = render_cell(_row_categorical_in(), 'score', 603)
        assert out is not None
        name, body, location = out
        assert '_v in (205, 206, 207)' in body

    def test_categorical_notin_bad_renders(self):
        out = render_cell(_row_categorical_in(), 'skip', 603)
        assert out is not None
        name, body, location = out
        assert '_v not in (205, 206, 207)' in body

    def test_unknown_mech_raises(self):
        with pytest.raises(KeyError):
            render_cell(_row_score_template(), 'bogus', 603)


import qc_storage as _storage_pf
from s001.fundamental_probes import pick_fields


def _seed_three_fields(tmp_db):
    """One templated untested, one templated already-tested, one with NULL template."""
    with _storage_pf.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint, classification) "
            "VALUES (1, 'ops', 'revenue_growth', '_ops_z.revenue_growth.one_year', "
            "'operation_ratios', 'one_year', '>', '0.10', 'decline > .12', 1.10, 'numeric', 'untested')")
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint, classification) "
            "VALUES (2, 'vr', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL, "
            "'<', '15', 'decline > .10', 1.10, 'numeric', 'hot')")
        cur.execute(
            "INSERT INTO probe_results "
            "(field_id, experiment_name, round_n, bake_hash, noop_baseline, spec_car_mdd, delta, classification, applied_op, applied_threshold, applied_gate, applied_boost, recorded_at) "
            "VALUES (2, 'S001_R500_vr_pe_ratio_lt15', 500, 'b4619', 1.9, 1.91, 0.01, 'hot', '<', '15', 'decline > .10', 1.10, '2026-04-29')")
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, classification) "
            "VALUES (3, 'sr', 'no_template_field', '_sr_z.no_template_field', 'security_reference', NULL, NULL, NULL, 'untested')")
        cur.execute("INSERT INTO settings (category, key, value) VALUES ('strategy', 'current_bake_hash', 'b4619')")
        con.commit()


class TestPickFieldsForceAll:
    def test_default_excludes_already_probed(self, tmp_db):
        _seed_three_fields(tmp_db)
        picked = pick_fields(tmp_db, k=10, classification='untested')
        ids = {p['id'] for p in picked}
        assert 1 in ids
        assert 2 not in ids
        assert 3 not in ids

    def test_force_all_includes_already_probed(self, tmp_db):
        _seed_three_fields(tmp_db)
        picked = pick_fields(tmp_db, k=10, force_all=True)
        ids = {p['id'] for p in picked}
        assert 1 in ids
        assert 2 in ids
        assert 3 not in ids

    def test_force_all_ignores_classification_arg(self, tmp_db):
        _seed_three_fields(tmp_db)
        picked = pick_fields(tmp_db, k=10, classification='hot', force_all=True)
        ids = {p['id'] for p in picked}
        assert 1 in ids
        assert 2 in ids


from s001.fundamental_probes import emit_mega_round


def _seed_mega_test_fields(tmp_db):
    with _storage_pf.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint) "
            "VALUES (1, 'ops', 'revenue_growth', '_ops_z.revenue_growth.one_year', "
            "'operation_ratios', 'one_year', '>', '0.10', 'decline > .12', 1.10, 'numeric')")
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint) "
            "VALUES (2, 'vr', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL, "
            "'<', '15', 'decline > .10', 1.10, 'numeric')")
        cur.execute("INSERT INTO settings (category, key, value) VALUES ('strategy', 'current_bake_hash', 'mega_test_hash')")
        con.commit()


class TestEmitMegaRound:
    def test_emits_six_cells_per_field(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, round_n=603, force_all=True))
        assert len(cells) == 12

    def test_each_cell_is_triple(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, 603, force_all=True))
        for c in cells:
            assert len(c) == 3
            name, body, location = c
            assert name.startswith('S001_R603_mg_')
            assert location in ('entry', 'exit')
            assert isinstance(body, str) and len(body) > 0

    def test_mechanism_breakdown(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, 603, force_all=True))
        from collections import Counter
        ctr = Counter(c[0].split('_')[3] for c in cells)
        for m in ('score', 'skip', 'stop', 'petgt', 'convg', 'convb'):
            assert ctr[m] == 2, f'{m}: {ctr[m]}'

    def test_location_split(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, 603, force_all=True))
        entry = [c for c in cells if c[2] == 'entry']
        exit_ = [c for c in cells if c[2] == 'exit']
        assert len(entry) == 8
        assert len(exit_) == 4

    def test_subset_of_mechanisms(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, 603,
                                     mechanisms=('score', 'skip'),
                                     force_all=True))
        assert len(cells) == 4
        for n, _, _ in cells:
            assert any(m in n for m in ('mg_score_', 'mg_skip_'))
