import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('early_report',Path(__file__).with_name('report.py'))
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)

def fixture(exit_day,reason='TIME'):
    entry='2019-11-01T16:00:00Z'
    return [dict(ticker='WAG R735QTJ8XC9X',entry=entry,exit=exit_day+'T17:00:00Z',expiry='2019-12-20',entry_dte=49,rolls=0,reason=reason,calendar_21dte_date='2019-11-29')],[dict(key='WAG R735QTJ8XC9X',entry=entry,batch_id=1,quantity=1,allocation_budget=3000)]

@pytest.mark.parametrize('threshold,day',[(21,'2019-11-29'),(28,'2019-11-22')])
def test_actual_calendar_at_configured_threshold(threshold,day):
    cycles,entries=fixture(day);report.audit_dates(cycles,entries,threshold)
    assert cycles[0]['first_eligible_configured_exit_date']==day
    assert cycles[0]['configured_time_exit_dte']==threshold

@pytest.mark.parametrize('threshold,day',[(21,'2019-11-22'),(28,'2019-11-29'),(28,'2019-11-25')])
def test_wrong_day_not_accepted_as_equivalent(threshold,day):
    with pytest.raises(ValueError,match='TIME exit missed'):
        report.audit_dates(*fixture(day),threshold)

def test_stop_after_mandatory_deadline_is_rejected():
    with pytest.raises(ValueError,match='survived mandatory'):
        report.audit_dates(*fixture('2019-11-25','STOP'),28)

@pytest.mark.parametrize('threshold',[True,27,28.0,None])
def test_invalid_configuration_cannot_pass(threshold):
    with pytest.raises(ValueError,match='Unsupported'):
        report.audit_dates(*fixture('2019-11-22'),threshold)


def test_end_label_does_not_hide_missed_mandatory_exit():
    with pytest.raises(ValueError,match='survived mandatory'):
        report.audit_dates(*fixture('2019-11-25','END'),28)

def test_end_before_mandatory_deadline_remains_valid():
    report.audit_dates(*fixture('2019-11-21','END'),28)
