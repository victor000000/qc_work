import math,unittest
from dataclasses import replace
from datetime import date,datetime,timedelta,timezone
from statistics import stdev
from completed_volatility import CompletedPrice,CompletedVolatilityWindow
EXPECTED=date(2020,1,1)+timedelta(days=60)
ASOF=datetime(2020,6,1,16,tzinfo=timezone.utc);SESSION=date(2020,6,1)
def points(prices,identity='A native',epoch='scale1'):
 start=date(2020,1,1)
 return [CompletedPrice(identity,start+timedelta(days=i),datetime(2020,1,1,21,tzinfo=timezone.utc)+timedelta(days=i),float(p),epoch) for i,p in enumerate(prices)]
def window(prices):
 w=CompletedVolatilityWindow();w.replace_rebased_history(points(prices),ASOF,SESSION,consecutive=True);return w
class CompletedRisk(unittest.TestCase):
 def test_exact_completed_log_return_sample_volatility(self):
  rs=[.01 if i%2 else -.005 for i in range(60)];prices=[100.]
  for r in rs:prices.append(prices[-1]*math.exp(r))
  f=window(prices).features(.4,expected_last_session=EXPECTED)
  self.assertTrue(f.ready);self.assertAlmostEqual(f.realized20,stdev(rs[-20:])*252**.5);self.assertAlmostEqual(f.realized60,stdev(rs)*252**.5)
  self.assertAlmostEqual(f.iv_to_max_realized,.4/max(f.realized20,f.realized60))
 def test_constant_rebasing_cannot_change_returns(self):
  ps=[100+i+(-1)**i for i in range(61)]
  a=window(ps).features(.3,expected_last_session=EXPECTED);b=window([p*.2 for p in ps]).features(.3,expected_last_session=EXPECTED)
  self.assertAlmostEqual(a.realized60,b.realized60)
 def test_today_or_future_price_is_rejected(self):
  p=replace(points([100])[0],session=SESSION)
  with self.assertRaisesRegex(ValueError,'completed'):CompletedVolatilityWindow().observe(p,ASOF,SESSION,consecutive=True)
  p=replace(points([100])[0],end_time=ASOF+timedelta(seconds=1))
  with self.assertRaises(ValueError):CompletedVolatilityWindow().observe(p,ASOF,SESSION,consecutive=True)
 def test_missing_session_breaks_path(self):
  w=window(range(100,161));p=points([161])[0];p=replace(p,session=date(2020,4,1),end_time=datetime(2020,4,1,21,tzinfo=timezone.utc))
  w.observe(p,ASOF,SESSION,consecutive=False);self.assertFalse(w.features(.3,expected_last_session=EXPECTED).ready);self.assertEqual(len(w.points),1)
 def test_futures_delivery_change_does_not_become_price_return(self):
  w=window(range(100,161));p=replace(points([400],identity='B delivery')[0],session=date(2020,4,1))
  w.observe(p,ASOF,SESSION,consecutive=True);self.assertEqual(len(w.points),1);self.assertFalse(w.features(.3,expected_last_session=EXPECTED).ready)
 def test_corporate_scale_change_demands_new_basis(self):
  w=window(range(100,161));p=replace(points([80],epoch='scale2')[0],session=date(2020,4,1))
  w.observe(p,ASOF,SESSION,consecutive=True);self.assertTrue(w.rebase_required);self.assertFalse(w.features(.3,expected_last_session=EXPECTED).ready)
  seed=[replace(p,session=p.session+timedelta(days=31),end_time=p.end_time+timedelta(days=31)) for p in points([.5*p for p in range(100,161)],epoch='scale2')];w.replace_rebased_history(seed,ASOF,SESSION,consecutive=True);self.assertTrue(w.features(.3,expected_last_session=date(2020,4,1)).ready)
 def test_mixed_history_rejected_atomically(self):
  w=window(range(100,161));old=list(w.points);seed=points(range(100,161));seed[-1]=replace(seed[-1],normalization_epoch='wrong')
  with self.assertRaises(ValueError):w.replace_rebased_history(seed,ASOF,SESSION,consecutive=True)
  self.assertEqual(list(w.points),old)
 def test_duplicate_conflict_is_not_second_sample(self):
  w=CompletedVolatilityWindow();p=points([100])[0];w.observe(p,ASOF,SESSION,consecutive=True)
  self.assertFalse(w.observe(p,ASOF,SESSION,consecutive=True));self.assertEqual(len(w.points),1)
  with self.assertRaises(ValueError):w.observe(replace(p,price=101),ASOF,SESSION,consecutive=True)
 def test_short_or_zero_volatility_window_is_not_infinite_premium(self):
  self.assertFalse(window(range(100,160)).features(.3,expected_last_session=EXPECTED).ready)
  f=window([100]*61).features(.3,expected_last_session=EXPECTED);self.assertFalse(f.ready);self.assertIsNone(f.iv_to_max_realized)
 def test_nonfinite_or_nonpositive_inputs_rejected(self):
  for x in [float('nan'),float('inf'),0,-1]:
   with self.assertRaises(ValueError):window([100]*60+[x])
   self.assertFalse(window(range(100,161)).features(x,expected_last_session=EXPECTED).ready)
 def test_naive_clock_rejected(self):
  with self.assertRaises(ValueError):CompletedVolatilityWindow().observe(points([100])[0],ASOF.replace(tzinfo=None),SESSION,consecutive=True)
 def test_seed_cannot_change_current_instrument(self):
  w=window(range(100,161))
  with self.assertRaises(ValueError):w.replace_rebased_history(points(range(100,161),identity='B'),ASOF,SESSION,consecutive=True)
 def test_stale_complete_window_cannot_qualify(self):
  f=window(range(100,161)).features(.3,expected_last_session=date(2020,4,1))
  self.assertFalse(f.ready);self.assertEqual(f.reason,'missing_last_completed_session')
 def test_old_rebase_cannot_erase_newly_observed_session(self):
  w=window(range(100,161));p=replace(points([80],epoch='scale2')[0],session=date(2020,4,1))
  w.observe(p,ASOF,SESSION,consecutive=True)
  with self.assertRaises(ValueError):w.replace_rebased_history(points(range(100,161),epoch='scale2'),ASOF,SESSION,consecutive=True)
 def test_continuity_must_be_boolean_not_truthy_string(self):
  with self.assertRaises(ValueError):CompletedVolatilityWindow().observe(points([100])[0],ASOF,SESSION,consecutive='False')
 def test_old_epoch_observation_cannot_clear_valid_window(self):
  w=window(range(100,161));old=list(w.points)
  with self.assertRaises(ValueError):w.observe(points([90],epoch='older_basis')[0],ASOF,SESSION,consecutive=True)
  self.assertEqual(list(w.points),old)
if __name__=='__main__':unittest.main()
