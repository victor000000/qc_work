"""Attach native pre-order admission tags and derived audits to saved episode rows."""
import argparse,json,hashlib
from pathlib import Path
import pandas as pd
from collect_three import metadata

def enrich(folder):
 orders=json.loads((folder/'orders.json').read_text())
 rt=json.loads((folder/'backtest.json').read_text())['backtest']['runtimeStatistics']
 ep=pd.read_parquet(folder/'episodes.parquet')
 tags={metadata(o.get('tag','')).get('e'):metadata(o.get('tag','')) for o in orders if ';r=OPEN;' in o.get('tag','')}
 for col,default in [('recovered',0),('anchor_pd',None),('anchor_cd',None)]:
  ep[col]=[float(tags[e].get(col,default)) if tags[e].get(col,default) is not None else None for e in ep.episode]
 ep['recovered']=ep.recovered.astype(bool)
 if rt['strategy_kind']=='put': ep['call_delta']=None;ep['anchor_cd']=None
 if 'recovered_filled_episodes' in rt:
  assert int(ep.recovered.sum())==int(rt['recovered_filled_episodes'])
 ep.to_parquet(folder/'episodes.parquet',compression='zstd',index=False);ep.to_csv(folder/'episodes.csv',index=False)
 features=ep[['episode','ticker','decision_at','put_delta','call_delta','entry_spot','recovered','anchor_pd','anchor_cd']].rename(columns={'entry_spot':'decision_spot'})
 features['decision_at']=pd.to_datetime(features.decision_at).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
 features.to_parquet(folder/'entry_features.parquet',compression='zstd',index=False)
 registry=json.loads((folder/'feature_registry.json').read_text())
 registry.update(strategy_kind=rt['strategy_kind'],features=list(features.columns[3:]),
    applicability={'call_delta':'null for put-only strategy','anchor_pd':'original nearest-short delta before exact-pair selection; null in initial smokes without tag','anchor_cd':'as above; null for put-only','recovered':'pre-order admission flag, not a future success label'})
 (folder/'feature_registry.json').write_text(json.dumps(registry,indent=2)+'\n')
 old=json.loads((folder/'audit.json').read_text())
 old['admission']=dict(recovered_filled=int(ep.recovered.sum()),strategy_kind=rt['strategy_kind'],wing_policy=rt.get('wing_policy','original'))
 old['delta_target_error']['call_max']=float((ep.call_delta-float(rt['call_target'])).abs().max()) if rt['strategy_kind']!='put' else None
 (folder/'audit.json').write_text(json.dumps(old,indent=2)+'\n')
 manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file() and p.name!='manifest.json'}
 (folder/'manifest.json').write_text(json.dumps({'files':manifest},indent=2)+'\n')
 print(folder.name,old['admission'])

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);enrich(p.parse_args().folder)
