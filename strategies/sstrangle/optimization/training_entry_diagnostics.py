"""Describe audited closed training cycles; never simulate alternate strategy returns."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import duckdb

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'equity_rv_failure_results_20261019'
OUT=HERE/'training_entry_diagnostics_20261019'


def main():
    summary=json.loads((SOURCE/'summary.json').read_text())
    if not summary['closed_prefix_entry_rule_audit'] or not summary['all_rust_python_fills_equal']:
        raise ValueError('Require audited source closed prefix and genuine Rust/Python fill agreement')
    OUT.mkdir(exist_ok=True)
    con=duckdb.connect(str(OUT/'diagnostics.duckdb'))
    con.execute("ATTACH '"+str(SOURCE/'research.duckdb').replace("'","''")+"' AS source (READ_ONLY)")
    # Native execution timestamps, not displayed ticker aliases, identify entries.
    con.execute('''CREATE OR REPLACE TABLE training_cycles AS
        SELECT c.*, e.ivr::DOUBLE AS entry_ivr, e.iv::DOUBLE AS entry_iv,
          try_cast(e.iv_rv AS DOUBLE) AS entry_iv_rv,
          e.estimated_initial_margin::DOUBLE AS entry_margin,
          CASE WHEN starts_with(c.ticker,'FUT_') THEN 'futures' ELSE 'equity_etf' END AS asset_type,
          c.initial_credit / e.estimated_initial_margin::DOUBLE AS opening_credit_to_margin,
          c.pnl / c.initial_credit AS net_pnl_in_opening_credits
        FROM source.closed_cycles c JOIN source.closed_entries e
          ON c.ticker=e.key AND c.entry=e.entry
        WHERE CAST(c.exit AS TIMESTAMPTZ) < TIMESTAMPTZ '2020-01-01 05:00:00+00'
          AND CAST(c.entry AS TIMESTAMPTZ) >= TIMESTAMPTZ '2012-01-03 05:00:00+00' ''')
    duplicate_entries=con.execute('SELECT count(*) FROM (SELECT key,entry,count(*) n FROM source.closed_entries GROUP BY key,entry HAVING n!=1)').fetchone()[0]
    expected_training=con.execute("SELECT count(*) FROM source.closed_cycles WHERE CAST(exit AS TIMESTAMPTZ)<TIMESTAMPTZ '2020-01-01 05:00:00+00' AND CAST(entry AS TIMESTAMPTZ)>=TIMESTAMPTZ '2012-01-03 05:00:00+00'").fetchone()[0]
    if duplicate_entries or con.execute('SELECT count(*) FROM training_cycles').fetchone()[0]!=expected_training:
        raise ValueError('Training feature join dropped or multiplied authentic closed cycles')
    all_count=con.execute('SELECT count(*) FROM source.closed_cycles').fetchone()[0]
    if all_count!=summary['closed_cycles']:raise ValueError('Source cycle count differs from audit')
    invalid=con.execute('''SELECT count(*) FROM training_cycles WHERE entry_ivr<=70 OR NOT isfinite(entry_ivr)
        OR initial_credit<=0 OR entry_margin<=0 OR NOT isfinite(opening_credit_to_margin)''').fetchone()[0]
    if invalid:raise ValueError('Invalid audited training entry features')
    queries={
      'by_asset':'''SELECT asset_type,count(*) AS closed_cycles,sum(pnl) AS actual_closed_net,
        sum(fees) AS actual_closed_fees,sum(CASE WHEN pnl>0 THEN 1 ELSE 0 END)::DOUBLE/count(*) AS winning_cycle_fraction,
        avg(pnl) FILTER (WHERE pnl>0) AS mean_winning_cycle_net,avg(pnl) FILTER (WHERE pnl<=0) AS mean_losing_cycle_net,
        median(entry_ivr) AS median_entry_ivr,median(opening_credit_to_margin) AS median_credit_to_margin,
        median(net_pnl_in_opening_credits) AS median_net_credit_units FROM training_cycles GROUP BY asset_type''',
      'by_ivr_band':'''SELECT asset_type,CASE WHEN entry_ivr<80 THEN '(70,80)' WHEN entry_ivr<90 THEN '[80,90)' ELSE '[90,100]' END AS ivr_band,
        count(*) AS closed_cycles,sum(pnl) AS actual_closed_net,sum(fees) AS actual_closed_fees,
        sum(CASE WHEN pnl>0 THEN 1 ELSE 0 END)::DOUBLE/count(*) AS winning_cycle_fraction,
        min(entry_ivr) AS min_ivr,max(entry_ivr) AS max_ivr FROM training_cycles GROUP BY ALL''',
      'by_exit':'''SELECT asset_type,reason,count(*) AS closed_cycles,sum(pnl) AS actual_closed_net,
        sum(fees) AS actual_closed_fees,median(net_pnl_in_opening_credits) AS median_net_credit_units,
        max(-net_pnl_in_opening_credits) AS worst_loss_credit_units FROM training_cycles GROUP BY ALL'''}
    for name,sql in queries.items():con.execute('CREATE OR REPLACE TABLE '+name+' AS '+sql)
    tables=['training_cycles',*queries]
    receipts={}
    for name in tables:
        path=OUT/(name+'.parquet')
        con.execute('COPY '+name+' TO ? (FORMAT PARQUET)',[str(path)])
        count=con.execute('SELECT count(*) FROM '+name).fetchone()[0]
        for left,right in [(name,"read_parquet('"+str(path)+"')"),("read_parquet('"+str(path)+"')",name)]:
            if con.execute('SELECT count(*) FROM (SELECT * FROM '+left+' EXCEPT ALL SELECT * FROM '+right+')').fetchone()[0]:
                raise ValueError('DuckDB/Parquet content differs')
        receipts[name]=dict(rows=count,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    def rows(name):
        result=con.execute('SELECT * FROM '+name+' ORDER BY ALL');names=[r[0] for r in result.description]
        return [dict(zip(names,row)) for row in result.fetchall()]
    result=dict(utc=datetime.now(timezone.utc).isoformat(),scope='Actual closed training2012-2019 cycles from preserved failed RV1.2 run; no2020+ outcomes in these tables',
        source_backtest=summary['backtest_id'],source_failed=True,full_period_completed=False,
        source_files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE/'summary.json',SOURCE/'research.duckdb')},
        closed_training_cycles=receipts['training_cycles']['rows'],by_asset=rows('by_asset'),by_ivr_band=rows('by_ivr_band'),by_exit=rows('by_exit'),tables=receipts,
        limitations=['Descriptive closed-cycle groups only; no alternate strategy replay or account Calmar.',
          'Changing a filter alters basket membership/sizing, flat times and future opportunities; summing retained trades is not a valid counterfactual backtest.',
          'No threshold selected from these groups; no claim that stronger IVR would improve performance.',
          'Training period and native failure fixtures were previously inspected; no pristine out-of-sample claim.',
          'Futures and equity option IV models differ; IVR ranks own histories, not cross-asset variance risk premiums.'],goal_achieved=False)
    con.close();(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('closed_training_cycles','by_asset','by_ivr_band','by_exit')},indent=2))


if __name__=='__main__':main()
