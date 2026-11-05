"""Independent full-window attempt; missing observations never become zero returns."""
import json,hashlib,sys
from pathlib import Path
from collections import Counter
import duckdb,pandas as pd,numpy as np
from local_engine import Leg,select,account,feature
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_poc_20261027_v087'
LAKE=Path('/home/vic/data_providers/runtime/lake')
snap=json.loads((OUT/'coverage_snapshot.json').read_text());manifest_path=LAKE/'snapshots'/snap['release']/'manifest.json';raw=manifest_path.read_bytes();assert hashlib.sha256(raw).hexdigest()==snap['manifest_sha256'];m=json.loads(raw)
c=duckdb.connect(':memory:');c.execute('SET threads=2');c.execute("SET memory_limit='1500MB'")
def view(name,store='history'):
 t=m['stores'][store]['tables'][name];files=[str(LAKE/p['path']) for p in t['partitions']];c.read_parquet(files).create_view(name,replace=True)
 return files
inputs={n:view(n) for n in ['option_nbbo','option_intraday_greeks','index_option_settlements','option_contract_history']}
inputs['prices_raw']=view('prices_raw','universe')
sett=c.execute("select expiry,min(settlement_value) lo,max(settlement_value) hi from index_option_settlements where underlying='SPX' group by 1 order by 1").df();assert ((sett.hi-sett.lo).abs()<1e-8).all();settlements={str(r.expiry.date()):float(r.lo) for r in sett.itertuples()}
features=c.execute("select cast(date as varchar) as session_day,high,low,close from prices_raw where symbol='QQQ' and date between '2021-01-01' and '2026-10-22' order by date").fetchall()
pd.DataFrame(features,columns=['day','high','low','close']).to_parquet(OUT/'independent_qqq_features.parquet',index=False)
# Calendar from actual exchange package; never infer zero-return market days from data absence.
import exchange_calendars as xc
cal=xc.get_calendar('XNYS');schedule=cal.schedule.loc['2022-05-16':'2026-10-22'];days=[str(x.date()) for x in schedule.index]
slots=['09:35']+[f'{h:02}:{minute:02}' for h in range(10,16) for minute in (0,30)]
# Materialize provider observations only: Greek identity/time joins are explicit.
sql="""select q.contract_id,q.session_date,q.interval_ts,q.quote_ts,q.available_at,q.bid,q.ask,
 g.delta,g.underlying_price spot,g.gamma,g.quote_ts greek_quote_ts,g.available_at greek_available_at,
 try_cast(split_part(q.contract_id,':',6) as double) strike,split_part(q.contract_id,':',5) as option_right,
 strftime(timezone('America/New_York',q.interval_ts),'%H:%M') hm
 from option_nbbo q join option_intraday_greeks g using(contract_id,interval_ts)
 where q.underlying='SPX' and g.underlying='SPX' and q.source='thetadata_v3' and g.source='thetadata_v3'
 and try_cast(split_part(q.contract_id,':',4) as date)=q.session_date
 and q.session_date between '2022-05-16' and '2026-10-22'
 and strftime(timezone('America/New_York',q.interval_ts),'%M') in ('00','30','35','34','59','29','33','58','28')"""
