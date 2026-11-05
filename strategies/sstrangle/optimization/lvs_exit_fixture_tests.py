"""Local mocked command-path checks; native QC fill/cancel behavior remains unproved."""
import ast,sys,unittest
from pathlib import Path
from datetime import date,datetime,timedelta,time
from decimal import Decimal,ROUND_CEILING
from types import SimpleNamespace as N
P=Path(__file__).parent
source=P/'lvs_exit_fixture.py';tree=ast.parse(source.read_text())
class Status:
 FILLED='filled';CANCELED='canceled';INVALID='invalid';SUBMITTED='submitted'
ns={'Decimal':Decimal,'ROUND_CEILING':ROUND_CEILING,'OrderStatus':Status,'date':date,'datetime':datetime,'timedelta':timedelta,'time':time,'Leg':N(create=lambda s,q:(s,q))}
for name in ['declared_buy_limit','all_terminal','phase_complete','on_margin_call','on_data','reconcile','receipt']:
 node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
 exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),ns)
class Sym(str):
 @property
 def id(self):return str(self)
class Fake:
 all_terminal=ns['all_terminal'];phase_complete=ns['phase_complete'];on_data=ns['on_data'];on_margin_call=ns['on_margin_call']
 def __init__(self):
  self.time=datetime(2015,8,19,9,33);self.pending_bind=False;self.failure_note=None;self.done=False
  self.state='CANCELING';self.cancel_started=self.time;self.forced=False
  self.contracts={'put':Sym('p'),'call':Sym('c')};self.portfolio={'p':N(quantity=-1),'c':N(quantity=-2)}
  self.limit_tickets=[N(order_id=1,status=Status.CANCELED),N(order_id=2,status=Status.CANCELED)]
  self.transactions=N(get_open_orders=lambda:[]);self.orders=[];self.CONFIG={'limit_exit':True};self.intended_fallback={}
  self.reconcile=lambda:None;self.finish_actual=lambda:setattr(self,'done',True)
 def market_order(self,s,q,**kwargs):
  self.orders.append((s,q));return N(order_id=len(self.orders)+2,status=Status.SUBMITTED,quantity=q,quantity_filled=0)
 def bind(self,ts,phase):self.phase_tickets=ts
