import unittest
from datetime import date,datetime,timezone
from account_drawdown import chart_drawdown,include_chart_drawdown
BEGIN=date(2020,1,2);END=date(2020,1,3)
T=int(datetime(2020,1,2,17,tzinfo=timezone.utc).timestamp())
def chart(values):return {'chart':{'series':{'Equity':{'values':values}}}}
class Drawdown(unittest.TestCase):
 def test_recovered_intraday_low_not_erased_by_daily_close(self):
  a=chart_drawdown(chart([[T,100],[T+60,50],[T+120,100]]),100,BEGIN,END)
  self.assertEqual(a['sampled_mdd_lower_bound'],.5)
 def test_unknown_high_low_order_keeps_bounds(self):
  a=chart_drawdown(chart([[T,100,120,90,110]]),100,BEGIN,END)
  self.assertAlmostEqual(a['sampled_mdd_lower_bound'],.1);self.assertAlmostEqual(a['sampled_mdd_upper_bound'],.25)
 def test_previous_high_precedes_later_low(self):
  a=chart_drawdown(chart([[T,100,120,100,110],[T+60,110,110,60,100]]),100,BEGIN,END)
  self.assertEqual(a['sampled_mdd_lower_bound'],.5)
 def test_marks_outside_requested_window_excluded(self):
  a=chart_drawdown(chart([[T-86400,1],[T,100]]),100,BEGIN,END)
  self.assertEqual(a['sampled_mdd_lower_bound'],0)
 def test_scalar_and_nested_dictionary_points(self):
  a=chart_drawdown(chart([{'x':T,'y':100},{'x':T+60,'y':{'open':100,'high':100,'low':80,'close':100}}]),100,BEGIN,END)
  self.assertAlmostEqual(a['sampled_mdd_lower_bound'],.2)
 def test_intraday_insolvency_cannot_qualify_after_recovery(self):
  a=chart_drawdown(chart([[T,100],[T+60,-1],[T+120,110]]),100,BEGIN,END)
  m={'denominator_mdd':.1,'cagr':.3,'positive_equity':True,'available':True}
  include_chart_drawdown(m,[a]);self.assertIsNone(m['calmar']);self.assertFalse(m['positive_equity'])
 def test_conservative_reported_drawdown_retained(self):
  a=chart_drawdown(chart([[T,100],[T+60,90]]),100,BEGIN,END)
  m={'denominator_mdd':.3,'cagr':.6};include_chart_drawdown(m,[a]);self.assertEqual(m['calmar'],2)
 def test_unknown_order_cannot_inflate_positive_calmar(self):
  a=chart_drawdown(chart([[T,100,120,90,110]]),100,BEGIN,END)
  m={'denominator_mdd':.1,'cagr':.3};include_chart_drawdown(m,[a])
  self.assertAlmostEqual(m['observed_account_chart_mdd_lower_bound'],.1)
  self.assertAlmostEqual(m['observed_account_chart_mdd_upper_bound'],.25)
  self.assertAlmostEqual(m['denominator_mdd'],.25)
  self.assertAlmostEqual(m['calmar'],1.2)
 def test_scalar_chart_has_no_ordering_penalty(self):
  a=chart_drawdown(chart([[T,100],[T+60,80],[T+120,110]]),100,BEGIN,END)
  m={'denominator_mdd':.1,'cagr':.3};include_chart_drawdown(m,[a])
  self.assertEqual(m['observed_account_chart_mdd_lower_bound'],m['observed_account_chart_mdd_upper_bound'])
  self.assertAlmostEqual(m['calmar'],1.5)
 def test_invalid_ohlc_fails(self):
  with self.assertRaises(ValueError):chart_drawdown(chart([[T,100,100,110,100]]),100,BEGIN,END)
if __name__=='__main__':unittest.main()
