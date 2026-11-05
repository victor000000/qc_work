import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from local_screen import DEFAULT,load_cycles,size,configs

class LocalScreenChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cycles=load_cycles(DEFAULT)
    def test_gate_does_not_read_postentry_outcomes(self):
        cfg=next(configs())
        for c in self.cycles:
            altered=copy.deepcopy(c)
            altered.update(exit='2099-01-01',exit_reason='UNKNOWN',baseline_pnl=1e100)
            self.assertEqual(size(c,cfg),size(altered,cfg))
    def test_no_original_quantity_increase_and_budget_compliance(self):
        for cfg in configs():
            batches={}
            for c in self.cycles:
                q=size(c,cfg)
                self.assertGreaterEqual(q,0);self.assertLessEqual(q,c['baseline_quantity'])
                cost=q*(c['initial_margin_per_lot']+c['entry_fees_per_lot'])
                self.assertLessEqual(cost,60000*cfg['per_symbol_fraction']+1e-6)
                batches[c['batch_id']]=batches.get(c['batch_id'],0)+cost
            self.assertTrue(all(v<=60000*cfg['total_fraction']+1e-6 for v in batches.values()))
    def test_true_strict_ivr_threshold(self):
        c=copy.deepcopy(self.cycles[0]);cfg=next(configs());c['ivr']=cfg['min_ivr']
        self.assertEqual(size(c,cfg),0)
    def test_all_attempts_retained_and_no_calmar(self):
        summary=json.loads(Path(__file__).with_name('local_results_20261019').joinpath('summary.json').read_text())
        self.assertEqual(summary['attempts'],len(list(configs())))
        self.assertIsNone(summary['valid_calmar']);self.assertFalse(summary['selection_uses_evaluation'])

if __name__=='__main__':unittest.main()
