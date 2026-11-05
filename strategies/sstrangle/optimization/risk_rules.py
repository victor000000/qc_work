"""Risk-budget research helpers; the frozen baseline does not import these."""
import math


def validate_risk(total_fraction,per_symbol_fraction,stop_multiple,risk_interval):
    if not 0<per_symbol_fraction<=total_fraction<=.5:
        raise ValueError('Require 0 < per-symbol <= total collateral fraction <= 0.5')
    if not 0<stop_multiple<=2 or risk_interval not in (1,5,15,30):
        raise ValueError('Invalid stop or intraday interval')


def collateral_budget(equity,count,total_fraction,per_symbol_fraction):
    if not math.isfinite(equity) or equity<=0 or count<1:return 0.
    return min(equity*total_fraction/count,equity*per_symbol_fraction)


def capped_candidates(candidates,held,equity,maximum,total_fraction,per_symbol_fraction):
    if held:raise ValueError('New research batch requires a fully flat portfolio')
    if (not math.isfinite(equity) or equity<=0 or not 1<=maximum<=13
            or not 0<per_symbol_fraction<=total_fraction<=.5):
        raise ValueError('Invalid capped basket inputs')
    ranked=sorted(candidates,key=lambda c:(-c['volume'],c['key']))
    # Evaluate every feasible opening count before committing membership. A
    # rejected 13-name budget can still permit 12 names, and unaffordable high
    # volume names must not conceal affordable names outside the first13.
    # These are pre-entry feasibility checks; no replacement follows a fill.
    for count in range(min(maximum,len(ranked)),0,-1):
        budget=collateral_budget(equity,count,total_fraction,per_symbol_fraction)
        affordable=[c for c in ranked if math.isfinite(c['unit_cost']) and 0<c['unit_cost']<=budget]
        if len(affordable)>=count:return affordable[:count],count
    return [],0


def capped_quantity(equity,count,unit_cost,remaining,total_fraction,per_symbol_fraction):
    budget=collateral_budget(equity,count,total_fraction,per_symbol_fraction)
    if not math.isfinite(unit_cost) or unit_cost<=0 or not math.isfinite(remaining):return 0
    return max(0,math.floor(min(budget,remaining)/unit_cost))
