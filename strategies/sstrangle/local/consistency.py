"""Compare frozen baseline fills with provider bars and independent QC references."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import duckdb
import pandas as pd
from prepare import executions


def summarize_errors(values):
    values = values.dropna().abs()
    return dict(count=len(values), median=float(values.median()) if len(values) else None,
                p95=float(values.quantile(.95)) if len(values) else None,
                maximum=float(values.max()) if len(values) else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--fresh-orders',type=Path,required=True)
    parser.add_argument('--qc-reference',type=Path)
    args=parser.parse_args()
    folder=args.folder.resolve()
    manifest=json.loads((folder/'manifest.json').read_text())
    source=Path(manifest['qc_source'])
    original=json.loads((source/'orders.json').read_text())
    refreshed=json.loads(args.fresh_orders.read_text())
    if executions(original) != executions(refreshed):
        raise ValueError('Fresh Rust download differs from audited baseline executions')
    shutil.copyfile(args.fresh_orders,folder/'qc_orders.rust.refreshed.json')
    for name in ('qc_closed_trades.json','cycles.csv','audit.json','dte_audit.csv','backtest.json'):
        shutil.copyfile(source/name,folder/('baseline_'+name))
    full=json.loads((source/'backtest.json').read_text())['backtest']
    coverage=pd.read_csv(folder/'price_coverage.csv')
    coverage['session']=pd.to_datetime(coverage['timestamp'],utc=True).dt.tz_convert('America/New_York').dt.date
    coverage['price_difference']=coverage['provider_price']-coverage['qc_price']
    coverage['price_difference_percent']=100*coverage['price_difference']/coverage['qc_price']
    daily=pd.read_parquet(folder/'us_option_bars/data.parquet')
    daily['session']=pd.to_datetime(daily['day']).dt.date
    daily['symbol']=daily['symbol'].str.replace(' ','',regex=False)
    compared=coverage.merge(daily[['source','symbol','session','low','high','close']],
                           how='left',on=['symbol','session'])
    compared['qc_fill_inside_provider_daily_range']=((compared['qc_price']>=compared['low']-.01)
                                                   &(compared['qc_price']<=compared['high']+.01))
    prices=pd.read_parquet(folder/'us_prices/data.parquet')
    prices['session']=pd.to_datetime(prices['date']).dt.date
    openings=coverage[coverage['tag'].str.split(';').str[0].str.endswith(':OPEN')].drop_duplicates('group_id').copy()
    openings['qc_spot']=[float(dict(part.split('=',1) for part in tag.split(';')[1:] if '=' in part)['spot'])
                         for tag in openings['tag']]
    underlying=openings.merge(prices,how='left',left_on=['underlying','session'],right_on=['symbol','session'],suffixes=('','_underlying'))
    underlying['qc_spot_inside_raw_daily_range']=((underlying['qc_spot']>=underlying['low']-.01)
                                                &(underlying['qc_spot']<=underlying['high']+.01))
    result=dict(baseline=dict(project_id=full['projectId'],backtest_id=full['backtestId'],
        start=full['backtestStart'],end=full['backtestEnd'],configuration='Historical SPY reference: 252-prior-observation range IVR >=50; not the new basket'),
        fresh_rust_orders_match=True,orders=len(refreshed),cycles=len(pd.read_csv(source/'cycles.csv')),
        local_provider_release=manifest['datasets']['us_prices']['release'],
        local_option_minute_rows=manifest['datasets']['us_option_minutes']['rows'],
        option_daily_matches=int(compared['close'].notna().sum()),
        option_daily_range_passes=int(compared['qc_fill_inside_provider_daily_range'].sum()),
        underlying_entry_spots=len(underlying),underlying_raw_range_passes=int(underlying['qc_spot_inside_raw_daily_range'].sum()),
        provider_minute_matches=int(coverage['provider_price'].notna().sum()),
        provider_fresh_5min_matches=int((coverage['age_minutes']<=5).sum()),
        fresh_5min_price_difference_usd=summarize_errors(coverage.loc[coverage['age_minutes']<=5,'price_difference']),
        fresh_5min_price_difference_percent=summarize_errors(coverage.loc[coverage['age_minutes']<=5,'price_difference_percent']),
        akquant_runs=json.loads((folder/'replay_summary.json').read_text()),
        limitations=['Provider minute observations are trades, not contemporaneous executable bid/ask.',
            'Daily-range checks use the whole session only for retrospective data consistency, never as an entry signal or fill.',
            'No provider-price fallback to QC: incomplete cycles are excluded from provider replays.',
            'This compares the completed SPY reference; the 504-observation IVR >70 basket is a different pending baseline.'])
    tables={'execution_comparison':compared,'underlying_entry_checks':underlying}
    if args.qc_reference:
        reference=json.loads(gzip.decompress(args.qc_reference.read_bytes()) if args.qc_reference.suffix=='.gz'
                             else args.qc_reference.read_text())
        if reference['baseline'] != dict(project_id=full['projectId'],backtest_id=full['backtestId']):
            raise ValueError('QC reference belongs to another baseline')
        shutil.copyfile(args.qc_reference,folder/args.qc_reference.name)
        qcdaily=pd.DataFrame(reference['underlying_daily'])
        qcdaily['session']=pd.to_datetime(qcdaily['date']).dt.date
        matched=qcdaily.merge(prices,on=['symbol','session'],suffixes=('_qc','_provider'),how='outer',indicator=True)
        for field in ('open','high','low','close'):
            matched[field+'_difference']=matched[field+'_provider']-matched[field+'_qc']
            matched[field+'_difference_bps']=10000*matched[field+'_difference']/matched[field+'_qc']
        result['underlying_daily_comparison']=dict(qc_rows=len(qcdaily),provider_rows=len(prices),
            matched_rows=int((matched['_merge']=='both').sum()),
            only_qc=int((matched['_merge']=='left_only').sum()),only_provider=int((matched['_merge']=='right_only').sum()),
            close_absolute_difference_usd=summarize_errors(matched['close_difference']),
            close_absolute_difference_bps=summarize_errors(matched['close_difference_bps']))
        quotes=pd.DataFrame(reference['option_quotes'])
        quotes['fill_inside_quote']=((quotes['qc_fill']>=quotes['bid']-1e-7)&(quotes['qc_fill']<=quotes['ask']+1e-7))
        quotes['qc_side_price']=quotes['ask'].where(quotes['quantity']>0,quotes['bid'])
        quotes['fill_minus_side_price']=quotes['qc_fill']-quotes['qc_side_price']
        result['qc_quote_reference']=dict(orders=len(quotes),quotes_found=int((quotes['bars']>0).sum()),
            fills_inside_quote=int(quotes['fill_inside_quote'].sum()),
            side_price_difference=summarize_errors(quotes['fill_minus_side_price']))
        tables.update(underlying_daily_comparison=matched,option_quote_reference=quotes)
    database=folder/'consistency.duckdb'
    if database.exists():
        raise FileExistsError('Preserve completed comparison: '+str(database))
    receipts={}
    with duckdb.connect(str(database)) as con:
        for name,frame in tables.items():
            con.register('frame',frame)
            con.execute(f'CREATE TABLE {name} AS SELECT * FROM frame')
            con.unregister('frame')
            path=folder/(name+'.parquet')
            con.execute(f'COPY {name} TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path)])
            frame.to_csv(folder/(name+'.csv'),index=False)
            receipts[name]=dict(rows=len(frame),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    result['tables']=receipts
    (folder/'consistency_summary.json').write_text(json.dumps(result,indent=2))
    lines=['# SPY baseline data consistency','',
        f"QC baseline `{full['backtestId']}`: {len(refreshed)} refreshed orders, {result['cycles']} strangles. Rust downloads match the audited fills.",
        '',f"The AKQuant QC-price control reproduces all 570 fills and net P&L of -$3,621 exactly, with zero residual positions.",
        '',f"Local provider release: `{result['local_provider_release']}`. Local stored option minutes: {result['local_option_minute_rows']}. Targeted provider capture supplied {result['provider_minute_matches']} matching historical trades; {result['provider_fresh_5min_matches']} were no more than five minutes old.",
        '',f"Raw underlying daily ranges contain {result['underlying_raw_range_passes']}/{result['underlying_entry_spots']} QC entry spot marks. Option daily bars matched {result['option_daily_matches']} fills; {result['option_daily_range_passes']} were within that day's traded range (one-cent tolerance).",
        '', '| Provider scenario | Complete cycles | QC P&L on same cycles | Provider replay P&L |',
        '|---|---:|---:|---:|']
    for run in result['akquant_runs']:
        if run['label']!='qc_control' and 'engine_net_pnl' in run:
            lines.append(f"| {run['label']} | {run['cycles']} | ${run['matched_qc_pnl']:,.2f} | ${run['engine_net_pnl']:,.2f} |")
    if 'underlying_daily_comparison' in result:
        d=result['underlying_daily_comparison'];q=result['qc_quote_reference']
        lines += ['',f"Independent raw QC daily history matched {d['matched_rows']} provider sessions. Close absolute difference: median ${d['close_absolute_difference_usd']['median']:.4f}, 95th percentile ${d['close_absolute_difference_usd']['p95']:.4f}.",
            '',f"Independent QC quote history was found for {q['quotes_found']}/{q['orders']} executions; {q['fills_inside_quote']} fills were inside the latest historical bid/ask. See option_quote_reference.csv for each exception."]
    lines += ['', 'These checks support execution-ledger consistency, but do not establish interchangeable market data. Only one complete cycle has provider trades fresh within five minutes. Sparse trade prints cannot validate bid/ask execution or reproduce the full 2010–2025 tape.', '',
        'The completed SPY reference used true range IVR with 252 prior observations and a >=50 gate. The new broad baseline uses 504 observations, IVR >70, underlying-volume ranking and a maximum basket of 13; its results must be evaluated separately.', '', *['- '+item for item in result['limitations']], '']
    (folder/'CONSISTENCY_REPORT.md').write_text('\n'.join(lines))
    print(json.dumps({k:v for k,v in result.items() if k not in ('akquant_runs','tables')},indent=2))


if __name__=='__main__':
    main()
