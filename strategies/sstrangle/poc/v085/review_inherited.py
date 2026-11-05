"""Read-only accounting review of ten inherited full accounts; write new receipts only."""
from campaign import ROOT,OUT,save,digest
from payoff import reconstruct
import json
BASE=ROOT/'strategies/sstrangle/results'
folders={
 'v065_condor_baseline':BASE/'qc_delta_poc_20261024/condor_full_t02_evidence',
 'v06_strangle_baseline':BASE/'qc_three_demo_poc_20261023/strangle_full_v2_evidence',
 'v06_put_baseline':BASE/'qc_three_demo_poc_20261023/put_full_v3_evidence',
 **{'v07_'+k:BASE/('qc_final_poc_20261024/'+k+'_alpha_full_evidence') for k in ['condor','strangle','put']},
 **{'v08_'+k+'_'+s:BASE/('qc_sizing_poc_20261024/'+k+'_'+s+'_evidence') for k in ['condor','put'] for s in ['control','final']}}
def main():
 results={}
 for name,folder in folders.items():
  _,r=reconstruct(folder);r['files']={str(folder/n):digest(folder/n) for n in ['orders.json','episodes.parquet','backtest.json']};results[name]=r
  print(name,r['episodes'],r['net_pnl'],flush=True)
 save(OUT/'inherited_account_reaudit.json',results)
 print('Re-audited',len(results),'accounts and',sum(r['episodes'] for r in results.values()),'episodes',flush=True)
if __name__=='__main__':main()
