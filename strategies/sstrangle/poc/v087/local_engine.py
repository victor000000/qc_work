"""Independent provider-driven SPXW selection and cash/expiry accounting."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class Leg:
    identity:str
    strike:float
    right:str
    delta:float
    bid:float
    ask:float
    spot:float

def select(contracts,kind):
    good=[c for c in contracts if all(isfinite(x) for x in [c.delta,c.bid,c.ask,c.spot]) and c.spot>0 and c.ask>0 and 0<=c.bid<=c.ask and c.ask-c.bid<=3]
    puts=[c for c in good if c.right=='P' and c.strike<c.spot and -.40<c.delta<-.01]
    calls=[c for c in good if c.right=='C' and c.strike>c.spot and .01<c.delta<.30]
    keyed={(c.right,c.strike):c for c in good}
    if not puts or (kind=='condor' and not calls):return None,'missing_candidates'
    p=min(puts,key=lambda c:(abs(c.delta+.2),c.strike))
    if kind=='condor':
        c=min(calls,key=lambda c:(abs(c.delta-.08),c.strike))
        if ('P',p.strike-20) not in keyed or ('C',c.strike+20) not in keyed:
            pp=[x for x in puts if ('P',x.strike-20) in keyed];cc=[x for x in calls if ('C',x.strike+20) in keyed]
            if not pp or not cc:return None,'missing_exact_wing'
            p=min(pp,key=lambda x:(abs(x.delta+.2),x.strike));c=min(cc,key=lambda x:(abs(x.delta-.08),x.strike))
        if abs(p.delta+.2)>.02+1e-12 or abs(c.delta-.08)>.02+1e-12:return None,'delta_tolerance'
        return [(keyed['P',p.strike-20],1),(p,-1),(c,-1),(keyed['C',c.strike+20],1)],'selected'
    pp=[x for x in puts if ('P',x.strike-20) in keyed]
    if not pp:return None,'missing_exact_wing'
    p=min(pp,key=lambda x:(abs(x.delta+.2),x.strike))
    if abs(p.delta+.2)>.02+1e-12:return None,'delta_tolerance'
    return [(keyed['P',p.strike-20],1),(p,-1)],'selected'

def account(legs,settlement,model='legacy',extra=0.):
    n=len(legs);fee=n*1.18
    prices=[(c.bid+c.ask)/2+q*.05/n if model=='legacy' else (c.ask+.05 if q>0 else c.bid-.05) for c,q in legs]
    if any(x<=0 for x in prices):return None
    credit=-sum(q*price for (_,q),price in zip(legs,prices))
    if not 0<credit<20:return None
    opening=credit*100-fee-extra
    expiry=sum(q*100*(max(c.strike-settlement,0) if c.right=='P' else max(settlement-c.strike,0)) for c,q in legs)
    return dict(credit=credit,fees=fee,opening_cash=opening,expiry_cash=expiry,pnl=opening+expiry,max_loss=(20-credit)*100+fee+extra)

def feature(rows,day):
    from datetime import date
    past=[r for r in rows if r[0]<day]
    if not past:return None
    latest=past[-1]
    if (date.fromisoformat(day)-date.fromisoformat(latest[0])).days-1>=7:return None
    return (latest[1]-latest[2])/latest[3] if latest[3]>0 else None
