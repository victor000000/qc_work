import ast
from pathlib import Path
from types import SimpleNamespace as S
import pytest

# Execute the actual pre-order gate from the submitted template in isolation.
s=Path(__file__).with_name('three_demos.py').read_text()
a=s.index('        tolerance = float(');b=s.index("        if self.fill_convention == 'oo_midpoint_package':",a)
code='def gate(self,put,call):\n'+s[a:b]+'        return True\n'
ns={};exec(code,ns)
@pytest.mark.parametrize('pd,cd,tol,ok',[(-.20,.08,.02,True),(-.22,.10,.02,True),(-.2201,.08,.02,False),(-.20,.1001,.02,False),(-.25,.13,.05,True),(-.25,.13,.02,False)])
def test_actual_gate(pd,cd,tol,ok):
 from collections import Counter
 obj=S(CONFIG={'delta_tolerance':tol,'put_target':.20,'call_target':.08},counts=Counter())
 assert bool(ns['gate'](obj,S(greeks=S(delta=pd)),S(greeks=S(delta=cd))))==ok
 assert obj.counts['skip_delta_tolerance']==int(not ok)
def test_gate_precedes_credit_reserve_and_orders():
 assert a<s.index('        day_reserve =')<s.index('        tickets = self.combo_market_order')
