from local_engine import Leg,select,account,feature
import pytest

def leg(k,r,d,b=2,a=2.2):return Leg(f'{r}{k}',k,r,d,b,a,5000)
def test_spread_payoff_boundaries():
 legs=[(leg(4960,'P',-.1,.9,1.1),1),(leg(4980,'P',-.2,2,2.2),-1)]
 a=account(legs,5000);b=account(legs,4900)
 assert a['pnl']==pytest.approx(102.64)
 assert b['pnl']==pytest.approx(-1897.36)
 assert a['max_loss']==pytest.approx(-b['pnl'])
 assert account(legs,4980)['pnl']==pytest.approx(a['pnl'])
 assert account(legs,4970)['pnl']==pytest.approx(a['pnl']-1000)
def test_two_leg_slippage():
 legs=[(leg(4960,'P',-.1,.9,1.1),1),(leg(4980,'P',-.2,2,2.2),-1)]
 assert account(legs,5000,'conservative')['credit']==pytest.approx(.8)
 assert account(legs,5000,'conservative')['fees']==pytest.approx(2.36)
def test_exact_wing_recovery_and_tie():
 cs=[leg(4980,'P',-.20),leg(4975,'P',-.21),leg(4955,'P',-.08),leg(4970,'P',-.21),leg(4950,'P',-.07)]
 out,why=select(cs,'put_spread');assert why=='selected';assert out[-1][0].strike==4970
 assert select([leg(4980,'P',-.20)],'put_spread')[0] is None

def test_condor_geometry_and_account():
 cs=[leg(4980,'P',-.2),leg(4960,'P',-.1,.4,.6),leg(5020,'C',.08),leg(5040,'C',.03,.4,.6)]
 out,_=select(cs,'condor');assert len(out)==4
 a=account(out,5000);assert a['fees']==pytest.approx(4.72)
 assert account(out,4900)['pnl']==pytest.approx(-a['max_loss'])
 assert account(out,5100)['pnl']==pytest.approx(-a['max_loss'])
def test_quote_and_delta_gates():
 assert select([leg(4980,'P',-.2,3,2),leg(4960,'P',-.1)],'put_spread')[0] is None
 assert select([leg(4980,'P',-.25),leg(4960,'P',-.1)],'put_spread')[0] is None

def test_prior_feature_no_lookahead():
 rows=[['2026-01-02',101,99,100],['2026-01-05',200,1,100]]
 assert feature(rows,'2026-01-05')==.02
 assert feature(rows,'2026-01-02') is None
 assert feature(rows,'2026-01-14') is None

def test_exhaustive_pair_oracle():
 import random
 random.seed(8701)
 for _ in range(200):
  contracts=[]
  for right,ks in [('P',range(4900,5000,5)),('C',range(5005,5105,5))]:
   for k in ks:
    if random.random()<.15:continue
    d=random.uniform(-.35,-.01) if right=='P' else random.uniform(.01,.29)
    contracts.append(leg(k,right,d))
  actual,_=select(contracts,'condor')
  pairs={right:[] for right in ['P','C']}
  for short in contracts:
   target=short.strike+(-20 if short.right=='P' else 20)
   wings=[x for x in contracts if x.right==short.right and x.strike==target]
   if wings:pairs[short.right].append((short,wings[0]))
  if not all(pairs.values()):assert actual is None;continue
  pp=sorted(pairs['P'],key=lambda z:(abs(z[0].delta+.2),z[0].strike))[0]
  cc=sorted(pairs['C'],key=lambda z:(abs(z[0].delta-.08),z[0].strike))[0]
  valid=abs(pp[0].delta+.2)<=.02+1e-12 and abs(cc[0].delta-.08)<=.02+1e-12
  if not valid:assert actual is None
  else:assert [x.identity for x,q in actual]==[pp[1].identity,pp[0].identity,cc[0].identity,cc[1].identity]
