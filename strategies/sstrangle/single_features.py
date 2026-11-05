#!/usr/bin/env python3
"""Publish shared-provider daily features and causal entry joins for the campaign."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import duckdb
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent/'local'))
from warehouse import daily_features, attach_features


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('batch',type=Path)
    args=p.parse_args()
    batch=args.batch.resolve()
    manifest=json.loads((batch/'manifest.json').read_text())
    out=batch/'shared_provider_v2';out.mkdir(exist_ok=True)
    export=out/'underlying_history'
    if not export.exists():
        from data_providers import MarketData
        MarketData().export('us_prices',export,symbols=list(manifest['variants']),
                            start='2022-12-01',end='2026-09-30')
    index_export=out/'index_history'
    if not index_export.exists():
        from data_providers import MarketData
        MarketData().export('us_daily',index_export,symbols=['^GSPC'],source='yfinance_index',
                            start='2022-12-01',end='2026-09-30')
    panel_path=out/'daily_features.parquet'
    if not panel_path.exists():
        prices=pd.read_parquet(export/'data.parquet')
        index=pd.read_parquet(index_export/'data.parquet').rename(columns={'day':'date'})
        index['provider_symbol']=index['symbol']
        index['symbol']=index['symbol'].replace({'^GSPC':'SPX'})
        # This is the S&P 500 price index, not a dividend-adjusted total-return index.
        index['adj_close']=index['close']
        prices=pd.concat([prices,index],ignore_index=True)
        panels=[]
        for basis in ['raw','adjusted']:
            data=prices.copy()
            if basis=='adjusted':
                data['close']=data['adj_close']
            f=daily_features(data)
            f['price_basis']=basis
            panels.append(f)
        frame=pd.concat(panels,ignore_index=True)
        frame.to_parquet(panel_path,index=False)
        missing=sorted(set(manifest['variants'])-set(prices['symbol']))
        metadata=dict(provider_home='/home/vic/data_providers/runtime',
            rows=len(frame),missing_symbols=missing,
            index_alias={'^GSPC':'SPX'},index_source='us_daily/yfinance_index',
            index_adjustment_policy='SPX raw and adjusted bases both use the same price-index close, not a total-return series',
            sha256=hashlib.sha256(panel_path.read_bytes()).hexdigest(),
            policy='Prior completed D1 only, available at next midnight New York. Raw and adjusted bases separate. These independent features are not added to the frozen selection grid.')
        (out/'manifest.json').write_text(json.dumps(metadata,indent=2))
        con=duckdb.connect(str(out/'daily_features.duckdb'))
        con.execute('CREATE TABLE daily_features AS SELECT * FROM read_parquet(?)',[str(panel_path)])
        con.close()
    panel=pd.read_parquet(panel_path)
    outcomes=json.loads((batch/'outcomes.json').read_text())
    for name,record in outcomes.items():
        if record['status']!='done':
            continue
        ticker=name.rsplit('_',1)[1]
        source=batch/name/'entry_features.csv'
        if not source.exists():
            continue
        local=batch/'local'/ticker
        local.mkdir(parents=True,exist_ok=True)
        target=local/'underlying_entry_features_v2.parquet'
        if target.exists():
            continue
        entries=pd.read_csv(source)
        if entries.empty:
            continue
        entries['entry']=pd.to_datetime(entries['entry'],utc=True)
        joined=[]
        for basis in ['raw','adjusted']:
            f=attach_features(entries[['ticker','entry']],panel[panel['price_basis']==basis].drop(columns='price_basis'))
            f['price_basis']=basis
            joined.append(f)
        result=pd.concat(joined,ignore_index=True)
        if (result['available_at']>result['entry']).any():
            raise ValueError('Future feature in entry join')
        result.to_parquet(target,index=False)
        (local/'underlying_feature_manifest_v2.json').write_text(json.dumps(dict(rows=len(result),
            complete_rows=int(result['feature_complete'].sum()),
            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            feature_source=str(panel_path),policy='Independent provider features; not used in frozen QC-annotation grid'),indent=2))
        print(ticker,'entry rows:',len(result),'complete:',int(result['feature_complete'].sum()),flush=True)


if __name__=='__main__':
    main()
