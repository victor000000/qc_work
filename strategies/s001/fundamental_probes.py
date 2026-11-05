"""Library for cataloguing, rendering, and classifying S001 fundamental probes.

Pure functions; all DB I/O lives in scripts/{catalogue,emit,score}_probes.py."""
import json
import re
import qc_storage as storage
import statistics

CONTAINER_ALIAS = {
    'balance_sheet':        '_bs_z',
    'cash_flow_statement':  '_cfs_z',
    'income_statement':     '_inc_z',
    'operation_ratios':     '_ops_z',
    'valuation_ratios':     '_vr_z',
    'earning_ratios':       '_ers_z',
    'earning_reports':      '_er_z',
    'asset_classification': '_ac_z',
    'security_reference':   '_sr_z',
}


def accessor_for(row):
    """Build the Python accessor string for a fundamental_fields row.

    row: dict-like with 'container', 'field_name', 'period' keys.
    Returns: e.g. '_vr_z.pe_ratio' or '_bs_z.long_term_debt.twelve_months'.
    """
    base = f"{CONTAINER_ALIAS[row['container']]}.{row['field_name']}"
    return f"{base}.{row['period']}" if row['period'] else base


HOT_THRESHOLD = 0.0015      # delta strictly greater → 'hot'
HARMFUL_THRESHOLD = -0.0015  # delta strictly less → 'harmful'


MECHANISMS = ('score', 'skip', 'stop', 'petgt', 'convg', 'convb')

MECH_DEFAULTS = {
    'score': {'action': 'score *= {mag}',  'mag': 1.10, 'gate': 'decline > .05',
              'side': 'good', 'location': 'entry'},
    'skip':  {'action': 'continue',        'mag': None, 'gate': 'decline > .10',
              'side': 'bad',  'location': 'entry'},
    'stop':  {'action': 'stop *= {mag}',   'mag': 0.85, 'gate': None,
              'side': 'bad',  'location': 'exit'},
    'petgt': {'action': 'petgt *= {mag}',  'mag': 1.15, 'gate': None,
              'side': 'good', 'location': 'exit'},
    'convg': {'action': 'conv *= {mag}',   'mag': 1.15, 'gate': 'decline > .05',
              'side': 'good', 'location': 'entry'},
    'convb': {'action': 'conv *= {mag}',   'mag': 0.70, 'gate': 'decline > .05',
              'side': 'bad',  'location': 'entry'},
}


def classify_delta(d):
    """Classify a probe's CAR/MDD delta vs round NOOP baseline.

    Returns one of: 'hot', 'neutral', 'harmful'.
    Boundary semantics: exact ±0.0015 is 'neutral' (strict >/<)."""
    if d > HOT_THRESHOLD:
        return 'hot'
    if d < HARMFUL_THRESHOLD:
        return 'harmful'
    return 'neutral'


def field_rollup(results):
    """Compute aggregate field classification from probe_results rows
    already filtered to the current bake_hash.

    Rule (conservative, matches §7.2 of spec):
      - empty → 'untested'
      - any 'harmful' → 'harmful' (poisons even if hot exists)
      - any 'hot' → 'hot'
      - else → 'neutral'

    results: iterable of dict-like rows with 'classification' key."""
    if not results:
        return 'untested'
    classes = {r['classification'] for r in results}
    if 'harmful' in classes:
        return 'harmful'
    if 'hot' in classes:
        return 'hot'
    return 'neutral'


def build_condition(row, var='_v'):
    """Build the boolean condition fragment for a probe row.

    row: must have probe_op, probe_threshold, data_type_hint keys.
    var: the local name of the value (default '_v').
    Returns: a Python expression string (no leading 'if', no trailing colon).
    """
    op = row['probe_op']
    thr = row['probe_threshold']
    hint = row.get('data_type_hint') or 'numeric'

    if op in ('>', '>='):
        return f"{var} is not None and {var} {op} {thr}"

    if op in ('<', '<='):
        if hint == 'absolute_amount':
            return f"{var} is not None and 0 < {var} {op} {thr}"
        if hint == 'absolute_amount_signed':
            return f"{var} is not None and abs({var}) {op} {thr}"
        return f"{var} is not None and {var} {op} {thr}"

    if op == 'eq':
        if hint != 'categorical':
            raise ValueError(f"op 'eq' requires data_type_hint='categorical', got {hint!r}")
        # threshold is JSON: a quoted string ('"A"') or a bare number ('207').
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError as e:
            raise ValueError(f"op 'eq' requires JSON threshold: {thr!r} ({e})")
        return f"{var} == {parsed!r}" if isinstance(parsed, str) else f"{var} == {parsed}"

    if op == 'in':
        if hint != 'categorical':
            raise ValueError(f"op 'in' requires data_type_hint='categorical', got {hint!r}")
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError as e:
            raise ValueError(f"op 'in' requires JSON array threshold: {thr!r} ({e})")
        if not isinstance(parsed, list):
            raise ValueError(f"op 'in' requires JSON array threshold: got {type(parsed).__name__}")
        if len(parsed) == 1:
            tup_repr = f"({parsed[0]!r},)" if isinstance(parsed[0], str) else f"({parsed[0]},)"
        else:
            inner = ", ".join(repr(x) if isinstance(x, str) else str(x) for x in parsed)
            tup_repr = f"({inner})"
        return f"{var} in {tup_repr}"

    if op == 'neq':
        if hint != 'categorical':
            raise ValueError(f"op 'neq' requires data_type_hint='categorical', got {hint!r}")
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError as e:
            raise ValueError(f"op 'neq' requires JSON threshold: {thr!r} ({e})")
        return f"{var} != {parsed!r}" if isinstance(parsed, str) else f"{var} != {parsed}"

    if op == 'notin':
        if hint != 'categorical':
            raise ValueError(f"op 'notin' requires data_type_hint='categorical', got {hint!r}")
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError as e:
            raise ValueError(f"op 'notin' requires JSON array threshold: {thr!r} ({e})")
        if not isinstance(parsed, list):
            raise ValueError(f"op 'notin' requires JSON array threshold: got {type(parsed).__name__}")
        if len(parsed) == 1:
            tup_repr = f"({parsed[0]!r},)" if isinstance(parsed[0], str) else f"({parsed[0]},)"
        else:
            inner = ", ".join(repr(x) if isinstance(x, str) else str(x) for x in parsed)
            tup_repr = f"({inner})"
        return f"{var} not in {tup_repr}"

    raise NotImplementedError(f"build_condition: op {op!r} not supported")


