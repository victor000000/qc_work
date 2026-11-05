"""Guard the four hand-maintained `_size` copies against silent drift.

The position-sizing rule is duplicated VERBATIM across four QC-rendered call sites:
  - src/lb/modules/sizing_ext.py     (VAL scorer, the canonical source)
  - src/lb/templates/infer.py.tmpl   (OOS replay — the crown metric)
  - src/lb/templates/live_trade.py.tmpl (live deploy)
  - src/lb/templates/portfolio.py.tmpl  (book replay)

They MUST stay logic-identical: a 2026-06-13 audit found `portfolio._size` had silently
dropped the `dd_overlay` branch, so the GLD champion (dd_overlay, 57.7% book weight) was
replayed as plain cdf in the book aggregate — a wrong, un-flagged book number. This test
AST-normalizes each copy (comments + docstring stripped) and asserts they are identical,
and that every VALID_SIZING mode is actually handled (not silently sized as cdf_plain).
"""
import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SOURCES = {
    "sizing_ext": os.path.join(ROOT, "src/lb/modules/sizing_ext.py"),
    "infer": os.path.join(ROOT, "src/lb/templates/infer.py.tmpl"),
    "live_trade": os.path.join(ROOT, "src/lb/templates/live_trade.py.tmpl"),
    "portfolio": os.path.join(ROOT, "src/lb/templates/portfolio.py.tmpl"),
    "combine": os.path.join(ROOT, "src/lb/templates/combine.py.tmpl"),
}


def _extract_func(path, name):
    """Return the source text of the top-level `def {name}` in a file (templates can't be
    whole-parsed — they carry bare placeholders like `CHAMPIONS = __CHAMPIONS__` — so we slice
    the self-contained function out by indentation and parse only that)."""
    out, started = [], False
    with open(path) as f:
        for ln in f:
            if not started:
                if re.match(r"def %s\s*\(" % re.escape(name), ln):
                    started = True
                    out.append(ln)
            else:
                if ln.strip() and not ln[0].isspace() and not ln.lstrip().startswith("#"):
                    break  # next top-level statement => function ended
                out.append(ln)
    assert out, "%s not found in %s" % (name, path)
    return "".join(out)


def _normalize(func_src):
    """AST dump with the docstring stripped (comments are already absent from the AST)."""
    fn = ast.parse(func_src).body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(getattr(fn.body[0], "value", None), ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        fn.body = fn.body[1:]
    return ast.dump(fn)


def test_size_copies_are_logic_identical():
    norms = {k: _normalize(_extract_func(p, "_size")) for k, p in SOURCES.items()}
    ref = norms["sizing_ext"]
    diverged = [k for k, n in norms.items() if n != ref]
    assert not diverged, (
        "_size diverged from the canonical sizing_ext copy in: %s — the four copies "
        "(VAL/infer/live/portfolio) must stay byte-for-byte logic-identical or VAL==OOS==live "
        "breaks silently." % diverged)


def test_size_covers_every_valid_sizing_mode():
    rr = ast.parse(open(os.path.join(ROOT, "scripts/run_round.py")).read())
    valid = None
    for node in ast.walk(rr):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "VALID_SIZING" for t in node.targets):
            valid = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    assert valid, "VALID_SIZING not found in run_round.py"
    src = _extract_func(SOURCES["sizing_ext"], "_size")
    handled = set(re.findall(r'sizing == "([a-z0-9_]+)"', src))
    for grp in re.findall(r"sizing in \(([^)]*)\)", src):
        handled |= set(re.findall(r'"([a-z0-9_]+)"', grp))
    handled.add("cdf_plain")  # the explicit fall-through default
    missing = [m for m in valid if m not in handled]
    assert not missing, (
        "VALID_SIZING modes with NO explicit branch in _size (they would silently size as "
        "cdf_plain in backtest AND live): %s" % missing)
