#!/usr/bin/env python3
"""Inspect immutable option tradebar coverage without fabricating quotes or P&L."""
import argparse,hashlib,json,math
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import duckdb

def json_safe(value):
    if isinstance(value,dict):return {k:json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [json_safe(v) for v in value]
    if value is None:return None
    if isinstance(value,float):return value if math.isfinite(value) else None
    if isinstance(value,(datetime,date)):return value.isoformat()
    if hasattr(value,'item'):return json_safe(value.item())
    return value

ROOT=Path(__file__).resolve().parents[3]
TARGETS=['SPY','QQQ','IWM','AAPL','MSFT','AMZN','NVDA','TSLA','TLT','GLD','IBIT']

def run(provider,out):
    out.mkdir(parents=True,exist_ok=True)
    lake=provider/'runtime/lake';release=(lake/'CURRENT').read_text().strip()
    mf=lake/'snapshots'/release/'manifest.json';manifest=json.loads(mf.read_text());con=duckdb.connect(str(out/'coverage.duckdb'))
    for table in ['iv_history','option_bars','option_greeks_daily','option_minutes','us_futures_option_daily']:
        files=[str(lake/p['path']) for p in manifest['stores']['history']['tables'][table]['partitions']]
        con.execute(f'create or replace view {table} as select * from read_parquet({files!r})')
    # No cross-source stitching and no duplicate dates count as additional samples.
    con.execute('''create or replace table iv_sample_counts as
      with valid as (select source,underlying,day,min(atm_iv) iv
        from iv_history where atm_iv>0 and isfinite(atm_iv) group by1,2,3),
      numbered as(select *,row_number()over(partition by source,underlying order by day) n from valid)
      select source,underlying,count(*) total_valid_dates,min(day) first_date,max(day) last_date,
       count(*)filter(where day<'2026-09-30') completed_dates_before_sep30,
       count(*)filter(where day<'2026-10-16') completed_dates_before_oct16,
       min(day)filter(where n=504) sample504_completed_date
      from numbered group by1,2'''.replace('by1','by 1'))
    con.execute('''create or replace table equity_session_dates as
      select distinct day from option_bars where source='alpaca' and underlying='SPY' ''')
    con.execute('''create or replace table iv_first_entry_dates as select i.*,
      (select min(day) from equity_session_dates where day>i.sample504_completed_date) first_observed_equity_entry_session
      from iv_sample_counts i''')
    # Last completed signal session; only subsequent observed SPY session is candidate entry.
    # These are provenance/coverage candidates, not verified original screen or brokerage orders.
    quoted=','.join("'"+s+"'" for s in TARGETS)
    con.execute(f'''create or replace table signal_legs as
      with g as(select g.*,(select min(day) from equity_session_dates where day>g.day) entry_day
       from option_greeks_daily g where source='alpaca_atm' and underlying in ({quoted})
        and abs(delta) between .16 and .22 and iv>0 and isfinite(iv)
        and isodow(expiry)=5 and extract(day from expiry) between15 and21),
      eligible as(select *,row_number()over(partition by underlying,day,expiry,call_put
        order by abs(abs(delta)-.19),strike,symbol) choice from g
        where date_diff('day',entry_day,expiry) between35 and95 and date_diff('day',day,entry_day)<=4)
      select * from eligible where choice=1'''.replace('between15','between 15').replace('and21','and 21').replace('between35','between 35').replace('and95','and 95'))
    con.execute('''create or replace table monthly_pairs as
      with paired as(select underlying,day signal_day,entry_day,expiry,
        max(symbol)filter(where call_put='P') put_symbol,
        max(symbol)filter(where call_put='C') call_symbol,
        max(delta)filter(where call_put='P') put_delta,
        max(delta)filter(where call_put='C') call_delta
        from signal_legs group by1,2,3,4 having count(distinct call_put)=2),
      choice as(select *,row_number()over(partition by underlying,entry_day
          order by expiry) expiry_choice from paired)
      select *,(select min(day) from equity_session_dates where day>=expiry-21) time_exit_day
      from choice where expiry_choice=1'''.replace('by1','by 1'))
    # Presence only: last trade prices are NOT executable bid/ask or noon marks.
    con.execute('''create or replace table pair_coverage as
      with bars as(select symbol,day,min(open) open_price,min(close) close_price
         from option_bars where source='alpaca' group by1,2),
      mins as(select symbol,cast(ts_utc as date) as day,count(*) n
         from option_minutes where source='alpaca_1min' group by1,2)
      select p.*,i.total_valid_dates ibkr_total_iv_dates,i.sample504_completed_date,
       i.sample504_completed_date<p.entry_day full504_prior_dates,
       ep.open_price>0 put_entry_trade_open,ec.open_price>0 call_entry_trade_open,
       xp.close_price>0 put_time_exit_trade_close,xc.close_price>0 call_time_exit_trade_close,
       coalesce(mp.n,0) put_entry_minute_bars,coalesce(mc.n,0) call_entry_minute_bars,
       coalesce(mxp.n,0) put_exit_minute_bars,coalesce(mxc.n,0) call_exit_minute_bars,
       (select count(distinct m.day) from mins m where m.symbol=p.put_symbol and m.day between p.entry_day and p.time_exit_day) put_held_minute_days,
       (select count(distinct m.day) from mins m where m.symbol=p.call_symbol and m.day between p.entry_day and p.time_exit_day) call_held_minute_days,
       (select count(*) from equity_session_dates d where d.day between p.entry_day and p.time_exit_day) expected_held_sessions
      from monthly_pairs p left join iv_sample_counts i on i.underlying=p.underlying and i.source='ibkr_tws30d'
       left join bars ep on ep.symbol=p.put_symbol and ep.day=p.entry_day
       left join bars ec on ec.symbol=p.call_symbol and ec.day=p.entry_day
       left join bars xp on xp.symbol=p.put_symbol and xp.day=p.time_exit_day
       left join bars xc on xc.symbol=p.call_symbol and xc.day=p.time_exit_day
       left join mins mp on mp.symbol=p.put_symbol and mp.day=p.entry_day
       left join mins mc on mc.symbol=p.call_symbol and mc.day=p.entry_day
       left join mins mxp on mxp.symbol=p.put_symbol and mxp.day=p.time_exit_day
       left join mins mxc on mxc.symbol=p.call_symbol and mxc.day=p.time_exit_day'''.replace('by1','by 1'))
    con.execute('''create or replace table per_underlying_pairs as select underlying,count(*) potential_paired_signal_dates,
      count(*)filter(where entry_day<='2026-09-30') paired_entries_to_requested_end,
      count(*)filter(where full504_prior_dates) warmed_pair_entries,
      count(*)filter(where full504_prior_dates and entry_day<='2026-09-30') warmed_pair_entries_to_requested_end,
      count(*)filter(where put_entry_trade_open and call_entry_trade_open) both_entry_trade_opens,
      count(*)filter(where put_time_exit_trade_close and call_time_exit_trade_close) both_exit_trade_closes,
      count(*)filter(where full504_prior_dates and put_entry_trade_open and call_entry_trade_open and
        put_time_exit_trade_close and call_time_exit_trade_close) fully_warmed_completed_trade_paths,
      count(*)filter(where time_exit_day is not null and expected_held_sessions>0 and put_held_minute_days=expected_held_sessions and call_held_minute_days=expected_held_sessions) both_legs_have_at_least_one_trade_per_held_day,
      count(*)filter(where put_entry_minute_bars>0 and call_entry_minute_bars>0) both_entry_minute_days,
      count(*)filter(where put_exit_minute_bars>0 and call_exit_minute_bars>0) both_exit_minute_days
      from pair_coverage group by underlying''')
    con.execute('''create or replace table warmed_futures_trade_coverage as
       select i.source iv_source,i.underlying,i.completed_dates_before_sep30,i.sample504_completed_date,
        count(d.contract_id) local_option_daily_rows
       from iv_sample_counts i left join us_futures_option_daily d on d.root=i.underlying
       where i.completed_dates_before_sep30>=504 group by1,2,3,4'''.replace('by1','by 1'))
    tables=['iv_sample_counts','iv_first_entry_dates','signal_legs','monthly_pairs','pair_coverage','per_underlying_pairs','warmed_futures_trade_coverage']
    counts={}
    for t in tables:
        counts[t]=con.execute(f'select count(*) from {t}').fetchone()[0]
        con.execute(f"copy {t} to '{out/t}.parquet' (format parquet)")
        assert con.execute('select count(*) from read_parquet(?)',[str(out/t)+'.parquet']).fetchone()[0]==counts[t]
        con.execute(f"copy {t} to '{out/t}.csv' (header,delimiter ',')")
    total=con.execute('select count(*) from pair_coverage where full504_prior_dates and put_entry_trade_open and call_entry_trade_open and put_time_exit_trade_close and call_time_exit_trade_close').fetchone()[0]
    details=con.execute('select * from per_underlying_pairs order by underlying').fetchdf().to_dict('records')
    cursor=con.execute(f"select * from iv_first_entry_dates where underlying in ({quoted}) order by underlying,source")
    ivrequested=[dict(zip([c[0] for c in cursor.description],row)) for row in cursor.fetchall()]
    summary=dict(created_utc=datetime.now(timezone.utc).isoformat(),provider_release=release,
      manifest_sha256=hashlib.sha256(mf.read_bytes()).hexdigest(),requested_end='2026-09-30',
      extended_inventory_end='2026-10-16',target_underlyings=TARGETS,table_rows=counts,
      fully_warmed_completed_trade_paths=total,per_underlying_pairs=details,iv_target_counts=ivrequested,
      decision='Insufficient completed warmed paths; no trade-price P&L or Calmar calculation is justified.' if not total else 'Coverage candidates only; review provenance and modeled costs before any sensitivity.',
      no_nbbo_fabricated=True,no_performance_claim=True,backtest_run=False,
      limitations=[
       'ibkr_tws30d underlying IV is a different source/tenor from QC option-derived45DTE ATM IV; it is not automatically interchangeable.',
       'A completed calendar day does not prove historical available_at; IV/Greeks point-in-time provenance remains uncertified.',
       'No OI, NBBO or historical listing membership. Delta-selected contracts are observed sparse ATM-model records, not a full historical chain.',
       'Monthly equity option rule uses third Friday. Futures product expiry rules and exact native contract mapping are separate.',
       'Signal is prior completed observed Greek session, entry next observed SPY session; no same-day close is used for entry selection.',
       'At least one minute trade per held day does not mean continuous15-minute prices, simultaneous paired marks or executable quotes.',
       'Session reference is observed SPY trade-bar dates, not independent exchange-calendar verification.',
       'Coverage alone cannot verify adjusted contract multipliers, assignments, corporate actions, margin or spreads.',
       'Sparse potential pairs may skip an earlier unpaired expiry: these are coverage upper bounds, not original strategy admission.',
       'No missing day/side is interpolated and no alternative exit, quote, return or MDD is fabricated.'
      ])
    summary['parquet_rowcounts_verified']=True
    summary=json_safe(summary)
    con.close();(out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['iv_target_counts','limitations']},indent=2,allow_nan=False))
    return summary
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--provider',type=Path,default=ROOT.parent/'data_providers')
    p.add_argument('--out',type=Path,default=Path(__file__).with_name('local_tradebar_results_20261019'))
    a=p.parse_args();run(a.provider.resolve(),a.out.resolve())
