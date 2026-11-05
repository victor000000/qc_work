"""Inference must never turn a missing/corrupt model into a successful flat run."""
import ast
from datetime import datetime
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


def algorithm(payload=None, read_error=None):
    source = (Path(__file__).parents[1] / 'src/lb/templates/infer.py.tmpl').read_text()
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    namespace = dict(QCAlgorithm=object, TICKER='GLD', CELL='vol_tertile_binary_t45',
                     Resolution=SimpleNamespace(MINUTE=1), DataNormalizationMode=SimpleNamespace(RAW=1),
                     datetime=datetime, json=json, math=math)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), '<infer>', 'exec'), namespace)
    instance = namespace['AutoresearchInfer']()
    instance.set_start_date = instance.set_end_date = instance.set_cash = lambda *args: None
    instance.add_equity = lambda *args, **kwargs: SimpleNamespace(symbol='GLD', set_leverage=lambda value: None)
    def read(key):
        if read_error:
            raise read_error
        return json.dumps(payload)
    instance.object_store = SimpleNamespace(read=read)
    instance.stats = {}
    instance.set_runtime_statistic = instance.stats.__setitem__
    return instance


def test_missing_model_fails_with_key_and_original_error():
    algo = algorithm(read_error=FileNotFoundError('not found'))
    with pytest.raises(RuntimeError, match='cell_vol_tertile_binary_t45.json.*not found'):
        algo.initialize()


@pytest.mark.parametrize('predictions', [[], None, [{'time':'invalid','pred':0.6}],
    [{'time':'2024-01-01T00:00:00','pred':float('nan')}],
    [{'time':'2024-02-01T00:00:00','pred':0.6}, {'time':'2024-01-01T00:00:00','pred':0.7}]])
def test_invalid_predictions_fail_initialization(predictions):
    with pytest.raises(RuntimeError, match='Cannot load inference predictions'):
        algorithm({'predictions':predictions}).initialize()


def test_loaded_predictions_are_counted_and_unreplayed_run_fails():
    algo = algorithm({'predictions':[{'time':'2024-01-01T00:00:00','pred':0.6}]})
    algo.initialize()
    assert algo.stats['n_predictions'] == '1'
    with pytest.raises(RuntimeError, match='No inference predictions were replayed'):
        algo.on_end_of_algorithm()
    assert algo.stats['n_replayed_predictions'] == '0'