BIND = """   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ers_z = getattr(_fz, 'earning_ratios', None) if _fz else None
    _er_z  = getattr(_fz, 'earning_reports', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _sr_z  = getattr(_fz, 'security_reference', None) if _fz else None
    _fs_z  = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z  = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _cfs_z = getattr(_fs_z, 'cash_flow_statement', None) if _fs_z else None
   except: _ops_z=_vr_z=_ers_z=_er_z=_ac_z=_sr_z=_fs_z=_bs_z=_inc_z=_cfs_z=None
"""

# ENTRY/EXIT bind aliases for the mega-round generator. Both injection points
# sit inside their respective `for sym in equities:` loops at the same 3-space
# indent level, so the fundamental-attribute prelude is identical for both.
ENTRY_BIND = BIND
EXIT_BIND = BIND



def render_probe(row):
    """Render Python probe code for a single fundamental_fields row.

    Returns the per-probe try/except block (does NOT include BIND).
    The caller injects BIND once per spec, then concatenates one or
    more render_probe() outputs.

    Raises ValueError if probe_threshold is NULL or template is invalid."""
    if row['probe_threshold'] is None:
        raise ValueError(
            f"probe_threshold is NULL for {row.get('container')}/{row.get('field_name')}; "
            f"field needs a template before it can be probed.")

    accessor = accessor_for(row)
    hint = row.get('data_type_hint') or 'numeric'
    if hint == 'categorical':
        coerced = accessor   # raw access, no float coerce
    else:
        coerced = f"f_({accessor})"

    cond = build_condition(row, '_v')
    gate = f" and ({row['probe_gate']})" if row['probe_gate'] else ""
    return (
        "   try:\n"
        f"    _v = {coerced}\n"
        f"    if {cond}{gate}: score *= {row['probe_boost']}\n"
        "   except: pass"
    )


CONTAINER_SHORT = {
    'balance_sheet':        'bs',
    'cash_flow_statement':  'cfs',
    'income_statement':     'inc',
    'operation_ratios':     'ops',
    'valuation_ratios':     'vr',
    'earning_ratios':       'ers',
    'earning_reports':      'er',
    'asset_classification': 'ac',
    'security_reference':   'sr',
}

OP_SHORT = {
    '>':  'gt',
    '>=': 'gte',
    '<':  'lt',
    '<=': 'lte',
    'eq': 'eq',
    'in': 'in',
}


def flip_op(op):
    """Return the logical inverse of a probe op.

    Used by mega-round 'bad-side' mechanisms (skip/stop/convb) which trigger on
    the opposite side of a field's stored 'good' template."""
    return {'>': '<', '<': '>', '>=': '<=', '<=': '>=',
            'eq': 'neq', 'in': 'notin'}[op]


def _threshold_short(thr, op):
    """Compress a probe_threshold into an identifier-safe suffix."""
    if op in ('eq', 'in'):
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError:
            parsed = thr
        if isinstance(parsed, list):
            joined = ''.join(str(x).replace('+', 'plus').replace('-', 'minus')
                             for x in parsed)
        else:
            joined = str(parsed).replace('+', 'plus').replace('-', 'minus')
        return re.sub(r'[^A-Za-z0-9]', '', joined)
    # Numeric: keep digits, decimal point dropped, scientific notation kept.
    return thr.replace('.', '').replace('-', 'neg').replace('+', '')


def _format_threshold(value, hint):
    """Format a numeric threshold for display in spec names and storage.

    - Returns '0' for exact zero.
    - For |value| >= 1e6 or |value| < 1e-3, uses scientific notation with 3
      fractional digits ('1.500e+09'). Higher precision avoids collisions when
      p25/p50/p75 cluster tightly.
    - Otherwise, uses 4 significant figures via Python's '{:.4g}' ('0.1080', '15', '120.0').
    - hint is reserved for future per-type formatting; currently unused.
    """
    if value == 0:
        return '0'
    abs_v = abs(value)
    if abs_v >= 1e6 or abs_v < 1e-3:
        return f'{value:.3e}'
    return f'{value:.4g}'


def spec_name(row, round_n):
    """Build the deterministic backtest spec name for a probe row.

    Format: S001_R{round_n}_{container_short}_{field_name}_{op_short}{thr_short}
    Truncated to 100 chars (UNIQUE constraint on backtest_queue.name is the safety net).
    """
    cs = CONTAINER_SHORT[row['container']]
    op_s = OP_SHORT[row['probe_op']]
    thr_s = _threshold_short(row['probe_threshold'], row['probe_op'])
    # Categorical ops get an underscore separator before the threshold.
    sep = '_' if row['probe_op'] in ('eq', 'in') else ''
    name = f"S001_R{round_n}_{cs}_{row['field_name']}_{op_s}{sep}{thr_s}"
    return name[:100]


def mega_spec_name(round_n, mech, field_row):
    """Build the deterministic mega-round spec name.

    Format: S001_R{round_n}_mg_{mech}_{container_short}_{field_name}

    The `_mg_<mech>_<cs>_` prefix is fully anchored, so the trailing field_name
    can contain `_in_`, `_gt_`, etc. without triggering the v1 parser bug."""
    if mech not in MECHANISMS:
        raise KeyError(f'Unknown mechanism {mech!r}; expected one of {MECHANISMS}')
    cs = CONTAINER_SHORT[field_row['container']]
    return f"S001_R{round_n}_mg_{mech}_{cs}_{field_row['field_name']}"


