import unittest
from dataclasses import replace
from limit_margin_coordinator import MarginOwnershipCoordinator as C,NativeTicket as T,MarginRequest as R,Snapshot as S

class FakeNativeAdapter:
 """Explicit SIMULATION of native cancellation/default regeneration, not QC proof."""
 def __init__(self,ack=True,partial=0,restored=False,race=False):
  self.ack=ack;self.partial=partial;self.restored=restored;self.race=race;self.epoch=0
  self.tickets=[T(1,'p',3,0,'SUBMITTED'),T(2,'c',3,0,'SUBMITTED')]
  self.cancel_calls=[];self.default_regenerate_calls=0
 def snapshot(self):
  if self.race and self.default_regenerate_calls:self.epoch+=1
  ts=tuple(self.tickets);holdings={s:-3+sum(t.filled for t in ts if t.sid==s) for s in ['p','c']}
  return S(self.epoch,holdings,ts,frozenset(t.order_id for t in ts if t.status not in {'FILLED','CANCELED','INVALID'}),{t.order_id:t.filled for t in ts},1 if self.restored else -10)
 def cancel_native(self,i):
  self.cancel_calls.append(i)
  for n,t in enumerate(self.tickets):
   if t.order_id==i:
    q=self.partial if i==1 else t.filled
    self.tickets[n]=replace(t,filled=q,status='CANCELED' if self.ack else 'CANCEL_PENDING');self.epoch+=1
 def regenerate_default_margin_requests(self):
  self.default_regenerate_calls+=1
  # Mock default model only; native fixture must inspect real configured default model.
  return [R(s,-q,'default_regenerated_'+s) for s,q in self.snapshot().holdings.items() if q<0]

