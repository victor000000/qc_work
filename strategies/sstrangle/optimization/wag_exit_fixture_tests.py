"""Source-extracted predicate checks only; no claims about native QC freshness/feed."""
import ast,unittest,sys
from pathlib import Path
from datetime import datetime,timedelta,date
from types import SimpleNamespace
P=Path(__file__).parent
frozen=P.parent/'results/strangle_basket-calmar_20261019_123602/cap20_stop1.py'
fixture=P/'wag_exit_fixture.py'
ns={'timedelta':timedelta,'QuoteBar':object}
for file,method in [(frozen,'good_quote'),(fixture,'buyback_quote')]:
 tree=ast.parse(file.read_text());node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==method)
 exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(file),'exec'),ns)
class Policy:
 good_quote=ns['good_quote'];buyback_quote=ns['buyback_quote']
 def __init__(self,buyback):self.CONFIG={'buyback':buyback}
class Getter:
 def __init__(self,v):self.v=v
 def __getitem__(self,k):return lambda:self.v

def sec(bid=0,ask=.1,age=1,ff=False,absent=False):
 now=datetime(2019,11,29,12)
 bar=None if absent else SimpleNamespace(is_fill_forward=ff,end_time=now-timedelta(minutes=age),ask=SimpleNamespace(close=ask))
 return SimpleNamespace(cache=SimpleNamespace(get_data=Getter(bar)),local_time=now,bid_price=bid,ask_price=ask)
class TestNativeAndDeadline(unittest.TestCase):
 def test_renderer_marker(self):self.assertEqual(fixture.read_text().count('    CONFIG = {}'),1)
 def test_exact_three_native_contracts(self):
  sys.path.insert(0,str(P.parent));from qc_contracts import option_identity
  tree=ast.parse(fixture.read_text());loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple) and [getattr(x,'id','') for x in n.target.elts]==['put','strike','encoded'])
  contracts=ast.literal_eval(loop.iter)
  self.assertEqual(contracts,[(True,57.5,'319LY2CLLOLC6'),(False,70,'XAHXWU0GSY86'),(False,65,'XAHXWUA227XI')])
  for put,strike,sid in contracts:
   native='WAG '+sid+'|WAG R735QTJ8XC9X';r=option_identity({'id':native})
   self.assertEqual(r['expiry'],'2019-12-20');self.assertEqual(r['strike'],strike);self.assertEqual(r['call_put'],'P' if put else 'C')
 def test_noon_deadline_source_condition(self):
  tree=ast.parse(fixture.read_text());check=next(n for n in ast.walk(tree) if isinstance(n,ast.Compare) and isinstance(n.left,ast.Attribute) and n.left.attr=='closed_at')
  code=compile(ast.Expression(check),str(fixture),'eval')
  for when,shouldfail in [(datetime(2019,11,29,12),False),(datetime(2019,11,29,12,1),True),(datetime(2019,12,2,12),True),(None,True)]:
   self.assertEqual(eval(code,{'self':SimpleNamespace(closed_at=when),'datetime':datetime}),shouldfail)
  self.assertEqual((date(2019,12,20)-date(2019,11,29)).days,21)
 def test_eligible_day_is_never_rewritten(self):
  self.assertIn("self.exit_requests.setdefault(self.key,dict(reason='TIME',day=today))",fixture.read_text())
  self.assertIn("if self.exit_requests and today>date(2019,11,29):",fixture.read_text())

class TestPredicate(unittest.TestCase):
 def test_original_rejects_zero_bid(self):self.assertFalse(Policy(False).buyback_quote(sec()))
 def test_repair_accepts_zero_bid_positiveask(self):self.assertTrue(Policy(True).buyback_quote(sec()))
 def test_positivebid_both_pass(self):
  for control in [False,True]:self.assertTrue(Policy(control).buyback_quote(sec(.05,.1)))
 def test_stale_not_relaxed(self):self.assertFalse(Policy(True).buyback_quote(sec(age=6)))
 def test_future_not_relaxed(self):self.assertFalse(Policy(True).buyback_quote(sec(age=-1)))
 def test_fillforward_not_relaxed(self):self.assertFalse(Policy(True).buyback_quote(sec(ff=True)))
 def test_absence_not_relaxed(self):self.assertFalse(Policy(True).buyback_quote(sec(absent=True)))
 def test_missing_ask_side_cannot_use_cached_security_ask(self):
  s=sec();s.cache.get_data.v.ask=None
  self.assertFalse(Policy(True).buyback_quote(s))
 def test_cached_ask_differing_from_current_bar_is_rejected(self):
  s=sec();s.cache.get_data.v.ask.close=.2
  self.assertFalse(Policy(True).buyback_quote(s))
 def test_askzero_negativebid_crossed_rejected(self):
  for bid,ask in [(0,0),(-.1,.1),(.2,.1)]:self.assertFalse(Policy(True).buyback_quote(sec(bid,ask)))
if __name__=='__main__':unittest.main()