def render_cell(field_row, mech, round_n, mag=None, gate_override=None):
    """Render a single mega-round cell.

    Returns (spec_name, body, location) or None if the cell should be dropped
    (safety valve for ambiguous inverses).

    location ∈ {'entry', 'exit'} — generator splices at the matching anchor."""
    defaults = MECH_DEFAULTS[mech]
    side = defaults['side']
    op = field_row['probe_op'] if side == 'good' else flip_op(field_row['probe_op'])
    thr = field_row['probe_threshold']
    hint = field_row.get('data_type_hint') or 'numeric'

    # Safety valve: drop bad-side `notin` cells when the inverse array is huge
    # (covers >50% of universe). Not triggered by any current DB row.
    if op == 'notin' and side == 'bad':
        try:
            parsed = json.loads(thr)
            if isinstance(parsed, list) and len(parsed) > 100:
                return None
        except (json.JSONDecodeError, TypeError):
            return None

    accessor = accessor_for(field_row)
    coerced = accessor if hint == 'categorical' else f'f_({accessor})'

    cond_row = {'probe_op': op, 'probe_threshold': thr, 'data_type_hint': hint}
    cond = build_condition(cond_row, '_v')

    chosen_mag = mag if mag is not None else defaults['mag']
    action = (defaults['action'].format(mag=chosen_mag)
              if chosen_mag is not None
              else defaults['action'])

    gate = gate_override if gate_override is not None else defaults['gate']
    name = mega_spec_name(round_n, mech, field_row)
    location = defaults['location']

    if gate:
        body = (
            "   try:\n"
            f"    _v = {coerced}\n"
            f"    if {cond} and ({gate}): {action}\n"
            "   except: pass"
        )
    else:
        body = (
            "   try:\n"
            f"    _v = {coerced}\n"
            f"    if {cond}: {action}\n"
            "   except: pass"
        )

    return name, body, location


CONTAINER_CYCLE = [
    'valuation_ratios', 'operation_ratios', 'asset_classification',
    'balance_sheet', 'cash_flow_statement', 'income_statement',
    'earning_ratios', 'earning_reports', 'security_reference',
]


def pick_fields(db_path, k, classification='untested', bake_hash=None,
                force_all=False):
    """Pick up to k fields with the given classification on the CURRENT bake_hash.

    For 'untested': fields with NO probe_results for this bake_hash.
    For 'hot'/'neutral'/'harmful': fields with at least one matching
    probe_results.classification on this bake_hash.

    If force_all=True: ignore classification + NOT EXISTS scoping; return every
    field with a non-null probe_threshold across all containers (mega-round mode).

    Within each container, ORDER BY id ASC. Cycles through containers until
    k fields collected (or pool exhausted). Skips rows with NULL probe_threshold.
    """
    if bake_hash is None and not force_all:
        bake_hash = current_bake_hash(db_path)

    queues = {}
    with storage.connect(db_path) as con:
        con.row_factory = storage.Row
        cur = con.cursor()
        for cont in CONTAINER_CYCLE:
            if force_all:
                cur.execute("""
                    SELECT * FROM fundamental_fields f
                    WHERE f.container = ?
                      AND f.probe_threshold IS NOT NULL
                    ORDER BY f.id ASC
                """, (cont,))
            elif classification == 'untested':
                cur.execute("""
                    SELECT * FROM fundamental_fields f
                    WHERE f.container = ?
                      AND f.probe_threshold IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM probe_results p
                        WHERE p.field_id = f.id AND p.bake_hash = ?
                      )
                    ORDER BY f.id ASC
                """, (cont, bake_hash))
            else:
                cur.execute("""
                    SELECT DISTINCT f.* FROM fundamental_fields f
                    JOIN probe_results p ON p.field_id = f.id
                    WHERE f.container = ? AND p.bake_hash = ?
                      AND p.classification = ?
                      AND f.probe_threshold IS NOT NULL
                    ORDER BY f.id ASC
                """, (cont, bake_hash, classification))
            queues[cont] = [dict(r) for r in cur.fetchall()]

    picked = []
    while len(picked) < k:
        progress = False
        for cont in CONTAINER_CYCLE:
            if queues[cont]:
                picked.append(queues[cont].pop(0))
                progress = True
                if len(picked) >= k:
                    break
        if not progress:
            break
    return picked


# Optional explicit override for research against a particular LEAN release.
# Otherwise use the stubs installed in the active Python environment.
import os
from importlib.metadata import distribution
LEAN_PYI = os.environ.get('QC_LEAN_STUB_PATH')


# Top-level container classes whose @property fields we extract.
# Map: lean_class_name → fundamental_fields.container value.
LEAN_CONTAINERS = {
    'BalanceSheet':        'balance_sheet',
    'CashFlowStatement':   'cash_flow_statement',
    'IncomeStatement':     'income_statement',
    'OperationRatios':     'operation_ratios',
    'ValuationRatios':     'valuation_ratios',
    'EarningRatios':       'earning_ratios',
    'EarningReports':      'earning_reports',
    'AssetClassification': 'asset_classification',
    'SecurityReference':   'security_reference',
}

# Patterns excluded when scanning property names (per spec §8.1).
EXCLUDE_FIELD_PATTERNS = (
    'file_date', 'accession_number', 'form_type', 'period_type',
    'period_ending_date', 'period_auditor',
)
EXCLUDE_FIELD_SUFFIXES = ('_currency_id',)


def _read_lean_pyi():
    path = LEAN_PYI or distribution('quantconnect-stubs').locate_file(
        'QuantConnect/Data/Fundamental/__init__.pyi')
    with open(path) as f:
        return f.read()


def _container_property_names(src, class_name):
    """Extract @property names from a class block in the .pyi source."""
    m = re.search(rf'^class {class_name}\b.*?(?=^class \w|\Z)', src, re.M | re.S)
    if not m:
        return []
    block = m.group(0)
    import ast
    definition = ast.parse(block).body[0]
    return [member.name for member in definition.body
            if isinstance(member, ast.FunctionDef)
            and any(isinstance(decorator, ast.Name) and decorator.id == 'property'
                    for decorator in member.decorator_list)
            and 'was retired by Morningstar' not in (ast.get_docstring(member) or '')]


