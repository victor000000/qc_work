"""Inspect the bounded independent PV delivery without inventing provenance.

Conditional RV calculations diagnose source basis only. Missing origin/carried/
normalization evidence is preserved, and no option backtest is claimed ready.
"""
from collections import defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
from statistics import stdev
import duckdb
import pandas as pd
from report import write_tables, noon_open

HERE = Path(__file__).resolve().parent
DELIVERY = Path('/home/vic/data_providers/runtime/var/maintenance/qc-rv-zc-20261019')
OUT = HERE / 'provider_rv_inspection_20261019'


def expected_sessions(decision, calendar):
    sessions = [decision-timedelta(days=n) for n in range(130,0,-1)]
    return [d for d in sessions if noon_open(d,calendar)][-61:]


def conditional_rv(values):
    if len(values)!=61 or any(v is None or not math.isfinite(v) or v<=0 for v in values):
        return None,None,None
    returns = [math.log(b/a) for a,b in zip(values,values[1:])]
    return stdev(returns[-20:])*math.sqrt(252),stdev(returns)*math.sqrt(252),max(map(abs,returns))


def main():
    manifest = json.loads((DELIVERY/'manifest.json').read_text())
    for name,sha in manifest.items():
        path = DELIVERY/name
        if path.resolve().parent != DELIVERY or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise ValueError('Provider delivery checksum/path mismatch: '+name)
    report = json.loads((DELIVERY/'report.json').read_text())
    counts = dict(equity_observed_daily=780,corporate_actions=2,coverage=12,zc_order_evidence=10)
    with duckdb.connect(str(DELIVERY/'availability.duckdb'),read_only=True) as conn:
        for name,count in counts.items():
            if conn.execute('select count(*) from '+name).fetchone()[0]!=count:
                raise ValueError('Independent consumer row-count mismatch: '+name)
            path = str(DELIVERY/(name+'.parquet')).replace("'","''")
            query = "select * from read_parquet('"+path+"')"
            for a,b in [(name,'('+query+')'),('('+query+')',name)]:
                if conn.execute('select count(*) from ((select * from '+a+') except all (select * from '+b+'))').fetchone()[0]:
                    raise ValueError('DuckDB/Parquet content differs: '+name)
        observations = conn.execute('select * from equity_observed_daily order by symbol,decision_date,session_label').fetchdf().to_dict('records')
        actions = conn.execute('select * from corporate_actions').fetchdf().to_dict('records')
    calendar = json.loads((HERE.parent/'research/reference/lean_market_hours_20261018.json').read_text())['entries']['Equity-usa-[*]']
    windows = defaultdict(list)
    for row in observations:
        decision=row['decision_date'].date();session=row['session_label'].date()
        if session>=decision:
            raise ValueError('Provider PV observation is not a prior session')
        windows[(row['symbol'],decision)].append(row)
    diagnostics=[]
    for (symbol,decision),rows in sorted(windows.items()):
        sessions=[r['session_label'].date() for r in rows]
        if len(rows)!=65 or len(set(sessions))!=65:
            raise ValueError('Duplicate or incomplete claimed65-observation window')
        expected=expected_sessions(decision,calendar)
        complete=sessions[-61:]==expected
        raw=conditional_rv([r['source_close'] for r in rows[-61:]]) if complete else (None,None,None)
        adjusted=conditional_rv([r['source_adj_close'] for r in rows[-61:]]) if complete else (None,None,None)
        # Null values remain unknown; they are never cast to False/current.
        unknown={field:sum(bool(pd.isna(r[field])) for r in rows) for field in
                 ('native_session_end','origin_timestamp','is_fill_forward','historically_available_at')}
        diagnostics.append(dict(symbol=symbol,decision=str(decision),observed_rows=len(rows),
            calendar_label_window_complete=complete,expected_last_session=str(expected[-1]),
            observed_last_session=str(sessions[-1]),conditional_source_close_rv20=raw[0],
            conditional_source_close_rv60=raw[1],conditional_source_close_max_abs_log_return=raw[2],
            conditional_adj_close_rv20=adjusted[0],conditional_adj_close_rv60=adjusted[1],
            source_basis_status=json.dumps(sorted({r['price_basis_status'] for r in rows})),
            unknown_provenance_counts=json.dumps(unknown),qc_scaled_raw_equivalence_verified=False,
            local_option_backtest_ready=False))
    split_checks=[]
    for action in actions:
        if action['kind']!='split':continue
        event=action['event_date'].date()
        candidates={r['session_label'].date():r for r in observations if r['symbol']==action['symbol']}
        before=[d for d in candidates if d<event]
        if event not in candidates or not before:continue
        prior=max(before)
        ratio=candidates[event]['source_close']/candidates[prior]['source_close']
        split_checks.append(dict(symbol=action['symbol'],event_date=str(event),preceding_observed_session=str(prior),
            source_event_split_value=float(action['value']),observed_source_close_ratio=ratio,
            basis_certified=False,automatic_split_adjustment_applied=False,
            note='Observed ratio is a basis diagnostic, not proof of source normalization. Do not apply a factor again or label this QC SCALED_RAW without source-method evidence.'))
    OUT.mkdir(exist_ok=True)
    write_tables(OUT,dict(window_diagnostics=diagnostics,split_basis_diagnostics=split_checks))
    result=dict(provider_delivery=str(DELIVERY),provider_manifest_sha256=hashlib.sha256((DELIVERY/'manifest.json').read_bytes()).hexdigest(),
        source_artifact_checksums_verified=True,duckdb_parquet_content_verified=True,observed_counts=counts,
        unique_underlying_session_labels=len({(r['symbol'],r['session_label'].date()) for r in observations}),
        overlapping_window_rows_are_not_unique_sessions=True,
        provider_network_requests_for_delivery=report.get('network_requests'),
        published_input_release=report.get('input_release'),
        windows=len(diagnostics),calendar_label_complete_windows=sum(d['calendar_label_window_complete'] for d in diagnostics),
        split_basis_diagnostics=split_checks,qc_scaled_raw_equivalence_verified=False,
        genuine_historical_option_quote_paths_delivered=0,local_option_backtest_ready=False,strategy_calmar_proven=False,
        limitations=['Calendar-date coverage does not establish genuine source close timestamps, carried flags or adjustment provenance.',
                     'Conditional source-close/adj-close volatility statistics are not promoted strategy features or trading results.',
                     'ZC order evidence comes from genuine consumer exports; it is not independent quote or expired-contract history.'])
    (OUT/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
