#!/usr/bin/env python3
"""Whole-cycle entry-filter research, audited through actual AKQuant executions."""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path

import duckdb
import pandas as pd

from prepare import executions, write_csv
from replay import assign_cycles, run_engine

HERE = Path(__file__).resolve().parent


def allowed(feature, cfg):
    if float(feature['ivr']) < cfg['ivr']:
        return False
    if cfg['iv_rv'] is not None:
        rv = float(feature.get('rv') or 0)
        if rv <= 0 or float(feature['iv']) / rv < cfg['iv_rv']:
            return False
    return cfg['trend'] is None or (feature.get('trend_z') not in (None, '')
                                    and abs(float(feature['trend_z'])) <= cfg['trend'])


def partition(cycles, end):
    # Purge any cycle whose outcome crosses the discovery boundary.
    train = [c for c in cycles if c['entry'][:10] <= end and c['exit'][:10] <= end]
    valid = [c for c in cycles if c['entry'][:10] > end]
    return train, valid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen_plan = source.parent/'research_plan.json'
    plan_path = frozen_plan if frozen_plan.exists() else HERE.parent/'single_research_plan.json'
    plan = json.loads(plan_path.read_text())
    (out/'plan.json').write_text(json.dumps(plan,indent=2))
    orders_path = source/'orders.json'
    orders = json.loads(orders_path.read_text())
    rows = executions(orders)
    if not rows:
        (out/'status.json').write_text(json.dumps({'status':'no baseline executions; cannot optimize'}))
        return
    assign_cycles(rows)
    write_csv(out/'qc_executions.csv',rows)
    cycles = list(csv.DictReader((source/'cycles.csv').open()))
    features = list(csv.DictReader((source/'entry_features.csv').open()))
    by_entry = {pd.Timestamp(r['timestamp']).value:r['cycle_id'] for r in rows if r['tag'].split(';')[0].endswith(':OPEN')}
    by_features = {pd.Timestamp(f['entry']).value:f for f in features}
    for c in cycles:
        key = pd.Timestamp(c['entry']).value
        c['cycle_id'] = by_entry[key]
        c['features'] = by_features[key]
        c['pnl'] = float(c['pnl'])
        c['executions'] = sum(r['cycle_id']==c['cycle_id'] for r in rows)
    full = json.loads((source/'backtest.json').read_text())['backtest']
    capital = float(full['runtimeStatistics'].get('initial_cash',250000))
    ticker = cycles[0]['ticker']
    for r in rows:
        r['age_minutes'] = None
    prices = {int(r['order_id']):float(r['qc_price']) for r in rows}
    _, control = run_engine(rows,prices,out/'baseline_control',initial_cash=capital)
    expected = json.loads((source/'audit.json').read_text())['pnl']
    if abs(control['engine_net_pnl']-expected) > .001:
        raise ValueError('Local full control differs from QC audited ledger')
    train, valid = partition(cycles,plan['discovery_end'])
    cache = {}

    def evaluate(subset, phase):
        ids = sorted(c['cycle_id'] for c in subset)
        key = phase+'_'+hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:12]
        if key in cache:
            return cache[key]
        selected = [r for r in rows if r['cycle_id'] in ids]
        if selected:
            _, audit = run_engine(selected,prices,out/key,initial_cash=capital)
            net = audit['engine_net_pnl']
        else:
            net = 0.0
        expected_net = sum(c['pnl'] for c in subset)
        if abs(expected_net-net)>.001:
            raise ValueError('Filtered engine P&L differs from whole-cycle ledger')
        result = dict(cycles=len(ids),executions=len(selected),net_pnl=net,
                      stress_pnl=net-len(selected)*plan['extra_execution_cost_dollars'],engine_run=key)
        cache[key] = result
        return result

    base = dict(ivr=50,iv_rv=None,trend=None)
    base_train = evaluate(train,'discovery')
    grid = []
    for ivr,rv,trend in itertools.product(plan['ivr_thresholds'],plan['iv_rv_thresholds'],plan['max_abs_trend_thresholds']):
        cfg = dict(ivr=ivr,iv_rv=rv,trend=trend)
        retained = [c for c in train if allowed(c['features'],cfg)]
        result = evaluate(retained,'discovery')
        years = {y:sum(c['entry'].startswith(str(y)) for c in retained) for y in [2024,2025]}
        eligible = (len(retained)>=plan['minimum_discovery_cycles'] and
                    min(years.values())>=plan['minimum_discovery_cycles_per_year'])
        grid.append(dict(config=cfg,**result,eligible=eligible,cycles_by_year=years))
    candidates = [g for g in grid if g['eligible'] and g['stress_pnl']>max(0,base_train['stress_pnl'])]
    best = max(candidates,key=lambda g:(g['stress_pnl'],g['cycles'])) if candidates else None
    selected_cfg = best['config'] if best else base
    selection = dict(ticker=ticker,config=selected_cfg,improvement_selected=best is not None,
        reason='positive discovery stress P&L improves baseline with sufficient cycles' if best else
               'no supported positive discovery improvement; baseline retained',
        discovery=best if best else base_train,plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        original_orders_sha256=hashlib.sha256(orders_path.read_bytes()).hexdigest())
    # Freeze before reading any validation outcomes into an objective or score.
    (out/'selection.json').write_text(json.dumps(selection,indent=2))
    baseline_valid = evaluate(valid,'validation')
    chosen_valid = evaluate([c for c in valid if allowed(c['features'],selected_cfg)],'validation')
    supported = bool(best and chosen_valid['cycles']>=plan['minimum_validation_cycles'] and
                     chosen_valid['stress_pnl']>0 and chosen_valid['stress_pnl']>baseline_valid['stress_pnl'])
    summary = dict(ticker=ticker,initial_cash=capital,baseline_control=control,
        discovery_baseline=base_train,selection=selection,validation_baseline=baseline_valid,
        validation_selected=chosen_valid,validation_supported=supported,
        crossing_cycles_excluded=len(cycles)-len(train)-len(valid),grid_configurations=len(grid),
        unique_engine_replays=sum(v['executions']>0 for v in cache.values())+1,
        empty_subsets_are_flat_cash=True,
        limitation=plan['simulation'],prior_inspection=plan['prior_inspection'])
    (out/'grid.json').write_text(json.dumps(grid,indent=2))
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    # This private research warehouse never contains credentials or algorithm source.
    con=duckdb.connect(str(out/'research.duckdb'))
    frames={'qc_executions':pd.DataFrame(rows),'entry_annotations':pd.DataFrame(features),
            'cycle_labels':pd.DataFrame([{k:v for k,v in c.items() if k!='features'} for c in cycles]),
            'candidate_results':pd.json_normalize(grid)}
    parquet=out/'parquet';parquet.mkdir()
    manifest={}
    for name,frame in frames.items():
        con.register('frame',frame)
        con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM frame')
        dest=parquet/(name+'.parquet')
        con.execute(f'COPY "{name}" TO ? (FORMAT PARQUET)',[str(dest)])
        manifest[name]=dict(rows=len(frame),sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
        con.unregister('frame')
    con.close()
    (parquet/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