def extract_lean_universe():
    """Reflect over the LEAN __init__.pyi and return per-container field name lists.

    Returns: {container_value: [field_name, ...]} for each LEAN_CONTAINERS entry.
    Filters out metadata fields per spec §8.1.
    """
    src = _read_lean_pyi()
    out = {}
    for class_name, cont_value in LEAN_CONTAINERS.items():
        props = _container_property_names(src, class_name)
        cleaned = []
        for p in props:
            if any(pat in p for pat in EXCLUDE_FIELD_PATTERNS):
                continue
            if any(p.endswith(suf) for suf in EXCLUDE_FIELD_SUFFIXES):
                continue
            # Strip the bs_/cf_/is_ prefix used by LEAN for some fields
            if cont_value == 'balance_sheet' and p.startswith('bs_'):
                continue  # bs_file_date etc — already filtered by patterns above
            cleaned.append(p)
        out[cont_value] = cleaned
    return out


DEFAULT_PERIOD = {
    'balance_sheet':        'twelve_months',
    'cash_flow_statement':  'twelve_months',
    'income_statement':     'twelve_months',
    'earning_reports':      'twelve_months',
    'operation_ratios':     'one_year',
    'earning_ratios':       'one_year',
    'valuation_ratios':     None,
    'asset_classification': None,
    'security_reference':   None,
}


def default_period(container):
    return DEFAULT_PERIOD[container]


# Field-name patterns that indicate a "low is good" valuation ratio.
LOW_GOOD_VR_PATTERNS = ('pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio',
                        'price_to_', 'ev_to_', 'forward_pe', 'normalized_pe')

# Operation-ratios patterns indicating leverage/debt (low is good).
LOW_GOOD_OPS_PATTERNS = ('debt', 'leverage', 'days_in_inventory', 'days_in_payable',
                         'days_sales_outstanding', 'cash_conversion_cycle')

# Balance-sheet/cash-flow patterns indicating debt items (low is good).
DEBT_LIKE_BS = ('debt', 'liabilities', 'accounts_payable', 'capital_lease')

# Categorical sector defaults: defensive sector codes (Utilities=207, Healthcare=206, ConsumerDef=205).
DEFAULT_DEFENSIVE_SECTORS = '[205, 206, 207]'
DEFAULT_A_TIER_GRADES = '["A", "A+", "A-"]'


def _matches_any(field_name, patterns):
    return any(pat in field_name for pat in patterns)


def default_template(container, field_name):
    """Return a dict with default {probe_op, probe_threshold, probe_gate,
    probe_boost, data_type_hint} for a (container, field_name) pair.

    Uses spec §8.3 heuristics. Author can override per-row via DB UPDATE."""
    if container == 'valuation_ratios':
        if _matches_any(field_name, LOW_GOOD_VR_PATTERNS):
            return {'probe_op': '<', 'probe_threshold': '15',
                    'probe_gate': 'decline > .10', 'probe_boost': 1.10,
                    'data_type_hint': 'numeric'}
        return {'probe_op': '>', 'probe_threshold': '5',
                'probe_gate': 'decline > .10', 'probe_boost': 1.10,
                'data_type_hint': 'numeric'}

    if container == 'operation_ratios':
        if _matches_any(field_name, LOW_GOOD_OPS_PATTERNS):
            return {'probe_op': '<', 'probe_threshold': '2',
                    'probe_gate': 'decline > .15', 'probe_boost': 1.08,
                    'data_type_hint': 'numeric'}
        return {'probe_op': '>', 'probe_threshold': '0.10',
                'probe_gate': 'decline > .12', 'probe_boost': 1.10,
                'data_type_hint': 'numeric'}

    if container == 'earning_ratios':
        return {'probe_op': '>', 'probe_threshold': '0.10',
                'probe_gate': 'decline > .15', 'probe_boost': 1.15,
                'data_type_hint': 'signed_ratio'}

    if container == 'balance_sheet':
        if _matches_any(field_name, DEBT_LIKE_BS):
            return {'probe_op': '<', 'probe_threshold': '5e8',
                    'probe_gate': 'decline > .10', 'probe_boost': 1.06,
                    'data_type_hint': 'absolute_amount'}
        return {'probe_op': '>', 'probe_threshold': '1e9',
                'probe_gate': 'decline > .12', 'probe_boost': 1.08,
                'data_type_hint': 'absolute_amount'}

    if container == 'cash_flow_statement':
        return {'probe_op': '>', 'probe_threshold': '1e9',
                'probe_gate': 'decline > .10', 'probe_boost': 1.08,
                'data_type_hint': 'absolute_amount'}

    if container == 'income_statement':
        return {'probe_op': '>', 'probe_threshold': '1e9',
                'probe_gate': 'decline > .12', 'probe_boost': 1.10,
                'data_type_hint': 'absolute_amount'}

    if container == 'earning_reports':
        return {'probe_op': '>', 'probe_threshold': '1',
                'probe_gate': 'decline > .10', 'probe_boost': 1.06,
                'data_type_hint': 'numeric'}

    if container == 'asset_classification':
        if 'sector_code' in field_name or 'industry_code' in field_name:
            return {'probe_op': 'in', 'probe_threshold': DEFAULT_DEFENSIVE_SECTORS,
                    'probe_gate': 'decline > .10', 'probe_boost': 1.08,
                    'data_type_hint': 'categorical'}
        if 'grade' in field_name:
            return {'probe_op': 'in', 'probe_threshold': DEFAULT_A_TIER_GRADES,
                    'probe_gate': 'decline > .10', 'probe_boost': 1.06,
                    'data_type_hint': 'categorical'}
        # Other AC fields (style_box, stock_type) — leave NULL template (manual).
        return {'probe_op': None, 'probe_threshold': None,
                'probe_gate': None, 'probe_boost': None,
                'data_type_hint': 'categorical'}

    if container == 'security_reference':
        # Only some fields are useful; leave NULL by default.
        return {'probe_op': None, 'probe_threshold': None,
                'probe_gate': None, 'probe_boost': None,
                'data_type_hint': 'categorical'}

    raise KeyError(f"Unknown container: {container!r}")


