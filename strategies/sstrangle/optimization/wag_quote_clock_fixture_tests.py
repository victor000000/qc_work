"""Contract checks for the thin observer bridge; no native fill claims."""
import ast
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).with_name('wag_quote_clock_fixture.py')


class Parent:
    def initialize(self):
        self.predicates = Counter()
        self.parent_data = []

    def on_data(self, data):
        self.parent_data.append(data)
        for side in ('put', 'call'):
            self.diagnose(side, side + '_native')

    def diagnose(self, side, symbol):
        self.predicates[side + '_original'] += 1


class Observer:
    def __init__(self):
        self.calls = []
        self.counts = Counter()

    def observe_native(self, side, algorithm, data, symbol, quote_type):
        self.calls.append((side, algorithm, data, symbol, quote_type))
        self.counts[side + '_observations'] += 1

    def runtime_counts(self):
        return dict(self.counts)


def make_fixture():
    tree = ast.parse(SOURCE.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    namespace = dict(WAGExitRegression=Parent, WAGQuoteClockDiagnostics=Observer, QuoteBar=object)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), str(SOURCE), 'exec'), namespace)
    fixture = namespace['WAGClockRegression']()
    fixture.initialize()
    return fixture, cls


def test_native_slice_is_forwarded_unchanged_to_original_path_and_observer():
    fixture, _ = make_fixture()
    data = SimpleNamespace()
    fixture.on_data(data)
    assert fixture.parent_data == [data]
    assert all(call[2] is data and call[1] is fixture for call in fixture.clock_observer.calls)
    assert [call[3] for call in fixture.clock_observer.calls] == ['put_native', 'call_native']


def test_cumulative_counts_are_assigned_without_double_counting_parent_observations():
    fixture, _ = make_fixture()
    for _ in range(3):
        fixture.on_data(SimpleNamespace())
    assert fixture.predicates == {'put_original': 3, 'call_original': 3,
                                  'clock_put_observations': 3, 'clock_call_observations': 3}


def test_bridge_cannot_override_trading_or_quote_eligibility_methods():
    _, cls = make_fixture()
    assert {node.name for node in cls.body if isinstance(node, ast.FunctionDef)} == {'initialize', 'on_data', 'diagnose'}
    assert SOURCE.read_text().count('    CONFIG = {}') == 1