frame=c.execute(sql).df();assert not frame.duplicated(['contract_id','interval_ts']).any()
frame['day']=frame.session_date.dt.strftime('%Y-%m-%d');frame.to_parquet(OUT/'independent_selection_inputs.parquet',index=False)
groups={(d,h):g for (d,h),g in frame.groupby(['day','hm'])}
results=[];all_slots=[];all_trades=[]
for mode in ['strict','sampled_predecision','equal_time_sensitivity']:
 for strategy in ['C0','C1','P1']:
  for fill in (['legacy','conservative'] if mode=='equal_time_sensitivity' else ['legacy']):
   cash=100000.;records=[];trade_records=[];daily=[]
   for day in days:
    prior_equity=cash;reserve=0.;pnl=0.;observed=False;day_missing=False
    close=schedule.loc[pd.Timestamp(day),'close'].tz_convert('America/New_York').strftime('%H:%M')
    for slot in (['10:00'] if strategy=='P1' else slots):
     if slot>=close:continue
     rec=dict(mode=mode,strategy=strategy,fill=fill,day=day,slot=slot,status='missing_snapshot')
     fv=feature(features,day);rec['feature']=fv
     if strategy=='C1' and (fv is None or fv<=.016380462988098386):
      rec['status']='missing_feature' if fv is None else 'filter_skip';records.append(rec);continue
     target=pd.Timestamp(day+' '+slot);candidates=[slot] if mode=='equal_time_sensitivity' else [(target-pd.Timedelta(minutes=i)).strftime('%H:%M') for i in [1,2]]
     parts=[groups[day,h] for h in candidates if (day,h) in groups]
     g=pd.concat(parts).sort_values('interval_ts').drop_duplicates('contract_id',keep='last') if parts else None
     if g is None:day_missing=True;records.append(rec);continue
     observed=True;rec['input_time']=str(g.interval_ts.iloc[0])
     if mode=='strict':
      deadline=target.tz_localize('America/New_York').tz_convert('UTC')
      g=g[g.quote_ts.notna()&g.available_at.notna()&g.greek_available_at.notna()&(g.quote_ts<=g.available_at)&(g.available_at<=deadline)&(g.greek_available_at<=deadline)&((deadline-g.quote_ts)<=pd.Timedelta(seconds=120))]
      if g.empty:rec['status']='unknown_or_invalid_clocks';day_missing=True;records.append(rec);continue
     if day not in settlements:rec['status']='missing_settlement';day_missing=True;records.append(rec);continue
     contracts=[Leg(str(r.contract_id),float(r.strike),str(r.option_right),float(r.delta) if pd.notna(r.delta) else float('nan'),float(r.bid),float(r.ask),float(r.spot)) for r in g.itertuples()]
     legs,status=select(contracts,'put_spread' if strategy=='P1' else 'condor');rec['status']=status
     if legs is None:records.append(rec);continue
     if mode=='strict':
      times=g[g.contract_id.isin([x.identity for x,q in legs])].quote_ts
      if (times.max()-times.min()).total_seconds()>30:
       rec['status']='cross_leg_skew';day_missing=True;records.append(rec);continue
     a=account(legs,settlements[day],fill)
     if a is None:rec['status']='invalid_credit';records.append(rec);continue
     if strategy=='P1' and a['max_loss']>.02*prior_equity:rec['status']='risk_cap';records.append(rec);continue
     if reserve+a['max_loss']>prior_equity:rec['status']='local_reserve';records.append(rec);continue
     reserve+=a['max_loss'];pnl+=a['pnl'];rec['status']='filled_model';rec['legs']=json.dumps([(x.identity,q) for x,q in legs]);rec.update(a);rec['settlement']=settlements[day];trade_records.append(dict(rec));records.append(rec)
    cash+=pnl
    daily.append(dict(day=day,pnl=pnl,covered=observed and not day_missing,equity=cash))
   counts=Counter(x['status'] for x in records);net=sum(x['pnl'] for x in trade_records)
   daily_frame=pd.DataFrame(daily);daily_frame.to_parquet(OUT/f'local_{strategy}_{mode}_{fill}_daily.parquet',index=False)
   result=dict(strategy=strategy,mode=mode,fill=fill,episodes=len(trade_records),net_pnl=net,ending_cash=cash,counts=dict(counts),covered_days=int(daily_frame.covered.sum()),calendar_days=len(days),full_period_complete=counts['missing_snapshot']==0 and counts['missing_feature']==0 and counts['unknown_or_invalid_clocks']==0 and counts['missing_settlement']==0,margin_model='independent sum of theoretical reserves; not QC native',performance_label='coverage-limited diagnostic, not full-period strategy performance',extra_package_cost_sensitivity={str(x):net-x*len(trade_records) for x in [10,25,50]})
   if trade_records:
    tf=pd.DataFrame(trade_records);result['annual']={str(y):{'episodes':len(g),'net_pnl':float(g.pnl.sum())} for y,g in tf.groupby(tf.day.str[:4])}
    result['best_five_days_removed_net']=net-sum(sorted((x['pnl'] for x in daily),reverse=True)[:5])
   results.append(result);all_slots+=records;all_trades+=trade_records
pd.DataFrame(all_slots).to_parquet(OUT/'local_slots.parquet',index=False);pd.DataFrame(all_trades).to_parquet(OUT/'local_episodes.parquet',index=False)
summary=dict(release=snap['release'],results=results,independent_inputs=True,qc_trades_used_for_selection=False,strict_replay_ready=False,full_research_ready=False,limitations=['Current SPXW sample is noncontiguous; path-dependent capital is conditional on observed dates.','Greek units/model and underlying input provenance remain unaccepted.','Calendar uses XNYS as RTH session baseline; independent SPXW expiry eligibility remains a separate gate.','Gamma absent; no marked-equity/drawdown claim; local reserve is not native brokerage margin.'])
(OUT/'local_summary.json').write_text(json.dumps(summary,indent=2)+'\n');(OUT/'local_input_manifest.json').write_text(json.dumps(inputs,indent=2)+'\n')
print(json.dumps(summary,indent=2))