def emit_probes_for_db(db_path, round_n, k_new=0,
                      k_coarse_fields=0, k_refine_fields=0,
                      k_sweep_fields=None, include_bind=False):
    """Emit probe specs for round_n.

    Returns list of (spec_name, body) tuples.

    k_new        : Phase 1 default-template specs (one per untested field).
    k_coarse_fields : v3 coarse pass — k fields × 72 specs (or 15 if categorical).
    k_refine_fields : v3 refine pass — k fields × ~26 specs.
    k_sweep_fields  : DEPRECATED alias for k_coarse_fields.
    """
    import warnings
    if k_sweep_fields is not None:
        warnings.warn(
            "k_sweep_fields is deprecated; use k_coarse_fields instead.",
            DeprecationWarning, stacklevel=2)
        k_coarse_fields = k_sweep_fields

    bake_hash = current_bake_hash(db_path)
    out = []

    # Phase 1: untested fields
    if k_new:
        new_fields = pick_fields(db_path, k=k_new, classification='untested',
                                 bake_hash=bake_hash)
        for f in new_fields:
            body = (BIND if include_bind else '') + render_probe(f)
            name = spec_name(f, round_n)
            out.append((name, body))

    # v3 coarse
    if k_coarse_fields:
        coarse_fields = pick_v3_coarse_candidates(db_path, k=k_coarse_fields,
                                                  bake_hash=bake_hash)
        for f in coarse_fields:
            specs = emit_v3_coarse(f, round_n, bake_hash, db_path)
            if include_bind:
                specs = [(n, BIND + b) for n, b in specs]
            out.extend(specs)

    # v3 refine
    if k_refine_fields:
        refine_fields = pick_v3_refine_candidates(db_path, k=k_refine_fields,
                                                  bake_hash=bake_hash)
        for f in refine_fields:
            specs = emit_v3_refine(f, round_n, bake_hash=bake_hash, db_path=db_path)
            if include_bind:
                specs = [(n, BIND + b) for n, b in specs]
            out.extend(specs)

    return out


def emit_mega_round(db_path, round_n, mechanisms=MECHANISMS, force_all=True):
    """Yield (spec_name, body, location) for every (field, mech) cell.

    All templated fields × all requested mechanisms. Skips cells where
    `render_cell` returns None (safety valve for ambiguous inverses)."""
    fields = pick_fields(db_path, k=10**9, force_all=force_all)
    out = []
    for field_row in fields:
        for mech in mechanisms:
            rendered = render_cell(field_row, mech, round_n)
            if rendered is not None:
                out.append(rendered)
    return out


def current_bake_hash(db_path):
    """Read settings.current_bake_hash. Raise if unset.

    Used by pick_fields and pick_sweep_candidates to scope queries
    to the current S001 base hash.
    """
    with storage.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("""SELECT value FROM settings
                       WHERE category = 'strategy'
                         AND key = 'current_bake_hash'""")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "settings.current_bake_hash not set; "
            "INSERT INTO settings (category, key, value) "
            "VALUES ('strategy', 'current_bake_hash', '<md5>') after baking.")
    return row[0]


SWEEP_MAGS = ['1.04', '1.06', '1.08', '1.10', '1.13']
SWEEP_GATES = ['.05', '.10', '.15']

COARSE_OPS = ['>', '<']
COARSE_MAGS = [1.04, 1.08, 1.13, 1.20]
COARSE_GATES = ['.05', '.10', '.15']
COARSE_THRESHOLD_PERCENTILES = ('p25', 'p50', 'p75')


def coarse_grid(field_row, bake_hash, db_path):
    """Build the v3 coarse Cartesian grid for one field.

    Returns: list of (op, mag, gate, threshold_str) tuples, or None if no
    field_universe_stats row exists for this (field_id, bake_hash).

    For numeric fields: 2 ops × 4 mags × 3 gates × 3 thresholds (p25/p50/p75) = 72 cells.
    For categorical fields (op in {'eq', 'in'}): falls back to v2-style
    SWEEP_MAGS × SWEEP_GATES = 15 cells, op held fixed (no inversion).
    """
    op = field_row['probe_op']

    if op in ('eq', 'in'):
        thr = field_row['probe_threshold']
        cells = []
        for mag in SWEEP_MAGS:
            for gate in SWEEP_GATES:
                cells.append((op, float(mag), gate, thr))
        return cells

    with storage.connect(db_path) as con:
        con.row_factory = storage.Row
        row = con.execute(
            "SELECT p25, p50, p75 FROM field_universe_stats "
            "WHERE field_id = ? AND bake_hash = ?",
            (field_row['id'], bake_hash)).fetchone()
    if row is None:
        return None

    hint = field_row.get('data_type_hint') or 'numeric'
    thresholds = [_format_threshold(row[col], hint) for col in ('p25', 'p50', 'p75')]
    # Collision guard: each percentile must produce a distinct formatted string.
    # Tightly-clustered fields collapse to <3 unique strings, breaking the
    # threshold→percentile mapping in spec naming. Skip those bakes.
    if len(set(thresholds)) < 3:
        return None

    cells = []
    for op_val in COARSE_OPS:
        for mag in COARSE_MAGS:
            for gate in COARSE_GATES:
                for thr in thresholds:
                    cells.append((op_val, mag, gate, thr))
    return cells


def emit_phase2_sweep(field_row, round_n):
    """Emit 15 (name, code) tuples for one field's Phase 2 sweep.

    Grid: 5 magnitudes × 3 decline gates. Threshold and op stay at the
    field's authored values.
    """
    out = []
    for mag in SWEEP_MAGS:
        for gate in SWEEP_GATES:
            row = dict(field_row)
            row['probe_boost'] = float(mag)
            row['probe_gate'] = f'decline > {gate}'
            body = render_probe(row)
            mag_short = mag.replace('.', '')
            gate_short = gate.replace('.', '').lstrip('-') or '0'
            cs = CONTAINER_SHORT[field_row['container']]
            name = (f"S001_R{round_n}_sw_{cs}_{field_row['field_name']}"
                    f"_m{mag_short}_g{gate_short}")[:100]
            out.append((name, body))
    return out


