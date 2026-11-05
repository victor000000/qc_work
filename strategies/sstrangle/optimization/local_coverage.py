#!/usr/bin/env python3
"""Record immutable provider coverage and enforce no quote backtest without NBBO/OI."""
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from importlib.metadata import version
import duckdb

BASE=Path(__file__).resolve().parents[3]

def run(provider,out):
    lake=provider/'runtime/lake';release=(lake/'CURRENT').read_text().strip()
    manifest_file=lake/'snapshots'/release/'manifest.json'
    manifest=json.loads(manifest_file.read_text())
    con=duckdb.connect();tables={}
    for name in ['option_bars','option_minutes','option_nbbo','option_oi_daily','option_research_observations',
        'option_contract_history','option_greeks_daily','underlying_daily','underlying_research_daily',
        'us_futures_option_daily','us_futures_option_settlements']:
        item=manifest['stores']['history']['tables'][name]
        table=dict(rows=item['rows'],time_min=item.get('time_min'),time_max=item.get('time_max'))
        paths=[str(lake/p['path']) for p in item['partitions']]
        if paths and item['rows']:
            sources=con.execute('select source,count(*) from read_parquet(?) group by source order by 2 desc',[paths]).fetchall()
            table['source_counts']=[dict(source=s,rows=n) for s,n in sources]
        tables[name]=table
    summary=dict(created_utc=datetime.now(timezone.utc).isoformat(),provider_release=release,
        provider_manifest_sha256=hashlib.sha256(manifest_file.read_bytes()).hexdigest(),tables=tables,
        akquant_installed_version=version('akquant'),baseline_observation_end='2020-03-12',
        independent_quote_backtest_ready=False,full_period_local_optimization_ready=False,
        missing=['Bid/ask time series: option_nbbo is empty.',
            'Point-in-time option open-interest observations: option_oi_daily is empty.',
            'Historical point-in-time option listing membership: option_contract_history is empty.',
            'No local option trade series overlaps the2014-2020 frozen baseline.',
            'The earliest2024 option observations lack preceding504-sample IV history; later2026 windows may exist but broad point-in-time IV construction has not been validated.',
            'Broad futures-option chain/quote coverage and exact contract/multiplier/calendar mapping.',
            'Default brokerage margin, assignments/exercise and corporate-action cashflow model parity.'],
        permitted_current_work=['Genuine QC execution ledger replay in AKQuant.',
            'Fixed original cycle admission/quantity sensitivity using entry-known metadata.',
            'Later separate2024-2026 trade-price sensitivity with explicit modeled spreads; never label trades as executable quotes.'],
        metric_policy='No Calmar from realized-only equity, fill-event marks or inferred bid/ask. Mark-to-market quote coverage is required.')
    con.close();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(summary,indent=2))
    return summary
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--provider',type=Path,default=BASE.parent/'data_providers')
    p.add_argument('--out',type=Path,default=Path(__file__).with_name('local_results_20261019')/'coverage.json')
    a=p.parse_args();print(json.dumps(run(a.provider.resolve(),a.out.resolve()),indent=2))
