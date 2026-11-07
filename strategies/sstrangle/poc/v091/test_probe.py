import hashlib
import json
import sys
from datetime import datetime
from types import SimpleNamespace as N
import pytest
from . import probe
from .build_probe import build


def plan(phase='on_data', prefix='M0'):
    return [dict(prefix=prefix, phase=phase, start='2022-11-15T13:40:00', end='2022-11-15T13:41:00')]


@pytest.mark.parametrize('bad', [[], plan()*2, plan()*5, [dict(plan()[0], phase='pre_trigger')], [dict(plan()[0], end='2022-11-14T00:00:00')], [dict(plan()[0], start='2022-11-15T13:40:00+00:00')]])
def test_reject_plan(bad):
    with pytest.raises(ValueError):
        probe.validate_plan(bad)


def test_windows_freeze_independent_callbacks_and_retry(monkeypatch):
    from . import margin_diagnostic as diagnostic
    monkeypatch.setattr(diagnostic, 'margin_snapshot', lambda a, r: dict(time=str(a.time)))
    stats = {}
    a = N(time=datetime(2022,11,15,13,39), set_runtime_statistic=stats.__setitem__)
    p = probe.MarginProbe(plan()+plan('on_order_event', 'M1'))
    p.observe(a, 'on_data')
    assert not stats
    a.time = datetime(2022,11,15,13,40)
    a.set_runtime_statistic = lambda *args: (_ for _ in ()).throw(RuntimeError())
    p.observe(a, 'on_data')
    assert not getattr(a, '_margin_receipt_sealed', set())
    a.set_runtime_statistic = stats.__setitem__
    p.observe(a, 'on_data')
    frozen = dict(stats)
    a.time = datetime(2022,11,15,13,41)
    p.observe(a, 'on_data')
    assert stats == frozen
    p.observe(a, 'on_order_event')
    assert len(stats) == 34
    a.time = datetime(2022,11,15,13,42)
    p.observe(a, 'on_margin_call')
    assert len(stats) == 34


def test_assembled_callbacks_preserve_native_behavior(tmp_path, monkeypatch):
    base, config, out = tmp_path/'base.py', tmp_path/'plan.json', tmp_path/'out'
    base.write_text('from __future__ import annotations\nclass Strategy(QCAlgorithm):\n    def initialize(self):\n        self.orders = []\n    def on_order_event(self, event):\n        self.orders.append(event)\n        return 42\n')
    config.write_text(json.dumps(plan()))
    manifest = build(base, config, out)
    assert manifest['cloud_parity'] is False
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((out/name).read_bytes()).hexdigest() == digest
    monkeypatch.syspath_prepend(str(out))
    namespace = dict(QCAlgorithm=object)
    exec((out/'main.py').read_text(), namespace)
    a = namespace['Strategy']()
    a.initialize()
    a.time = datetime(2022,11,15,13,40)
    a.set_runtime_statistic = lambda *args: (_ for _ in ()).throw(RuntimeError())
    assert a.on_order_event('native') == 42 and a.orders == ['native']
    requests = [object()]
    assert a.on_margin_call(requests) is requests
    a.on_data(None)  # Even failed telemetry cannot escape.
    with pytest.raises(ValueError):
        build(base, config, out)


def test_group_composition_and_capacity(monkeypatch):
    from . import margin_diagnostic as diagnostic
    monkeypatch.setitem(sys.modules, 'QuantConnect.Securities.Positions', N(ReservedBuyingPowerForPositionGroupParameters=lambda *args: None))
    model = N(GetType=lambda: N(Name='Spread'), get_reserved_buying_power_for_position_group=lambda p: N(absolute_used_buying_power=700))
    group = N(buying_power_model=model, positions=[N(symbol='SPXW',quantity=-1)])
    a = N(time='now', portfolio=N(positions=N(groups=[group]), total_portfolio_value=900, cash=1000, total_margin_used=700, margin_remaining=200), securities={})
    assert diagnostic.margin_snapshot(a, [])['groups'][0]['positions'] == [dict(symbol='SPXW',quantity=-1)]
    monkeypatch.setattr(diagnostic, 'margin_snapshot', lambda *args: dict(large='x'*4000))
    stats = {}
    a.set_runtime_statistic = stats.__setitem__
    diagnostic.record_margin_state(a,'M0',once=True)
    raw = ''.join(stats['M0'+str(i).zfill(2)] for i in range(16))[:int(stats['M0len'])]
    assert json.loads(raw)['error'] == 'capacity'
    assert max(map(len, stats.values())) <= 180


@pytest.mark.parametrize('source', [
    'class A: pass\n',
    'class A(QCAlgorithm):\n    def initialize(self): pass\n',
    'class A(QCAlgorithm):\n    def initialize(self):\n        pass\n    async def on_data(self, data):\n        pass\n',
    'class A(QCAlgorithm):\n    def initialize(self):\n        pass\n    def on_data(self, wrong):\n        pass\n',
])
def test_builder_rejects_unsupported_source(tmp_path, source):
    base, config = tmp_path/'base.py', tmp_path/'plan.json'
    base.write_text(source)
    config.write_text(json.dumps(plan()))
    with pytest.raises(ValueError):
        build(base, config, tmp_path/'out')
    assert not (tmp_path/'out').exists()