def pick_sweep_candidates(db_path, k, bake_hash, min_abs_delta=0.0001):
    """Pick up to k fields with |Phase 1 delta| >= min_abs_delta AND sweep_phase = 0.

    Sorted by max(|delta|) DESC so highest-impact fields sweep first.
    """
    sql = """
    SELECT f.*, MAX(ABS(p.delta)) AS max_abs_delta
    FROM fundamental_fields f
    JOIN probe_results p ON p.field_id = f.id
    WHERE p.bake_hash = ?
      AND p.is_sweep_variant = 0
      AND ABS(p.delta) >= ?
      AND f.sweep_phase = 0
      AND f.probe_threshold IS NOT NULL
    GROUP BY ALL
    ORDER BY max_abs_delta DESC
    LIMIT ?
    """
    with storage.connect(db_path) as con:
        con.row_factory = storage.Row
        cur = con.cursor()
        cur.execute(sql, (bake_hash, min_abs_delta, k))
        return [dict(r) for r in cur.fetchall()]


def update_sweep_winner(con, field_id, bake_hash):
    """After Phase 2 sweep completes for a field, find the variant with
    max delta and write it to fundamental_fields.sweep_winner_* columns.
    Set sweep_phase = 2.

    Caller passes an open storage connection so the update is part of
    the same transaction as the result inserts.
    """
    cur = con.cursor()
    cur.execute("""
        SELECT applied_op, applied_threshold, applied_gate, applied_boost, delta
        FROM probe_results
        WHERE field_id = ? AND bake_hash = ? AND is_sweep_variant = 1
        ORDER BY delta DESC LIMIT 1
    """, (field_id, bake_hash))
    row = cur.fetchone()
    if row is None:
        return  # no sweep variants yet; not ready
    op, thr, gate, boost, delta = row
    cur.execute("""
        UPDATE fundamental_fields
        SET sweep_winner_op = ?, sweep_winner_threshold = ?,
            sweep_winner_gate = ?, sweep_winner_boost = ?,
            sweep_winner_delta = ?, sweep_phase = 2
        WHERE id = ?
    """, (op, thr, gate, boost, delta, field_id))


V3_COARSE_PREFIX = 'v3c'
V3_REFINE_PREFIX = 'v3r'

OP_TO_SHORT_V3 = {'>': 'gt', '<': 'lt', 'eq': 'eq', 'in': 'in'}

# Indexes used in spec names so the `_t{NN}` token decodes to a percentile slot
COARSE_THRESHOLD_INDEX = {'p25': '25', 'p50': '50', 'p75': '75'}


def _v3_spec_name(prefix, round_n, container, field_name, op, mag, gate, thr_index):
    """Build a v3 spec name. Truncates to 100 chars; UNIQUE constraint is the safety net."""
    cs = CONTAINER_SHORT[container]
    op_s = OP_TO_SHORT_V3[op]
    mag_int = int(round(mag * 100))
    # Pad gate to 2 chars for stable parsing — strip leading dot, keep digits.
    # zfill(2) ensures 1-digit gates emit as e.g. 'g05', matching the score
    # parser's zfill(2) fallback. Currently inert because COARSE_GATES has only
    # 2-digit values, but future-proof for consistency.
    gate_padded = gate.lstrip('.').zfill(2)
    name = (f"S001_R{round_n}_{prefix}_{cs}_{field_name}"
            f"_o{op_s}_m{mag_int:03d}_g{gate_padded}_t{thr_index}")
    return name[:100]


def emit_v3_coarse(field_row, round_n, bake_hash, db_path):
    """Render the v3 coarse grid for a field as [(spec_name, body), ...].

    Returns [] if `coarse_grid` returns None (no universe stats).
    Each body is the per-probe try/except block (BIND injected once per spec
    by the caller in `gen_s001_R{N}.py`)."""
    cells = coarse_grid(field_row, bake_hash, db_path)
    if cells is None:
        return []

    # Map each threshold string back to its percentile slot for stable naming
    if field_row['probe_op'] in ('eq', 'in'):
        thr_to_pct = {field_row['probe_threshold']: '25'}  # categorical fallback uses one slot
    else:
        with storage.connect(db_path) as con:
            con.row_factory = storage.Row
            stats = con.execute(
                "SELECT p25, p50, p75 FROM field_universe_stats "
                "WHERE field_id = ? AND bake_hash = ?",
                (field_row['id'], bake_hash)).fetchone()
        hint = field_row.get('data_type_hint') or 'numeric'
        thr_to_pct = {
            _format_threshold(stats[col], hint): COARSE_THRESHOLD_INDEX[col]
            for col in ('p25', 'p50', 'p75')
        }

    specs = []
    for (op, mag, gate, thr) in cells:
        thr_idx = thr_to_pct[thr]
        name = _v3_spec_name(V3_COARSE_PREFIX, round_n, field_row['container'],
                             field_row['field_name'], op, mag, gate, thr_idx)
        # Build a row dict suitable for render_probe with this cell's overrides
        cell_row = dict(field_row)
        cell_row['probe_op'] = op
        cell_row['probe_threshold'] = thr
        cell_row['probe_gate'] = f'decline > {gate}'
        cell_row['probe_boost'] = mag
        body = render_probe(cell_row)
        specs.append((name, body))
    return specs


COARSE_TRIGGER_DELTA = 0.0001


def pick_v3_coarse_candidates(db_path, k, bake_hash):
    """Pick up to k fields ready for v3 coarse sweep.

    Eligibility:
      - sweep_phase = 1 (Phase 1 default-template probe complete)
      - max(|delta|) >= COARSE_TRIGGER_DELTA across this field's probe_results
        for this bake_hash
      - field_universe_stats row exists for this (field_id, bake_hash)
      - probe_threshold IS NOT NULL

    Side effect: each picked field's sweep_phase bumped to 2.
    Returns list of field dicts (storage.Row → dict)."""
    if k <= 0:
        return []
    with storage.connect(db_path) as con:
        con.row_factory = storage.Row
        cur = con.cursor()
        cur.execute("""
            SELECT f.* FROM fundamental_fields f
            WHERE f.sweep_phase = 1
              AND f.probe_threshold IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM field_universe_stats s
                WHERE s.field_id = f.id AND s.bake_hash = ?)
              AND (
                SELECT MAX(ABS(p.delta)) FROM probe_results p
                WHERE p.field_id = f.id AND p.bake_hash = ?
              ) >= ?
            ORDER BY f.id ASC
            LIMIT ?
        """, (bake_hash, bake_hash, COARSE_TRIGGER_DELTA, k))
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            cur.execute("UPDATE fundamental_fields SET sweep_phase = 2 WHERE id = ?",
                        (r['id'],))
        con.commit()
    return rows


