import ast
from datetime import date,timedelta
import pytest
from holding_age import age_exit_due,validate_max_holding_days
from build_holding_cap_source import render,PARENT


def test_exact_calendar_deadline_and_first_open_session_are_separate():
    assert not age_exit_due('2022-09-21',date(2022,10,14),24)
    assert age_exit_due('2022-09-21',date(2022,10,15),24)
    assert age_exit_due('2022-09-21',date(2022,10,17),24)


@pytest.mark.parametrize('bad',[0,True,24.0,46])
def test_explicit_deadline_cannot_silently_disable_policy(bad):
    with pytest.raises(ValueError):validate_max_holding_days(bad)


def test_target45to21_calendar_duration_is24days():
    entry=date(2020,1,2);expiry=entry+timedelta(days=45)
    assert age_exit_due(entry,expiry-timedelta(days=21),24)
    assert not age_exit_due(entry,expiry-timedelta(days=22),24)


def test_only_declared_initialization_noon_management_and_annotation_change():
    def methods(s):return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(s)) if isinstance(n,ast.FunctionDef)}
    a,b=methods(PARENT.read_text()),methods(render())
    assert set(a)==set(b) and {k for k in a if a[k]!=b[k]}=={'initialize','on_data','open_candidate'}
    source=render()
    assert source.index("'TIME' if dte <= self.time_exit_dte")<source.index("'AGE' if age_exit_due")
    assert "put.exchange.exchange_open" in source
    old=next(n for n in ast.walk(ast.parse(PARENT.read_text())) if isinstance(n,ast.FunctionDef) and n.name=='open_candidate')
    new=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='open_candidate')
    removed=0
    for call in ast.walk(new):
        if isinstance(call,ast.Call):
            removed+=sum(k.arg=='max_holding_days' for k in call.keywords)
            call.keywords=[k for k in call.keywords if k.arg!='max_holding_days']
    assert removed==1 and ast.dump(old,include_attributes=False)==ast.dump(new,include_attributes=False)
