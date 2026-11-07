"""Adversarial regressions for issues found in the 0.9.1 self-review."""
import json
from datetime import datetime
from types import SimpleNamespace as N
import pytest
from . import margin_diagnostic as diagnostic
from .probe import MarginProbe, validate_plan
from .receipt import decode, verify
from .build_probe import build


def plan():
    return [dict(prefix='M0',phase='on_data',start='2022-11-15T13:40:00',end='2022-11-15T13:41:00')]


def payload():
    return dict(time='2022-11-15 13:40:00',phase='on_data',equity=900,cash=1000,used=700,remaining=200,groups=[dict(model='Spread',reserved=700,positions=[dict(symbol='SPXW',quantity=-1)])],holdings=[],requests=[])


def publish(monkeypatch, value=None):
    stats = {}
    monkeypatch.setattr(diagnostic,'margin_snapshot',lambda *a: payload() if value is None else value)
    a = N(set_runtime_statistic=stats.__setitem__)
    diagnostic.record_margin_state(a,'M0',once=True,phase='on_data')
    return stats


def test_valid_and_tampered_export(monkeypatch):
    stats = publish(monkeypatch)
    assert verify(stats,plan()) == {'M0':payload()}
    stats['M000'] = stats['M000'].replace('900','901')
    with pytest.raises(ValueError,match='checksum'):
        decode(stats,plan()[0])


@pytest.mark.parametrize('value', [dict(error='capacity'),dict(payload(),cash=float('nan')),dict(payload(),time='2022-11-15 13:42:00'),dict(payload(),groups=[{}])])
def test_invalid_evidence(monkeypatch,value):
    with pytest.raises(ValueError):
        decode(publish(monkeypatch,value),plan()[0])


def test_missing_checkpoint_and_phase(monkeypatch):
    stats=publish(monkeypatch)
    with pytest.raises(ValueError):
        verify(stats,plan()+[dict(plan()[0],prefix='M1')])
    with pytest.raises(ValueError,match='phase'):
        decode(stats,dict(plan()[0],phase='on_order_event'))


def test_interrupted_commit_and_retry(monkeypatch):
    monkeypatch.setattr(diagnostic,'margin_snapshot',lambda *a:payload())
    stats={}
    def fail_commit(key,value):
        if key.endswith('sha256') and value != 'pending':
            raise RuntimeError('transport')
        stats[key]=value
    a=N(set_runtime_statistic=fail_commit)
    with pytest.raises(RuntimeError):
        diagnostic.record_margin_state(a,'M0',once=True,phase='on_data')
    with pytest.raises(ValueError):
        decode(stats,plan()[0])
    assert not getattr(a,'_margin_receipt_sealed',set())
    a.set_runtime_statistic=stats.__setitem__
    assert diagnostic.record_margin_state(a,'M0',once=True,phase='on_data')
    assert decode(stats,plan()[0]) == payload()


def test_plan_copy_and_type_errors():
    original=plan(); probe=MarginProbe(original)
    original[0]['phase']='bad'
    assert probe.plan[0]['phase']=='on_data'
    with pytest.raises(ValueError):
        validate_plan([dict(plan()[0],start=42)])


def assemble(tmp_path,source):
    base=tmp_path/'base.py'; config=tmp_path/'plan.json'
    base.write_text(source);config.write_text(json.dumps(plan()))
    out=tmp_path/'out';build(base,config,out)
    return out


@pytest.mark.parametrize('body', ['    on_data = lambda self, data: 42\n', '    if True:\n        def on_data(self, data):\n            pass\n', '    def on_data(self, data):\n        yield 42\n'])
def test_ambiguous_callback_rejected(tmp_path,body):
    with pytest.raises(ValueError):
        assemble(tmp_path,'class A(QCAlgorithm):\n    def initialize(self):\n        pass\n'+body)
    assert not (tmp_path/'out').exists()


def test_multiple_inheritance_rejected(tmp_path):
    with pytest.raises(ValueError):
        assemble(tmp_path,'class A(QCAlgorithm, Mixin):\n    def initialize(self):\n        pass\n')


def test_tabbed_docstrings_and_callback_parity(tmp_path,monkeypatch):
    out=assemble(tmp_path,'from __future__ import annotations\nclass A(QCAlgorithm):\n\tdef initialize(self):\n\t\t"""native docs"""\n\t\tself.events=[]\n\tdef on_order_event(self,event):\n\t\t"""event docs"""\n\t\tself.events.append(event)\n\t\treturn 42\n')
    monkeypatch.syspath_prepend(str(out))
    ns=dict(QCAlgorithm=object);exec((out/'main.py').read_text(),ns)
    a=ns['A']();a.initialize()
    assert a.initialize.__doc__=='native docs'
    assert a.on_order_event.__doc__=='event docs'
    assert a.on_order_event('event')==42 and a.events==['event']
    requests=[object()]
    assert a.on_margin_call(requests) is requests
    a.time=datetime(2022,11,15,13,40)
    a.set_runtime_statistic=lambda *args: (_ for _ in ()).throw(RuntimeError())
    a.on_data(None)


def test_docstring_only_initialize_and_failed_log(tmp_path,monkeypatch):
    out=assemble(tmp_path,'class A(QCAlgorithm):\n    def initialize(self):\n        """only documentation"""\n')
    monkeypatch.syspath_prepend(str(out))
    ns=dict(QCAlgorithm=object);exec((out/'main.py').read_text(),ns)
    a=ns['A']();a.initialize()
    assert hasattr(a,'_v092_probe')
    assert a.initialize.__doc__=='only documentation'
    requests=[object()]
    assert diagnostic.observe_margin_call(N(debug=lambda *args: (_ for _ in ()).throw(RuntimeError())),requests) is requests


@pytest.mark.parametrize('binding',['    from module import on_data\n','    del on_data\n'])
def test_other_callback_bindings_rejected(tmp_path,binding):
    with pytest.raises(ValueError):
        assemble(tmp_path,'class A(QCAlgorithm):\n    def initialize(self):\n        pass\n'+binding)
