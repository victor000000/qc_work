"""Pin read-only provider release; export only relevant public datasets."""
from pathlib import Path
import json
from data_providers import MarketData
import pandas as pd
OUT=Path('strategies/sstrangle/results/qc_delta_poc_20261024/provider');OUT.mkdir(exist_ok=True)
pin=OUT/'release.json'
if pin.exists():m=MarketData(backend='parquet',release=json.loads(pin.read_text())['release'])
else:
 m=MarketData(backend='parquet');pin.write_text(json.dumps({'release':m.release.id,'availability':'Historical EOD fields use conservative next-session publication assumption; not vintage-certified.'},indent=2))
for ds in ['us_prices','us_iv','us_minutes','us_option_research_observations']:
 p=OUT/ds
 if not p.exists():m.export(ds,p,symbols=['SPX','SPY','QQQ','VIX','IWM','TLT','GLD'],start='2021-01-01',end='2026-07-13')
 f=pd.read_parquet(p/'data.parquet');print(ds,len(f),flush=True)
 col='symbol' if 'symbol' in f else 'underlying'
 day=next((x for x in ['date','day','ts_utc','session_date'] if x in f),None)
 if len(f):print(f.groupby([col]+(['source'] if 'source' in f else []))[day].agg(['count','min','max']).to_string(),flush=True)
