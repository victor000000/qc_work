"""Outcome-only diagnostic on already frozen rules, never candidate reselection.
Same official-covered contracts on both sides isolate the payoff-label change.
Missing dates are excluded on both sides; this is not a funded account rerun.
"""
import json
import pandas as pd
from campaign import OUT,save,ACTIVE_KINDS
from research import features,mask_for,evaluate

def main():
 results={}
 for kind in ACTIVE_KINDS:
  folder=OUT/(kind+'_baseline_evidence');f=features(pd.read_parquet(folder/'episodes.parquet'));legs=pd.read_parquet(folder/'legs.parquet');spots=pd.read_csv(OUT/(kind+'_baseline_official_settlement.csv')).set_index('day').official_settlement.dropna()
  legs['spot_official']=legs.expiry.map(spots);good=legs.groupby('episode').spot_official.apply(lambda x:x.notna().all());legs=legs[legs.episode.isin(good[good].index)].copy()
  legs['official_pnl']=[r.entry_cash-r.fees+r.quantity*100*(max(0,r.spot_official-r.strike) if r.right=='C' else max(0,r.strike-r.spot_official)) for r in legs.itertuples()]
  payoffs=legs.groupby('episode').official_pnl.sum();covered=f[f.episode.isin(payoffs.index)].copy();official=covered.copy();official['pnl']=official.episode.map(payoffs)
  trials=json.loads((OUT/(kind+'_trials.json')).read_text());rows=[]
  for rule in trials:
   mask=mask_for(covered,rule)
   native=evaluate(covered,mask,10,'2024-01-01','2024-12-31');alt=evaluate(official,mask,10,'2024-01-01','2024-12-31')
   rows.append(dict(feature=rule['feature'],side=rule['side'],quantile=rule['quantile'],threshold=rule['threshold'],original_eligible=rule['eligible'],native_covered_score=native['calmar'],official_covered_score=alt['calmar'],native_covered_net=native['pnl'],official_covered_net=alt['pnl']))
  def rank(field):return sorted([r for r in rows if r['original_eligible']],key=lambda r:(-r[field],r['feature'],r['side'],r['quantile']))
  n=rank('native_covered_score');o=rank('official_covered_score')
  frozen=json.loads((OUT/'frozen_rules.json').read_text())[kind];mask=mask_for(covered,frozen)
  results[kind]=dict(covered_episodes=len(covered),all_baseline_episodes=len(f),frozen_rule=frozen,covered_frozen_native=evaluate(covered,mask),covered_frozen_official=evaluate(official,mask),diagnostic_native_top=n[0] if n else None,diagnostic_official_top=o[0] if o else None,all_rules=rows,policy='Diagnostic only: original thresholds and eligibility frozen; no funded rerun, missing-date imputation, replacement rule, or retrospective promotion')
 save(OUT/'settlement_rule_sensitivity.json',results)
if __name__=='__main__':main()
