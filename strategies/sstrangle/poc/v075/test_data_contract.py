import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
sys.path.insert(0, str(Path(__file__).parent))
from data_contract import quote_rejections, package_rejections, entry_grid, storage_plan

D = datetime(2026, 10, 23, 13, 35, 1, tzinfo=timezone.utc)
def row():
    return dict(interval_ts=D-timedelta(seconds=1),quote_ts=D-timedelta(seconds=2),
                available_at=D-timedelta(milliseconds=100),bid=1.,ask=1.1,
                bid_size=3,ask_size=4,quote_type='NBBO')

def test_known_fresh_quote_and_multileg():
    assert not quote_rejections(row(),D)
    assert not package_rejections([row(),row()],D)

@pytest.mark.parametrize('key',['interval_ts','quote_ts','available_at'])
def test_unknown_and_equal_timestamp_do_not_pass(key):
    r=row();r[key]=None
    assert 'unknown_'+key in quote_rejections(r,D)
    r[key]=D
    assert 'not_prior_'+key in quote_rejections(r,D)

@pytest.mark.parametrize('key',['interval_ts','quote_ts'])
def test_stale_source_and_interval_are_separate(key):
    r=row();r[key]=D-timedelta(seconds=121)
    assert 'stale_'+key in quote_rejections(r,D)

@pytest.mark.parametrize('bid,ask',[(0,1),(-1,1),(2,1),(float('nan'),1),(1,float('inf'))])
def test_bad_quotes_fail(bid,ask):
    r=row();r.update(bid=bid,ask=ask)
    assert 'invalid_market' in quote_rejections(r,D)

def test_snapshot_time_never_repairs_unknown_origin():
    r=row();r['quote_ts']=None
    assert 'unknown_quote_ts' in quote_rejections(r,D)

def test_strict_pre_slot_5m_is_stale_but_1m_can_be_recent():
    r=row();r.update(interval_ts=D-timedelta(seconds=301),quote_ts=D-timedelta(seconds=302))
    assert 'stale_interval_ts' in quote_rejections(r,D)
    r.update(interval_ts=D-timedelta(seconds=61),quote_ts=D-timedelta(seconds=62))
    assert not quote_rejections(r,D)

def test_cross_leg_skew_can_fail_individually_fresh_quotes():
    a,b=row(),row();b['quote_ts']=D-timedelta(seconds=60)
    assert not quote_rejections(b,D)
    assert 'cross_leg_skew' in package_rejections([a,b],D)

def test_bad_clock_order_and_naive_clock():
    r=row();r['quote_ts']=D-timedelta(milliseconds=500)
    assert 'quote_after_snapshot' in quote_rejections(r,D)
    r=row();r['available_at']=D-timedelta(seconds=3)
    assert 'available_before_snapshot' in quote_rejections(r,D)
    with pytest.raises(ValueError):quote_rejections(row(),D.replace(tzinfo=None))

@pytest.mark.parametrize('field,value,reason',[
    ('bid_size',0,'missing_executable_size'),('ask_size',None,'missing_executable_size'),
    ('quote_type','TRADE','not_nbbo'),('is_fill_forward',True,'fill_forward')])
def test_no_implicit_liquidity_or_trade_substitution(field,value,reason):
    r=row();r[field]=value
    assert reason in quote_rejections(r,D)

def test_half_day_has_no_close_boundary_entry_and_dst_is_explicit():
    ny=ZoneInfo('America/New_York')
    for month,day,utc_hour in [(1,2,14),(7,1,13)]:
        op=datetime(2026,month,day,9,30,tzinfo=ny)
        assert op.astimezone(timezone.utc).hour==utc_hour
        assert len(entry_grid(op,op.replace(hour=16,minute=0)))==13
        slots=entry_grid(op,op.replace(hour=13,minute=0))
        assert len(slots)==7 and slots[-1].hour==12 and slots[-1].minute==30

def test_capacity_counts_puts_and_calls_as_contracts_not_tickers():
    assert storage_plan(1000,1)['rows']==391000
    assert storage_plan(1000,5)['rows']==79000
    assert storage_plan(1400,5)['rows']==110600
    with pytest.raises(ValueError):storage_plan(1000,0)
