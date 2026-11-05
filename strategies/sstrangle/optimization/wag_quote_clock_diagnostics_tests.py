import unittest
from datetime import datetime,timedelta,date
from types import SimpleNamespace as N
from wag_quote_clock_diagnostics import WAGQuoteClockDiagnostics as D
class Quote:
 def __init__(self,end,ff=False,period=timedelta(minutes=1)):
  self.end_time=end;self.time=end-period;self.period=period;self.is_fill_forward=ff
class Hours:
 def is_date_open(self,when):return when.weekday()<5 and when.date()!=date(2019,11,28)
class Getter:
 def __init__(self,x):self.x=x
 def __getitem__(self,key):return lambda:self.x
class ClockTests(unittest.TestCase):
 def setUp(self):self.now=datetime(2019,11,29,12);self.sec=N(local_time=self.now,exchange=N(exchange_open=True,hours=Hours()));self.d=D()
 def obs(self,c,s):self.d.observe('put',self.now,self.sec,c,s,Quote,slice_has_quote=s is not None);return dict(self.d.counts)
 def test_stale_cache_real_fresh_slice(self):
  r=self.obs(Quote(self.now-timedelta(minutes=6)),Quote(self.now));self.assertEqual(r['put_stale_cache_fresh_real_slice'],1);self.assertEqual(r['put_cache_end_future'],0)
 def test_ff_slice_does_not_imply_real_cache_update(self):
  r=self.obs(Quote(datetime(2019,11,27,16)),Quote(self.now,ff=True));self.assertEqual(r['put_stale_cache_fresh_ff_slice'],1);self.assertEqual(r['put_slice_fresh_nonff'],0);self.assertEqual(r['put_cache_fill_forward'],0)
 def test_future_direction_separate(self):
  r=self.obs(Quote(self.now+timedelta(hours=5)),Quote(self.now));self.assertEqual(r['put_cache_end_future'],1);self.assertEqual(r['put_cache_end_stale_gt5m'],0);self.assertEqual(r['put_cache_endpoint_after_slice'],1)
 def test_prior_open_session_skips_thanksgiving(self):
  r=self.obs(Quote(datetime(2019,11,27,16)),None);self.assertEqual(r['put_cache_end_prior_open_session'],1);self.assertEqual(r['put_slice_present'],0)
 def test_older_than_prior_session(self):
  r=self.obs(Quote(datetime(2019,11,26,16)),None);self.assertEqual(r['put_cache_end_older_than_prior_open_session'],1)
 def test_local_clock_disagreement(self):
  self.sec.local_time=self.now+timedelta(hours=5);r=self.obs(Quote(self.now),Quote(self.now));self.assertEqual(r['put_security_local_equals_algorithm_ny'],0);self.assertEqual(r['put_cache_end_within5m_algorithm_ny'],1);self.assertEqual(r['put_cache_end_within5m'],0)
 def test_cache_equal_slice_endpoint(self):
  r=self.obs(Quote(self.now),Quote(self.now));self.assertEqual(r['put_cache_slice_equal_endpoint'],1);self.assertEqual(r['put_cache_period_minute'],1)
 def test_daily_source_period_flag(self):
  r=self.obs(Quote(self.now,period=timedelta(days=1)),Quote(self.now));self.assertEqual(r['put_cache_period_minute'],0);self.assertEqual(r['put_slice_period_minute'],1)
 def test_exchange_closed_flag(self):
  self.sec.exchange.exchange_open=False;r=self.obs(None,None);self.assertEqual(r['put_security_exchange_open'],0)
 def test_missing_cache_present_slice(self):
  r=self.obs(None,Quote(self.now));self.assertEqual(r['put_cache_present'],0);self.assertEqual(r['put_slice_present'],1)
 def test_boundary_age_5minutes_is_fresh(self):
  r=self.obs(Quote(self.now-timedelta(minutes=5)),None);self.assertEqual(r['put_cache_end_within5m'],1);self.assertEqual(r['put_cache_end_stale_gt5m'],0)
 def test_no_price_or_timestamp_rows_returned(self):
  r=self.obs(Quote(self.now),Quote(self.now));self.assertTrue(all(isinstance(v,int) for v in r.values()));self.assertNotIn('2019-',str(r));self.assertNotIn('price',str(r))
 def test_native_slice_cache_bridge_read_only(self):
  s='nativeSID';q=Quote(self.now);sec=self.sec;sec.cache=N(get_data=Getter(q));algorithm=N(time=self.now,securities={s:sec});data=N(quote_bars={s:q});self.d.observe_native('call',algorithm,data,s,Quote);self.assertEqual(self.d.runtime_counts()['call_cache_slice_equal_endpoint'],1);self.assertIs(data.quote_bars[s],q)
 def test_export_exactly12_counters_per_leg(self):
  self.obs(Quote(datetime(2019,11,27,16)),Quote(self.now,ff=True));r=self.d.runtime_counts()
  self.assertEqual(len(r),24);self.assertEqual(len([k for k in r if k.startswith('put_')]),12);self.assertEqual(r['put_slice_fresh_ff'],1);self.assertEqual(r['put_slice_fresh_nonff'],0);self.assertEqual(r['put_cache_prior_open_session_or_older'],1);self.assertTrue(all(isinstance(x,int) for x in r.values()))
 def test_probe_bounded_session_only(self):
  with self.assertRaises(ValueError):self.d.observe('put',self.now-timedelta(minutes=1),self.sec,None,None,Quote,slice_has_quote=False)
if __name__=='__main__':unittest.main()
