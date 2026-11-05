"""Read-only raw pilot audit; does not publish provider data or invent an underlying axis."""
import hashlib,json
from pathlib import Path
import pandas as pd


def audit(folder,out):
    folder,out=Path(folder),Path(out)
    if out.exists():raise ValueError('new preflight output required')
    status=json.loads((folder/'status.json').read_text());frames={};receipts={}
    for r in status['results']:
        if r['status']!='downloaded' or r['params'].get('interval')!='1m':raise ValueError('native minute download incomplete')
        raw=Path(r['raw_path'])
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=r['raw_sha256']:raise ValueError('raw hash mismatch')
        frames[r['kind']]=pd.read_csv(raw);receipts[r['kind']]=r['raw_sha256']
    keys=['symbol','expiration','strike','right','timestamp']
    q,g=frames['quotes'],frames['greeks']
    if q.duplicated(keys).any() or g.duplicated(keys).any():raise ValueError('duplicate raw identity')
    joined=q.merge(g,on=keys,how='outer',indicator=True,suffixes=('_q','_g'),validate='one_to_one')
    paired=int((joined['_merge']=='both').sum())
    stamps=pd.to_datetime(q.timestamp).drop_duplicates().sort_values()
    expected=int((stamps.iloc[-1]-stamps.iloc[0]).total_seconds()/60)+1
    grid_pass=len(stamps)==expected and bool((stamps.diff().dropna()==pd.Timedelta(minutes=1)).all())
    result=dict(version='0.8.8',scope='Raw one-minute provider pilot preflight only; not published replay acceptance',
                provider_phase=status['phase'],raw_sha256=receipts,quote_rows=len(q),greek_rows=len(g),
                paired_keys=paired,unpaired_keys=int((joined['_merge']!='both').sum()),
                contracts=int(q[keys[:-1]].drop_duplicates().shape[0]),sample_timestamps=len(stamps),
                full_observed_minute_grid=grid_pass,
                bid_ask_pair_mismatches=int(((joined.bid_q!=joined.bid_g)|(joined.ask_q!=joined.ask_g)).sum()) if 'bid_g' in joined else None,
                strict_replay_ready=False,axis_replay_ready=False,
                pending=['verified normalized publication','SPX/SPY underlying minute history and warmup','historical availability and actual quote clocks','accepted Greek methodology'])
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(audit(a.folder,a.out),indent=2))
