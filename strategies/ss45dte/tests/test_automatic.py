import importlib.util
import math
import sys
import types
import unittest
from datetime import date,timedelta,datetime
from pathlib import Path
from collections import Counter

shim=types.ModuleType('AlgorithmImports')
shim.QCAlgorithm=type('QCAlgorithm',(),{})
shim.FeeModel=type('FeeModel',(),{})
shim.OrderStatus=types.SimpleNamespace(FILLED='filled',CANCELED='cancelled',INVALID='invalid')
sys.modules['AlgorithmImports']=shim
spec=importlib.util.spec_from_file_location('ss45_under_test',Path(__file__).parents[1]/'strategy.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Rules(unittest.TestCase):
    def test_slippage_is_dollars_per_share_not_fraction_of_price(self):
        model=m.AbsoluteSlippage()
        for price in [.5,5.,50.]:
            self.assertEqual(model.get_slippage_approximation(types.SimpleNamespace(price=price),None),.01)
    def test_short_margin_is_positive_and_legs_do_not_offset(self):
        self.assertEqual(m.standalone_margin([-1200,-800]),2000)
        self.assertEqual(m.standalone_margin([-1200,800]),2000)
        for values in [[],[0],[-100,float('nan')],[-100,float('inf')]]:
            self.assertTrue(math.isinf(m.standalone_margin(values)))
    def test_review_preserves_actual_entry_basis_per_pair(self):
        a=m.Ss45Dte();a.time=datetime(2025,1,2,10);a.peak=1e6;a.min_margin=1e6;a.halt=False
        a.eq={'X':'stock'};a.assignment_names=set();a.counts=Counter()
        class Portfolio(dict):pass
        a.portfolio=Portfolio(stock=types.SimpleNamespace(invested=False))
        a.portfolio.total_portfolio_value=1e6;a.portfolio.margin_remaining=1e6;a.portfolio.total_margin_used=0
        a.states={'X':dict(status='open',legs=[{},{}],quantity=2,cashflow=400,fees=4,exit_day=date(2025,2,1),stress=0)}
        a.reconcile=lambda:None;a.report=lambda:None;a.upcoming=lambda *args:False
        a.quote=lambda r:(1.,1.1,100.)
        credits=[]
        a.pair_stress=lambda n,legs,credit:credits.append(credit) or 10
        a.review()
        # 400 collected less four dollars fees, spread over two pairs.
        # Current midpoint liquidation value is 210 per pair and must not reset basis.
        self.assertEqual(credits,[198.])
    def test_held_names_continue_daily_iv_history(self):
        a=m.Ss45Dte();a.time=datetime(2025,1,2,10);a.last_day=None;a.halt=False
        a.counts=Counter();a.states={n:{} for n in m.CONFIG['names']};a.candidates={}
        a.iv={n:{date(2024,12,31):.2} for n in m.CONFIG['names']}
        a.review=lambda:None;a.report=lambda:None;a.records=lambda n:[]
        a.seed_iv=lambda n:None;a.atm=lambda rows,today:.3
        a.prepare()
        self.assertTrue(all(a.iv[n][a.time.date()]==.3 for n in m.CONFIG['names']))
    def test_stress_model_roundtrip(self):
        for put in [True,False]:
            price=m.option_value(100,105,45/365,.35,put)
            self.assertAlmostEqual(m.implied_vol(price,100,105,45/365,put),.35,places=8)
    def test_quantity_fails_closed_and_rounds_down(self):
        for loss in [0,-1,float('nan'),float('inf')]:self.assertEqual(m.quantity_for(loss,1000,10),0)
        self.assertEqual(m.quantity_for(620,750,10),1)
        self.assertEqual(m.quantity_for(620,500,10),0)
    def test_vol_units_are_decimal(self):
        a=m.option_value(100,100,45/365,.20,False)
        b=m.option_value(100,100,45/365,.21,False)
        self.assertTrue(0<b-a<1)
    def test_exit_moves_before_halfday_and_holiday(self):
        closed={date(2026,11,26),date(2026,11,27)}
        full=lambda d:d.weekday()<5 and d not in closed
        self.assertEqual(m.target_exit(date(2026,12,18),full),date(2026,11,25))
    def test_ivr_zero_range_and_strict_boundary(self):
        self.assertIsNone(m.iv_rank([.3]*60,.3))
        self.assertAlmostEqual(m.iv_rank([.2,.4],.3),50)
    def algorithm(self,qty,status='opening',ticket='filled',stock=False):
        a=m.Ss45Dte();a.eq={'X':'stock'};a.states={'X':dict(legs=[{'symbol':'p'},{'symbol':'c'}],quantity=1,status=status,tickets=[1],cashflow=100,fees=4,reason='21dte')}
        a.transactions=types.SimpleNamespace(get_order_ticket=lambda _:types.SimpleNamespace(status=ticket))
        a.portfolio={s:types.SimpleNamespace(quantity=q,invested=bool(q)) for s,q in zip(['p','c'],qty)}
        a.portfolio['stock']=types.SimpleNamespace(invested=stock)
        a.counts=Counter();a.realized=[];a.assignment_names=set()
        return a
    def test_submission_does_not_mean_position_open(self):
        a=self.algorithm([0,0],ticket='submitted');a.reconcile()
        self.assertEqual(a.states['X']['status'],'opening')
        self.assertEqual(a.counts['opened'],0)
    def test_partial_leg_triggers_recovery(self):
        a=self.algorithm([-1,0]);actions=[];a.close=lambda n,r:actions.append((n,r));a.reconcile()
        self.assertEqual(actions,[('X','partial_or_assignment')])
    def test_close_keeps_state_until_both_legs_and_stock_flat(self):
        a=self.algorithm([0,-1],status='closing');actions=[];a.close=lambda n,r:actions.append((n,r));a.reconcile()
        self.assertIn('X',a.states);self.assertEqual(actions,[('X','21dte')])
    def test_flat_close_records_whole_episode(self):
        a=self.algorithm([0,0],status='closing');a.reconcile()
        self.assertFalse(a.states);self.assertEqual(a.realized,[96]);self.assertEqual(a.counts['closed'],1)

if __name__=='__main__':unittest.main()
