#!/usr/bin/env python3
"""Publish the frozen execution replay, entry features and labels to DuckDB/Parquet."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd

from prepare import write_csv


def daily_features(prices):
    output = []
    for symbol, data in prices.groupby('symbol'):
        d = data.sort_values('date').copy()
        r = d['close'].pct_change(fill_method=None)
        d['ret_1d'] = r
        d['ret_5d'] = d['close'].pct_change(5, fill_method=None)
        d['ret_20d'] = d['close'].pct_change(20, fill_method=None)
        d['rv20'] = r.rolling(20, min_periods=20).std(ddof=1)*252**.5
        d['close_sma20_ratio'] = d['close']/d['close'].rolling(20,min_periods=20).mean()
        d['source_day'] = pd.to_datetime(d['date'])
        # Conservative availability: use a completed prior daily bar only,
        # including early-close days. Never attach the entry day's close.
        d['available_at'] = (d['source_day']+pd.Timedelta(days=1)).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
        output.append(d[['symbol','source_day','available_at','ret_1d','ret_5d','ret_20d','rv20','close_sma20_ratio']])
    return pd.concat(output, ignore_index=True)


def attach_features(trades, features):
    output = []
    for symbol, group in trades.groupby('ticker'):
        f = features[features['symbol']==symbol].sort_values('available_at')
        d = pd.merge_asof(group.sort_values('entry'), f, left_on='entry', right_on='available_at', direction='backward')
        d['feature_age_hours'] = (d['entry']-d['available_at']).dt.total_seconds()/3600
        d['feature_complete'] = d[['ret_1d','ret_5d','ret_20d','rv20','close_sma20_ratio']].notna().all(axis=1) & (d['feature_age_hours']<=7*24)
        if (d['available_at'] > d['entry']).any():
            raise ValueError('Future information in entry features')
        output.append(d)
    return pd.concat(output, ignore_index=True).sort_values('entry')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    args = p.parse_args()
    folder = args.folder.resolve()
    db = folder/'research.duckdb'
    if db.exists():
        raise FileExistsError(db)
    from data_providers import MarketData
    history = folder/'feature_price_history'
    if not history.exists():
        m = MarketData()
        manifest = json.loads((folder/'manifest.json').read_text())
        symbols = sorted({r['underlying'] for r in csv.DictReader((folder/'qc_executions.csv').open())})
        m.export('us_prices', history, symbols=symbols, start='2022-12-01',end=manifest['end'])
    con = duckdb.connect(str(db))
    con.execute("SET TimeZone='UTC'")
    con.execute('CREATE TABLE qc_executions AS SELECT * FROM read_csv_auto(?)', [str(folder/'qc_executions.csv')])
    con.execute('CREATE TABLE execution_price_coverage AS SELECT * FROM read_csv_auto(?)', [str(folder/'price_coverage.csv')])
    captures = []
    daily = []
    for path in sorted((folder/'provider_capture').glob('*.json')):
        if path.name=='manifest.json':
            continue
        destination = captures if path.name.startswith('minute_') else daily
        for page in json.loads(path.read_text())['pages']:
            for symbol, bars in page.get('bars',{}).items():
                for b in bars:
                    destination.append(dict(source='alpaca',symbol=symbol,timestamp=pd.Timestamp(b['t']),
                        open=b['o'],high=b['h'],low=b['l'],close=b['c'],volume=b['v'],vwap=b.get('vw')))
    for name, rows in [('provider_trade_minutes',captures),('provider_trade_daily',daily)]:
        frame=pd.DataFrame(rows)
        if frame.duplicated(['source','symbol','timestamp']).any():
            raise ValueError('Duplicate captured market bars')
        con.register('frame',frame)
        con.execute(f'CREATE TABLE {name} AS SELECT * FROM frame')
        con.unregister('frame')
    summaries=json.loads((folder/'replay_summary.json').read_text())
    executions=[]
    for run in summaries:
        if not (folder/run['label']/'executions.csv').exists():
            continue
        f=pd.read_csv(folder/run['label']/'executions.csv')
        f['scenario']=run['label'];executions.append(f)
    frame=pd.concat(executions,ignore_index=True)
    con.register('frame',frame)
    con.execute('CREATE TABLE akquant_executions AS SELECT * FROM frame')
    con.unregister('frame')
    frame=pd.DataFrame(summaries)
    con.register('frame',frame)
    con.execute('CREATE TABLE replay_runs AS SELECT * FROM frame')
    con.unregister('frame')
    source=Path(json.loads((folder/'manifest.json').read_text())['qc_source'])
    trades=pd.read_csv(source/'cycles.csv')
    trades['entry']=pd.to_datetime(trades['entry'],utc=True)
    trades['exit']=pd.to_datetime(trades['exit'],utc=True)
    coverage=pd.read_csv(folder/'price_coverage.csv')
    opening=coverage[coverage['tag'].str.split(';').str[0].str.endswith(':OPEN')]
    identity={(r['underlying'],pd.Timestamp(r['timestamp']).value):int(r['cycle_id'])
              for r in opening.to_dict('records')}
    # Cycles close in a different order from their openings when ETFs overlap.
    trades['cycle_id']=[identity[(r.ticker,r.entry.value)] for r in trades.itertuples()]
    prices=con.execute('SELECT * FROM read_parquet(?)',[str(history/'data.parquet')]).df()
    features=daily_features(prices)
    entries=attach_features(trades[['cycle_id','ticker','entry']],features)
    for name,frame in [('baseline_trade_labels',trades),('daily_features',features),('entry_features',entries)]:
        con.register('frame',frame)
        con.execute(f'CREATE TABLE {name} AS SELECT * FROM frame')
        con.unregister('frame')
    # Keep labels physically separate from candidate input features.
    con.execute('CREATE VIEW featured_trades AS SELECT f.*, l.exit, l.pnl, l.fees, l.rolls, l.reason FROM entry_features f JOIN baseline_trade_labels l USING(cycle_id)')
    release=folder/'parquet';release.mkdir(exist_ok=False)
    tables={}
    for (name,) in con.execute('SHOW TABLES').fetchall():
        dest=release/(name+'.parquet')
        con.execute(f'COPY (SELECT * FROM "{name}") TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(dest)])
        tables[name]=dict(rows=con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0],
            sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    (release/'manifest.json').write_text(json.dumps(dict(tables=tables,
        price_basis='Raw underlying closes; completed prior-day feature availability at next midnight New York',
        label_policy='QC outcomes kept separate from entry features; current outcomes already inspected',
        validation_policy='No claim of untouched holdout for previously inspected 2024–2025 outcomes',
        engine_policy='Frozen QC signal replay; proxy trade prices are not bid/ask fills'),indent=2))
    con.close()
    print(db)
    print(json.dumps(tables,indent=2))


if __name__=='__main__':
    main()
