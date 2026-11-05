"""Consume hash-verified staged 1m Parquet for alignment/selection smoke only.

Not publication acceptance, a funded replay, or an underlying-axis backtest.
"""
import argparse,json
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import duckdb
from .pipeline import file_hash
from .shadow import align_options
from strategies.sstrangle.poc.v087.local_engine import Leg,select


def run(proof,out):
    proof,out=Path(proof),Path(out)
    if out.exists():raise ValueError('fresh evidence path required')
    d=json.loads(proof.read_text())
    if d['native_resolution_seconds']!=60 or d['raw_to_normalized_numeric_and_key_mismatches']!=0:
        raise ValueError('unverified native minute stage')
    paths={}
    for name,item in d['artifacts'].items():
        if file_hash(item['path'])!=item['sha256']:raise ValueError('stage hash mismatch')
        paths[name]=item['path']
    c=duckdb.connect();c.execute("SET TimeZone='UTC'")
    frame=c.execute('''select q.contract_id,q.session_date,q.interval_ts,q.quote_ts,q.available_at,
        q.bid,q.ask,g.delta,g.underlying_price,g.available_at greek_available_at,
        g.underlying_ts from read_parquet(?) q join read_parquet(?) g
        on q.source=g.source and q.contract_id=g.contract_id and q.interval_ts=g.interval_ts''',
        [paths['option_nbbo'],paths['option_intraday_greeks']]).fetchdf()
    results=[]
    for day in sorted(frame.session_date.dt.strftime('%Y-%m-%d').unique()):
        for hour,minute in [(9,35)]+[(h,m) for h in range(10,16) for m in (0,30)]:
            deadline=datetime.fromisoformat(f'{day}T{hour:02}:{minute:02}:00').replace(tzinfo=ZoneInfo('America/New_York'))
            window=frame[(frame.interval_ts<deadline)&(frame.interval_ts>=deadline-timedelta(seconds=120))]
            rows=[]
            for r in window.itertuples():
                _,_,root,expiry,right,strike=r.contract_id.split(':')
                rows.append(dict(contract_id=r.contract_id,root=root,expiry=expiry,right=right,strike=float(strike),
                    # This flag establishes only the dated quoted inventory for the sampled smoke.
                    listed_asof=True,source_row_id=r.contract_id+'@'+r.interval_ts.isoformat(),
                    observed_at=r.interval_ts.isoformat(),quote_ts=None,available_at=None,
                    greek_asof=r.interval_ts.isoformat(),greek_input_at=r.underlying_ts.isoformat(),
                    greek_available_at=None,greek_model_accepted=False,frequency_seconds=60,greek_frequency_seconds=60,
                    bid=float(r.bid),ask=float(r.ask),delta=float(r.delta),spot=float(r.underlying_price)))
            sampled,rejected=align_options(rows,deadline,'sampled');strict,strict_bad=align_options(rows,deadline,'strict')
            legs,status=select([Leg(x['contract_id'],x['strike'],x['right'],x['delta'],x['bid'],x['ask'],x['spot']) for x in sampled],'condor')
            results.append(dict(decision_at=deadline.isoformat(),sampled_candidates=len(sampled),sampled_exclusions=len(rejected),
                                strict_candidates=len(strict),strict_exclusions=len(strict_bad),selection_status=status,
                                selected=[(leg.identity,q) for leg,q in legs] if legs else []))
    result=dict(version='0.8.8',scope='Real staged native1m alignment and frozen-selector smoke; assumed availability, unaccepted Greek methodology',
                proof_path=str(proof),proof_sha256=file_hash(proof),source=d['source'],joined_rows=len(frame),decisions=results,
                strict_replay_ready=False,underlying_axis_tested=False,publication_accepted=False)
    out.write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--proof',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=run(a.proof,a.out);print(json.dumps({k:v for k,v in r.items() if k!='decisions'},indent=2));print('decisions',len(r['decisions']))
