from types import SimpleNamespace as S
from selection import choose_exact_pairs

def c(strike,delta):return S(strike=strike,greeks=S(delta=delta))

def test_nearest_short_without_wing_no_longer_vetoes_feasible_trade():
    best,p=c(4990,-.20),c(4985,-.18)
    best_call,call=c(5020,.08),c(5025,.06)
    lp,lc=c(4965,-.06),c(5045,.01)
    result=choose_exact_pairs([best,p],[best_call,call],{('P',4965):lp,('C',5045):lc},'P','C',.20,.08)
    assert result==(p,call,lp,lc)

def test_exact_width_and_admitted_wings_are_required():
    p,call=c(4990,-.20),c(5020,.08)
    assert choose_exact_pairs([p],[call],{('P',4975):c(4975,-.1),('C',5040):c(5040,.01)},'P','C',.20,.08) is None

def test_existing_feasible_best_shorts_are_unchanged_with_deterministic_tie():
    p,p2,call=c(4990,-.20),c(4985,-.20),c(5020,.08)
    lookup={('P',4970):c(4970,-.1),('P',4965):c(4965,-.05),('C',5040):c(5040,.01)}
    result=choose_exact_pairs([p,p2],[call],lookup,'P','C',.20,.08)
    assert result[0] is p2 and result[1] is call
