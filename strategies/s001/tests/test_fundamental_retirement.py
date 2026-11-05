"""Retired feed descriptors are missing data; unrelated provider errors still fail."""
import ast
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import warnings
import pytest
from s001.fundamental_probes import _container_property_names


def accessor():
    source = Path(__file__).resolve().parents[1] / 's001_20260628_base.py'
    function = next(node for node in ast.parse(source.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=='_g1')
    environment = {'g_':getattr,'f_':float,'_Dec':Decimal,'_RETIRED_FUNDAMENTAL_FIELDS':set(),'warnings':warnings}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),environment)
    return environment['_g1'],environment


def test_retired_field_is_missing_and_reported_once_per_accessor():
    class Retired:
        calls=0
        @property
        def normalized_diluted_eps_growth(self):
            Retired.calls+=1
            raise RuntimeError('NormalizedDilutedEPSGrowth was retired by Morningstar in 2026 for all periods; no replacement is available.')
    read,state = accessor()
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter('always')
        assert read(Retired(),'normalized_diluted_eps_growth','three_months') is None
        assert read(Retired(),'normalized_diluted_eps_growth','three_months') is None
    assert len(emitted)==1
    assert Retired.calls==1
    assert state['_RETIRED_FUNDAMENTAL_FIELDS']=={'Retired.normalized_diluted_eps_growth.three_months'}
    assert read(SimpleNamespace(active=SimpleNamespace(value=Decimal('0'))),'active','value')==0


def test_unrelated_descriptor_failure_is_not_hidden():
    class Broken:
        @property
        def active(self):
            raise RuntimeError('provider connection lost')
    read,_ = accessor()
    with pytest.raises(RuntimeError,match='connection lost'):
        read(Broken(),'active')


def test_catalogue_excludes_retired_properties_but_keeps_supported_fields():
    source='''class Fields:
    @property
    def active(self):
        """Supported financial field."""
        ...
    @property
    def retired(self):
        """This field was retired by Morningstar in 2026."""
        ...
'''
    assert _container_property_names(source,'Fields')==['active']


@pytest.mark.parametrize('roic,expected_score,expected_cap',[(None,1.0,1.0),(0.10,1.0,1.0),(0.20,1.08,1.5)])
def test_missing_roic_skips_baked_score_adjustment(roic,expected_score,expected_cap):
    source = Path(__file__).resolve().parents[1] / 's001_20260628_base.py'
    tree = ast.parse(source.read_text())
    conditions = [node for node in ast.walk(tree) if isinstance(node,ast.If)
                  and isinstance(node.body[0],ast.AugAssign)
                  and isinstance(node.body[0].target,ast.Name)
                  and node.body[0].target.id in {'S','C'}
                  and {'_rc3','_r3'} <= {n.id for n in ast.walk(node.test) if isinstance(n,ast.Name)}]
    assert len(conditions) == 2
    env = {'S':1.0,'C':1.0,'_rc3':roic,'_r3':-0.03,
           '_AN':lambda *values:all(v is not None for v in values),
           '_nrg':lambda v,lo,hi:v is not None and lo<v<hi}
    exec(compile(ast.Module(body=conditions,type_ignores=[]),str(source),'exec'),env)
    assert env['S'] == pytest.approx(expected_score)
    assert env['C'] == pytest.approx(expected_cap)