class CoordinatorTests(unittest.TestCase):
 def make(self,**kw):return C({'p':3,'c':3},[1,2]),FakeNativeAdapter(**kw),[R('p',3,'original_p'),R('c',3,'original_c')]
 def test_live_cancel_pending_preserves_original_default_requests(self):
  c,a,old=self.make(ack=False);d=c.on_native_margin(old,a)
  self.assertIs(d.returned_requests,old);self.assertFalse(d.local_barrier_passed);self.assertEqual(c.state,'INVALID_BROKER_OWNED');self.assertEqual(a.default_regenerate_calls,0)
 def test_partial_fill_before_ack_regenerates_default_residual(self):
  c,a,old=self.make(partial=1);d=c.on_native_margin(old,a)
  self.assertTrue(d.local_barrier_passed);self.assertEqual([(r.sid,r.quantity) for r in d.returned_requests],[('p',2),('c',3)]);self.assertEqual(a.default_regenerate_calls,1);self.assertEqual(old[0].quantity,3)
 def test_full_fill_wins_cancel_race_no_overbuy_request_for_leg(self):
  c,a,old=self.make(partial=3);d=c.on_native_margin(old,a)
  self.assertEqual([(r.sid,r.quantity) for r in d.returned_requests],[('c',3)])
 def test_margin_restored_returns_original_for_native_default_guard(self):
  c,a,old=self.make(partial=1,restored=True);d=c.on_native_margin(old,a)
  self.assertIs(d.returned_requests,old);self.assertTrue(d.local_barrier_passed);self.assertEqual(a.default_regenerate_calls,0)
 def test_no_voluntary_fallback_during_broker_owner(self):
  c,a,old=self.make();c.on_native_margin(old,a)
  with self.assertRaisesRegex(RuntimeError,'Broker owns'):c.authorize_voluntary_market_fallback()
 def test_no_voluntary_fallback_after_invalid_cancellation(self):
  c,a,old=self.make(ack=False);c.on_native_margin(old,a)
  with self.assertRaisesRegex(RuntimeError,'Broker owns'):c.authorize_voluntary_market_fallback()
 def test_regeneration_epoch_race_preserves_original_and_invalidates(self):
  c,a,old=self.make(partial=1,race=True);d=c.on_native_margin(old,a)
  self.assertFalse(d.local_barrier_passed);self.assertIs(d.returned_requests,old)
 def test_broker_fill_completion_requires_actual_ids_and_holdings(self):
  c,a,old=self.make(partial=1);c.on_native_margin(old,a);c.bind_actual_broker_tickets([3,4])
  a.tickets.extend([T(3,'p',2,2,'FILLED'),T(4,'c',3,3,'FILLED')]);self.assertTrue(c.after_native_broker(a.snapshot())[0].startswith('COMPLETE_ACTUAL'))
 def test_partial_native_broker_wait_no_extra_market(self):
  c,a,old=self.make(partial=1);c.on_native_margin(old,a);c.bind_actual_broker_tickets([3,4]);a.tickets.extend([T(3,'p',2,1,'PARTIALLY_FILLED'),T(4,'c',3,0,'SUBMITTED')]);self.assertEqual(c.after_native_broker(a.snapshot()),('WAIT_NATIVE_BROKER_AND_CANCEL_BARRIER',))
 def test_broker_stops_after_margin_restored_residual_requires_checks(self):
  c,a,old=self.make();c.on_native_margin(old,a);c.bind_actual_broker_tickets([3]);a.tickets.append(T(3,'p',1,1,'FILLED'));cmd=c.after_native_broker(a.snapshot());self.assertEqual(cmd,('REQUIRE_SEPARATE_NATIVE_DEFAULT_CHECKED_RESIDUAL_CLOSE',{'p':2,'c':3}))
 def test_native_event_mismatch_preserves_original_forced_behavior(self):
  c,a,old=self.make();original=a.snapshot
  a.snapshot=lambda:replace(original(),event_fill_totals={1:1,2:0})
  d=c.on_native_margin(old,a);self.assertIs(d.returned_requests,old);self.assertFalse(d.local_barrier_passed)
 def test_broker_rejection_not_hidden(self):
  c,a,old=self.make();c.on_native_margin(old,a);c.bind_actual_broker_tickets([3]);a.tickets.append(T(3,'p',3,0,'INVALID'))
  with self.assertRaisesRegex(RuntimeError,'unresolved'):c.after_native_broker(a.snapshot())
 def test_actual_overclose_detected_not_offset_with_fake_fill(self):
  c,a,old=self.make(partial=1);c.on_native_margin(old,a);c.bind_actual_broker_tickets([3]);a.tickets.append(T(3,'p',3,3,'FILLED'))
  with self.assertRaisesRegex(RuntimeError,'Actual overclose'):c.after_native_broker(a.snapshot())
 def test_no_assumed_cancel_from_response(self):
  c,a,old=self.make(ack=False,partial=1);d=c.on_native_margin(old,a);self.assertFalse(d.local_barrier_passed);self.assertEqual(a.snapshot().holdings['p'],-2)
 def test_duplicate_sid_cannot_overclose_aggregate(self):
  c,a,old=self.make(partial=1)
  a.regenerate_default_margin_requests=lambda:[R('p',2,'p1'),R('p',2,'p2')]
  d=c.on_native_margin(old,a);self.assertIs(d.returned_requests,old);self.assertFalse(d.local_barrier_passed);self.assertIn('Duplicate',d.reason)
 def test_duplicate_request_id_across_distinct_sids_rejected(self):
  c,a,old=self.make()
  a.regenerate_default_margin_requests=lambda:[R('p',3,'same'),R('c',3,'same')]
  d=c.on_native_margin(old,a);self.assertFalse(d.local_barrier_passed);self.assertIs(d.returned_requests,old)
 def test_invalidity_latched_across_repeated_margin_callback(self):
  c,a,old=self.make(ack=False);first=c.on_native_margin(old,a)
  a.ack=True;second_requests=[R('p',3,'second_p')]
  before=(len(a.cancel_calls),a.default_regenerate_calls)
  second=c.on_native_margin(second_requests,a)
  self.assertIs(second.returned_requests,second_requests);self.assertFalse(second.local_barrier_passed);self.assertEqual(second.reason,first.reason);self.assertEqual(c.state,'INVALID_BROKER_OWNED');self.assertEqual((len(a.cancel_calls),a.default_regenerate_calls),before)
 def test_invalidity_latches_after_later_default_regeneration_becomes_safe(self):
  c,a,old=self.make();a.regenerate_default_margin_requests=lambda:[R('p',3,'same'),R('c',3,'same')]
  first=c.on_native_margin(old,a);a.regenerate_default_margin_requests=lambda:[R('p',3,'newp'),R('c',3,'newc')]
  second=c.on_native_margin(old,a);self.assertFalse(second.local_barrier_passed);self.assertEqual(second.reason,first.reason)
 def test_scope_requires_exact_two_native_original_ids(self):
  with self.assertRaises(ValueError):C({'p':3},[1,2])
  with self.assertRaises(ValueError):C({'p':3,'c':3},[1,1])
if __name__=='__main__':unittest.main()
