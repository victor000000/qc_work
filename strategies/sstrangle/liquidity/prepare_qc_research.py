"""Prepare actual QC tape for local feature research; never fabricate quotes or trades."""
import argparse
import hashlib
import json
from pathlib import Path
import duckdb

def prepare(campaign, out):
    campaign=Path(campaign).resolve();out=Path(out).resolve()
    summary=json.loads((campaign/'research_report/summary.json').read_text())
    if len(summary['variants'])!=1:raise ValueError('Choose an explicit single-variant source')
    audited=summary['variants'][0]['summary']
    if not audited['period_complete']:raise ValueError('Full-period audited control required')
    src=campaign/audited['name']/'research_report'
    if out.exists():raise FileExistsError('Preserve previous research output: '+str(out))
    out.mkdir(parents=True)
    con=duckdb.connect(str(out/'research.duckdb'))
    hashes={}
    for table in ['executions','cycles','entries','batches','daily_equity']:
        p=src/(table+'.parquet');hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        con.execute(f'CREATE TABLE {table} AS SELECT * FROM read_parquet(?)',[str(p)])
    # Full native strategy IDs and opening timestamps, not display tickers.
    for table,key in [('cycles','ticker,entry'),('entries','key,entry')]:
        assert con.execute(f'SELECT count(*) FROM (SELECT {key},count(*) n FROM {table} GROUP BY {key} HAVING n<>1)').fetchone()[0]==0
    con.execute('''CREATE TABLE entry_features AS SELECT key AS strategy_key,entry,
      CAST(ivr AS DOUBLE) ivr,CAST(iv AS DOUBLE) iv,CAST(volume AS DOUBLE) underlying_volume,
      try_cast(rv20 AS DOUBLE) rv20,try_cast(rv60 AS DOUBLE) rv60,try_cast(iv_rv AS DOUBLE) iv_rv,
      rv_policy,rv_last_session,CAST(put_delta AS DOUBLE) put_delta,CAST(call_delta AS DOUBLE) call_delta,
      CAST(spot AS DOUBLE) spot,CAST(quantity AS INTEGER) quantity,
      CAST(estimated_initial_margin AS DOUBLE) initial_margin,
      CAST(allocation_equity AS DOUBLE) opening_account_equity FROM entries''')
    con.execute('''CREATE TABLE cycle_labels AS SELECT *, CASE WHEN ticker LIKE 'FUT_%' THEN 'futures' ELSE 'equity_etf' END asset_group,
      CASE WHEN CAST(exit AS TIMESTAMPTZ) < TIMESTAMPTZ '2020-01-01 05:00:00+00' THEN 'training' ELSE 'evaluation' END period FROM cycles''')
    con.execute('''CREATE TABLE research_join AS SELECT l.*,f.* EXCLUDE(strategy_key,entry,quantity)
      FROM cycle_labels l JOIN entry_features f ON l.ticker=f.strategy_key AND l.entry=f.entry''')
    assert con.execute('SELECT count(*) FROM research_join').fetchone()[0]==audited['cycles']
    totals=con.execute('SELECT count(*),sum(fee),sum(-quantity*qc_price*multiplier-fee) FROM executions').fetchone()
    assert totals[0]==audited['fills'] and abs(totals[1]-audited['fees'])<1e-6 and abs(totals[2]-audited['net_pnl'])<1e-6
    assert abs(con.execute('SELECT sum(pnl) FROM cycles').fetchone()[0]-audited['net_pnl'])<1e-6
    assert con.execute('SELECT count(*) FROM (SELECT symbol_id,sum(quantity) q FROM executions GROUP BY symbol_id HAVING abs(q)>1e-9)').fetchone()[0]==0
    con.execute('''CREATE TABLE contract_quote_requests AS SELECT symbol_id,underlying_id,option_root,
      expiry,call_put,strike,multiplier,security_type,min(CAST(timestamp AS TIMESTAMPTZ)) first_fill_utc,
      max(CAST(timestamp AS TIMESTAMPTZ)) last_fill_utc,count(*) fill_events
      FROM executions GROUP BY ALL''')
    con.execute('''CREATE TABLE loss_attribution AS SELECT period,asset_group,reason,count(*) cycles,
      sum(pnl) net_pnl,sum(fees) fees,sum(rolls) rolls,avg(CASE WHEN pnl>0 THEN 1.0 ELSE 0.0 END) win_rate
      FROM cycle_labels GROUP BY ALL ORDER BY period,asset_group,reason''')
    names=['entry_features','cycle_labels','research_join','contract_quote_requests','loss_attribution']
    for table in names:
        dest=str(out/(table+'.parquet')).replace("'","''")
        con.execute(f"COPY {table} TO '{dest}' (FORMAT PARQUET)")
    cols=[d[0] for d in con.execute('SELECT * FROM loss_attribution').description]
    attribution=[dict(zip(cols,row)) for row in con.fetchall()]
    report={'source_campaign':str(campaign),'source_hashes':hashes,'cycles':audited['cycles'],
      'fills':totals[0],'fees':totals[1],'net_pnl':totals[2], 'account':audited['account'],
      'join_coverage':'Every audited cycle joins one opening annotation by native key and opening timestamp',
      'features_source':'QC opening annotations only; provider as-of features pending validated release',
      'loss_attribution':attribution,'historical_top_n_membership_ready':False,
      'independent_backtest_performed':False,'classification':'Descriptive actual baseline analysis; not counterfactual portfolio returns',
      'provider_request_scope':'Actual held contract windows only; candidate inventory and alternatives still required'}
    con.close();(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('campaign');p.add_argument('out');a=p.parse_args()
    r=prepare(a.campaign,a.out);print(json.dumps({k:r[k] for k in ['cycles','fills','fees','net_pnl','loss_attribution']},indent=2))
