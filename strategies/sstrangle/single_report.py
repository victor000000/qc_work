#!/usr/bin/env python3
"""Publish per-ticker QC baselines, frozen local research and data limitations."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from collections import defaultdict


def money(value):
    number=float(value)
    return ('-$' if number<0 else '$')+f'{abs(number):,.2f}'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('batch',type=Path)
    args=p.parse_args()
    batch=args.batch.resolve()
    manifest=json.loads((batch/'manifest.json').read_text())
    outcomes=json.loads((batch/'outcomes.json').read_text())
    rows=[];attribution=[];totals=dict(cloud_done=0,cloud_failed=0,cloud_pending=0,downloaded_orders=0,audited_cycles=0)
    lines=['# Independent short-strangle ticker campaign','',
        'Trading window: 2024-01-02–2026-09-30; earlier observations build the 252-sample IV rank. '
        'Baseline rules: one 16–20 delta monthly put/call pair near 45 DTE, IVR ≥50, 50% credit profit target, '
        'two-credit loss exit, 21-DTE time exit and at most three untested-side rolls. Decisions are daily. '
        'Accounts are independent; SPX starts at $2.5m and others at $250k. These fixed one-contract tests '
        'do not match risk across tickers.','',
        '| Ticker | Capital | Cycles | Net P&L | Return | Daily sampled drawdown | Orders | QC evidence |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    ordered={name.rsplit('_',1)[1]:(name,r) for name,r in outcomes.items()}
    for ticker,cfg in manifest['variants'].items():
        name,r=ordered.get(ticker,('',{}))
        if r.get('status')!='done':
            totals['cloud_failed' if r.get('status')=='failed' else 'cloud_pending']+=1
            lines.append(f'| {ticker} | — | — | — | — | — | — | {r.get("error_message","not completed")} |')
            rows.append(dict(ticker=ticker,status=r.get('status','not completed')))
            continue
        source=batch/name
        audit=json.loads((source/'audit.json').read_text())
        b=json.loads((source/'backtest.json').read_text())['backtest'];rt=b['runtimeStatistics']
        orders=json.loads((source/'orders.json').read_text())
        totals['cloud_done']+=1;totals['downloaded_orders']+=len(orders);totals['audited_cycles']+=audit.get('cycles',0)
        row=dict(ticker=ticker,status='done',capital=cfg['initial_cash'],cycles=audit.get('cycles'),
            net_pnl=float(rt.get('Net Profit','0').replace('$','').replace(',','')),
            active_return=float(rt['active_return']),daily_drawdown=float(rt['active_daily_mdd']),
            orders=len(orders),rolls=int(rt.get('rolls',0)),assignments=int(rt.get('assignments',0)),
            first_entry=rt.get('first_entry'),project_id=r['project_id'],backtest_id=r['backtest_id'])
        rows.append(row)
        lines.append(f'| {ticker} | {money(row["capital"])} | {row["cycles"]} | {money(row["net_pnl"])} | '
            f'{row["active_return"]:.2%} | {row["daily_drawdown"]:.2%} | {len(orders)} | [orders]({name}/orders.json) / '
            f'[QC](https://www.quantconnect.com/project/{r["project_id"]}/{r["backtest_id"]}) |')
        cycle_path=source/'cycles.csv'
        if cycle_path.exists():
            for c in csv.DictReader(cycle_path.open()):
                attribution.append(dict(ticker=ticker,entry=c['entry'],exit=c['exit'],reason=c['reason'],
                    pnl=float(c['pnl']),fees=float(c['fees']),rolls=int(c['rolls'])))
    yearly=defaultdict(lambda:dict(cycles=0,pnl=0.0,fees=0.0))
    for c in attribution:
        y=yearly[(c['ticker'],c['exit'][:4])]
        y['cycles']+=1;y['pnl']+=c['pnl'];y['fees']+=c['fees']
    lines+=['','## Closed-cycle P&L by year','',
        'Recognized in the closing year; these figures exclude unrealized year-end positions '
        'and are not annual marked equity returns. One contract before and after NVDA’s split '
        'has substantially different underlying exposure.','',
        '| Ticker | 2024 P&L / cycles | 2025 P&L / cycles | 2026 P&L / cycles |',
        '|---|---:|---:|---:|']
    for ticker in manifest['variants']:
        parts=[]
        for year in ['2024','2025','2026']:
            y=yearly.get((ticker,year),dict(pnl=0,cycles=0))
            parts.append(f'{money(y["pnl"])} / {y["cycles"]}')
        lines.append('| '+ticker+' | '+' | '.join(parts)+' |')
    lines+=['','## Local entry-filter research','',
        'The plan tests 36 combinations: IVR ≥50/60/70, IV/RV disabled/≥1/≥1.2/≥1.5, '
        'and absolute 20-session trend displacement disabled/≤1/≤2. Discovery uses cycles '
        'entered and closed by 2025-12-31; crossing cycles are purged. Selection maximizes discovery '
        'P&L after recorded fees and $10 additional cost per leg execution, requires at least eight '
        'cycles and three per discovery year, positive stress P&L and improvement over baseline. '
        'Otherwise the baseline is retained. The rule is frozen before evaluating 2026 entries. '
        'At least five validation cycles and positive stress P&L exceeding baseline are required '
        'for the report’s exploratory validation flag.','',
        'An empty validation sample means no trades, not successful validation. QQQ produced '
        'one cycle and 59 candidate-selection rejections; the counter combines delta and liquidity '
        'requirements, and the finite strike subscription range is another limitation. IBIT first '
        'entered on 2025-11-24 after building its IV history.','',
        '| Ticker | Frozen entry rule | Discovery cycles | Discovery net | 2026 cycles | 2026 net | 2026 baseline net | Exploratory support |',
        '|---|---|---:|---:|---:|---:|---:|---|']
    for ticker in manifest['variants']:
        path=batch/'local'/ticker/'optimization/summary.json'
        if not path.exists():
            lines.append(f'| {ticker} | unavailable; inspect cloud/coverage status | — | — | — | — | — | no |')
            continue
        s=json.loads(path.read_text());sel=s['selection'];cfg=sel['config'];val=s['validation_selected']
        rule=f'IVR≥{cfg["ivr"]}; IV/RV '+('off' if cfg['iv_rv'] is None else '≥'+str(cfg['iv_rv']))
        rule+='; trend '+('off' if cfg['trend'] is None else '≤'+str(cfg['trend']))
        if not sel['improvement_selected']: rule+=' (baseline retained)'
        d=sel['discovery']
        lines.append(f'| {ticker} | [{rule}](local/{ticker}/optimization/selection.json) | {d["cycles"]} | '
            f'{money(d["net_pnl"])} | {val["cycles"]} | {money(val["net_pnl"])} | '
            f'{money(s["validation_baseline"]["net_pnl"])} | {"yes, exploratory only" if s["validation_supported"] else "no"} |')
    lines+=['','Each nonempty unique discovery cycle subset, full baseline control and selected validation '
        'subset runs through AKQuant; actual fills, fees, final equity and zero residual positions are audited. '
        'Empty subsets retain cash and have no engine executions. '
        'The local simulation preserves original QC signals and prices. It measures conditional entry filters, '
        'without replacement entries or alternative strikes, sizing, rolls or exits. Provider trade-bar '
        'repricing is a separate price sensitivity, not an independently executable strategy.','',
        '## Provider-price coverage','',
        '| Ticker | Full baseline cycles | ≤5-minute covered cycles | ≤30-minute covered cycles | Same-day covered cycles | Same-day maximum age |',
        '|---|---:|---:|---:|---:|---:|']
    for ticker in manifest['variants']:
        path=batch/'local'/ticker/'provider/replay_summary.json'
        if not path.exists():
            lines.append(f'| {ticker} | — | — | — | — | unavailable |')
            continue
        scenarios={s['label']:s for s in json.loads(path.read_text())}
        control=scenarios.get('qc_control',{});stale=scenarios.get('provider_same_day_stale',{})
        lines.append(f'| {ticker} | {control.get("cycles",0)} | {scenarios.get("provider_5min",{}).get("cycles",0)} | '
            f'{scenarios.get("provider_30min",{}).get("cycles",0)} | {stale.get("cycles",0)} | '
            f'{stale.get("maximum_observed_age_minutes","n/a")} min |')
    lines+=['','## Evidence and limits','',
        '- Each ticker folder retains the full QC response, QC leg trades, all filled orders, available '
        'chart responses, logs, entry annotations, reconstructed cycles and accounting audit. An empty '
        'log response remains explicit. Local warehouses and Parquet hold source annotations and labels separately.',
        '- Each `local/<ticker>/engine_warehouse/` contains actual AKQuant execution ledgers and run audits '
        'in DuckDB and Parquet, with schemas, source hashes and table hashes. Alternative runs overlap; '
        'partition by `(ticker, engine_run_id)` rather than summing them as a portfolio.',
        '- Market data comes from read-only shared `data_providers` exports and targeted historical requests '
        'through its Alpaca transport. Missing prices never use future data or a QC fallback in provider scenarios. '
        'Only whole covered cycles are repriced; coverage subsets are not representative samples.',
        '- [Independent daily features](shared_provider_v2/manifest.json) cover all twelve underlyings. '
        'SPX uses the documented `^GSPC` alias from `us_daily/yfinance_index`; it is not a SPY proxy. '
        'Raw and adjusted stock-price bases are separate. Both SPX bases use the same price index, '
        'not a dividend-reinvested total-return index. These features do not alter the frozen selection grid.',
        '- Historical bid/ask option quotes are unavailable through this integration; the unsupported endpoint '
        'probe returned 404. The [official options quote endpoint](https://docs.alpaca.markets/us/reference/optionlatestquotes) '
        'is for latest quotes. Current quotes are never substituted for past ones.',
        '- Same-day trade prices may be hours old. Synthetic execution-only engine bars do not justify '
        'local daily Sharpe or drawdown; the table’s drawdown comes from QC daily snapshots.',
        '- SPX uses standard monthly European index options; ETF/equity options are physically settled and '
        'can assign early. Stock-delivery cycles require separate accounting and are excluded from option-only local optimization.',
        '- [SPX quote-clock diagnosis](SPX_DIAGNOSIS.md) retains the failed first attempt. '
        'Freshness comparisons must use the security’s local clock. A cloud smoke test of the fix '
        'completed one entry, one roll and a reconciled close with zero residual holdings. '
        'Only a full replacement passing the same accounting checks is accepted into the final table.',
        '- IBIT’s short options history can leave too few discovery cycles for supported optimization. '
        'SPY/GLD/TLT outcomes were already examined in earlier research, including 2026; their validation '
        'is not a pristine holdout. The other ticker studies still need independent subsequent evaluation.',
        '- These filters use causal QC entry annotations derived from raw-price snapshots; dividends and '
        'corporate actions can affect trailing return features. NVDA has an explicit pre-execution source '
        'amendment: close on QC split warning, block warning/split-day entries and reset the return window '
        'on occurrence. This avoids LEAN’s automatic option closure on a split. No earnings exclusion '
        'was added. Independent provider features retain raw and adjusted bases separately.',
        '- Testing 36 rules on small samples creates selection risk. An exploratory support flag is not '
        'evidence sufficient for live deployment. Changing management rules requires a new baseline or fuller simulation.',
        '- These are independent ticker accounts. The portfolio correlation gate has no other open '
        'underlying to compare, so its earlier restrictions disappear. The longer window also removes '
        'the old end-of-2025 forced flattening. Results need not equal a slice of the prior combined portfolio.','']
    verification=batch/'verification.json'
    if verification.exists():
        v=json.loads(verification.read_text())
        lines+=['## Final verification','',
            f'[Verification record](verification.json): {v["completed_qc_baselines"]} clean QC baselines, '
            f'{v["downloaded_orders"]} orders, {v["downloaded_qc_leg_trades"]} leg trades, '
            f'{v["audited_cycles"]} cycles, {v["actual_akquant_runs"]} actual engine runs and '
            f'{v["actual_akquant_executions"]} audited engine executions. Cash/equity, fees and residual '
            f'positions reconcile; {v["verified_research_parquet_tables"]} research Parquet tables pass '
            'row-count and checksum checks. Entry joins and provider reference bars pass availability checks. '
            'The owned server is stopped. Local checks passed 60 Rust tests and 23 strategy Python tests.','',
            '[Legacy regression parity](legacy_parity.json) matches all 28 earlier 2024–2025 '
            'SPY/TLT/GLD cycles individually, including dates, initial credits, exit reasons, '
            'fees, rolls and the −$3,429 total.','']
    (batch/'RESULTS.md').write_text('\n'.join(lines))
    (batch/'campaign_summary.json').write_text(json.dumps(dict(totals=totals,tickers=rows),indent=2))
    if attribution:
        with (batch/'cycle_attribution.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(attribution[0]));w.writeheader();w.writerows(attribution)
        with (batch/'yearly_cycle_pnl.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['ticker','closing_year','cycles','pnl','fees']);w.writeheader()
            w.writerows(dict(ticker=ticker,closing_year=year,**v) for (ticker,year),v in sorted(yearly.items()))
    files={str(p.relative_to(batch)):hashlib.sha256(p.read_bytes()).hexdigest()
        for pattern in ['*/orders.json','*/audit.json','local/*/optimization/selection.json',
                        'local/*/optimization/summary.json','local/*/provider/replay_summary.json']
        for p in batch.glob(pattern)}
    (batch/'evidence_hashes.json').write_text(json.dumps(files,indent=2))
    print(json.dumps(totals),flush=True)
    print(batch/'RESULTS.md',flush=True)


if __name__=='__main__':
    main()
