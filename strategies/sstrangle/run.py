#!/usr/bin/env python3
"""Render reproducible experiments and run them through the shared Rust queue."""
import argparse
import ast
import hashlib
import pprint
from datetime import date
import json
from pathlib import Path
import signal
import qc_storage as storage
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from qc_api_check import credentials, request


def cloud_terminal_evidence(record):
    """Local queue completion alone is not proof that the cloud run stopped."""
    if not record.get('project_id') or not record.get('backtest_id'):
        return None
    payload=record.get('result') or {}
    if not isinstance(payload,dict) or payload.get('success') is False or payload.get('errors'):
        return None
    full=payload.get('backtest',payload)
    if not isinstance(full,dict):
        return None
    for remote,local in [('projectId','project_id'),('backtestId','backtest_id')]:
        if remote in full and str(full[remote])!=str(record[local]):
            return None
    if full.get('completed') is True and all(k in full for k in ('projectId','backtestId')):
        return 'identity_verified_full_terminal_read'
    if not full and str(record.get('error_message','')).startswith('poll: runtime_error:'):
        # This exact prefix is emitted only after Rust observes completed=true
        # with a real algorithm error. It still requires full export for audit.
        return 'rust_observed_completed_runtime_error; full_export_pending'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['smoke', 'comparison', 'improvements', 'validation', 'single', 'basket-probe', 'basket-smoke', 'basket-regression', 'basket-margin-probe', 'basket-scale-probe', 'basket-scale-survey', 'basket-cl-regression', 'basket-zw-regression', 'basket-performance-regression', 'basket-insolvency-regression', 'basket-wag-regression', 'basket-lvs-regression', 'basket-lvs-guard', 'basket-wag-clock', 'basket-wag-early', 'basket-wdc-quote', 'basket-wdc-history', 'basket-volatility-source', 'basket-volatility-roots', 'basket-volatility-coverage', 'basket-volatility-minute', 'basket-equity-rv-gate', 'basket-zc-risk-guard', 'basket-twtr-event-probe', 'basket-twtr-age-regression', 'basket-calmar', 'basket', 'data-probe'], default='smoke')
    parser.add_argument('--zw-control',action='store_true',help='Original combo close in exact ZW fixture')
    parser.add_argument('--qc-source', type=Path, help='Collected baseline evidence for --phase data-probe')
    parser.add_argument('--tickers', nargs='+', default=['SPX','SPY','QQQ','IWM','AAPL','MSFT','AMZN','NVDA','TSLA','TLT','GLD','IBIT'])
    parser.add_argument('--selection', type=Path, help='Frozen selection.json from the discovery batch')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--timeout', type=int, default=3600)
    parser.add_argument('--start', type=date.fromisoformat, help='Single-ticker phase history start (YYYY-MM-DD)')
    parser.add_argument('--trade-start', type=date.fromisoformat, help='Single-ticker phase earliest entry date')
    parser.add_argument('--end', type=date.fromisoformat, help='Single-ticker phase end date')
    parser.add_argument('--entry-policy', choices=['high-ivr', 'continuous'],
        help='Single-ticker entry gate: IVR >=50, or no IVR/history prerequisite')
    parser.add_argument('--diagnose-unfilled', action='store_true',
        help='Log past quote coverage on an unresolved order; never use history as fills')
    args = parser.parse_args()
    if args.zw_control and args.phase!='basket-zw-regression':
        parser.error('--zw-control requires --phase basket-zw-regression')
    if any((args.start,args.trade_start,args.end)) and args.phase not in ('single','basket','basket-calmar'):
        parser.error('Date overrides are supported for --phase single or basket')
    if (args.entry_policy or args.diagnose_unfilled) and args.phase != 'single':
        parser.error('--entry-policy and --diagnose-unfilled are supported for --phase single')
    stamp = time.strftime('%Y%m%d_%H%M%S')
    batch = f'strangle_{args.phase}_{stamp}'
    out = HERE / 'results' / batch
    out.mkdir(parents=True)
    if args.phase == 'basket-probe':
        variants = {'basket_probe': dict(start=[2012,1,3],end=[2012,1,10])}
    elif args.phase == 'basket-twtr-age-regression':
        variants={name:dict(engineering_smoke=True,holding_cap=cap,max_holding_days=24,stop_multiple=1.,risk_interval_minutes=15) for name,cap in [('twtr_age_control',False),('twtr_age24',True)]}
    elif args.phase == 'basket-twtr-event-probe':
        variants={'twtr_events':dict(engineering_smoke=True)}
    elif args.phase == 'basket-zc-risk-guard':
        variants={name:dict(engineering_smoke=True,cross_asset_voluntary_guard=guard,stop_multiple=1.,risk_interval_minutes=15)
            for name,guard in [('zc_control',False),('zc_guard_retry',True)]}
    elif args.phase == 'basket-equity-rv-gate':
        variants={'equity_rv_gate':dict(engineering_smoke=True,min_equity_iv_rv=1.2,future_rv_policy='original_rules')}
    elif args.phase == 'basket-volatility-minute':
        variants={'vol_minute':dict(engineering_smoke=True,roots=['CL','RB','HO','NG','ZN','ZT','ZB','ZC','ZS','ZW','NQ','ES','HG','GC','SI'])}
    elif args.phase == 'basket-volatility-coverage':
        variants={'vol_coverage':dict(engineering_smoke=True,roots=['CL','RB','HO','NG','ZN','ZT','ZB','ZC','ZS','ZW','NQ','ES','HG','GC','SI'])}
    elif args.phase == 'basket-volatility-roots':
        variants={'vol_all_roots':dict(engineering_smoke=True,probe='futures',roots=['CL','RB','HO','NG','ZN','ZT','ZB','ZC','ZS','ZW','NQ','ES','HG','GC','SI'])}
    elif args.phase == 'basket-volatility-source':
        variants = {'vol_equity':dict(engineering_smoke=True,probe='equity'),'vol_futures':dict(engineering_smoke=True,probe='futures')}
    elif args.phase == 'basket-wdc-history':
        variants = {'wdc_history':dict(engineering_smoke=True)}
    elif args.phase == 'basket-wdc-quote':
        variants = {'wdc_quote':dict(engineering_smoke=True)}
    elif args.phase == 'basket-wag-early':
        variants = {'wag_early28':dict(engineering_smoke=True,buyback=False,time_exit_dte=28)}
    elif args.phase == 'basket-wag-clock':
        variants = {'wag_clock':dict(engineering_smoke=True,buyback=False)}
    elif args.phase == 'basket-lvs-guard':
        variants = {name:dict(engineering_smoke=True,limit_exit=False,voluntary_guard=guard,stop_multiple=1.,risk_interval_minutes=15,time_exit_dte=28)
                    for name,guard in [('lvs_guard_control',False),('lvs_guarded',True)]}
    elif args.phase == 'basket-lvs-regression':
        variants = {'lvs_market_control':dict(engineering_smoke=True,limit_exit=False),
                    'lvs_limit_exit':dict(engineering_smoke=True,limit_exit=True)}
    elif args.phase == 'basket-wag-regression':
        variants = {'wag_control':dict(engineering_smoke=True,buyback=False),
                    'wag_buyback':dict(engineering_smoke=True,buyback=True)}
    elif args.phase == 'basket-calmar':
        plan=json.loads((HERE/'optimization/research_plan.json').read_text())
        common=dict(start=[2012,1,3],trade_start=[2012,1,3],end=[2026,9,30],
            initial_cash=60000,lookback=504,allow_no_trades=True,profile_performance=True)
        for key,value in [('start',args.start),('trade_start',args.trade_start),('end',args.end)]:
            if value:common[key]=[value.year,value.month,value.day]
        variants={name:dict(common,**cfg) for name,cfg in plan['variants'].items()}
    elif args.phase == 'basket-insolvency-regression':
        variants = {'insolvency_regression':dict(engineering_smoke=True)}
    elif args.phase == 'basket-performance-regression':
        variants = {'perf_reference':dict(engineering_smoke=True,performance_probe=True,performance_reference=True),
            'perf_optimized':dict(engineering_smoke=True,performance_probe=True,performance_reference=False,profile_performance=True)}
    elif args.phase == 'basket-zw-regression':
        variants = {('zw_control' if args.zw_control else 'zw_regression'):dict(engineering_smoke=True,combo_control=args.zw_control)}
    elif args.phase == 'basket-cl-regression':
        variants = {'cl_regression':dict(engineering_smoke=True)}
    elif args.phase == 'basket-scale-survey':
        variants = {'scale_survey':dict(engineering_smoke=True,initial_cash=60000)}
    elif args.phase == 'basket-scale-probe':
        variants = {'scale_probe':dict(engineering_smoke=True,initial_cash=60000)}
    elif args.phase == 'basket-margin-probe':
        variants = {'margin_probe':dict(engineering_smoke=True,initial_cash=60000)}
    elif args.phase == 'data-probe':
        if not args.qc_source:
            parser.error('--qc-source is required for --phase data-probe')
        from local.prepare import executions
        fills = executions(json.loads((args.qc_source/'orders.json').read_text()))
        backtest = json.loads((args.qc_source/'backtest.json').read_text())['backtest']
        variants = {'data_reference':dict(executions=fills,baseline=dict(
            project_id=backtest['projectId'],backtest_id=backtest['backtestId']),
            object_key=f'sstrangle/data_reference_{stamp}/qc_reference.json')}
    elif args.phase in ('basket-smoke','basket-regression','basket'):
        cfg = dict(start=[2012,1,3],trade_start=[2012,1,3],end=[2026,9,30],
                   lookback=504,initial_cash=60000,allow_no_trades=True,profile_performance=True)
        if args.phase == 'basket-smoke':
            cfg.update(end=[2012,6,29],lookback=20,engineering_smoke=True)
        if args.phase == 'basket-regression':
            cfg.update(end=[2014,12,31],engineering_smoke=True,
                engineering_reason='Full 504-observation margin-call and rejected-roll regression')
        for key,value in [('start',args.start),('trade_start',args.trade_start),('end',args.end)]:
            if value:
                cfg[key]=[value.year,value.month,value.day]
        variants = {'basket':cfg}
    elif args.phase == 'smoke':
        variants = {'smoke': dict(start=[2024, 1, 2], end=[2024, 4, 30],
            trade_start=[2024, 2, 1], tickers=['SPY'], lookback=20, iv_min=0, rolls=True)}
    elif args.phase == 'comparison':
        variants = {'managed': dict(rolls=True), 'no_roll': dict(rolls=False)}
    elif args.phase == 'improvements':
        variants = {'stop1': dict(rolls=True, stop_multiple=1.0),
                    'trend': dict(rolls=True, max_trend_z=1.0),
                    'edge': dict(rolls=True, min_iv_rv=1.2)}
    elif args.phase == 'single':
        variants = {ticker: dict(tickers=[ticker], start=[2022,12,1],
                    trade_start=[2024,1,2], end=[2026,9,30], rolls=True,
                    initial_cash=2500000 if ticker == 'SPX' else 250000,
                    strike_width=80 if ticker == 'SPX' else 40,
                    allow_no_trades=True) for ticker in args.tickers}
        for cfg in variants.values():
            if args.diagnose_unfilled:
                cfg['diagnose_unfilled'] = True
            if args.entry_policy:
                cfg['iv_min'] = None if args.entry_policy == 'continuous' else 50
                cfg['entry_policy'] = args.entry_policy
            for key,value in [('start',args.start),('trade_start',args.trade_start),('end',args.end)]:
                if value:
                    cfg[key]=[value.year,value.month,value.day]
            if not date(*cfg['start']) <= date(*cfg['trade_start']) < date(*cfg['end']):
                parser.error('Dates must satisfy start <= trade-start < end')
    else:
        if args.selection is None:
            parser.error('--selection is required for validation')
        selection = json.loads(args.selection.read_text())
        common = dict(start=[2024, 12, 1], trade_start=[2026, 1, 2], end=[2026, 9, 30],
                      rolls=True, allow_no_trades=True)
        variants = {'baseline': common, 'selected': {**common, **selection['candidate_config']}}
    source_path = ('optimization/twtr_age_fixture.py' if args.phase=='basket-twtr-age-regression' else
                   'optimization/twtr_event_probe.py' if args.phase=='basket-twtr-event-probe' else
                   'optimization/zc_risk_guard_fixture.py' if args.phase=='basket-zc-risk-guard' else
                   'optimization/equity_rv_gate_fixture.py' if args.phase=='basket-equity-rv-gate' else
                   'optimization/volatility_minute_fixture.py' if args.phase=='basket-volatility-minute' else
                   'optimization/volatility_coverage_fixture.py' if args.phase=='basket-volatility-coverage' else
                   'optimization/volatility_all_roots_fixture.py' if args.phase=='basket-volatility-roots' else
                   'optimization/volatility_source_fixture.py' if args.phase=='basket-volatility-source' else
                   'optimization/wdc_history_fixture.py' if args.phase=='basket-wdc-history' else
                   'optimization/wdc_quote_fixture.py' if args.phase=='basket-wdc-quote' else
                   'optimization/lvs_guard_fixture.py' if args.phase=='basket-lvs-guard' else
                   'optimization/wag_early_exit_fixture.py' if args.phase=='basket-wag-early' else
                   'optimization/wag_quote_clock_fixture.py' if args.phase=='basket-wag-clock' else
                   'optimization/lvs_exit_fixture.py' if args.phase=='basket-lvs-regression' else
                   'optimization/wag_exit_fixture.py' if args.phase=='basket-wag-regression' else
                   'optimization/main.py' if args.phase=='basket-calmar' else
                   'basket/insolvency_regression.py' if args.phase=='basket-insolvency-regression' else
                   'basket/zw_regression.py' if args.phase in ('basket-zw-regression','basket-performance-regression') else
                   'basket/cl_regression.py' if args.phase == 'basket-cl-regression' else
                   'basket/scale_survey.py' if args.phase == 'basket-scale-survey' else
                   'basket/scale_probe.py' if args.phase == 'basket-scale-probe' else
                   'basket/margin_probe.py' if args.phase == 'basket-margin-probe' else
                   'local/qc_data_probe.py' if args.phase == 'data-probe' else
                   'basket/probe.py' if args.phase == 'basket-probe' else
                   'basket/main.py' if args.phase in ('basket','basket-smoke','basket-regression') else 'project/main.py')
    source = (HERE / source_path).read_text()
    extras = {'rules.py': (HERE / 'project/rules.py').read_text()}
    if args.phase in ('basket-wag-regression','basket-wag-clock','basket-wag-early','basket-wdc-quote','basket-wdc-history'):
        # Freeze the already-verified original execution dependencies. The
        # fixture changes only the candidate buyback quote predicate.
        frozen=HERE/'results/strangle_basket_20261018_191012'
        dependencies=json.loads((frozen/'extra_files.json').read_text())
        for filename in ('rules.py','execution_base.py','basket_rules.py',
                         'terminal_margin.py','premium_units.py','premium_filter.py'):
            extras[filename]=dependencies[filename]
        extras['basket_strategy.py']=(frozen/'basket.py').read_text()
        if args.phase=='basket-wdc-history':
            extras['wdc_original_fixture.py']=(HERE/'results/strangle_basket-wdc-quote_20261019_162136/wdc_quote.py').read_text()
        if args.phase == 'basket-wag-clock':
            extras['wag_original_fixture.py']=(HERE/'results/strangle_basket-wag-regression_20261019_142652/wag_control.py').read_text()
            extras['wag_quote_clock_diagnostics.py']=(HERE/'optimization/wag_quote_clock_diagnostics.py').read_text()
    if args.phase == 'basket-lvs-guard':
        frozen=HERE/'results/strangle_basket_20261018_191012'
        dependencies=json.loads((frozen/'extra_files.json').read_text())
        for filename in ('rules.py','execution_base.py','basket_rules.py',
                         'terminal_margin.py','premium_units.py','premium_filter.py'):
            extras[filename]=dependencies[filename]
        extras['lvs_original_fixture.py']=(HERE/'results/strangle_basket-lvs-regression_20261019_143611/lvs_market_control.py').read_text()
        extras['guarded_strategy.py']=(HERE/'optimization/guarded_main.py').read_text()
        extras['unguarded_reference.py']=(HERE/'results/strangle_basket-calmar_20261019_150331/cap20_stop1_exit28.py').read_text()
        extras['voluntary_quote_guard.py']=(HERE/'optimization/voluntary_quote_guard.py').read_text()
        extras['research_risk_rules.py']=(HERE/'optimization/risk_rules.py').read_text()
    if args.phase=='basket-twtr-age-regression':
        frozen=HERE/'results/strangle_basket-calmar_20261019_182746'
        extras=json.loads((frozen/'extra_files.json').read_text())
        extras['twtr_original_strategy.py']=(frozen/'cap20_stop1_guard_rv12_exit21.py').read_text()
        extras['holding_age.py']=(HERE/'optimization/holding_age.py').read_text()
    if args.phase=='basket-twtr-event-probe':
        frozen=json.loads((HERE/'results/strangle_basket-calmar_20261019_182746/extra_files.json').read_text())
        extras={name:frozen[name] for name in ('rules.py','execution_base.py','voluntary_quote_guard.py')}
    if args.phase=='basket-zc-risk-guard':
        frozen=HERE/'results/strangle_basket-calmar_20261019_163122'
        extras=json.loads((frozen/'extra_files.json').read_text())
        extras['guarded_control_strategy.py']=(frozen/'cap20_stop1_guard_exit21.py').read_text()
        extras['cross_asset_candidate_strategy.py']=(HERE/'optimization/cross_asset_guard_main.py').read_text()
        extras.update({name:(HERE/'optimization'/name).read_text() for name in
            ('completed_volatility.py','equity_rv_features.py','fresh_risk_slots.py','cross_asset_buyback_guard.py')})
        for name in ('equity_rv_source_receipt_20261019.json','risk_retry_source_receipt_20261019.json','cross_asset_guard_source_receipt_20261019.json'):
            (out/name).write_bytes((HERE/'optimization'/name).read_bytes())
    if args.phase=='basket-equity-rv-gate':
        extras=json.loads((HERE/'results/strangle_basket-calmar_20261019_163122/extra_files.json').read_text())
        extras.update({name:(HERE/'optimization'/name).read_text() for name in ['completed_volatility.py','equity_rv_features.py']})
        extras['equity_rv_strategy.py']=(HERE/'optimization/equity_rv_main.py').read_text()
    if args.phase=='basket-volatility-minute':
        extras={name:(HERE/'optimization'/name).read_text() for name in ['completed_volatility.py','minute_session_closes.py']}
    if args.phase=='basket-volatility-coverage':
        extras={}
    if args.phase in ('basket-volatility-source','basket-volatility-roots'):
        extras={'completed_volatility.py':(HERE/'optimization/completed_volatility.py').read_text()}
    if args.phase=='basket-volatility-roots':
        extras['volatility_original_fixture.py']=(HERE/'results/strangle_basket-volatility-source_20261019_174306/vol_futures.py').read_text()
    if args.phase == 'data-probe':
        columns = ('order_id','timestamp','symbol','underlying','expiry','call_put','strike','quantity','qc_price')
        tape = [{key:row[key] for key in columns} for row in fills]
        imports = ['ROWS = []']
        for i,start in enumerate(range(0,len(tape),100)):
            name = 'reference_tape_'+str(i)
            extras[name+'.py'] = 'ROWS = '+pprint.pformat(tape[start:start+100],width=100)+'\n'
            imports += [f'from {name} import ROWS as part_{i}',f'ROWS.extend(part_{i})']
        extras['reference_tape.py'] = '\n'.join(imports)+'\n'
    if args.phase in ('basket','basket-smoke','basket-regression','basket-calmar'):
        extras.update({'execution_base.py':(HERE/'project/main.py').read_text(),
                       'basket_rules.py':(HERE/'basket/basket_rules.py').read_text()})
    if args.phase in ('basket-margin-probe','basket-cl-regression','basket-zw-regression','basket-performance-regression','basket-insolvency-regression'):
        extras.update({'basket_strategy.py':(HERE/'basket/main.py').read_text(),
            'execution_base.py':(HERE/'project/main.py').read_text(),
            'basket_rules.py':(HERE/'basket/basket_rules.py').read_text()})
    if args.phase in ('basket','basket-smoke','basket-regression','basket-margin-probe','basket-cl-regression','basket-zw-regression','basket-performance-regression','basket-insolvency-regression'):
        extras.update({'terminal_margin.py':(HERE/'basket/terminal_margin.py').read_text(),
                       'premium_units.py':(HERE/'basket/premium_units.py').read_text(),
                       'premium_filter.py':(HERE/'basket/premium_filter.py').read_text()})
    if args.phase == 'basket-performance-regression':
        frozen=HERE/'results/strangle_basket_20261018_173739'
        reference=json.loads((frozen/'extra_files.json').read_text())
        extras['reference_basket.py']=(frozen/'basket.py').read_text().replace(
            'import execution_base','import reference_execution_base as execution_base').replace(
            'from basket_rules import','from reference_rules import')
        extras['reference_execution_base.py']=reference['execution_base.py']
        extras['reference_rules.py']=reference['basket_rules.py']
    if args.phase=='basket-calmar':
        extras['research_risk_rules.py']=(HERE/'optimization/risk_rules.py').read_text()
        if any(cfg.get('voluntary_spread_guard',False) for cfg in variants.values()):
            extras['voluntary_quote_guard.py']=(HERE/'optimization/voluntary_quote_guard.py').read_text()
        if any('min_equity_iv_rv' in cfg for cfg in variants.values()):
            extras.update({name:(HERE/'optimization'/name).read_text()
                for name in ('completed_volatility.py','equity_rv_features.py')})
            receipt=HERE/'optimization/equity_rv_source_receipt_20261019.json'
            (out/receipt.name).write_bytes(receipt.read_bytes())
        if any('max_holding_days' in cfg for cfg in variants.values()):
            sys.path.insert(0,str(HERE/'optimization'))
            from holding_source_chain import freeze_chain
            extras.update({name:(HERE/'optimization'/name).read_text() for name in
                ('fresh_risk_slots.py','cross_asset_buyback_guard.py','holding_age.py')})
            freeze_chain(out,extras)
        for filename in ('terminal_margin.py','premium_units.py','premium_filter.py'):
            extras[filename]=(HERE/'basket'/filename).read_text()
        (out/'research_plan.json').write_text(json.dumps(plan,indent=2))
    for value in extras.values():
        ast.parse(value)
    (out / 'extra_files.json').write_text(json.dumps(extras, indent=2))
    jobs = []
    for label, cfg in variants.items():
        rendered_cfg = {key:value for key,value in cfg.items() if args.phase != 'data-probe' or key != 'executions'}
        variant_source=source
        if args.phase=='basket-calmar' and cfg.get('voluntary_spread_guard',False):
            if cfg['voluntary_spread_guard'] is not True:
                raise ValueError('Voluntary spread guard must be explicitly boolean True')
            variant_source=(HERE/'optimization/guarded_main.py').read_text()
        if args.phase=='basket-calmar' and 'min_equity_iv_rv' in cfg:
            if cfg.get('voluntary_spread_guard') is not True or cfg.get('future_rv_policy')!='original_rules':
                raise ValueError('Equity-only RV research requires preserved guarded execution and explicit future policy')
            variant_source=(HERE/'optimization/equity_rv_main.py').read_text()
        if args.phase=='basket-calmar' and 'max_holding_days' in cfg:
            if (cfg.get('voluntary_spread_guard') is not True or 'min_equity_iv_rv' not in cfg
                    or cfg.get('future_rv_policy')!='original_rules'
                    or cfg.get('cross_asset_voluntary_guard') is not True
                    or cfg.get('fresh_risk_retry') is not True):
                raise ValueError('Holding-cap source requires its declared complete research chain')
            from holding_age import validate_max_holding_days
            validate_max_holding_days(cfg['max_holding_days'])
            variant_source=(HERE/'optimization/holding_cap_main.py').read_text()
        if args.phase=='basket-performance-regression' and cfg['performance_reference']:
            variant_source=source.replace('from basket_strategy import BasketShortStrangle',
                'from reference_basket import BasketShortStrangle')
        code = variant_source.replace('CONFIG = {}', 'CONFIG = ' + repr(rendered_cfg), 1)
        ast.parse(code)
        path = out / f'{label}.py'
        path.write_text(code)
        jobs.append((f'SSTRANGLE_{stamp}_{label}', path))
    manifest = dict(batch=batch, phase=args.phase, variants=variants, jobs=[n for n, _ in jobs])
    if args.phase=='basket-twtr-age-regression':
        manifest['research_scope']='Isolated TWTR held-position AGE24 execution regression. Both branches retain original risk methods. Control must reproduce6genuine source fills plus actualOct29failure/residuals. Candidate must close through real native orders before halt; no settlement, quote substitution or full strategy performance claim.'
        manifest['source_backtest']='ef390020506ba958395a628bb1668af0'
        manifest['source_order_ids']=[733,734,735,736,737,738]
        manifest['source_orders_sha256']=hashlib.sha256((HERE/'results/strangle_basket-calmar_20261019_182746/SSTRANGLE_20261019_182746_cap20_stop1_guard_rv12_exit21/orders.json').read_bytes()).hexdigest()
        manifest['holding_age_helper_sha256']=hashlib.sha256(extras['holding_age.py'].encode()).hexdigest()
        manifest['expected_control_cloud_failure']=True
        manifest['evidence_only']=True
    if args.phase=='basket-twtr-event-probe':
        manifest['research_scope']='No-trade native TWTR corporate-event warning timing and actual held-pair quote availability,2022Sep20-Oct31; aggregate counters/event timestamps only. No quote-history export, settlement inference or strategy performance.'
        manifest['source_backtest']='ef390020506ba958395a628bb1668af0'
        manifest['source_order_ids']=[733,734,735,736,737,738]
        manifest['evidence_only']=True
    if args.phase=='basket-zc-risk-guard':
        manifest['research_scope']='Isolated native ZC training-cycle replay: original actual entry and scheduled roll identities; control must match all10genuine source fills. Prospective branch combines fresh-risk retry and voluntary futures spread guard. Not a new universe screen, factorial causal comparison, or strategy Calmar test.'
        manifest['source_backtest']='8c5f9a8bc08d580e81d38e49dcf3b34d'
        manifest['source_order_ids']=[569,570,571,572,573,574,579,580,581,582]
        manifest['source_orders_sha256']=hashlib.sha256((HERE/'results/strangle_basket-calmar_20261019_163122/SSTRANGLE_20261019_163122_cap20_stop1_guard_exit21/orders.json').read_bytes()).hexdigest()
        manifest['evidence_only']=True
    if args.phase=='basket-equity-rv-gate':
        manifest['research_scope']='Actual proposed equity admission methods on native SCALED_RAW history, including unsubscribed symbols; synthetic IV pass/reject tests and explicit futures bypass; no trades or performance claim'
        manifest['evidence_only']=True
    if args.phase=='basket-volatility-minute':
        manifest['research_scope']='All15root two-delivery minute-derived completed-session RV; all unavailable windows counted, no orders or raw price history export; not strategy performance'
        manifest['evidence_only']=True
    if args.phase=='basket-volatility-coverage':
        manifest['research_scope']='No-trade aggregate daily/minute row availability for30native deliveries across15roots on July3/4; not market-history export, native feature proof or strategy performance'
        manifest['evidence_only']=True
    if args.phase=='basket-volatility-roots':
        manifest['research_scope']='Aggregate completed-session feature/calendar checks for two native deliveries of all15supported futures roots; no orders, source-history exports or Calmar claims'
        manifest['evidence_only']=True
    if args.phase=='basket-volatility-source':
        manifest['research_scope']='Two no-trade native completed-price feature probes: equity corporate rebase and distinct futures delivery identities; aggregate counts/fingerprint only, no market-history export or Calmar claim'
        manifest['evidence_only']=True
    if args.phase in ('basket-wdc-quote','basket-wdc-history'):
        manifest['research_scope']='Original WDC six native fills and aggregate mandatory-session quote-gate predicates; real residuals retained; not strategy performance'
        manifest['source_failure']=dict(project_id=31338456,backtest_id='3d5fefa21dd61cc75b1a5c579c390c3c')
        manifest['evidence_only']=True
        if args.phase=='basket-wdc-history':
            manifest['research_scope']='Same six actual WDC fills; AFTER execution, bounded Apr18/Apr22 history availability counts only. No raw history export or trading-rule changes.'
    if args.phase == 'basket-wag-early':
        manifest['research_scope']='Changed28DTE exit: original two opening fills, actual earlier close; not baseline equivalence or Calmar evidence'
        manifest['evidence_only']=True
    if args.phase == 'basket-wag-clock':
        manifest['research_scope']='Same native four-fill WBA control plus aggregate quote-clock predicates; no quote history export or trade-gate change'
        manifest['source_failure']=dict(project_id=31338456,backtest_id='8a6d193829c51b26976d40707c081eb5')
        manifest['parent_control']=dict(project_id=31338456,backtest_id='871156fba7043ac4ea179dc019564eb4')
        manifest['evidence_only']=True
    if args.phase == 'basket-lvs-guard':
        manifest['research_scope']='Native original LVS control versus optional voluntary spread guard from Aug19 training observation; no limit orders, full-strategy or Calmar claim'
        manifest['parent_control']=dict(project_id=31338456,backtest_id='1b00778a981e8fe863f87227c76af67f')
        manifest['evidence_only']=True
    if args.phase == 'basket-lvs-regression':
        manifest['research_scope']='Isolated native LVS market-control/limit-exit execution regression; excludes simultaneous ZC positions; no strategy performance claim'
        manifest['source_failure']=dict(project_id=31338456,backtest_id='8a6d193829c51b26976d40707c081eb5')
        manifest['evidence_only']=True
    if args.phase == 'basket-wag-regression':
        manifest['research_scope']='Exact WBA engineering control/buyback-predicate regression; no strategy performance claim'
        manifest['source_failure']=dict(project_id=31338456,backtest_id='8a6d193829c51b26976d40707c081eb5')
        manifest['evidence_only']=True
    if args.phase in ('basket','basket-smoke','basket-regression'):
        manifest['research_scope'] = ('Engineering smoke with shortened IV history; no baseline performance claims'
            if args.phase == 'basket-smoke' else
            'Engineering regression with full IV history; not the full requested baseline'
            if args.phase == 'basket-regression' else 'Two-year range-IVR >70 broad baseline; no optimization')
        (out/'baseline_plan.json').write_text((HERE/'basket/baseline_plan.json').read_text())
    if args.phase == 'single':
        if any((args.start,args.trade_start,args.end,args.entry_policy)):
            manifest['research_scope'] = 'Historical baseline and data coverage; no local optimization plan'
        else:
            plan = (HERE/'single_research_plan.json').read_text()
            (out/'research_plan.json').write_text(plan)
    if args.phase == 'validation':
        manifest['frozen_selection'] = selection
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(f'Artifacts: {out}', flush=True)
    if args.dry_run:
        return
    binary = ROOT / 'target/release/qc-backtest-server'
    subprocess.run([str(binary), '--data-dir', str(ROOT/'data'), 'init-strategy', '--strategy', 'sstrangle'], check=True)
    server, server_log = None, None
    pid_file = ROOT / 'data/qc-server.pid'
    existing = False
    if pid_file.exists():
        try:
            import os
            os.kill(int(pid_file.read_text().strip()), 0)
            existing = True
        except (ValueError, ProcessLookupError):
            pass
    if not existing:
        server_log = (out / 'server.log').open('w')
        server = subprocess.Popen([str(binary), '--data-dir', str(ROOT/'data'), 'serve'],
                                  stdout=server_log, stderr=subprocess.STDOUT, cwd=ROOT)
    outcomes = {}
    try:
        for name, path in jobs:
            subprocess.run([str(binary), '--data-dir', str(ROOT/'data'), 'queue',
                '--strategy', 'sstrangle', '--name', name, '--batch', batch,
                '--code-file', str(path), '--extra-files', str(out/'extra_files.json')], check=True)
        deadline = time.monotonic() + args.timeout
        previous = {}
        while len(outcomes) < len(jobs):
            if server and server.poll() is not None:
                raise RuntimeError(f'Server exited: {server.returncode}')
            if time.monotonic() > deadline:
                raise TimeoutError('Cloud run deadline exceeded; inspect recorded queue jobs')
            with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro', uri=True) as conn:
                conn.row_factory = storage.Row
                rows = [dict(conn.execute('SELECT * FROM backtest_queue WHERE name=?', (n,)).fetchone()) for n, _ in jobs]
            for row in rows:
                name, status = row['name'], row['status']
                if previous.get(name) != status:
                    print(f'{name}: {status} project={row["project_id"]} backtest={row["backtest_id"]}', flush=True)
                    previous[name] = status
                if status not in ('done', 'failed') or name in outcomes:
                    continue
                record = {k: row[k] for k in ('name', 'status', 'error_message', 'project_id', 'backtest_id', 'runtime_seconds', 'code_hash')}
                result = json.loads(row['result_json']) if row['result_json'] else {}
                record['result'] = result
                record['cloud_terminal_evidence'] = cloud_terminal_evidence(record)
                record['cloud_terminal_verified'] = bool(record['cloud_terminal_evidence'])
                outcomes[name] = record
                (out / f'{name}.json').write_text(json.dumps(record, indent=2))
                print(json.dumps(record.get('result', {}).get('runtimeStatistics', {})), flush=True)
                user, token = credentials(ROOT/'data/S001.duckdb')
                if record['cloud_terminal_verified']:
                    try:
                        pages = []
                        for start in range(0, 10000, 200):
                            log = request(user, token, '/backtests/read/log', dict(
                                projectId=row['project_id'], backtestId=row['backtest_id'],
                                start=start, end=start+200, query=''))
                            pages.append(log)
                            if len(log.get('log', log.get('logs', []))) < 200:
                                break
                        (out / f'{name}.log.json').write_text(json.dumps(pages, indent=2))
                    except Exception as exc:
                        print(f'Log retrieval: {exc}', flush=True)
            (out / 'outcomes.json').write_text(json.dumps(outcomes, indent=2))
            if len(outcomes) < len(jobs):
                time.sleep(10)
    finally:
        safe_to_stop = len(outcomes)==len(jobs) and all(cloud_terminal_evidence(r) for r in outcomes.values())
        if server and server.poll() is None and not safe_to_stop:
            print('Preserving owned Rust server and cloud IDs: jobs are not all terminal; use read-only recovery.',flush=True)
        if server and server.poll() is None and safe_to_stop:
            server.send_signal(signal.SIGTERM)
            try:
                server.wait(timeout=155)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        if server_log:
            server_log.close()
    if any(not cloud_terminal_evidence(r) for r in outcomes.values()):
        raise RuntimeError(f'Local observation stopped without verified cloud completion; retain existing IDs and use read-only recovery. Do not restart serve or resubmit while cloud state is nonterminal/unknown. See {out}')
    if any(r['status'] != 'done' for r in outcomes.values()):
        raise RuntimeError(f'Cloud test failed; full evidence collection is required; see {out}')
    print(f'Completed: {out}', flush=True)


if __name__ == '__main__':
    main()
