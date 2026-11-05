#!/usr/bin/env python3
"""Explore causal admission/sizing on observed closed cycles; never compute Calmar.

This is a fixed-exit sensitivity, not an independent backtest: altered positions
would change margin exits, future entry dates and the set of eligible candidates.
"""
from __future__ import annotations
import argparse,csv,hashlib,itertools,json,math,time
from datetime import datetime,timezone
from pathlib import Path
import duckdb

ROOT=Path(__file__).resolve().parents[3]
DEFAULT=ROOT/'strategies/sstrangle/results/strangle_basket_20261018_191012/baseline_report'

def read_csv(path):
    with path.open() as f:return list(csv.DictReader(f))

def load_cycles(folder):
    entries={(e['key'],e['entry']):e for e in read_csv(folder/'entries.csv')}
    output=[]
    for i,c in enumerate(read_csv(folder/'cycles.csv')):
        e=entries[(c['ticker'],c['entry'])]
        q=int(c['quantity'])
        assert q>0 and q==int(e['quantity'])
        output.append(dict(cycle_id=i,key=c['ticker'],entry=c['entry'],exit=c['exit'],
            batch_id=int(c['batch_id']),baseline_quantity=q,baseline_pnl=float(c['pnl']),
            initial_margin_per_lot=float(e['estimated_initial_margin'])/q,
            entry_fees_per_lot=float(e['estimated_entry_fees'])/q,
            original_basket_count=int(e['basket_count']),ivr=float(e['ivr']),
            iv=float(e['iv']),volume=float(e['volume']),spot=float(e['spot']),
            asset='futures' if c['ticker'].startswith('FUT_') else 'equity',
            training=c['entry'][:10]<='2019-12-31',exit_reason=c['reason']))
    assert len(output)==145 and abs(sum(c['baseline_pnl'] for c in output)+60042.29)<1e-6
    return output

def size(c,config):
    # All gates use OPEN annotations. No realized P&L or exit fields enter here.
    if c['ivr']<=config['min_ivr'] or c['iv']>config['max_iv']:return 0
    if config['asset']!='all' and c['asset']!=config['asset']:return 0
    if c['original_basket_count']<config['min_original_basket_count']:return 0
    budget=60000*min(config['total_fraction']/c['original_basket_count'],config['per_symbol_fraction'])
    perlot=c['initial_margin_per_lot']+c['entry_fees_per_lot']
    assert perlot>0
    # No leverage increase or change to the original candidate list is modeled.
    return min(c['baseline_quantity'],math.floor(budget/perlot))

def configs():
    for total,per,ivr,iv,asset,minbasket in itertools.product(
        [.1,.2,.3,.5],[.025,.05,.075,.1],[70,80,90],[.5,1.0,100.0],['all','equity','futures'],[1,3]):
        if per>total:continue
        yield dict(total_fraction=total,per_symbol_fraction=per,min_ivr=ivr,max_iv=iv,
            asset=asset,min_original_basket_count=minbasket)

def run(folder,out):
    started=time.perf_counter();out.mkdir(parents=True,exist_ok=True)
    cycles=load_cycles(folder);attempts=[];decisions=[]
    for cfg in configs():
        ident=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()[:12]
        row=dict(config_id=ident,**cfg,training_cycles=0,evaluation_cycles=0,
            training_fixed_exit_pnl=0.,evaluation_fixed_exit_pnl=0.,training_losing_cycles=0,
            retained_baseline_margin_exits=0)
        for c in cycles:
            q=size(c,cfg)
            if not q:continue
            pnl=c['baseline_pnl']*q/c['baseline_quantity']
            label='training' if c['training'] else 'evaluation'
            row[label+'_cycles']+=1;row[label+'_fixed_exit_pnl']+=pnl
            row['training_losing_cycles']+=int(c['training'] and pnl<0)
            row['retained_baseline_margin_exits']+=int(c['exit_reason']=='MARGIN')
            decisions.append(dict(config_id=ident,cycle_id=c['cycle_id'],quantity=q,
                scaled_fixed_exit_pnl=pnl,entry=c['entry'],exit=c['exit'],key=c['key']))
        attempts.append(row)
    # Evaluation P&L is deliberately not consulted for ranking.
    eligible=[a for a in attempts if a['training_cycles']>=40]
    ranked=sorted(eligible,key=lambda a:(-a['training_fixed_exit_pnl'],a['config_id']))
    import pandas as pd
    con=duckdb.connect(str(out/'local_screen.duckdb'))
    for name,rows in [('cycles',cycles),('attempts',attempts),('decisions',decisions)]:
        frame=pd.DataFrame(rows);con.register('frame',frame)
        con.execute(f'create or replace table {name} as select * from frame')
        con.execute(f"copy {name} to '{out/name}.parquet' (format parquet)")
        frame.to_csv(out/(name+'.csv'),index=False)
    con.close()
    summary=dict(created_utc=datetime.now(timezone.utc).isoformat(),classification='exploratory_fixed_exit_sensitivity_only',
        source=str(folder),source_hashes={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in ['cycles.csv','entries.csv']},
        baseline_cycles=len(cycles),attempts=len(attempts),eligible_training_attempts=len(ranked),
        runtime_seconds=time.perf_counter()-started,selection_uses_evaluation=False,
        training_ranked_top10=ranked[:10],valid_calmar=None,
        selected_for_qc_by_this_screen=None,
        limitations=[
          'This conditions on the original entry opportunities, original batch sizes and original exits.',
          'Positive fixed-exit P&L does not establish CAGR, marked drawdown or Calmar; no such metric is calculated.',
          'Baseline stopped March2020: no2020-2026 full evaluation data exist here.',
          'A changed quantity or filtered basket changes margin, liquidation times, later candidates and re-entry dates.',
          'Margin per lot is linearly approximated from original entry; portfolio-margin offsets and slippage are not simulated.',
          'Post-entry margin-event timing is endogenous; the original MARGIN closes are retained only as sensitivity inputs.',
          'Fees scale linearly as an explicit sensitivity; brokerage minimums and changed execution impact need cloud validation.',
          'No alternative stop/profit time, roll, strike or monthly expiration can be optimized with these fills alone.',
          'Known baseline losses were previously inspected; these screens are research and not pristine out-of-sample validation.'
        ])
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['limitations','source_hashes']},indent=2))
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,default=DEFAULT)
    p.add_argument('--out',type=Path,default=Path(__file__).with_name('local_results_20261019'))
    a=p.parse_args();run(a.baseline.resolve(),a.out.resolve())
if __name__=='__main__':main()
