import copy,unittest
from volatility_source_report import audit

def example():
 rt={'Equity':'$60,000.00','Fees':'$0.00','Holdings':'$0.00','Unrealized':'$0.00','vol_requests':'2','vol_aligned_windows':'2','vol_numpy_matches':'2','vol_sampled_closes':'122','vol_equity_windows':'2','vol_split_basis_verified':'1','vol_actual_split_events':'1','vol_feature_fingerprint':'a'*64,'vol_no_trades':'1','vol_synthetic_iv_input':'1.0; arithmetic only, not a source IV'}
 return {'runtimeStatistics':rt},{'chart':{'series':{'Equity':{'values':[[1596456000,60000]]}}}}
class NativeSourceAudit(unittest.TestCase):
 def test_complete_positive_evidence_is_engineering_only(self):
  f,c=example();r=audit(f,[],[],c,'equity');self.assertTrue(r['engineering_verified']);self.assertFalse(r['strategy_performance_claim']);self.assertFalse(r['market_iv_gate_validated'])
 def test_missing_native_comparisons_fail(self):
  f,c=example();f['runtimeStatistics']['vol_numpy_matches']='1'
  with self.assertRaises(ValueError):audit(f,[],[],c,'equity')
 def test_changed_cash_or_fee_or_actual_order_is_rejected(self):
  for key,value in [('Equity','$60,001'),('Fees','-$1'),('Holdings','$1')]:
   f,c=example();f['runtimeStatistics'][key]=value
   with self.assertRaises(ValueError):audit(f,[],[],c,'equity')
  f,c=example()
  with self.assertRaises(ValueError):audit(f,[{'id':1}],[],c,'equity')
 def test_fingerprint_and_synthetic_iv_disclosure_required(self):
  for k,v in [('vol_feature_fingerprint','bad'),('vol_synthetic_iv_input','market IV')]:
   f,c=example();f['runtimeStatistics'][k]=v
   with self.assertRaises(ValueError):audit(f,[],[],c,'equity')
 def test_account_curve_change_cannot_be_hidden_by_terminal_cash(self):
  f,c=example();c['chart']['series']['Equity']['values'].append([1596542400,59000])
  with self.assertRaises(ValueError):audit(f,[],[],c,'equity')
 def test_missing_split_or_delivery_controls_fail(self):
  f,c=example();f['runtimeStatistics']['vol_actual_split_events']='0'
  with self.assertRaises(ValueError):audit(f,[],[],c,'equity')
  f,c=example();f['runtimeStatistics'].update(vol_futures_windows='2',vol_native_delivery_resets='0')
  with self.assertRaises(ValueError):audit(f,[],[],c,'futures')
 def test_normal_log_checksum_is_collected_without_runtime_hash(self):
  f,c=example();f['runtimeStatistics'].pop('vol_feature_fingerprint')
  r=audit(f,[],[],c,'equity',log='2020-09-04 VOLATILITY_SOURCE_CHECKSUM '+'b'*64)
  self.assertTrue(r['engineering_verified']);self.assertEqual(r['feature_fingerprint'],'b'*64)
  with self.assertRaises(ValueError):audit(f,[],[],c,'equity')
 def test_duplicate_or_conflicting_native_checksums_rejected(self):
  f,c=example()
  with self.assertRaises(ValueError):audit(f,[],[],c,'equity',log='VOLATILITY_SOURCE_CHECKSUM '+'b'*64)
  f['runtimeStatistics'].pop('vol_feature_fingerprint')
  line='VOLATILITY_SOURCE_CHECKSUM '+'b'*64
  with self.assertRaises(ValueError):audit(f,[],[],c,'equity',log=line+'\n'+line)
if __name__=='__main__':unittest.main()
