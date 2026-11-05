"""Same adversarial oracles run against old and new packages via AXIS_REVIEW_VERSION."""
import importlib
import os
from datetime import timedelta
from types import SimpleNamespace
import pytest

PACKAGE='strategies.sstrangle.poc.'+os.environ.get('AXIS_REVIEW_VERSION','v090')
axis=importlib.import_module(PACKAGE+'.axis')
shadow=importlib.import_module(PACKAGE+'.shadow')
qc=importlib.import_module(PACKAGE+'.qc_adapter')
helpers=importlib.import_module(PACKAGE+'.test_axis')
OP,minute,quote=helpers.OP,helpers.minute,helpers.quote
DEADLINE='2024-01-08T15:00:00+00:00'


def test_conflicting_contract_does_not_remove_other_contracts():
    rows=[quote(),quote(bid=.9),quote(contract_id='healthy',source_row_id='healthy')]
    chain,bad=shadow.align_options(rows,DEADLINE)
    assert [r['contract_id'] for r in chain]==['healthy']
    assert any(r['reason']=='conflicting_duplicate_contract_snapshot' for r in bad)


def test_bad_observation_clock_is_an_exclusion():
    chain,bad=shadow.align_options([quote(observed_at='broken'),quote(contract_id='healthy')],DEADLINE)
    assert [r['contract_id'] for r in chain]==['healthy']
    assert any(r['reason'].startswith('invalid_field:') for r in bad)


def test_nonpositive_calibration_is_rejected():
    a=axis.Axis()
    with pytest.raises(ValueError):
        a.seed([dict(session='2024-01-05',activity=0.,complete=True,available_at='2024-01-05T21:00:01Z')])


def test_qc_exports_incomplete_bar_created_during_gap():
    c=[dict(session='2024-01-08',open=axis.stamp(OP),close=axis.stamp(OP+timedelta(minutes=30)))]
    bridge=qc.QCShadow(c)
    bridge.axis.seed([dict(session=f'2023-12-{i:02}',activity=26.,complete=True,
        available_at=f'2023-12-{i:02}T21:00:01Z') for i in range(1,21)])
    for i in [0,2]:
        start=OP+timedelta(minutes=i)
        bar=SimpleNamespace(time=start,end_time=start+timedelta(minutes=1),open=100.,high=100.,low=100.,close=100.,is_fill_forward=False)
        algo=SimpleNamespace(utc_time=start+timedelta(minutes=1,seconds=1),time=start,index='SPX',slots=[])
        bridge.on_slice(algo,SimpleNamespace(bars={'SPX':bar}))
    assert bridge.valid
    exported=[r['value']['axis_id'] for r in bridge.records if r['kind']=='bar']
    assert exported==[b['axis_id'] for b in bridge.axis.bars]
    assert len(exported)==1 and not bridge.axis.bars[0]['is_complete']
