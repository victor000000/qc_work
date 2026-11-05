"""Describe genuine training entry reserve annotations; no alternative strategy replay."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import duckdb
import report

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'equity_rv_failure_results_20261019/research.duckdb'
CAMPAIGN=HERE.parent/'results/strangle_basket-calmar_20261019_182746'
ORDERS=CAMPAIGN/'SSTRANGLE_20261019_182746_cap20_stop1_guard_rv12_exit21/orders.json'
OUT=HERE/'training_capital_diagnostics_20261019'


def main():
    OUT.mkdir(exist_ok=True)
    con=duckdb.connect(str(OUT/'diagnostics.duckdb'))
    con.execute("ATTACH '"+str(SOURCE).replace("'","''")+"' AS source (READ_ONLY)")
    con.execute('''CREATE OR REPLACE TABLE training_entries AS SELECT * FROM source.closed_entries
        WHERE CAST(entry AS TIMESTAMPTZ)<TIMESTAMPTZ '2020-01-01 05:00:00+00'
        AND CAST(entry AS TIMESTAMPTZ)>=TIMESTAMPTZ '2012-01-03 05:00:00+00' ''')
    con.execute('''CREATE OR REPLACE TABLE training_batches AS SELECT batch_id::INT AS batch_id,
        count(*) AS actual_members,min(basket_count::INT) AS declared_min,max(basket_count::INT) AS declared_max,
        min(allocation_equity::DOUBLE) AS equity_min,max(allocation_equity::DOUBLE) AS equity_max,
        sum(estimated_initial_margin::DOUBLE+estimated_entry_fees::DOUBLE)/min(allocation_equity::DOUBLE) AS annotated_initial_reserve_fraction,
        min(total_collateral_fraction::DOUBLE) AS total_cap_min,max(total_collateral_fraction::DOUBLE) AS total_cap_max,
        min(entry) AS entry FROM training_entries GROUP BY batch_id''')
    bad=con.execute('''SELECT count(*) FROM training_batches WHERE actual_members!=declared_min OR declared_min!=declared_max
        OR abs(equity_max-equity_min)>.001 OR total_cap_min!=total_cap_max OR equity_min<=0
        OR annotated_initial_reserve_fraction>total_cap_min+1e-8 OR NOT isfinite(annotated_initial_reserve_fraction)''').fetchone()[0]
    if bad:raise ValueError('Incomplete batch membership/equity or opening reserve cap violation')
    orders=json.loads(ORDERS.read_text());observations=[]
    expected={(r[0],r[1]) for r in con.execute('SELECT key,entry FROM training_entries').fetchall()}
    for o in orders:
        head=o['tag'].split(';')[0]
        if not head.endswith(':OPEN') or (head[:-5],o['time']) not in expected:continue
        # Require actual complete event evidence before describing an executed entry.
        report.execution_rows([o])
        identity=report.option_identity(o['symbol']);m=report.metadata(o)
        spot=float(m['spot']);strike=identity['strike'];side=identity['call_put']
        observations.append(dict(order_id=o['id'],native_symbol=o['symbol']['id'],entry=o['time'],key=head[:-5],
            side=side,strike=strike,annotated_opening_spot=spot,strictly_otm=(strike<spot if side=='P' else strike>spot)))
    if len(observations)!=2*len(expected) or len({o['order_id'] for o in observations})!=len(observations):
        raise ValueError('Native opening leg evidence differs from complete entry membership')
    import pandas as pd
    frame=pd.DataFrame(observations);con.register('observations_frame',frame)
    con.execute('CREATE OR REPLACE TABLE entry_moneyness AS SELECT * FROM observations_frame')
    receipts={}
    for name in ('training_entries','training_batches','entry_moneyness'):
        path=OUT/(name+'.parquet');con.execute('COPY '+name+' TO ? (FORMAT PARQUET)',[str(path)])
        count=con.execute('SELECT count(*) FROM '+name).fetchone()[0]
        parquet="read_parquet('"+str(path).replace("'","''")+"')"
        for left,right in ((name,parquet),(parquet,name)):
            if con.execute('SELECT count(*) FROM (SELECT * FROM '+left+' EXCEPT ALL SELECT * FROM '+right+')').fetchone()[0]:
                raise ValueError('DuckDB/Parquet content mismatch')
        receipts[name]=dict(rows=count,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    def record(query):
        r=con.execute(query);names=[x[0] for x in r.description];return dict(zip(names,r.fetchone()))
    result=dict(utc=datetime.now(timezone.utc).isoformat(),scope='2012-2019 entry-time annotations and genuine executed opening identities only; no2020+ P&L used',
        source_orders_sha256=hashlib.sha256(ORDERS.read_bytes()).hexdigest(),source_database_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        batches=record('''SELECT count(*) AS count,median(actual_members) AS median_members,max(actual_members) AS max_members,
            median(annotated_initial_reserve_fraction) AS median_reserve_fraction,
            min(annotated_initial_reserve_fraction) AS min_reserve_fraction,max(annotated_initial_reserve_fraction) AS max_reserve_fraction
            FROM training_batches'''),
        entries=record('''SELECT count(*) AS count,sum(CASE WHEN quantity::INT=1 THEN 1 ELSE 0 END) AS one_lot_strangles,
            median(estimated_initial_margin::DOUBLE/allocation_equity::DOUBLE) AS median_margin_to_equity,
            median(estimated_initial_margin::DOUBLE/allocation_budget::DOUBLE) AS median_margin_to_root_budget FROM training_entries'''),
        opening_legs=len(observations),otm_violations=sum(not o['strictly_otm'] for o in observations),tables=receipts,
        limitations=['Reserve annotations are the native pre-entry margin/fee estimates, not the entire intraday account margin path.',
            'Observed instrument mix does not prove why untraded candidates were excluded; full eligibility/feasibility counters are needed.',
            'No claim that increasing collateral or per-root caps improves Calmar; it also changes entries and tail exposure.',
            'OTM at the annotated opening spot does not establish fresh intraday option delta; the precomputed selection delta has a separate source time.',
            'These descriptive observations are not a different-strategy replay, full account result, or independent heldout validation.'],goal_achieved=False)
    con.close();(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    b,e=result['batches'],result['entries']
    text=(f"Training capital and entry diagnosis\n\n{b['count']} completed-membership entry batches contained {e['count']} strangles. Median basket size was {b['median_members']:g}; maximum was {b['max_members']}. "
        f"The median annotated initial margin-plus-fee reserve was {b['median_reserve_fraction']:.2%} of opening equity, against the frozen 20% total cap. The maximum was {b['max_reserve_fraction']:.2%}. "
        f"There were {e['one_lot_strangles']} one-lot strangles. Median initial margin was {e['median_margin_to_root_budget']:.1%} of the root budget.\n\n"
        f"All {result['opening_legs']} genuine opening legs were strictly out of the money at their annotated opening underlying price. There is no observed at-/in-the-money opening defect in this training sample. Fresh intraday delta was not independently established by this check.\n\n"
        "The small realized basket sizes warrant reviewing eligibility and whole-contract feasibility counters when the active full trial finishes. These entry records do not identify which untraded symbols failed each gate. They do not justify increasing leverage or claim that greater deployment improves Calmar.\n\n"
        "The active candidate and original baseline remain unchanged. No P&L was resimulated, no ticker was excluded, and no Calmar result was inferred.\n")
    (OUT/'FINDINGS.txt').write_text(text);print(json.dumps({k:result[k] for k in ('batches','entries','opening_legs','otm_violations')},indent=2))


if __name__=='__main__':main()