PRUNE_DOMINANCE_THRESHOLD = 0.001


def _sort_thresholds(thresholds):
    """Sort threshold strings numerically when possible, else lexicographically.

    Numeric thresholds in `refine_threshold_set` would otherwise sort as strings,
    yielding e.g. ['1.0e+09', '1.0e+08', '5.0e+08'] (lexical). Try float-keyed sort
    first, falling back to lexical for categorical / non-numeric values."""
    try:
        return sorted(thresholds, key=float)
    except (ValueError, TypeError):
        return sorted(thresholds)


def _neighbors(value, allowed_set, k=1):
    """Return up to 2k+1 values around `value` from `allowed_set`.

    If `value` is in `allowed_set`: returns value plus the k nearest values
    above and below within the set.
    If `value` is not in the set: returns the k nearest values above and below
    (no center element).
    Result is sorted ascending. Caller is responsible for passing a homogeneous
    `allowed_set` (all comparable to `value`).
    """
    sorted_set = sorted(allowed_set)
    if value in sorted_set:
        idx = sorted_set.index(value)
        lo = max(0, idx - k)
        hi = min(len(sorted_set), idx + k + 1)
    else:
        idx = next((i for i, v in enumerate(sorted_set) if v >= value), len(sorted_set))
        lo = max(0, idx - k)
        hi = min(len(sorted_set), idx + k)
    return sorted_set[lo:hi]


def dimension_prune(coarse_results):
    """Compute survivors per dimension from completed coarse_results.

    coarse_results: iterable of dicts with keys op, mag, gate, threshold, delta.

    Returns: {'op': set, 'mag': set, 'gate': set, 'threshold': set} of survivors.

    Rules:
      - For dimensions with ≥3 distinct values: drop values whose median delta is
        below the median of medians.
      - For dimensions with exactly 2 distinct values: drop the loser only if its
        median is ≥ PRUNE_DOMINANCE_THRESHOLD worse than the winner.
      - For dimensions with 1 distinct value: keep the singleton.
    """
    dims = ('op', 'mag', 'gate', 'threshold')
    survivors = {}
    for dim in dims:
        groups = {}
        for r in coarse_results:
            groups.setdefault(r[dim], []).append(r['delta'])
        if not groups:
            survivors[dim] = set()
            continue
        medians = {v: statistics.median(deltas) for v, deltas in groups.items()}
        if len(medians) == 1:
            survivors[dim] = set(medians)
        elif len(medians) == 2:
            (winner_v, winner_m), (loser_v, loser_m) = sorted(
                medians.items(), key=lambda kv: kv[1], reverse=True)
            if winner_m - loser_m >= PRUNE_DOMINANCE_THRESHOLD:
                survivors[dim] = {winner_v}
            else:
                survivors[dim] = {winner_v, loser_v}
        else:
            cutoff = statistics.median(list(medians.values()))
            survivors[dim] = {v for v, m in medians.items() if m >= cutoff}
    return survivors


def refine_grid(coarse_winner, refine_sets):
    """Build the refine cells around `coarse_winner` within `refine_sets`.

    coarse_winner: dict with keys op, mag, gate, threshold.
    refine_sets: dict {dim: set} from dimension_prune.

    Returns list of (op, mag, gate, threshold) tuples — the Cartesian product of
    ±1 neighbors of the coarse winner within refine_sets, excluding the winner
    itself."""
    op_choices = [coarse_winner['op']] if coarse_winner['op'] in refine_sets['op'] else []
    mag_choices = _neighbors(coarse_winner['mag'], refine_sets['mag'], k=1)
    gate_choices = _neighbors(coarse_winner['gate'], refine_sets['gate'], k=1)
    # For thresholds (strings), convert to float for neighbor finding, then convert back
    thr_set = refine_sets['threshold']
    try:
        thr_as_floats = {float(t) for t in thr_set}
        float_neighbors = _neighbors(float(coarse_winner['threshold']), thr_as_floats, k=1)
        # Map back to original string representation
        float_to_str = {float(t): t for t in thr_set}
        thr_choices = [float_to_str[f] for f in float_neighbors]
    except (ValueError, TypeError):
        # If thresholds aren't numeric, use string sort
        thr_choices = _neighbors(coarse_winner['threshold'], thr_set, k=1)

    winner = (coarse_winner['op'], coarse_winner['mag'],
              coarse_winner['gate'], coarse_winner['threshold'])
    cells = []
    for op in op_choices:
        for mag in mag_choices:
            for gate in gate_choices:
                for thr in thr_choices:
                    cell = (op, mag, gate, thr)
                    if cell == winner:
                        continue
                    cells.append(cell)
    return cells


