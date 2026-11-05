"""Mutation boundaries: constraints, target isolation and generated Python syntax."""
import ast
from pathlib import Path
import pytest
from s002.round_lib import mut_etf, make_spec, parse_all_etfs

BASE = "ETFS = {\n 'spy': {'wt':0.04,'tp':0.1},\n 'vti': {'wt':0.05,'tp':0.2},\n}\n"


def test_mutation_preserves_other_etfs_and_parses():
    mutated = mut_etf({'tp': 0.15}, 'spy', BASE)
    assert mutated is not None
    values = ast.literal_eval(ast.parse(mutated).body[0].value)
    assert values['spy']['tp'] == 0.15
    assert values['vti'] == {'wt': 0.05, 'tp': 0.2}


@pytest.mark.parametrize('etf,change', [
    ('spy', {'wt': 0.5}), ('spy', {'sl': 0.01}), ('gdx', {'wt': 0.04}),
    ('mgv', {'tf_t': 0.99}), ('pjp', {'tp': 0.2}), ('spy', {'sp': 281}),
    ('spy', {'sf': 0}),
])
def test_dangerous_parameter_combinations_are_rejected(etf, change):
    with pytest.raises(ValueError):
        mut_etf(change, etf, BASE)


def test_missing_target_never_mutates_some_other_etf():
    assert mut_etf({'tp': 0.15}, 'qqq', BASE) is None


def test_real_baseline_remains_parseable_and_can_be_salted():
    path = Path(__file__).resolve().parents[1] / 's002_20260628_ls_base.py'
    code = path.read_text()
    ast.parse(code)
    assert parse_all_etfs(code)
    salted = make_spec('vti', {'tp': 0.1}, 17, code)
    assert salted is not None
    ast.parse(salted)