class TestFixture(unittest.TestCase):
 def test_renderer_marker(self):self.assertEqual(source.read_text().count('    CONFIG = {}'),1)
 def test_exact_native_sid_and_expiry(self):
  sys.path.insert(0,str(P.parent));from qc_contracts import option_identity
  loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple) and [getattr(x,'id','') for x in n.target.elts]==['put','strike','encoded'])
  values=ast.literal_eval(loop.iter);self.assertEqual(values,[(True,47.5,'3033TD1OREOZQ'),(False,60.,'W3ZT7JJZY6RQ')])
  for put,strike,sid in values:
   r=option_identity({'id':'LVS '+sid+'|LVS T4J5S7AT6WRP'});self.assertEqual(r['strike'],strike);self.assertEqual(r['expiry'],'2015-09-18');self.assertEqual(r['call_put'],'P' if put else 'C')
 def test_one_declared_limit_policy(self):
  f=ns['declared_buy_limit'];self.assertAlmostEqual(f(.61,.01),.63);self.assertAlmostEqual(f(.06,.01),.08);self.assertAlmostEqual(f(.61,.05),.75)
  for b,t in [(0,.01),(.1,0),(-1,.01),(float('nan'),.01)]:
   with self.assertRaises(ValueError):f(b,t)
 def test_actual_partial_residual_only(self):
  f=Fake();f.on_data(None);self.assertEqual(f.orders,[('p',1),('c',2)]);self.assertEqual(f.intended_fallback,{'p':1.,'c':2.})
 def test_pending_cancel_no_fallback(self):
  f=Fake();f.limit_tickets[0].status=Status.SUBMITTED;f.on_data(None);self.assertEqual(f.orders,[])
 def test_cancel_timeout_no_fallback(self):
  f=Fake();f.cancel_started=f.time-timedelta(minutes=2);f.limit_tickets[0].status=Status.SUBMITTED
  with self.assertRaisesRegex(RuntimeError,'Cancellation not definitive'):f.on_data(None)
  self.assertEqual(f.orders,[])
 def test_fill_wins_cancellation(self):
  f=Fake();f.portfolio={s:N(quantity=0) for s in ['p','c']};f.limit_tickets[0].status=Status.FILLED;f.limit_tickets[1].status=Status.FILLED;f.on_data(None);self.assertTrue(f.done);self.assertEqual(f.orders,[])
 def test_terminal_but_native_open_blocks(self):
  f=Fake();f.transactions=N(get_open_orders=lambda:[N(id=1)])
  with self.assertRaisesRegex(RuntimeError,'open native'):f.on_data(None)
  self.assertEqual(f.orders,[])
 def test_overclose_rejected(self):
  f=Fake();f.portfolio['p'].quantity=1
  with self.assertRaisesRegex(RuntimeError,'overclose'):f.on_data(None)
 def test_default_margin_requests_preserved(self):
  f=Fake();requests=[object(),object()];self.assertIs(f.on_margin_call(requests),requests);self.assertTrue(f.forced);self.assertIsNotNone(f.failure_note)
 def test_native_market_fallback_rejection_retained(self):
  f=Fake();f.state='RESIDUAL_MARKET';f.phase_tickets=[N(status=Status.INVALID)]
  with self.assertRaisesRegex(RuntimeError,'real exposure remains'):f.on_data(None)
 def ledger_host(self):
  class Portfolio(dict):total_portfolio_value=57000
  h=N(pending_bind=False,subscribed=True,contracts={'put':Sym('p'),'call':Sym('c')},tickets={},events={},securities={},portfolio=Portfolio(),CONFIG={'limit_exit':True},initial_cash=57718.42,open_ids=[1,2],close_ids=[3,4],cancel_requested={3,4},intended_fallback={},triggered_at=datetime(2015,8,19,9,31),forced=False,done=False)
  specifications=[(1,Sym('p'),-2,.61,1.3),(2,Sym('c'),-2,.62,1.3),(3,Sym('p'),1,.63,.65),(4,Sym('c'),0,0,0)]
  for i,symbol,q,price,fee in specifications:
   h.tickets[i]=N(symbol=symbol,quantity_filled=q,status=Status.CANCELED if i>2 else Status.FILLED)
   h.events[(i,1)]={'order_id':i,'event_id':1,'native_sid':str(symbol),'quantity':q,'price':price,'fee':fee,'status':'actual_test_event','utc':'test'}
   h.securities[symbol]=N(symbol_properties=N(contract_multiplier=100))
  h.portfolio['p']=N(quantity=-1);h.portfolio['c']=N(quantity=-2)
  return h
 def test_partial_cancel_fills_fees_not_dropped(self):
  h=self.ledger_host();ns['reconcile'](h);r=ns['receipt'](h,'localtest')
  self.assertAlmostEqual(r['actual_cashflow'],183);self.assertAlmostEqual(r['actual_fees'],3.25);self.assertEqual(len(r['actual_fill_events']),3);self.assertEqual(r['native_order_ids'],[1,2,3,4]);self.assertEqual(r['residual_native'],{'p':-1.,'c':-2.})
 def test_ticket_event_mismatch_blocks_fallback(self):
  h=self.ledger_host();h.tickets[3].quantity_filled=2
  with self.assertRaisesRegex(RuntimeError,'event/ticket'):ns['reconcile'](h)
 def test_unexpected_broker_fill_retained_failure(self):
  h=self.ledger_host();h.events[(99,1)]={'order_id':99,'quantity':1}
  with self.assertRaisesRegex(RuntimeError,'Unexpected broker native execution'):ns['reconcile'](h)
 def test_before_scheduled_subscription_does_not_index_absent_security(self):
  h=N(pending_bind=False,subscribed=False,tickets={},events={},portfolio=N(invested=False))
  ns['reconcile'](h)
 def test_pre_subscription_exposure_is_not_silently_skipped(self):
  h=N(pending_bind=False,subscribed=False,tickets={},events={},portfolio=N(invested=True))
  with self.assertRaisesRegex(RuntimeError,'before native contract'):ns['reconcile'](h)
 def test_missing_subscriptions_are_explicit_in_receipt_not_invented_flat(self):
  h=self.ledger_host();h.tickets={};h.events={};h.securities={}
  r=ns['receipt'](h,'pre-subscription')
  self.assertEqual(r['residual_native'],{});self.assertEqual(r['unsubscribed_native'],['p','c'])
 def test_no_midpoint_price_or_fill_model_override(self):
  text=source.read_text();self.assertNotIn('set_fill_model(',text);self.assertNotIn('set_buying_power_model(',text);self.assertIn('timedelta(minutes=2)',text);self.assertIn('initial_cash=57718.42',text)
if __name__=='__main__':unittest.main()
