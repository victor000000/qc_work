import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest


HERE = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, HERE / relative)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HERE))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


collector = load('review_collector', 'collect.py')
capture = load('review_capture', 'local/capture.py')
pipeline = load('review_pipeline', 'single_pipeline.py')


def test_collector_rejects_cache_from_a_different_cloud_run():
    ids = dict(projectId=123, backtestId='new')
    collector.validate_cached_backtest({'backtest': ids}, ids)
    for cached in ({}, {'projectId': 123, 'backtestId': 'old'},
                   {'projectId': 456, 'backtestId': 'new'}):
        with pytest.raises(ValueError, match='identity'):
            collector.validate_cached_backtest({'backtest': cached}, ids)


def test_open_orders_without_group_are_not_silently_deduplicated():
    orders = [dict(tag='SPY:OPEN;ivr=60', time='2025-01-01')]
    with pytest.raises(ValueError, match='group identity'):
        collector.entry_features(orders)


def test_capture_checks_request_identity_and_pagination(tmp_path):
    path = tmp_path / 'capture.json'
    query = {'symbols': 'SPY250117C00600000', 'timeframe': '1Min'}
    valid = dict(query=query, pages=[{'bars': {}, 'next_page_token': None}])
    path.write_text(json.dumps(valid))
    capture.validate_cached_response(path, query)
    with pytest.raises(ValueError, match='differs'):
        capture.validate_cached_response(path, dict(query, symbols='OTHER'))
    for pages in ([], [{'bars': {}, 'next_page_token': 'unfinished'}], [{}]):
        path.write_text(json.dumps(dict(valid, pages=pages)))
        with pytest.raises(ValueError):
            capture.validate_cached_response(path, query)


def test_pipeline_resumes_failure_and_retains_partial_evidence(tmp_path, monkeypatch):
    name = 'SSTRANGLE_test_SPY'
    source = tmp_path / name
    source.mkdir()
    (source / 'audit.json').write_text(json.dumps({'cycles': 1}))
    (tmp_path / 'manifest.json').write_text(json.dumps({'jobs': [name], 'variants': {'SPY': {}}}))
    (tmp_path / 'outcomes.json').write_text(json.dumps({name: {'status': 'done'}}))
    monkeypatch.setattr(sys, 'argv', ['single_pipeline.py', str(tmp_path)])
    calls = []
    fail = [True]

    def run(command, **kwargs):
        script = Path(command[1]).name
        calls.append(script)
        if script == 'optimize_single.py':
            output = Path(command[-1])
            output.mkdir()
            (output / 'partial.txt').write_text('preserve me')
            if fail[0]:
                raise subprocess.CalledProcessError(1, command)
        if script == 'prepare.py':
            Path(command[-1]).mkdir()

    monkeypatch.setattr(pipeline.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='Local stages failed'):
        pipeline.main()
    progress = json.loads((tmp_path / 'local_progress.json').read_text())
    assert progress['SPY']['status'].startswith('failed;')
    assert progress['SPY']['stages']['provider_replay'] == 'complete'
    fail[0] = False
    calls.clear()
    pipeline.main()
    assert calls == ['collect.py', 'optimize_single.py']
    assert json.loads((tmp_path / 'local_progress.json').read_text())['SPY']['status'] == 'complete'
    archived = list((tmp_path / 'local' / 'SPY').glob('optimization.incomplete.*'))
    assert len(archived) == 1
    assert (archived[0] / 'partial.txt').read_text() == 'preserve me'


def test_capture_stops_repeated_page_tokens_without_publishing_bad_cache(tmp_path, monkeypatch):
    (tmp_path/'qc_executions.csv').write_text('timestamp,symbol\n2025-01-02T20:30:00+00:00,SPY250117C00600000\n')
    credentials = ModuleType('data_providers.credentials')
    credentials.AlpacaHeaders = lambda: {}
    http = ModuleType('data_providers.providers.alpaca_http')
    http.get_json = lambda *args, **kwargs: {'bars': {}, 'next_page_token': 'repeated'}
    monkeypatch.setitem(sys.modules, credentials.__name__, credentials)
    monkeypatch.setitem(sys.modules, http.__name__, http)
    monkeypatch.setattr(sys, 'argv', ['capture.py', str(tmp_path)])
    with pytest.raises(RuntimeError, match='2 provider requests failed'):
        capture.main()
    manifest = json.loads((tmp_path/'provider_capture/manifest.json').read_text())
    assert manifest['completed_jobs'] == 0
    assert len(manifest['failures']) == 2
    assert manifest['files'] == {}


def test_historical_baseline_does_not_inherit_an_unrelated_optimization_period(tmp_path, monkeypatch):
    (tmp_path/'manifest.json').write_text(json.dumps({'research_scope':'Historical baseline and data coverage'}))
    monkeypatch.setattr(sys,'argv',['single_pipeline.py',str(tmp_path)])
    with pytest.raises(ValueError,match='plan matching its dates'):
        pipeline.main()


def test_chart_sampling_window_preserves_daily_resolution_for_long_histories():
    window=collector.chart_window({'backtestStart':'2008-01-01 00:00:00','backtestEnd':'2026-09-30 23:59:59'})
    assert window['start']>1199000000
    assert (window['end']-window['start'])/window['count']<=43200


def test_chart_loading_response_is_polled_not_cached_as_data(monkeypatch):
    responses=iter([{'success':True,'status':'loading','progress':0},
                    {'success':True,'chart':{'series':{}}}])
    monkeypatch.setattr(collector,'request',lambda *args:next(responses))
    monkeypatch.setattr(collector.time,'sleep',lambda seconds:None)
    assert collector.read_chart('test','test',{})['chart']=={'series':{}}


def test_missing_order_payload_cannot_be_published_as_zero_orders(monkeypatch):
    responses=iter([{'success':True,'status':'loading'}, {'success':True,'orders':[{'id':1}]}])
    monkeypatch.setattr(collector,'request',lambda *args:next(responses))
    monkeypatch.setattr(collector.time,'sleep',lambda seconds:None)
    assert collector.read_order_page('test','test',{})==[{'id':1}]
    monkeypatch.setattr(collector,'request',lambda *args:{'success':True})
    with pytest.raises(RuntimeError,match='no orders field'):
        collector.read_order_page('test','test',{})


def test_order_collection_has_no_ten_thousand_order_truncation(monkeypatch):
    count=10_107
    monkeypatch.setattr(collector,'read_order_page',lambda user,token,p:
        [{'id':i} for i in range(p['start'],min(count,p['end']))])
    orders=collector.read_all_orders('test','test',{},count)
    assert len(orders)==count
    assert orders[-1]['id']==count-1


def test_order_collection_rejects_early_end_and_repeated_page(monkeypatch):
    monkeypatch.setattr(collector,'read_order_page',lambda *args:[])
    with pytest.raises(RuntimeError,match='ended early'):
        collector.read_all_orders('test','test',{},2)
    monkeypatch.setattr(collector,'read_order_page',lambda *args:[{'id':1}])
    with pytest.raises(RuntimeError,match='Duplicate order'):
        collector.read_all_orders('test','test',{},2)
