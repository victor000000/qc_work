import unittest
from limit_exit_prototype import LimitExitLifecycle as S,Ticket as T,quote_limit

class LifecycleTests(unittest.TestCase):
 def setup_state(self,q=3):
  s=S(('P nativeSID','C nativeSID'),q,'STOP',0);s.bind_limit([T(1,s.symbols[0],q,0,'SUBMITTED'),T(2,s.symbols[1],q,0,'SUBMITTED')]);return s
 def tickets(self,a=0,b=0,status='SUBMITTED',q=3):return [T(1,'P nativeSID',q,a,status),T(2,'C nativeSID',q,b,status)]
 def advance(self,s,now,ts,**kw):
  hs={sym:-s.quantity+sum(t.filled for t in ts if t.symbol==sym) for sym in s.symbols}
  return s.advance(now,ts,hs,native_open_ids=[t.order_id for t in ts if t.status not in {'FILLED','CANCELED','INVALID'}],**kw)
 def test_duplicate_complete_no_double_accounting(self):
  s=self.setup_state();self.advance(s,2,self.tickets(3,3,'FILLED'));self.assertEqual(self.advance(s,3,self.tickets(3,3,'FILLED')),[])
 def test_clock_regression(self):
  s=self.setup_state();self.advance(s,2,self.tickets())
  with self.assertRaisesRegex(RuntimeError,'Nonmonotonic'):self.advance(s,1,self.tickets())
 def test_no_assumed_mid_fills(self):
  s=self.setup_state();self.assertEqual(self.advance(s,1,self.tickets()),[]);self.assertEqual(s.state,'LIMIT')
 def test_real_fill_completes(self):
  s=self.setup_state();self.assertEqual(self.advance(s,2,self.tickets(3,3,'FILLED')),[('COMPLETE_ACTUAL_FILL_AUDIT',)])
 def test_cancel_request_not_ack(self):
  s=self.setup_state();self.assertEqual(self.advance(s,60,self.tickets()),[('CANCEL_NATIVE_TICKETS',(1,2))]);self.assertEqual(self.advance(s,61,self.tickets(status='CANCEL_PENDING')),[])
 def test_zero_fill_cancel_then_fallback(self):
  s=self.setup_state();self.advance(s,60,self.tickets());cmd=self.advance(s,61,self.tickets(status='CANCELED'));self.assertEqual(cmd[0][1],dict(zip(s.symbols,[3,3])))
 def test_fill_wins_cancel_race(self):
  s=self.setup_state();self.advance(s,60,self.tickets());self.assertEqual(self.advance(s,61,self.tickets(3,3,'FILLED')),[('COMPLETE_ACTUAL_FILL_AUDIT',)])
 def test_asymmetric_partial_true_residual(self):
  s=self.setup_state();self.advance(s,60,self.tickets());ts=self.tickets(1,0,'CANCELED');cmd=self.advance(s,61,ts);self.assertEqual(cmd[0][1],dict(zip(s.symbols,[2,3])));s.bind_market([T(3,s.symbols[0],2,0,'SUBMITTED'),T(4,s.symbols[1],3,0,'SUBMITTED')]);self.assertEqual(self.advance(s,62,ts+[T(3,s.symbols[0],2,2,'FILLED'),T(4,s.symbols[1],3,3,'FILLED')]),[('COMPLETE_ACTUAL_FILL_AUDIT',)])
 def test_cancel_timeout_no_market(self):
  s=self.setup_state();self.advance(s,60,self.tickets())
  with self.assertRaisesRegex(RuntimeError,'Cancel not definitive'):self.advance(s,120,self.tickets(status='CANCEL_PENDING'))
 def test_native_ids_not_aliases(self):
  s=self.setup_state();ts=self.tickets();ts[1]=T(2,'wrong mapped symbol',3,0,'SUBMITTED')
  with self.assertRaisesRegex(RuntimeError,'identity'):self.advance(s,1,ts)
 def test_broker_interference_detected(self):
  s=self.setup_state()
  with self.assertRaisesRegex(RuntimeError,'Portfolio differs'):s.advance(1,self.tickets(),dict(zip(s.symbols,[0,-3])),native_open_ids=[1,2])
 def test_terminal_change_rejected(self):
  s=self.setup_state();self.advance(s,60,self.tickets());ts=self.tickets(status='CANCELED');self.advance(s,61,ts);s.bind_market([T(3,s.symbols[0],3,0,'SUBMITTED'),T(4,s.symbols[1],3,0,'SUBMITTED')]);ts[0]=T(1,s.symbols[0],3,1,'CANCELED')
  with self.assertRaisesRegex(RuntimeError,'race'):self.advance(s,62,ts+list(s.orders.values())[2:])
 def test_emergency_cancels_immediately(self):
  s=self.setup_state();self.assertEqual(self.advance(s,1,self.tickets(),urgent_reason='MARGIN'),[('CANCEL_NATIVE_TICKETS',(1,2))])
 def test_wrong_fallback_overclose_blocked(self):
  s=self.setup_state();self.advance(s,60,self.tickets());self.advance(s,61,self.tickets(status='CANCELED'))
  with self.assertRaisesRegex(RuntimeError,'residual'):s.bind_market([T(3,s.symbols[0],4,0,'SUBMITTED'),T(4,s.symbols[1],3,0,'SUBMITTED')])
 def test_scope(self):
  for reason,future,dte in [('TIME',False,30),('STOP',True,30),('PROFIT',False,21)]:
   with self.assertRaises(ValueError):S(('p','c'),3,reason,0,future=future,dte=dte)
 def test_quote_limit_no_fill_assumption(self):
  self.assertEqual(str(quote_limit(.5,4.8,.05)),'3.70')
  with self.assertRaises(ValueError):quote_limit(0,4.8,.05)
 def test_fallback_rejected_retains_exposure(self):
  s=self.setup_state();self.advance(s,60,self.tickets());ts=self.tickets(status='CANCELED');self.advance(s,61,ts);s.bind_market([T(3,s.symbols[0],3,0,'INVALID'),T(4,s.symbols[1],3,0,'SUBMITTED')])
  with self.assertRaisesRegex(RuntimeError,'unresolved'):self.advance(s,62,ts+[T(3,s.symbols[0],3,0,'INVALID'),T(4,s.symbols[1],3,0,'SUBMITTED')])

if __name__=='__main__':unittest.main()
