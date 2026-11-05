#!/usr/bin/env python3
"""Bounded, offline evidence for Draft 0.5; never submits QC/provider requests."""
import argparse
import hashlib
import json
import resource
import sys
import time
from importlib.metadata import version
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'strategies/sstrangle/local'))
from warehouse import daily_features
from replay import run_engine, assign_cycles


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_future(trades, features):
    """Strict decision contract: equality requires a documented sequencing policy."""
    trades = trades.copy()
    features = features.copy()
    trades['entry'] = pd.to_datetime(trades.entry, utc=True).astype('datetime64[ns, UTC]')
    features['available_at'] = pd.to_datetime(features.available_at, utc=True).astype('datetime64[ns, UTC]')
    frames = []
    for ticker, group in trades.groupby('ticker'):
        f = features[features.symbol == ticker].sort_values('available_at')
        joined = pd.merge_asof(group.sort_values('entry'), f, left_on='entry',
                               right_on='available_at', direction='backward',
                               allow_exact_matches=False, tolerance=pd.Timedelta(days=7))
        assert not (joined.available_at >= joined.entry).any()
        frames.append(joined)
    return pd.concat(frames).sort_values('cycle_id').reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    old = ROOT / 'strategies/sstrangle/results/local_akquant_20261017'
    broad = ROOT / 'strategies/sstrangle/results/liquidity_local_research_20261020'
    sources = {str((ROOT / 'strategies/sstrangle/local' / name).relative_to(ROOT)):
               digest(ROOT / 'strategies/sstrangle/local' / name)
               for name in ('warehouse.py', 'replay.py', 'prepare.py')}

    def read(path):
        sources[str(path.relative_to(ROOT))] = digest(path)
        return pd.read_parquet(path)

    summary_path = broad / 'summary.json'
    sources[str(summary_path.relative_to(ROOT))] = digest(summary_path)
    summary = json.loads(summary_path.read_text())
    for path, expected in summary['source_hashes'].items():
        path = Path(path)
        assert digest(path) == expected, path
        sources[str(path.relative_to(ROOT))] = expected
    executions = read(next(Path(p) for p in summary['source_hashes'] if p.endswith('executions.parquet')))
    labels = read(broad / 'cycle_labels.parquet')
    annotations = read(broad / 'entry_features.parquet')
    assert not executions.event_id.duplicated().any()
    assert not annotations.duplicated(['strategy_key', 'entry']).any()
    assert not labels.duplicated(['ticker', 'entry']).any()
    assert len(labels.merge(annotations, left_on=['ticker', 'entry'],
                            right_on=['strategy_key', 'entry'], validate='one_to_one')) == len(labels)
    # Reconstruct complete episodes from actual native identities, including rolls.
    active, rows, number = {}, [], 0
    for _, group in executions.groupby('group_id', sort=False):
        key = group.strategy_key.iloc[0]
        reason = group.reason.iloc[0]
        assert group.strategy_key.nunique() == group.reason.nunique() == 1
        if reason == 'OPEN':
            assert key not in active
            number += 1
            active[key] = (number, pd.Timestamp(group.timestamp.iloc[0]))
        cycle, entry = active[key]
        for r in group.to_dict('records'):
            rows.append(dict(r, episode_id=cycle, episode_entry=entry))
        if reason not in ('OPEN', 'ROLL'):
            del active[key]
    assert not active
    legs = pd.DataFrame(rows)
    legs['net_cash'] = -legs.quantity * legs.qc_price * legs.multiplier - legs.fee
    totals = legs.groupby(['strategy_key', 'episode_entry']).agg(
        net_cash=('net_cash', 'sum'), fees_actual=('fee', 'sum')).reset_index()
    labels['episode_entry'] = pd.to_datetime(labels.entry, utc=True)
    joined = labels.merge(totals, left_on=['ticker', 'episode_entry'],
                         right_on=['strategy_key', 'episode_entry'], validate='one_to_one')
    assert len(joined) == len(labels) == number
    assert np.allclose(joined.pnl, joined.net_cash, atol=1e-7, rtol=0)
    assert np.allclose(joined.fees, joined.fees_actual, atol=1e-7, rtol=0)
    assert legs.groupby('symbol_id').quantity.sum().abs().max() == 0
    assert abs(legs.net_cash.sum() - summary['net_pnl']) < 1e-7
    legs.to_parquet(out / 'episode_legs.parquet', compression='zstd', index=False)

    trades = read(old / 'parquet/baseline_trade_labels.parquet')
    prices = read(old / 'feature_price_history/data.parquet')
    features = daily_features(prices)
    entries = reject_future(trades[['cycle_id', 'ticker', 'entry']], features)
    fields = ['ret_1d', 'ret_5d', 'ret_20d', 'rv20', 'close_sma20_ratio']
    entries['complete'] = entries[fields].notna().all(axis=1)
    entries['missing_reason'] = np.where(entries.complete, '', 'no_fresh_complete_daily_history')
    assert entries.cycle_id.is_unique and len(entries) == len(trades)
    # Mutating future observations must leave all earlier features unchanged.
    cutoff = pd.Timestamp('2025-01-01', tz='UTC')
    changed = prices.copy()
    changed.loc[pd.to_datetime(changed.date) >= cutoff.tz_localize(None), 'close'] *= 100
    before = entries[entries.entry < cutoff].reset_index(drop=True)
    after = reject_future(trades[['cycle_id', 'ticker', 'entry']], daily_features(changed))
    pd.testing.assert_frame_equal(before[fields], after[after.entry < cutoff][fields].reset_index(drop=True))
    # Inject a future/equal timestamp and a stale bar, exercising both rejections.
    probe = trades[['cycle_id', 'ticker', 'entry']].iloc[[0]].copy()
    bad = features[features.symbol == probe.ticker.iloc[0]].iloc[[-1]].copy()
    for delta in (pd.Timedelta(0), pd.Timedelta(minutes=1), -pd.Timedelta(days=8)):
        bad['available_at'] = probe.entry.iloc[0] + delta
        assert reject_future(probe, bad)[fields].isna().all().all()
    assert set(fields).isdisjoint({'pnl', 'fees', 'exit', 'initial_credit'})
    # Small explicit vector and contemporaneous group operators; no BRAIN equivalence claim.
    delta_vector = annotations[['put_delta', 'call_delta']].to_numpy()
    assert delta_vector.shape == (188, 2) and np.isfinite(delta_vector).all()
    annotations['abs_delta_sum'] = np.abs(delta_vector).sum(axis=1)
    annotations['ivr_rank_same_entry'] = annotations.groupby('entry').ivr.rank(pct=True)
    assert annotations.ivr_rank_same_entry.between(0, 1).all()
    annotations.to_parquet(out / 'annotation_operator_examples.parquet', compression='zstd', index=False)
    entries.to_parquet(out / 'entry_features.parquet', compression='zstd', index=False)
    trades.to_parquet(out / 'labels.parquet', compression='zstd', index=False)
    registry = dict(version='0.5-poc', fields={f: dict(dtype='float64', role='entry_feature',
        scope='underlying', frequency='daily',
        unit='annualized_return_volatility' if f == 'rv20' else 'dimensionless_ratio',
        availability='next New York midnight',
        max_age_days=7, source='saved raw daily prices; warehouse.daily_features') for f in fields},
        vector_example='sum(abs([put_delta, call_delta])); QC annotation only',
        group_example='IVR percentile within exact entry batch only; not full-market rank',
        excluded_inputs=['pnl', 'fees', 'exit', 'initial_credit'],
        point_in_time_policy='available_at < decision_at; same timestamp needs explicit event ordering')
    (out / 'feature_registry.json').write_text(json.dumps(registry, indent=2)+'\n')
    con = duckdb.connect(str(out / 'research.duckdb'))
    con.read_parquet(str(out / 'entry_features.parquet')).create_view('entry_features')
    con.read_parquet(str(out / 'labels.parquet')).create_view('labels')
    assert con.execute('SELECT count(*) FROM entry_features').fetchone()[0] == len(trades)
    con.close()

    # Identical frozen schedule across 5/15/30/60: data engineering only.
    minute = read(old / 'parquet/provider_trade_minutes.parquet')
    minute['timestamp'] = pd.to_datetime(minute.timestamp, utc=True)
    minute = minute.sort_values(['symbol', 'timestamp'])
    assert not minute.duplicated(['source', 'symbol', 'timestamp']).any()
    benches = []
    for freq in (5, 15, 30, 60):
        for repeat in range(3):
            wall, cpu = time.perf_counter(), time.process_time()
            m = minute.copy()
            local = m.timestamp.dt.tz_convert('America/New_York')
            # RTH session anchored at 09:30. Early close calendar not available:
            # these bins are workload samples only, not accepted execution data.
            session = local.dt.normalize() + pd.Timedelta(hours=9, minutes=30)
            offset = (local-session).dt.total_seconds() // 60
            m = m[(offset >= 0) & (offset < 390)].copy()
            m['session'] = session.loc[m.index].dt.tz_convert('UTC')
            m['bucket'] = (offset.loc[m.index] // freq).astype(int)
            panel = m.groupby(['source', 'symbol', 'session', 'bucket'], observed=True).agg(
                open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
                close=('close', 'last'), volume=('volume', 'sum'), observed_minutes=('timestamp', 'nunique')).reset_index()
            panel['available_at'] = panel.session + pd.to_timedelta((panel.bucket+1)*freq, unit='m')
            panel['complete_fixed_interval'] = panel.observed_minutes.eq(freq)
            dest = out / f'panel_{freq}m.parquet'
            panel.to_parquet(dest, compression='zstd', index=False)
            # Read and bounded 1,024-column arithmetic workload over same real trade rows.
            loaded = pd.read_parquet(dest)
            x = entries[fields].to_numpy(dtype=float)
            count = 0
            for pack in range(16):
                shifts = np.arange(pack*64, (pack+1)*64)[None, :]
                values = x[:, [0]] * (1 + shifts/1024) + x[:, [1]]
                count += np.isfinite(values).sum().item()
            benches.append(dict(minutes=freq, repeat=repeat, cache='first-pass' if repeat == 0 else 'warm-repeat',
                rows=len(loaded), complete_intervals=int(panel.complete_fixed_interval.sum()),
                parquet_bytes=dest.stat().st_size, bytes_per_row=dest.stat().st_size/max(len(panel),1),
                wall_seconds=time.perf_counter()-wall, cpu_seconds=time.process_time()-cpu,
                formula_values=count, process_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024))
    pd.DataFrame(benches).to_csv(out / 'benchmarks.csv', index=False)

    # Same library used by notebook/batch: full tape and both sides of one predeclared filter.
    csv = old / 'qc_executions.csv'
    sources[str(csv.relative_to(ROOT))] = digest(csv)
    tape = pd.read_csv(csv).to_dict('records')
    assign_cycles(tape)
    for r in tape:
        r['age_minutes'] = None
    trials = []
    for name, mask in [('all', np.ones(len(entries), dtype=bool)),
                       ('ret5_positive', entries.complete & (entries.ret_5d > 0)),
                       ('ret5_nonpositive', entries.complete & (entries.ret_5d <= 0))]:
        ids = set(entries.loc[mask, 'cycle_id'])
        selected = [r for r in tape if r['cycle_id'] in ids]
        wall, cpu = time.perf_counter(), time.process_time()
        _, audit = run_engine(selected, {int(r['order_id']):float(r['qc_price']) for r in selected},
                              out / ('replay_' + name), initial_cash=250000)
        expected = float(trades[trades.cycle_id.isin(ids)].pnl.sum())
        assert abs(audit['engine_net_pnl']-expected) < 1e-7
        trials.append(dict(trial=name, status='accounting_pass', retained_trades=len(ids),
            entry_days=entries.loc[mask, 'entry'].dt.date.nunique(),
            net_pnl=expected, wall_seconds=time.perf_counter()-wall,
            cpu_seconds=time.process_time()-cpu, **audit,
            interpretation='Conditional fixed-tape replay; no independent portfolio, OOS or marked-risk claim'))
    pd.DataFrame(trials).to_json(out / 'trials.json', orient='records', indent=2)
    assert trials[1]['retained_trades'] + trials[2]['retained_trades'] == int(entries.complete.sum())
    result = dict(date='2026-10-23', classification='offline mini PoC; existing QC/provider fixtures',
        qc_broad=dict(episodes=len(labels), fills=len(legs), fees=float(legs.fee.sum()),
                      net_pnl=float(legs.net_cash.sum()), max_episode_cash_error=float((joined.pnl-joined.net_cash).abs().max()),
                      native_identity_and_event_uniqueness=True, residual_contract_positions=0),
        features=dict(trades=len(entries), complete=int(entries.complete.sum()), missing=int((~entries.complete).sum()),
                      fields=fields, per_ticker=entries.groupby('ticker').complete.agg(['size', 'sum']).to_dict('index'),
                      future_mutation_invariance=True, future_equal_stale_rejection=True),
        benchmark=dict(input_minutes=len(minute), measurements=len(benches), formula_workload=1024,
                       process_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                       cache_policy='OS cache not cleared; first pass and warm repeats only',
                       scope='Sparse saved option trade bars, no NBBO; arithmetic workload is redundant, not 1024 independent alphas'),
        trials=trials, total_wall_seconds=time.perf_counter()-started,
        versions={p:version(p) for p in ['pandas', 'numpy', 'duckdb', 'pyarrow', 'akquant']},
        sources=sources,
        pending=['Fresh SPX baseline', 'new QC pagination/tag roundtrip', 'current provider release admission',
                 'NBBO/OI and full candidate inventory', 'independent quote-backed simulation',
                 'economic timeframe comparison', 'marked risk of filtered paths', 'final QC parity'])
    (out / 'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    files = {str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'manifest.json').write_text(json.dumps(dict(script_sha256=digest(Path(__file__)), files=files), indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources','trials')}, indent=2))


if __name__ == '__main__':
    main()