def emit_v3_refine(field_row, round_n, bake_hash=None, db_path=None):
    """Render the v3 refine grid for a field as [(spec_name, body), ...].

    Reads coarse_winner_* and refine_*_set from field_row; returns [] if
    coarse_winner_op is NULL (refine not yet ready).

    bake_hash + db_path required for numeric fields to canonicalize threshold
    percentile labels (avoids the C1 relabeling bug where prune-dropped p25
    causes p50/p75 cells to be relabeled t25/t50). For categorical fields they
    can be None (a single-slot mapping is used)."""
    if field_row.get('coarse_winner_op') is None:
        return []
    coarse_winner = {
        'op': field_row['coarse_winner_op'],
        'mag': field_row['coarse_winner_mag'],
        'gate': field_row['coarse_winner_gate'],
        'threshold': field_row['coarse_winner_threshold'],
    }
    refine_sets = {
        'op': set(json.loads(field_row['refine_op_set'])),
        'mag': set(json.loads(field_row['refine_mag_set'])),
        'gate': set(json.loads(field_row['refine_gate_set'])),
        'threshold': set(json.loads(field_row['refine_threshold_set'])),
    }
    cells = refine_grid(coarse_winner, refine_sets)

    # CANONICAL threshold → percentile mapping. Always use p25/p50/p75 from
    # field_universe_stats so the slot label matches the original coarse pass,
    # regardless of which percentiles survived dimension_prune.
    if field_row['probe_op'] in ('eq', 'in') or db_path is None or bake_hash is None:
        # Categorical or no DB context — fall back to single-slot mapping
        thr_to_pct = {coarse_winner['threshold']: '50'}
    else:
        with storage.connect(db_path) as con:
            con.row_factory = storage.Row
            stats = con.execute(
                "SELECT p25, p50, p75 FROM field_universe_stats "
                "WHERE field_id = ? AND bake_hash = ?",
                (field_row['id'], bake_hash)).fetchone()
        if stats is None:
            thr_to_pct = {coarse_winner['threshold']: '50'}
        else:
            hint = field_row.get('data_type_hint') or 'numeric'
            thr_to_pct = {
                _format_threshold(stats[col], hint): COARSE_THRESHOLD_INDEX[col]
                for col in ('p25', 'p50', 'p75')
            }

    specs = []
    for (op, mag, gate, thr) in cells:
        thr_idx = thr_to_pct.get(thr, '50')
        name = _v3_spec_name(V3_REFINE_PREFIX, round_n, field_row['container'],
                             field_row['field_name'], op, mag, gate, thr_idx)
        cell_row = dict(field_row)
        cell_row['probe_op'] = op
        cell_row['probe_threshold'] = thr
        cell_row['probe_gate'] = f'decline > {gate}'
        cell_row['probe_boost'] = mag
        body = render_probe(cell_row)
        specs.append((name, body))
    return specs


EXPECTED_COARSE_CELLS_NUMERIC = 72
EXPECTED_COARSE_CELLS_CATEGORICAL = 15  # SWEEP_MAGS × SWEEP_GATES


def _expected_coarse_count(field_row):
    if field_row['probe_op'] in ('eq', 'in'):
        return EXPECTED_COARSE_CELLS_CATEGORICAL
    return EXPECTED_COARSE_CELLS_NUMERIC


def pick_v3_refine_candidates(db_path, k, bake_hash):
    """Pick fields with all coarse cells scored, run prune+winner detection,
    persist refine_*_set and coarse_winner_*, bump phase to 3.

    Returns list of field dicts."""
    if k <= 0:
        return []
    with storage.connect(db_path) as con:
        con.row_factory = storage.Row
        cur = con.cursor()
        # I4: filter NULL probe_threshold (render_probe would crash on it).
        # I5: defensively exclude any future v2 fields that might land at phase=2.
        cur.execute(
            "SELECT * FROM fundamental_fields "
            "WHERE sweep_phase = 2 AND probe_threshold IS NOT NULL "
            "AND (sweep_version IS NULL OR sweep_version != 2) "
            "ORDER BY id ASC")
        candidates = [dict(r) for r in cur.fetchall()]

        ready = []
        for f in candidates:
            cur.execute(
                "SELECT COUNT(*) FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? AND sweep_stage = 'coarse'",
                (f['id'], bake_hash))
            count = cur.fetchone()[0]
            if count >= _expected_coarse_count(f):
                ready.append(f)
            if len(ready) >= k:
                break

        picked = []
        for f in ready[:k]:
            cur.execute(
                """SELECT applied_op, applied_threshold, applied_gate, applied_boost, delta
                   FROM probe_results
                   WHERE field_id = ? AND bake_hash = ? AND sweep_stage = 'coarse'""",
                (f['id'], bake_hash))
            results = []
            for r in cur.fetchall():
                gate = r['applied_gate'].split('decline > ')[-1] if r['applied_gate'] else ''
                results.append({
                    'op': r['applied_op'],
                    'mag': r['applied_boost'],
                    'gate': gate,
                    'threshold': r['applied_threshold'],
                    'delta': r['delta'],
                })

            survivors = dimension_prune(results)
            best = max(results, key=lambda r: r['delta'])

            cur.execute("""UPDATE fundamental_fields SET
                sweep_phase = 3,
                coarse_winner_op = ?, coarse_winner_mag = ?, coarse_winner_gate = ?,
                coarse_winner_threshold = ?, coarse_winner_delta = ?,
                refine_op_set = ?, refine_mag_set = ?,
                refine_gate_set = ?, refine_threshold_set = ?
                WHERE id = ?""",
                (best['op'], best['mag'], best['gate'], best['threshold'], best['delta'],
                 json.dumps(sorted(survivors['op'])),
                 json.dumps(sorted(survivors['mag'])),
                 json.dumps(sorted(survivors['gate'])),
                 json.dumps(_sort_thresholds(survivors['threshold'])),
                 f['id']))

            cur.execute("SELECT * FROM fundamental_fields WHERE id = ?", (f['id'],))
            picked.append(dict(cur.fetchone()))
        con.commit()
    return picked


def update_v3_winner(con, field_id, bake_hash):
    """After all v3 refine variants have scored for `field_id`, find the best
    overall (coarse winner + refine cells), write to sweep_winner_* columns,
    set sweep_phase=4 and sweep_version=3.

    Caller is responsible for con.commit()."""
    cur = con.cursor()
    cur.execute(
        """SELECT applied_op, applied_threshold, applied_gate, applied_boost, delta
           FROM probe_results
           WHERE field_id = ? AND bake_hash = ?
             AND sweep_stage IN ('coarse', 'refine')""",
        (field_id, bake_hash))
    rows = cur.fetchall()
    if not rows:
        return
    best = max(rows, key=lambda r: r[4])  # delta is index 4
    op, thr, gate, boost, delta = best
    cur.execute("""UPDATE fundamental_fields SET
        sweep_winner_op = ?, sweep_winner_threshold = ?,
        sweep_winner_gate = ?, sweep_winner_boost = ?, sweep_winner_delta = ?,
        sweep_phase = 4, sweep_version = 3
        WHERE id = ?""",
        (op, thr, gate, boost, delta, field_id))
