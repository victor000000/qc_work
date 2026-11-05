"""Compare native terminal reference to independently retrieved official Cboe archives.
Prices are outcome-only; never imported into an entry signal or QC source.
"""
import json,hashlib
from pathlib import Path
import pandas as pd
from campaign import ROOT,OUT,save,digest
SOURCE=OUT/'official_settlement_sources'
def check(folder):
 official={};sources={}
 manifest=json.loads((SOURCE/'manifest.json').read_text())
 for item in manifest:assert digest(SOURCE/item['snapshot'])==item['sha256']
 for year in range(2022,2027):
  p=SOURCE/f'weekly-{year}.json';sources[str(p)]=digest(p)
  for r in json.loads(p.read_text())['data']:
   if r['trading_symbol']=='SPXW':
    d=r['expiration_date'];v=float(r['settlement_value']);assert d not in official or official[d]==v;official[d]=v
 ep=pd.read_parquet(folder/'episodes.parquet');legs=pd.read_parquet(folder/'legs.parquet')
 dates=ep.groupby('day').settlement_spot.agg(['first','nunique']);assert (dates['nunique']==1).all()
 rows=[]
 for d,r in dates.iterrows():
  rows.append(dict(day=d,native_reference=float(r['first']),official_settlement=official.get(d),difference=None if d not in official else float(r['first'])-official[d]))
 comparison=pd.DataFrame(rows);known=comparison[comparison.official_settlement.notna()]
 legs['official_settlement']=legs.expiry.map(official)
 legs['official_intrinsic']=[None if pd.isna(r.official_settlement) else max(0,r.official_settlement-r.strike) if r.right=='C' else max(0,r.strike-r.official_settlement) for r in legs.itertuples()]
 legs['official_expiry_cash']=legs.quantity*legs.official_intrinsic*100
 available=legs.groupby('episode').official_settlement.apply(lambda s:s.notna().all());good=legs[legs.episode.isin(available[available].index)]
 bridge=good.groupby('episode').agg(native_expiry=('expiry_attribution','sum'),official_expiry=('official_expiry_cash','sum'));bridge['difference']=bridge.official_expiry-bridge.native_expiry
 return comparison,dict(native_days=len(dates),official_covered_days=len(known),missing_days=comparison.loc[comparison.official_settlement.isna(),'day'].tolist(),days_differ_over_001=int((known.difference.abs()>.0100001).sum()),max_absolute_index_difference=float(known.difference.abs().max()),covered_episodes=len(bridge),sum_official_minus_native_expiry=float(bridge.difference.sum()),max_absolute_episode_cash_difference=float(bridge.difference.abs().max()),sources=sources,scope='Official settlement outcome sensitivity on fixed native contracts; neither an account rerun nor certified historical availability; do not alter frozen selection')
def main():
 results={}
 for key in ['condor_baseline','put_spread_baseline','condor_final','put_spread_final']:
  folder=OUT/(key+'_evidence')
  if not (folder/'episodes.parquet').exists():continue
  frame,result=check(folder);frame.to_csv(OUT/(key+'_official_settlement.csv'),index=False);results[key]=result
 save(OUT/'official_settlement_audit.json',results)
if __name__=='__main__':main()
