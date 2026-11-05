"""QC ObjectStore returns a boolean; rejected writes cannot claim persisted models."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def save_required():
    source = (Path(__file__).parents[1] / 'src/lb/templates/footer.py.tmpl').read_text()
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_put')
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<footer>', 'exec'), namespace)
    return namespace['_put']


def test_rejected_write_reports_the_model_key():
    with pytest.raises(RuntimeError, match='Cannot save owned/cell.json'):
        save_required()(SimpleNamespace(save=lambda *args: False), 'owned/cell.json', '{}')


def test_successful_write_preserves_payload():
    calls = []
    def save(key, value):
        calls.append((key, value))
        return True
    save_required()(SimpleNamespace(save=save), 'owned/cell.json', '{"predictions":[]}')
    assert calls == [('owned/cell.json', '{"predictions":[]}')]
