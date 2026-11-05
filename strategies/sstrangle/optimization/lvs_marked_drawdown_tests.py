import unittest
from lvs_marked_drawdown_audit import analyze
class AccountBounds(unittest.TestCase):
 def test_unknown_high_low_order_does_not_imply_exact_drawdown(self):
  r=analyze([[0,100,120,90,110]])
  self.assertAlmostEqual(r['sampled_account_ohlc_mdd_lower_bound'],.1)
  self.assertAlmostEqual(r['sampled_account_ohlc_mdd_upper_bound'],.25)
 def test_previous_high_known_to_precede_next_low(self):
  r=analyze([[0,100,120,100,110],[1,110,110,90,100]])
  self.assertAlmostEqual(r['sampled_account_ohlc_mdd_lower_bound'],.25)
  self.assertAlmostEqual(r['sampled_account_ohlc_mdd_upper_bound'],.25)
 def test_high_before_close_is_known(self):
  r=analyze([[0,100,120,90,90]])
  self.assertAlmostEqual(r['sampled_account_ohlc_mdd_lower_bound'],.25)
 def test_recovery_does_not_erase_marked_drawdown(self):
  r=analyze([[0,100,100,100,100],[1,100,100,60,60],[2,60,101,60,101]])
  self.assertAlmostEqual(r['sampled_close_mdd'],.4)
  self.assertGreaterEqual(r['sampled_account_ohlc_mdd_lower_bound'],.4)
 def test_invalid_ohlc_rejected(self):
  with self.assertRaises(ValueError):analyze([[0,100,100,110,100]])
if __name__=='__main__':unittest.main()
