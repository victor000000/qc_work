import ast
from pathlib import Path
from types import SimpleNamespace as N
import random
from local_engine import Leg,select

def test_independent_selection_matches_frozen_qc_helper():
 tree=ast.parse((Path(__file__).parent/'strategy.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='choose_exact_pairs');env={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'qc_helper','exec'),env)
 random.seed(871)
 compared=0
 for _ in range(500):
  contracts=[]
  for right,ks in [('P',range(4900,5000,5)),('C',range(5005,5105,5))]:
   for k in ks:
    if random.random()<.1:continue
    d=random.uniform(-.35,-.01) if right=='P' else random.uniform(.01,.29)
    contracts.append(Leg(str(k)+right,k,right,d,1,1.2,5000))
  mock=[N(strike=x.strike,right=x.right,greeks=N(delta=x.delta)) for x in contracts]
  result=env['choose_exact_pairs']([x for x in mock if x.right=='P'],[x for x in mock if x.right=='C'],{(x.right,x.strike):x for x in mock},'P','C',.2,.08)
  independent,_=select(contracts,'condor')
  if result is None:assert independent is None;continue
  p,c,lp,lc=result
  if abs(p.greeks.delta+.2)>.02+1e-12 or abs(c.greeks.delta-.08)>.02+1e-12:assert independent is None;continue
  assert [(x.right,x.strike,q) for x,q in independent]==[('P',lp.strike,1),('P',p.strike,-1),('C',c.strike,-1),('C',lc.strike,1)]
  compared+=1
 assert compared>10
