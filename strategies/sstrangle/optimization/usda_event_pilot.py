"""Describe training grain positions against dated official forward notices.

This pilot is deliberately incomplete and must not be loaded as a trading calendar.
It contains no alternative-strategy returns or forecasts of event outcomes.
"""
from datetime import date,datetime,timedelta,timezone
import hashlib,json
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb
import pandas as pd
from cache_usda_pilot_sources import ROWS

HERE=Path(__file__).resolve().parent
OUT=HERE/'usda_event_pilot_20261019'
SOURCE=HERE/'training_entry_diagnostics_20261019/diagnostics.duckdb'
# Manually reviewed primary-source Upcoming Reports tables, including winners.
FACTS=[('2015-01-12','Crop Production Annual / Grain Stocks','2014-12-10'),
 ('2015-06-30','Acreage / Grain Stocks','2015-06-10'),
 ('2015-08-12','Crop Production','2015-07-10'),
 ('2016-06-30','Acreage / Grain Stocks','2016-06-10'),
 ('2019-06-11','Crop Production','2019-05-10'),
 ('2019-06-28','Acreage / Grain Stocks','2019-06-11'),
 ('2019-07-11','Crop Production','2019-06-11'),
 ('2019-08-12','Crop Production','2019-07-11')]


def main():
    OUT.mkdir(exist_ok=True)
    sources={r['document_date']:r for r in json.loads((OUT/'source_manifest.json').read_text())}
    definitions={day:dict(url=f'https://data.nass.usda.gov/Newsroom/Executive_Briefings/{year}/{name}',page_zero_based=page) for day,year,name,page in ROWS}
    events=[]
    for event_day,title,notice in FACTS:
        document=definitions[notice];cached=sources.get(notice)
        if cached and hashlib.sha256(Path(cached['file']).read_bytes()).hexdigest()!=cached['sha256']:
            raise ValueError('Cached official PDF changed')
        if date.fromisoformat(notice)>=date.fromisoformat(event_day):raise ValueError('Not a forward notice')
        events.append(dict(event_date=event_day,report=title,printed_notice_date=notice,
            source_url=document['url'],source_upcoming_page=document['page_zero_based']+1,
            cached_pdf_sha256=cached['sha256'] if cached else None,pdf_cached=bool(cached),
            publication_timestamp_verified=False,original_revision_history_verified=False,
            release_clock_time=None,complete_calendar_eligible=False))
    con=duckdb.connect(str(OUT/'event_pilot.duckdb'))
    con.execute("ATTACH '"+str(SOURCE).replace("'","''")+"' AS source (READ_ONLY)")
    con.execute("CREATE OR REPLACE TABLE training_futures AS SELECT * FROM source.training_cycles WHERE asset_type='futures'")
    frame=pd.DataFrame(events);con.register('reviewed_events',frame)
    con.execute('CREATE OR REPLACE TABLE forward_notices AS SELECT * FROM reviewed_events')
    con.execute('''CREATE OR REPLACE TABLE grain_trade_event_links AS
      SELECT c.ticker,c.entry,c.exit,c.reason,c.pnl AS observed_original_cycle_net,
        n.event_date,n.report,n.printed_notice_date,n.source_url,n.source_upcoming_page,n.pdf_cached,
        CAST(c.exit AS TIMESTAMPTZ) AT TIME ZONE 'America/New_York' AS local_exit,
        CAST(c.entry AS TIMESTAMPTZ) AT TIME ZONE 'America/New_York' AS local_entry,
        CAST(n.printed_notice_date AS DATE)<CAST(CAST(c.entry AS TIMESTAMPTZ) AT TIME ZONE 'America/New_York' AS DATE) AS notice_predates_entry,
        CAST(n.event_date AS DATE)=CAST(CAST(c.exit AS TIMESTAMPTZ) AT TIME ZONE 'America/New_York' AS DATE) AS report_date_equals_exit_date
      FROM training_futures c JOIN forward_notices n
        ON c.ticker='FUT_ZC'
        AND CAST(n.event_date AS DATE) BETWEEN
          CAST(CAST(c.entry AS TIMESTAMPTZ) AT TIME ZONE 'America/New_York' AS DATE)
          AND CAST(CAST(c.exit AS TIMESTAMPTZ) AT TIME ZONE 'America/New_York' AS DATE)''')
    if con.execute('SELECT count(*) FROM grain_trade_event_links WHERE NOT notice_predates_entry').fetchone()[0]:
        raise ValueError('A pilot release notice does not predate the original trade')
    con.execute('''CREATE OR REPLACE TABLE grain_cycles AS
      SELECT ticker,entry,exit,reason,pnl AS observed_original_cycle_net,
        (SELECT count(*) FROM grain_trade_event_links l WHERE l.ticker=c.ticker AND l.entry=c.entry) AS matching_notices,
        EXISTS(SELECT 1 FROM grain_trade_event_links l WHERE l.ticker=c.ticker AND l.entry=c.entry AND report_date_equals_exit_date) AS release_date_exit
      FROM training_futures c WHERE ticker='FUT_ZC' ''')
    tables={}
    for name in ('training_futures','forward_notices','grain_trade_event_links','grain_cycles'):
        path=OUT/(name+'.parquet');con.execute('COPY '+name+' TO ? (FORMAT PARQUET)',[str(path)])
        parquet="read_parquet('"+str(path).replace("'","''")+"')"
        for left,right in ((name,parquet),(parquet,name)):
            if con.execute('SELECT count(*) FROM (SELECT * FROM '+left+' EXCEPT ALL SELECT * FROM '+right+')').fetchone()[0]:raise ValueError('DuckDB/Parquet content mismatch')
        tables[name]=dict(rows=con.execute('SELECT count(*) FROM '+name).fetchone()[0],sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    def records(sql):
        r=con.execute(sql);columns=[d[0] for d in r.description];return [dict(zip(columns,row)) for row in r.fetchall()]
    summary=dict(utc=datetime.now(timezone.utc).isoformat(),scope='Descriptive training-period event-date association; hypothesis chosen after inspecting prior losses',
        source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),events=events,tables=tables,
        cached_pdf_documents=len(sources),uncached_document_dates=sorted(set(definitions)-set(sources)),
        grain_cycles=records('SELECT * FROM grain_cycles ORDER BY entry'),
        same_date_stop_cycles=records("SELECT * FROM grain_cycles WHERE reason='STOP' AND release_date_exit ORDER BY entry"),
        affected_winners=records("SELECT * FROM grain_cycles WHERE observed_original_cycle_net>0 AND matching_notices>0 ORDER BY entry"),
        no_event_free_grain_comparison=con.execute('SELECT count(*) FROM grain_cycles WHERE matching_notices=0').fetchone()[0]==0,
        proposed_research='Study a general pre-announcement grain-risk exit and report-day entry deferral using complete versioned public calendars; no loser-date whitelist. No next candidate is selected or queued by this pilot.',
        requirements_before_backtest=['Full2012-2026 calendar coverage, including winners/non-event intervals and all relevant grain releases.',
          'Printed forward-notice dates are preliminary evidence; validate publication availability, original revisions/reschedules/cancellations and actual release times. Do not assume every historical report released at noon.',
          'Predeclare commodity mappings, prior product-open exit deadline, entry cooldown and missing-calendar handling. Preserve all15supported roots; report effective participation.',
          'Native paired source/execution tests, then a full funded chronological backtest. Keep actual fees, margin, quote checks and no fake settlement/fills.',
          'The current full cloud trial must complete/audit and its owner stop naturally before another campaign.'],
        complete_calendar_for_backtest=False,counterfactual_pnl_computed=False,causal_effect_proven=False,
        native_event_exit_verified=False,active_strategy_changed=False,goal_achieved=False,
        limitations=['All observed training corn cycles crossed at least one reviewed release, including both winners. There is no event-free corn control group.',
          'Four stop exits share release dates; coincidence does not identify how much was caused by the release versus quote/execution behavior.',
          'Original cycle P&L is shown only as observed history. Removing those losses from the ledger would not be a valid alternate backtest.',
          f'{len(sources)} of{len(definitions)} source PDF binaries were cached. Missing local binaries: '+str(sorted(set(definitions)-set(sources)))+'. All forward tables were read with the web tool; no missing binary hash/publication timestamp is invented.',
          'These trades belong to the preserved earlier RV1.2 trial. The current combined guard/retry/AGE24 path may already change their selection or outcomes; do not transfer old losses to it as if unchanged.'])
    con.close();(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    hits=summary['same_date_stop_cycles'];wins=summary['affected_winners']
    text=(f"USDA event-risk pilot\n\nFour corn-option STOP cycles ended on reviewed scheduled crop/stock report dates. Their original net P&L totals ${sum(r['observed_original_cycle_net'] for r in hits):,.2f}. "
          f"Both profitable corn cycles also held through reviewed releases; their original net P&L totals ${sum(r['observed_original_cycle_net'] for r in wins):,.2f}. "
          "Every observed training corn cycle crossed a report, so there is no event-free corn control in this sample.\n\n"
          "The forward schedules appear in official USDA briefings dated before the affected entries. They support a prospective event-risk research hypothesis, not a causal or profitable-filter claim. A fixed whitelist of the losing dates must not become an entry rule.\n\n"
          f"The pilot is not a complete or approved backtest calendar. Original publication timestamps and revisions, reschedules/cancellations, historical release times and full 2012-2026 coverage still require validation. {len(sources)} of {len(definitions)} official PDF binaries are cached and hashed; missing documents: {sorted(set(definitions)-set(sources))}. All forward tables were read via the web tool. No missing provenance was invented.\n\n"
          "These observations describe the older RV1.2 trial, not the current combined strategy. The active guard/retry/holding-cap changes may already alter these trades or losses.\n\nA possible future experiment is to close grain risk at a prior product-open session before preannounced releases and defer new entries on release days. It must use complete, versioned calendars and native fills; it must not simply delete old losing trades. No strategy code was changed or new QC campaign submitted. Calmar above 2 remains unverified.\n\nSources:\n"+
          '\n'.join(f"{row['document_date']}: {row['url']} (Upcoming Reports, page {row['page_zero_based']+1})" for row in [dict(document_date=k,**v) for k,v in definitions.items()])+'\n')
    (OUT/'FINDINGS.txt').write_text(text)
    print(json.dumps(dict(training_futures=tables['training_futures']['rows'],grain_cycles=tables['grain_cycles']['rows'],same_date_stops=len(hits),original_same_date_stop_net=sum(r['observed_original_cycle_net'] for r in hits),event_exposed_winners=len(wins),calendar_backtest_ready=False),indent=2))


if __name__=='__main__':main()
