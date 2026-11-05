from AlgorithmImports import *
import math
f_=float
_RD=Resolution.DAILY
from datetime import timedelta

# =============================================================================
# S001 — QQQ mean-reversion strategy. CONSOLIDATED ACTIVE BASE (post-BAKE-261).
# ~190 active bakes. NOOP ≈ 2.5565. Date: 2026-05-05.
#
# Big-bake stack (BAKE-247..261, +0.0820 cumulative on top of pre-BAKE-247 base):
#   BAKE-247 R1169 +0.01941  SKIP         vs>60 × q_flat × d6_12 (HUGE)
#   BAKE-249 R1175 +0.02325  score×1.20   vs ∈ [15,30] × q_flat × d6_12 (HUGE)
#   BAKE-250 R1178 +0.02886  score×0.5    vs ∈ [50,60] × q_flat × d6_12 (HUGE soft-skip)
#   BAKE-251 R1183 +0.00917  score×1.20   vs ∈ [25,30] × q_flat × d6_12 (sub-band stack)
#   BAKE-252 R1191 +0.00598  score×0.85   vs ∈ [50,60] × q_flat × d4_8 (BAKE-250 shallow sister)
#   BAKE-253 R1190 +0.00278  score×1.20   vs ∈ [25,30] × q_flat × d6_12 (saturated stack)
#   BAKE-254 R1194 +0.00670  score×0.95   vs ∈ [15,30] × q_flat × d4_8 (BAKE-249 shallow inv)
#   BAKE-255 R1196 +0.00412  score×0.85   sector 206 (Healthcare) × q_flat × d6_12
#   BAKE-256 R1194 +0.00351  score×0.95   sector 102 (Consumer Cyclical) × q_flat × d6_12
#   BAKE-257 R1198 +0.00474  score×1.05   sector 308 (Comm Svc) × q_flat × d6_12
#   BAKE-258 R1200 +0.00753  score×1.05   sector 308 × q_flat × d2_4 (shallower)
#   BAKE-259 R1200 +0.00619  score×1.25   sector 311 (Tech) × q_neg × d6_12
#   BAKE-260 R1200 +0.00186  score×1.50   sector 309 (Energy) × q_flat × d4_8
#   BAKE-261 R1199 +0.00113  score×0.95   sector 308 × q_flat × d4_8 (non-monotonic)
#
# Cohort × regime patterns:
#   vs<15 (deep-value):    score boost + tighter exits → strongest mean-reverters
#   vs ∈ [15,30]:          q_flat d6_12 BOOST, q_flat d4_8 demote (decline-asymmetric)
#   vs ∈ [30,50] (mid):    demote entry + wider exits → slow recovery names
#   vs ∈ [50,60]:          SOFT-SKIP across d4_8 + d6_12 (near-skip cohort)
#   vs>60 (high-quality):  HARD-SKIP in q_flat × d6_12 → don't mean-revert
# Sectors:
#   206 (Healthcare):      DEMOTE 0.85
#   102 (Consumer Cyc):    DEMOTE 0.95
#   308 (Comm Services):   BOOST 1.05 (d2_4 + d6_12), DEMOTE 0.95 (d4_8) — non-monotonic
#   309 (Energy):          BOOST 1.50 (d4_8 only)
#   311 (Tech):            BOOST 1.25 (q_neg × d6_12)
#
# Levers in use: score×, score+, conv×, wt_tilt×, stop×, petgt×, skip (continue)
# Inject points: ENTRY INJECT POINT, EXIT INJECT POINT, ENTRY WT_TILT INJECT POINT,
#                ENTRY ALT_SCORE INJECT POINT
# =============================================================================

# === Hard structural constants ===
STARTING_CASH = 70000   # User-directive 2026-04-27: fixed at 70k, no further cash sweeps
GROSS_HIGH    = 1.0     # max total gross exposure
GROSS_LOW     = .62     # BAKE-138 R765: .55→.62 (post-MNV-bake) +0.01871; sweet-spot .58-.62 all positive, .62 winner; BAKE-20 R217-R218: .60→.55 joint with grad .022, +0.0492 verified 5/5
GRAD_RANGE    = .0130   # BAKE-157 R788: .0142→.0130 +0.00149 (broke 5-round zero-bake; GR_130 best variant in re-test); BAKE-61 R591: .0145→.0142 (joint with Combo4 mag 1.85), +0.0023
MA_PERIOD     = 170     # MA period for QQQ/bond ratio (BAKE-6 R175: 120→170, +0.076 on TIP base)
BOND_SYMBOL   = "TIP"   # BAKE-5 R174: HYG→TIP, +0.151 (largest single bond-symbol gain)
WT_CAP        = .07     # per-stock weight cap (HARD: do not exceed)
WT_PER_CONV   = .080    # weight scaling (BAKED R166: .025→.080, +0.17)
MIN_WT        = .02     # min weight to bother holding
MIN_PRICE     = 32      # min stock price filter (BAKED R166: 24→32, +0.10)
MIN_VOLUME    = 810000  # BAKE-139 R766: 800k→810k +0.00307 marginal refinement; BAKE-137 R764: 900k→800k score-saturation breakthrough +0.02139; BAKE-35 R319-R320: 700k→900k on BAKE-34 base, +0.0057 verified 3/3 deterministic
MTF_WEEKDAYS  = {0,2,4} # MTF days (BAKED R166: {0,3,4}→{0,2,4} Mon/Wed/Fri, +0.32)
WARMUP_DAYS   = 280  # was 260; user-directed 2026-04-30



# Lambda-base helper #2 (qaccel pattern, range/comparison/regime flexible) — module-level for fast access
def _try_score_bake_qaccel(score, alias, attrs, gates, qaccel, qa_lo, qa_hi, decline, d_lo, d_hi, mag, regime=True):
 """gates is tuple of (op, thr) pairs. e.g. (('>', 0.30),) for v > .30; (('>', 0), ('<', 1.5)) for range."""
 try:
  if alias is None: return score
  obj = alias
  for p in attrs:
   obj = getattr(obj, p, None)
   if obj is None: return score
  v = float(obj)
  if qaccel is None: return score
  if not (qa_lo < qaccel < qa_hi): return score
  if d_lo is not None and not (decline > d_lo): return score
  if d_hi is not None and not (decline < d_hi): return score
  if not regime: return score
  for op, thr in gates:
   if op == '>' and not (v > thr): return score
   if op == '<' and not (v < thr): return score
   if op == '==' and not (v == thr): return score
  score *= mag
 except: pass
 return score

# Lambda-base helper #3 (2-field bake) — module-level
def _try_score_bake_v2f(score, alias_a, attrs_a, op_a, thr_a, alias_b, attrs_b, op_b, thr_b, decline, d_lo, d_hi, mag, regime=True):
 try:
  if alias_a is None or alias_b is None: return score
  obj = alias_a
  for p in attrs_a:
   obj = getattr(obj, p, None)
   if obj is None: return score
  va = float(obj)
  obj = alias_b
  for p in attrs_b:
   obj = getattr(obj, p, None)
   if obj is None: return score
  vb = float(obj)
  if d_lo is not None and not (decline > d_lo): return score
  if d_hi is not None and not (decline < d_hi): return score
  if not regime: return score
  ca = (op_a == '>' and va > thr_a) or (op_a == '<' and va < thr_a)
  cb = (op_b == '>' and vb > thr_b) or (op_b == '<' and vb < thr_b)
  if ca and cb:
   score *= mag
 except: pass
 return score
# Module-level helper (was class @staticmethod)
def _try_score_bake_v1(score, alias, attrs, op, thr, decline, d_lo, d_hi, mag, regime=True):
 try:
  if alias is None: return score
  if not regime: return score
  obj = alias
  for p in attrs:
   obj = getattr(obj, p, None)
   if obj is None: return score
  v = float(obj)
  if (d_lo is None or decline > d_lo) and (d_hi is None or decline < d_hi):
   if (op == '>' and v > thr) or (op == '<' and v < thr) or (op == '==' and v == thr):
    score *= mag
 except: pass
 return score


# Lambda-base helper #4 (skip pattern) — module-level
def _try_skip_bake(alias, attrs, gates, decline, d_lo, d_hi, regime=True):
 try:
  if alias is None: return False
  obj = alias
  for p in attrs:
   obj = getattr(obj, p, None)
   if obj is None: return False
  v = float(obj)
  if d_lo is not None and not (decline > d_lo): return False
  if d_hi is not None and not (decline < d_hi): return False
  if not regime: return False
  for op, thr in gates:
   if op == '>' and not (v > thr): return False
   if op == '<' and not (v < thr): return False
   if op == '==' and not (v == thr): return False
  return True
 except: return False

# Lambda-base helper #5 (exit lever) — generic for stop/petgt/conv multipliers.
# When `gates` given (tuple of (op, thr) pairs), overrides op/thr with multi-gate check.
def _try_lever_bake(lever_val, alias, attrs, op, thr, mag, gates=None, regime=True):
 try:
  if alias is None: return lever_val
  obj = alias
  for p in attrs:
   obj = getattr(obj, p, None)
   if obj is None: return lever_val
  v = float(obj)
  if not regime: return lever_val
  if gates:
   for op2, thr2 in gates:
    if op2 == '>' and not (v > thr2): return lever_val
    if op2 == '<' and not (v < thr2): return lever_val
  elif not ((op == '>' and v > thr) or (op == '<' and v < thr)):
   return lever_val
  lever_val *= mag
 except: pass
 return lever_val

# Lambda-base helper #6 (qaccel 2-field: sector_code == X × peg-style range) — module-level
def _try_score_qaccel_2f(score, alias_a, attrs_a, sector_eq, alias_b, attrs_b, vlo, vhi, qaccel, qa_lo, qa_hi, decline, d_lo, d_hi, mag, regime=True):
 try:
  if alias_a is None or alias_b is None: return score
  obj = alias_a
  for p in attrs_a:
   obj = getattr(obj, p, None)
   if obj is None: return score
  va = float(obj)
  if va != sector_eq: return score
  obj = alias_b
  for p in attrs_b:
   obj = getattr(obj, p, None)
   if obj is None: return score
  vb = float(obj)
  if not (vlo < vb < vhi): return score
  if qaccel is None or not (qa_lo < qaccel < qa_hi): return score
  if d_lo is not None and not (decline > d_lo): return score
  if d_hi is not None and not (decline < d_hi): return score
  if not regime: return score
  score *= mag
 except: pass
 return score

# Lambda-base helper #7 (2-field skip) — for compound-gate continue patterns
def _try_skip_2f(alias_a, attrs_a, op_a, thr_a, alias_b, attrs_b, op_b, thr_b, decline, d_lo, d_hi=None):
 try:
  if alias_a is None or alias_b is None: return False
  obj = alias_a
  for p in attrs_a:
   obj = getattr(obj, p, None)
   if obj is None: return False
  va = float(obj)
  obj = alias_b
  for p in attrs_b:
   obj = getattr(obj, p, None)
   if obj is None: return False
  vb = float(obj)
  if d_lo is not None and not (decline > d_lo): return False
  if d_hi is not None and not (decline < d_hi): return False
  if not ((op_a == '>' and va > thr_a) or (op_a == '<' and va < thr_a)): return False
  if not ((op_b == '>' and vb > thr_b) or (op_b == '<' and vb < thr_b)): return False
  return True
 except: return False
class MeanReversionAlgorithm(QCAlgorithm):
 # PERFOPT 2026-05-05 (DSL2 pass): single-line helper for simple score bakes.
 # Replaces 5-line try/except blocks with one-liner. Preserves order (additive-safe).
 def initialize(self):
  self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
  self.set_start_date(2009, 8, 1)
  self.set_end_date(2026, 6, 1)
  self.set_cash(STARTING_CASH)
  self.set_warm_up(timedelta(days=WARMUP_DAYS), _RD)
  self.universe_settings.resolution = _RD
  self.add_equity("QQQ", _RD)
  self.add_equity(BOND_SYMBOL, _RD)
  self.add_universe_selection(ETFConstituentsUniverseSelectionModel("QQQ"))
  self.set_benchmark("QQQ")
  self._initialized = False
  self._hedge_syms = set()
  self.pending_entries = []
  self.pending_exits = []
  self.schedule.on(
   self.date_rules.every_day("QQQ"),
   self.time_rules.before_market_open("QQQ", 300),
   self.execute_pending_orders
  )
  self.tune = {
   # Exit thresholds (stop-loss + profit-take)
   'stop_default':    .40,    # BAKE-140 R767: .42→.40 +0.00119 (cluster .38/.40/.41 all tied at +0.0011 — flat region winner); BAKE-38 R327-R328: .40→.42 (joint with stop_lowmargin .09), +0.0088 verified 3/3
   'stop_lowmargin':  .09,    # BAKE-38 R327-R328: .08→.09 (joint with stop_default .42), +0.0088 verified 3/3
   'petgt_hi':        .12,
   'petgt_mid':       .11,
   'petgt_lo':        .0275,  # BAKE-40 R390-R392: .045→.0275, +0.0089 verified 3/3 deterministic
   'nm_low_thresh':   .04,
   'qr_hi_thresh':    2.2,    # BAKE-58 R583 part 1: 2.5→2.2 (joint with Combo4 boost)
   'nm_mid_thresh':   .05,
   # Gross-target adjustments
   'momentum_haircut_thresh': -.045,    # BAKE-31 R310-R311: -.042→-.045 (tighter trigger; min4_045 component, +0.0350 verified)
   'momentum_haircut': 1.344,           # BAKE-39 R383-R384: 1.34→1.344 (joint with petlo .045), +0.0041 verified 3/3
  }

 def on_data(self, data):
  if not self._initialized:
   self._qqq_sym = self.securities["QQQ"].symbol
   self._bond_sym = self.securities[BOND_SYMBOL].symbol
   self._hedge_syms = {self._bond_sym}
   self._initialized = True
  equities = [s for s in data.bars.keys() if s.security_type == SecurityType.EQUITY and s not in self._hedge_syms]
  self._compute_regime()
  self._scan_exits(data, equities)
  if self.time.weekday() == 0:
   self._scan_entries(data, equities)

 def _compute_regime(self):
  """Compute QQQ/bond regime once per tick. Sets self._qa_scan / self._ha_scan
  aliases for existing baked probes (BAKE-8/16/29-AB/53-58/62)."""
  try: qa = list(self.history[TradeBar](self._qqq_sym, 60, _RD))
  except (AttributeError, KeyError, ValueError): qa = []
  try: ha = list(self.history[TradeBar](self._bond_sym, 30, _RD))
  except (AttributeError, KeyError, ValueError): ha = []
  def _r(bars, n):
   if len(bars) <= n or f_(bars[-n].close) <= 0: return None
   return (f_(bars[-1].close) - f_(bars[-n].close)) / f_(bars[-n].close)
  self._qa_scan = qa
  self._ha_scan = ha
  # PERFOPT 2026-05-05: cache common multi-day returns (was inline in 10 bakes)
  self._qd5 = _r(qa, 5)
  self._qd10 = _r(qa, 10)
  self._qd20 = _r(qa, 20)
  self._bd5 = _r(ha, 5)
  self._bd10 = _r(ha, 10)
  # PERFOPT 2026-05-04: cache _qaccel (3d-7d return diff) on self — used by 33 inline bakes BAKE-199..236.
  # Preserves inline semantics: requires qa, len(qa)>=7, qa[-3].close>0, qa[-7].close>0.
  try:
   if qa and len(qa) >= 7 and f_(qa[-3].close) > 0 and f_(qa[-7].close) > 0:
    _qr3c = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close)
    _qr7c = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close)
    self._qaccel = _qr3c - _qr7c
   else:
    self._qaccel = None
  except (TypeError, ZeroDivisionError, AttributeError, IndexError): self._qaccel = None
  # PERFOPT: pre-compute regime flags once per tick (replaces N×per-symbol expressions in bakes 103-120)
  def _qd(n):
   try: return f_(qa[-1].close) < f_(qa[-n].close) if (qa and len(qa)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  def _hd(n):
   try: return f_(ha[-1].close) < f_(ha[-n].close) if (ha and len(ha)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  def _hu(n):
   try: return f_(ha[-1].close) > f_(ha[-n].close) if (ha and len(ha)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  # consecutive-down checks (strict monotone)
  self._reg_qqq_dn3 = bool(qa and len(qa)>=3 and f_(qa[-1].close)<f_(qa[-2].close)<f_(qa[-3].close))
  self._reg_qqq_up3 = bool(qa and len(qa)>=3 and f_(qa[-1].close)>f_(qa[-2].close)>f_(qa[-3].close))
  self._reg_hyg_dn3 = bool(ha and len(ha)>=3 and f_(ha[-1].close)<f_(ha[-2].close)<f_(ha[-3].close))
  self._reg_hyg_up3 = bool(ha and len(ha)>=3 and f_(ha[-1].close)>f_(ha[-2].close)>f_(ha[-3].close))
  # N-day comparisons (single-point) — only flags actually consumed downstream
  self._reg_qqq_dn5 = _qd(5); self._reg_qqq_dn7 = _qd(7)
  self._reg_hyg_dn5 = _hd(5); self._reg_hyg_dn14 = _hd(14)
  self._reg_hyg_up5 = _hu(5)
  # compound regime (gen's double_panic uses LOOSE qqq check [-1 vs -3 only], not strict monotone)
  self._reg_double_panic = bool(qa and len(qa)>=3 and f_(qa[-1].close)<f_(qa[-3].close)) and self._reg_hyg_dn5

 def _dynamic_gross(self) -> float:
  """Gross target derived from QQQ/HYG ratio vs its MA. Bullish → GROSS_HIGH; bearish → GROSS_LOW."""
  try:
   n = MA_PERIOD + 1
   qqq_bars = list(self.history[TradeBar](self._qqq_sym, n, _RD))
   bond_bars = list(self.history[TradeBar](self._bond_sym, n, _RD))
   if len(qqq_bars) < MA_PERIOD or len(bond_bars) < MA_PERIOD: return GROSS_HIGH
   ratios = [f_(qqq_bars[i].close)/max(.01, f_(bond_bars[i].close)) for i in range(-MA_PERIOD, 0)]
   ma_ratio = sum(ratios)/len(ratios)
   cur_ratio = f_(qqq_bars[-1].close)/max(.01, f_(bond_bars[-1].close))
   pct_above = (cur_ratio - ma_ratio)/ma_ratio
   base = max(GROSS_LOW, min(GROSS_HIGH, GROSS_LOW + (pct_above/GRAD_RANGE)*(GROSS_HIGH - GROSS_LOW)))
   if len(ratios) >= 10:
    ratio_mom = (ratios[-1] - ratios[-10])/max(.01, ratios[-10])
    if ratio_mom < self.tune['momentum_haircut_thresh']:
     base = max(GROSS_LOW, base * self.tune['momentum_haircut'])
   return base
  except: return GROSS_HIGH

 def _scan_exits(self, data, equities):
  for sym in equities:
   pos = self.portfolio[sym]
   if not pos.invested: continue
   pnl = f_(pos.unrealized_profit_percent)
   stop = self.tune['stop_default']  # BAKED R172: removed bear-stop logic (stop_bear=.99 was no-op +0.051)
   petgt = self.tune['petgt_mid']
   try:
    f = self.securities[sym].fundamentals
    ops = getattr(f, 'operation_ratios', None) if f else None
    if f and ops:
     nm = self._fv(ops, 'net_margin', 'value')
     qr = self._fv(ops, 'quick_ratio', 'value')
     if nm is not None and nm < self.tune['nm_low_thresh']: stop = self.tune['stop_lowmargin']
     if qr is not None and qr > self.tune['qr_hi_thresh']: petgt = self.tune['petgt_hi']
     elif nm is not None and nm > self.tune['nm_mid_thresh']: petgt = self.tune['petgt_mid']
     else: petgt = self.tune['petgt_lo']
   except: pass
   # PERFOPT 2026-05-04 (DSL pass): hoist standard fundamentals aliases (exit-loop counterpart).
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ers_z = getattr(_fz, 'earning_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _er_z  = getattr(_fz, 'earning_reports', None) if _fz else None
    _sr_z  = getattr(_fz, 'security_reference', None) if _fz else None
    _fs_z  = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z  = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _cfs_z = getattr(_fs_z, 'cash_flow_statement', None) if _fs_z else None
   except: _fz=_ops_z=_vr_z=_ers_z=_ac_z=_er_z=_sr_z=_fs_z=_bs_z=_inc_z=_cfs_z=None
   # BAKE-65 R608 +0.0012
   stop = _try_lever_bake(stop, _bs_z, ('work_in_process', 'twelve_months'), '<', 1e9, 0.9)
   # BAKE-66 R611 +0.0099
   stop = _try_lever_bake(stop, _inc_z, ('write_off', 'twelve_months'), '<', 1e9, .82)
   # BAKE-67 R616 +0.0050
   petgt = _try_lever_bake(petgt, _vr_z, ('ev_to_total_assets_3_year_growth',), '<', 15, 1.05)
   # BAKE-68 R617 +0.0035
   stop = _try_lever_bake(stop, _bs_z, ('cash', 'twelve_months'), '<', 1e9, 0.9)
   # BAKE-69 R621 +0.0039
   try:
    _va = f_(_inc_z.write_off.twelve_months)
    _vb = f_(_ops_z.net_income_growth.one_year)
    if _va is not None and _vb is not None and _va > 1e7 and _vb < 0.0: stop *= 0.78
   except: pass
   # BAKE-70 R625 +0.0017
   try:
    _va = f_(_ops_z.fcf_growth.one_year)
    _vb = f_(_ops_z.fcf_sales_ratio.one_year)
    if _va is not None and _vb is not None and _va > 0.20 and _vb < 0.05: stop *= 0.85
   except: pass
   # BAKE-75 R633 +0.0014
   stop = _try_lever_bake(stop, _ops_z, ('fcf_growth', 'one_year'), '<', 0.0, 0.85)
   # BAKE-76 R635 +0.0041
   petgt = _try_lever_bake(petgt, _ops_z, ('roic', 'one_year'), '>', 0.15, 1.10)
   # BAKE-87 R649 +0.0040
   petgt = _try_lever_bake(petgt, _ops_z, ('fcf_sales_ratio', 'one_year'), '>', 0.20, 1.20)
   # BAKE-88 R651 +0.0049
   petgt = _try_lever_bake(petgt, _ops_z, ('fcf_sales_ratio', 'one_year'), '>', 0.25, 1.25)
   # BAKE-91 R653 +0.0024
   petgt = _try_lever_bake(petgt, _ops_z, ('fcf_sales_ratio', 'one_year'), '>', 0.20, 1.30)
   # BAKE-239 R1150 +0.00743 — EXIT lever: tighten profit-take to 85% of base for
   # deep-value names (vs<15). Same cohort BAKE-238 boosts via score×1.20 — they
   # mean-revert quickly, so earlier profit-take captures the full move.
   petgt = _try_lever_bake(petgt, _ac_z, ('value_score',), '<', 15, 0.85)
   # BAKE-240 R1151 +0.00218 — EXIT lever: LOOSEN profit-take to 150% for mid-vs
   # cohort (vs ∈ [30, 50]). Mid-quality names take longer to mean-revert (less
   # immediate panic-buy after dip), so giving them more room captures more upside.
   # Inverse direction from BAKE-239 — different cohort, different dynamics.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 30 and _v < 50: petgt *= 1.50
   except: pass
   # BAKE-241 R1152 +0.00168 — EXIT lever: tighten STOP to 95% for vs<15 cohort.
   # Stacks with BAKE-238/239 (score boost + petgt tighten on same cohort).
   # Pattern: deep-value names hit stop cleanly when entry was wrong — earlier
   # stop limits damage. Sweet spot at s95; s90 and below hurt.
   stop = _try_lever_bake(stop, _ac_z, ('value_score',), '<', 15, 0.95)
   # BAKE-243 R1154 +0.00396 — EXIT stop×1.12 on mid-vs ∈ [30, 50] cohort. Loosens
   # stop to give mid-vs more room. Stacks with BAKE-240 (petgt×1.50) and BAKE-242
   # (score×0.85 entry) on same cohort. Sweet spot s107-s112; s114+ turns negative.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 30 and _v < 50: stop *= 1.12
   except: pass
   # BAKE-292 R1226 +0.00423 — EXIT stop×0.85 on vs<5 (extreme deep-value tighten).
   # Stacks with BAKE-241 (vs<15 stop×0.95): vs<5 effective = 0.95×0.85 = 0.8075.
   # Distress demote of vs<5 entry (BAKE-262/263/264) means wrong entries should
   # be cut faster — heavier stop tighten on this sub-cohort.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v < 5: stop *= 0.85
   except: pass
   # BAKE-293 R1226 +0.00144 — EXIT stop×1.05 on vs ∈ [10, 15] (boundary cohort loosen).
   # Tied cluster s105/s110/s125/s150; picked s105 for parsimony.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 10 and _v < 15: stop *= 1.05
   except: pass
   # BAKE-294 R1226 +0.00113 — EXIT stop×1.05 on vs ∈ [5, 10] (BAKE-265 cohort loosen).
   # Cohort that BAKE-265 boosts on entry deserves more room on exit too.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 5 and _v < 10: stop *= 1.05
   except: pass
   # BAKE-295 R1227 +0.00567 — EXIT stop×1.50 on vs ∈ [15, 25] (BAKE-249 cohort HEAVY loosen).
   # The BAKE-249 boost cohort (vs[15,30] q_flat d6_12 ×1.20) deserves the most room on exit.
   # m150 winner — peak may be even higher but unprobed.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 15 and _v < 25: stop *= 1.50
   except: pass
   # BAKE-296 R1228 +0.00278 — EXIT stop×1.05 on vs ∈ [25, 30] (BAKE-251/253 cohort loosen).
   # Mild loosen on the BAKE-251/253 sub-band cohort (vs[25,30] q_flat d6_12 stack ×1.728).
   # Pattern: BAKE-249/265 boost cohorts get loose stops; vs<5 distress cohort (BAKE-292) tight.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 25 and _v < 30: stop *= 1.05
   except: pass
   # PERFOPT: hoist exit-side close price once for BAKE-297/298 + future price-tier exit bakes.
   try: _p = f_(self.securities[sym].close)
   except: _p = None
   # BAKE-297 R1229 +0.00918 — EXIT stop×1.50 on close > $150 (HIGH-PRICE HEAVY LOOSEN).
   # Largest exit-side bake this session. High-price names (BAKE-267 boost cohort) deserve
   # much wider stops — they don't whipsaw to stop-out as easily as small-caps.
   if _p is not None and _p > 150: stop *= 1.50
   # BAKE-298 R1229 +0.00186 — EXIT petgt×1.10 on close < $50 (low-price PROFIT-TAKE loosen).
   # Low-price names get more profit-take room — more upside per percentage move.
   if _p is not None and _p < 50: petgt *= 1.10
   # --- EXIT INJECT POINT ---
   if pnl < -stop or pnl > petgt:
    self.pending_exits.append(sym); continue
   try:
    bars = list(self.history[TradeBar](sym, 2, _RD))
    if len(bars) >= 2 and bars[-1].close > bars[-2].high:
     self.pending_exits.append(sym)
   except: pass

 def _scan_entries(self, data, equities):
  self.pending_entries = []
  candidates = []
  gross_target = self._dynamic_gross()

  # PERFOPT: regime caches (_qa_scan / _ha_scan) populated by _compute_regime in on_data.

  for sym in equities:
   if self.portfolio[sym].invested and sym not in self.pending_exits: continue
   if sym not in data.bars: continue
   bar = data.bars[sym]
   _bc = f_(bar.close); _bv = f_(bar.volume)
   if _bc <= MIN_PRICE or _bv < MIN_VOLUME: continue

   # Multi-day-decline filter (3 consecutive lower closes on MTF days)
   # PERFOPT 2026-05-04: window widened 10→20 to be reused by BAKE-27's vol filter
   # (saves one per-symbol history call). _w10 retained for original 10-bar semantics.
   try:
    window = list(self.history[TradeBar](sym, 20, _RD))
    _w10 = window[-10:] if len(window) >= 10 else window
    mtf = [b for b in _w10 if b.time.weekday() in MTF_WEEKDAYS]
    if len(mtf) < 3: continue
    if not (mtf[-1].close < mtf[-2].close): continue  # BAKE-2 R171: 3-day→2-day decline filter, +0.25
   except (AttributeError, KeyError, IndexError, ValueError, TypeError): continue

   decline = f_((mtf[-3].close - mtf[-1].close)/mtf[-3].close) if f_(mtf[-3].close) > 0 else 0

   # Volume-climax filter: skip shallow declines on volume-spike bars (uses _w10 — preserved 10-bar scope)
   # PERFOPT: cache 10-bar volumes once for _av + max_dv + later BAKE-58 reuse (saves redundant f_() calls)
   _wvol10 = [f_(b.volume) for b in _w10]
   _av = sum(_wvol10)/max(len(_w10), 1)
   max_dv = max((_wvol10[i] for i in range(max(1, len(_w10)-5), len(_w10))  # BAKE-52 R566: 6→5 bar window, +0.0022
                 if _w10[i].close < _w10[i-1].close), default=0)
   vol_climax = _av > 0 and max_dv > 2.5 * _av  # BAKE-4 R173: 2.0→2.5, +0.041
   if vol_climax and decline < .05: continue  # BAKE-47 R560: .04→.05, +0.0032 (no-verify auto-bake; was BAKE-18 .02→.04)

   # PERFOPT 2026-05-05: cache multi-day returns _r3/_r5/_r7 once per symbol (was inline in 19 bakes).
   # _bc already computed at MIN_PRICE filter; reuse it. Cache mtf closes once per N (3 → 1 f_() each).
   _m3 = f_(mtf[-3].close) if len(mtf) >= 3 else 0
   _m5 = f_(mtf[-5].close) if len(mtf) >= 5 else 0
   _m7 = f_(mtf[-7].close) if len(mtf) >= 7 else 0
   _r3 = (_bc - _m3) / _m3 if _m3 > 0 else None
   _r5 = (_bc - _m5) / _m5 if _m5 > 0 else None
   _r7 = (_bc - _m7) / _m7 if _m7 > 0 else None
   # PERFOPT: hoist window closes once for BAKE-27 vol filter + BAKE-299/300/301/302 vol-tier bakes
   # (was: f_(window[i-1].close) called 2× per iter × 2 separate calcs). Saves ~38 f_() per symbol.
   _wcl = [f_(b.close) for b in window] if window and len(window) >= 20 else None

   # PERFOPT 2026-05-04 (DSL pass): hoist standard fundamentals aliases once per symbol.
   # Per-bake try/except blocks below have had their redundant alias lines stripped — they
   # rely on these names being in scope. On exception, all aliases set None.
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ers_z = getattr(_fz, 'earning_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _er_z  = getattr(_fz, 'earning_reports', None) if _fz else None
    _sr_z  = getattr(_fz, 'security_reference', None) if _fz else None
    _fs_z  = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z  = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _cfs_z = getattr(_fs_z, 'cash_flow_statement', None) if _fs_z else None
   except: _fz=_ops_z=_vr_z=_ers_z=_ac_z=_er_z=_sr_z=_fs_z=_bs_z=_inc_z=_cfs_z=None

   # === SCORE: selection lever (sort top-down) ===
   score = math.log2(math.log2(_bv))  # log2(log2(volume)): heavy compression, range ~[4.31, 4.90] for v ≥ MIN_VOLUME (900k); _bv cached at filter

   # === CONV: sizing lever (deeper decline → more conviction) ===
   if decline < .05:
    conv = max(1.0, 1.0 + (decline - .02) * (1.5/.10))
   else:
    conv = 1.0 + .375 + (decline - .05) * (3.5/.10)
   conv = min(5.0, conv)
   if vol_climax: conv *= .70

   # NEW LEVERS 2026-05-04 base. Defaults preserve NOOP vs 20260501 base.
   wt_tilt = 1.0      # weight multiplier (cohort sizing tilt) — capped by WT_TILT_CAP below
   alt_score = 0.0    # secondary score dimension (NOT used in selection unless probe sets alt_blend>0)
   alt_blend = 0.0    # blend weight for alt_score in final ranking

   # BAKE-71 R628 +0.0913
   score = _try_score_bake_v1(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, decline, 0.05, None, 1.3)
   # BAKE-72 R629 +0.0530
   score = _try_score_bake_v2f(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, _ops_z, ('fcf_growth', 'one_year'), '>', 0.1, decline, 0.07, None, 1.4, True)
   # BAKE-73 R630 +0.0580
   score = _try_score_bake_v2f(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, _ops_z, ('long_term_debt_equity_ratio', 'one_year'), '<', 0.3, decline, 0.05, None, 1.4, True)
   # BAKE-74 R631 +0.0533
   score = _try_score_bake_v2f(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, _ops_z, ('solvency_ratio', 'one_year'), '>', 0.5, decline, 0.05, None, 1.4, True)
   # BAKE-77 R636 +0.0063
   score = _try_score_bake_v1(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, decline, 0.05, None, 1.05)
   # BAKE-78 R639 +0.0019
   try:
    _va = f_(_inc_z.write_off.twelve_months)
    _vb = f_(_ops_z.cfo_growth.one_year)
    _vc = f_(_ops_z.gross_margin.one_year)
    if _va is not None and _vb is not None and _vc is not None and _va > 1e8 and _vb < 0.0 and _vc < 0.20 and (decline > .10): continue
   except: pass
   # BAKE-79 R640 +0.0041
   score = _try_score_bake_v1(score, _ops_z, ('gross_margin', 'one_year'), '>', 0.45, decline, 0.03, None, 1.07)
   # BAKE-80 R642 +0.0091
   if _try_skip_2f(_ops_z, ('tax_rate', 'one_year'), '>', 0.5, _ops_z, ('cfo_growth', 'one_year'), '<', -0.05, decline, 0.1, None): continue
   # BAKE-81 R643 +0.0113
   if _try_skip_2f(_ops_z, ('tax_rate', 'one_year'), '>', 0.4, _ops_z, ('cfo_growth', 'one_year'), '<', -0.1, decline, 0.07, None): continue
   # BAKE-82 R644 +0.0173
   if _try_skip_2f(_ops_z, ('tax_rate', 'one_year'), '>', 0.3, _ops_z, ('cfo_growth', 'one_year'), '<', 0.0, decline, 0.05, None): continue
   # BAKE-83 R645 +0.0187
   score = _try_score_bake_v2f(score, _ops_z, ('receivable_turnover', 'one_year'), '>', 10.0, _ops_z, ('tax_rate', 'one_year'), '<', 0.2, decline, 0.05, None, 1.2, True)
   # BAKE-84 R646 +0.0165
   score = _try_score_bake_v2f(score, _ops_z, ('receivable_turnover', 'one_year'), '>', 8.0, _ops_z, ('tax_rate', 'one_year'), '<', 0.15, decline, 0.07, None, 1.4, True)
   # BAKE-85 R647 +0.0077
   score = _try_score_bake_v2f(score, _ops_z, ('receivable_turnover', 'one_year'), '>', 6.0, _ops_z, ('tax_rate', 'one_year'), '<', 0.18, decline, 0.1, None, 1.3, True)
   # BAKE-86 R648 +0.0057
   score = _try_score_bake_v2f(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.35, _ops_z, ('tax_rate', 'one_year'), '<', 0.15, decline, 0.07, None, 1.3, True)
   # BAKE-93 R655 +0.0348
   score = _try_score_bake_v1(score, _vr_z, ('peg_ratio',), '<', 1.5, decline, 0.03, None, 1.1)
   # BAKE-95 R659 +0.0248
   score = _try_score_bake_v1(score, _vr_z, ('peg_ratio',), '<', 1.5, decline, 0.1, None, 1.2)
   # BAKE-113 R682 +0.0072
   score = _try_score_bake_v1(score, _vr_z, ('peg_ratio',), '<', 1.5, decline, 0.2, None, 1.5)
   # BAKE-115 R685 +0.0063
   score = _try_score_bake_v1(score, _vr_z, ('peg_ratio',), '<', 2.5, decline, 0.25, None, 1.5)
   # BAKE-116 R686 +0.0044
   score = _try_score_bake_v1(score, _ac_z, ('morningstar_sector_code',), '==', 309, decline, 0.03, None, 1.10, True)
   # BAKE-117 R688 +0.0068
   score = _try_score_bake_v1(score, _ac_z, ('morningstar_sector_code',), '==', 309, decline, None, None, 1.20, self._reg_hyg_dn5)
   # BAKE-118 R690 +0.0057
   score = _try_score_bake_v1(score, _ac_z, ('morningstar_sector_code',), '==', 308, decline, 0.07, None, 1.30, True)
   # BAKE-119 R691 +0.0048
   score = _try_score_bake_v1(score, _ac_z, ('morningstar_sector_code',), '==', 309, decline, None, None, 1.30, self._reg_double_panic)
   # BAKE-120 R692 +0.0064
   score = _try_score_bake_v1(score, _ac_z, ('morningstar_sector_code',), '==', 309, decline, None, None, 1.50, self._reg_double_panic)
   # BAKE-121 R697 +0.0022
   try:
    _va = f_(_ac_z.morningstar_sector_code)
    _vb = f_(_ops_z.tax_rate.six_months)
    if _va is not None and _vb is not None and _va == 310 and _vb < 0.18 and (decline > .03): score *= 1.25
   except: pass
   # BAKE-122 R702 +0.0069
   score = _try_score_bake_v1(score, _bs_z, ('total_assets', 'twelve_months'), '<', 1000000000.0, decline, None, None, 1.2, self._reg_hyg_dn5)
   # BAKE-123 R703 +0.0050
   score = _try_score_bake_v1(score, _bs_z, ('total_assets', 'twelve_months'), '<', 3000000000.0, decline, 0.07, None, 1.15)
   # BAKE-124 R704 +0.0021
   score = _try_score_bake_v1(score, _bs_z, ('total_assets', 'twelve_months'), '>', 500000000000.0, decline, 0.05, None, 1.1)
   # BAKE-125 R706 +0.0011
   score = _try_score_bake_v1(score, _bs_z, ('total_assets', 'twelve_months'), '<', 1000000000.0, decline, None, None, 1.2, self._reg_qqq_dn5)
   # BAKE-126 R740 +0.0022
   try:
    _r_open = f_(bar.open)
    _r = _bc / _r_open if _r_open is not None and _r_open > 0 else 1.0
    if _r > 1.02 and (decline > .03): score *= 1.12
   except: pass
   # BAKE-127 R741 +0.0027
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.0 and (decline > .05): score += 0.10
   except: pass
   # BAKE-128 R740 +0.0018 (loop, large-cap shallow-decline range)
   score = _try_score_bake_v1(score, _bs_z, ('total_assets', 'twelve_months'), '>', 100000000000.0, decline, 0.04, 0.07, 1.1)
   # BAKE-129 ROLLED BACK R744 (PEG×hyg_dn5 +=0.30 catastrophic stack with BAKE-127)
   # BAKE-130 R741 +0.0012
   try:
    _v = f_(_vr_z.cash_return)
    if _v is not None and _v > 0.10 and self._reg_hyg_dn5: score += 0.50
   except: pass
   # BAKE-131 R743 +0.0021 (loop, big-cap shallow-decline range)
   score = _try_score_bake_v1(score, _bs_z, ('total_assets', 'twelve_months'), '>', 300000000000.0, decline, 0.04, 0.08, 1.05)
   # BAKE-132 R752 +0.0134 (loop, low-goodwill cohort)
   try:
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and (decline > .05) and (decline < .10): score *= 1.10
   except: pass
   # BAKE-133 R758 +0.00455 (loop, neg-margin PENALTY)
   score = _try_score_bake_v1(score, _ops_z, ('net_margin', 'three_months'), '<', 0.0, decline, 0.05, 0.1, 0.9)
   # BAKE-134 R758 +0.00406 (loop, fcf_yield UNTOUCHED)
   score = _try_score_bake_v1(score, _vr_z, ('fcf_yield',), '>', 0.08, decline, 0.04, 0.08, 1.1)
   # BAKE-135 R757 +0.00149 (loop, low-goodwill × low-payout STACK)
   try:
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _p = f_(_vr_z.payout_ratio)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _p is not None and _p < 0.40 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-136 R760 +0.00129 (loop, low-goodwill × low-CAPE STACK)
   try:
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _c = f_(_vr_z.cape_ratio)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _c is not None and _c < 22 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-141 R767 +0.00337 (loop, om_3m TIGHTER decline subset)
   score = _try_score_bake_v1(score, _ops_z, ('operation_margin', 'three_months'), '>', 0.35, decline, 0.05, 0.1, 1.05)
   # BAKE-143 R769 +0.00426 (loop, om_3m d4_8 SISTER to BAKE-141)
   score = _try_score_bake_v1(score, _ops_z, ('operation_margin', 'three_months'), '>', 0.35, decline, 0.04, 0.08, 1.03)
   # BAKE-144 R769 +0.00277 (loop, om_3m DEEPER cohort)
   score = _try_score_bake_v1(score, _ops_z, ('operation_margin', 'three_months'), '>', 0.35, decline, 0.06, 0.1, 1.03)
   # BAKE-145 R770 +0.00228 (loop, om_3m STRICTER threshold)
   score = _try_score_bake_v1(score, _ops_z, ('operation_margin', 'three_months'), '>', 0.4, decline, 0.04, 0.08, 1.03)
   # BAKE-146 R770 +0.00129 (loop, sector_308 × fcf_yield stack)
   try:
    _s = f_(_ac_z.morningstar_sector_code)
    _v = f_(_vr_z.fcf_yield)
    if _s == 308 and _v is not None and _v > 0.08 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-147 R771 +0.00287 (loop, low-goodwill ∩ om_3m triple-stack)
   try:
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _v = f_(_ops_z.operation_margin.three_months)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _v is not None and _v > 0.35 and (decline > .04) and (decline < .08): score *= 1.03
   except: pass
   # BAKE-148 R771 +0.00267 (loop, low-goodwill ∩ nm_3m triple-stack)
   try:
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _v = f_(_ops_z.net_margin.three_months)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _v is not None and _v > 0.25 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-149 R772 +0.00139 (loop, om_1y FRESH timeframe)
   score = _try_score_bake_v1(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.4, decline, 0.04, 0.08, 1.05)
   # BAKE-150 R773 +0.00178 (loop, sector_310 × ev_to_ebitda)
   try:
    _s = f_(_ac_z.morningstar_sector_code)
    _v = f_(_vr_z.ev_to_ebitda)
    if _s == 310 and _v is not None and _v > 0 and _v < 12 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-151 R773 +0.00178 (loop, sector_206 × fcf_yield)
   try:
    _s = f_(_ac_z.morningstar_sector_code)
    _v = f_(_vr_z.fcf_yield)
    if _s == 206 and _v is not None and _v > 0.05 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-152 R778 +0.00297 (loop, UNTOUCHED cf_yield)
   score = _try_score_bake_v1(score, _vr_z, ('cf_yield',), '>', 0.1, decline, 0.04, 0.08, 1.05)
   # BAKE-154 R779 +0.00168 (loop, cf_yield STRICTER threshold)
   score = _try_score_bake_v1(score, _vr_z, ('cf_yield',), '>', 0.15, decline, 0.05, 0.1, 1.05)
   # BAKE-155 R779 +0.00119 (loop, UNTOUCHED earning_yield)
   score = _try_score_bake_v1(score, _vr_z, ('earning_yield',), '>', 0.06, decline, 0.04, 0.08, 1.05)
   # BAKE-158 R795 +0.00693 (loop, cf_yield SHALLOW decline UNTESTED REGION)
   score = _try_score_bake_v1(score, _vr_z, ('cf_yield',), '>', 0.08, decline, 0.02, 0.05, 1.05)
   # BAKE-161 ROLLED BACK R800 (over-stacked with 159+160). RT161 individual +0.00644 verified R802; kept rolled back.
   # BAKE-164 R802 +0.00663 (re-introduce RT159)
   score = _try_score_bake_v1(score, _ops_z, ('roic', 'three_months'), '>', 0.18, decline, 0.005, 0.02, 1.05)
   # BAKE-165 R805 +0.00238 (loop, roic_3m WIDER threshold/decline)
   score = _try_score_bake_v1(score, _ops_z, ('roic', 'three_months'), '>', 0.15, decline, 0.005, 0.025, 1.05)
   # BAKE-163 R802 +0.00693 (loop, low_gw × cape × shallow decline RE-INTRODUCED)
   try:
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _c = f_(_vr_z.cape_ratio)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _c is not None and _c > 0 and _c < 22 and (decline > .01) and (decline < .03): score *= 1.03
   except: pass
   # BAKE-162 R798 +0.00792 (loop, MULTI-DAY 7-day cumulative loss pattern)
   try:
    if _r7 is not None and _r7 > -0.10 and _r7 < -0.05: score *= 1.08
   except: pass
   # BAKE-166 R807 +0.00208 (loop, peg shallow decline)
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 0.8 and (decline > .01) and (decline < .03): score *= 1.05
   except: pass
   # BAKE-167 R808 +0.00198 (loop, MULTI-DAY high-low spread)
   try:
    _bars7 = mtf[-7:] if len(mtf) >= 7 else None
    _hi7 = max(f_(b.high) for b in _bars7) if _bars7 else None
    _lo7 = min(f_(b.low) for b in _bars7) if _bars7 else None
    if _hi7 is not None and _lo7 is not None and _lo7 > 0 and (_hi7/_lo7) > 1.12 and (decline > .03): score *= 1.05
   except: pass
   # BAKE-168 R812 +0.00307 (loop, normalized_diluted_eps_growth × earning_yield STACK)
   try:
    _g = f_(_ers_z.normalized_diluted_eps_growth.one_year)
    _e = f_(_vr_z.earning_yield)
    if _g is not None and _g > 0.05 and _e is not None and _e > 0.06 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-169 R815 +0.01832 (loop, SHARE BUYBACK signal)
   score = _try_score_bake_v1(score, _ers_z, ('basic_average_shares_growth', 'one_year'), '<', -0.02, decline, 0.04, 0.08, 1.05)
   # BAKE-170 R825 +0.01139 (loop, cf_yield × 5-day cum mild loss STACK)
   try:
    _v = f_(_vr_z.cf_yield)
    if _v is not None and _v > 0.08 and _r5 is not None and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   # BAKE-171 R826 +0.01752 (loop, value_score × 5d mild-loss STACK)
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 50 and _r5 is not None and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   # BAKE-172 R828 +0.00446 (loop, peg × 7d mild-loss)
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.0 and _r7 is not None and _r7 > -0.05 and _r7 < -0.02: score *= 1.05
   except: pass
   # BAKE-173 R829 +0.00455 (loop, peg TIGHTER × 5d mild-loss)
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 0.6 and _r5 is not None and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   # BAKE-174 R830 +0.00218 (loop, roic × 3d mild-loss)
   try:
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.18 and _r3 is not None and _r3 > -0.04 and _r3 < -0.02: score *= 1.08
   except: pass
   # BAKE-175 R832 +0.00198 (loop, conv ×1.50 on BAKE-174 cohort)
   try:
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.18 and _r3 is not None and _r3 > -0.04 and _r3 < -0.02: conv *= 1.50
   except: pass
   # BAKE-176 R852 +0.00436
   conv = _try_lever_bake(conv, _vr_z, ('cf_yield',), None, None, 2.5, gates=(('>', 0.08),), regime=self._reg_hyg_dn5)
   # BAKE-177 R857 +0.00129
   conv = _try_lever_bake(conv, _vr_z, ('cf_yield',), None, None, 2.0, gates=(('>', 0.08),), regime=self._reg_hyg_dn3)
   # BAKE-178 R859 +0.00584
   conv = _try_lever_bake(conv, _vr_z, ('peg_ratio',), None, None, 2.0, gates=(('>', 0.0), ('<', 1.5)), regime=self._reg_hyg_dn3)
   # BAKE-179 R860 +0.00109 (/R874 (loop, peg<1.5 × QQQ_dn3 regime conv×1.50)
   conv = _try_lever_bake(conv, _vr_z, ('peg_ratio',), None, None, 1.5, gates=(('>', 0.0), ('<', 1.5)), regime=self._reg_qqq_dn3)
   # BAKE-180 R878 +0.00713 (/R880 (loop, peg<1.5 × HYG_dn3 × shallow-decline score×1.05)
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-181 R881 +0.01000 (loop, peg<1.5 × HYG_dn3 × very-shallow-decline score×1.05)
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and (decline > .02) and (decline < .04): score *= 1.05
   except: pass
   # BAKE-182 R884 +0.00138 (/R885 (loop, peg<1.5 × HYG_dn3 × shallow-decline × CLOSE>OPE)
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and (_bc > f_(bar.open)) and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-183 R887 +0.00119 (loop, peg<1.5 × HYG_dn3 × shallow-decline × HAMMER score×1.0)
   try:
    _v = f_(_vr_z.peg_ratio)
    _bo = f_(bar.open); _bl = f_(bar.low)
    _body = abs(_bc - _bo) if _bc and _bo else 0
    _ls = (min(_bo, _bc) - _bl) if _bo and _bc and _bl else 0
    _hammer = _body > 0 and _ls > 2 * _body
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and _hammer and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-184 R893 +0.00139 (/R895/R896 (loop, peg<1.5 × HYG_dn3 × decline∈(.04,.08) × 3d)
   try:
    _v = f_(_vr_z.peg_ratio)
    _both = _r3 is not None and _r5 is not None and _r3 > -0.05 and _r3 < -0.02 and _r5 > -0.05 and _r5 < -0.02
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and _both and (decline > .04) and (decline < .08): score *= 1.14
   except: pass
   # BAKE-185 R898 +0.00327 (loop, peg<1.5 × HYG_dn3 × WIDER decline∈(.04,.10) × 3d AND 5)
   try:
    _v = f_(_vr_z.peg_ratio)
    _both = _r3 is not None and _r5 is not None and _r3 > -0.05 and _r3 < -0.02 and _r5 > -0.05 and _r5 < -0.02
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and _both and (decline > .04) and (decline < .10): score *= 1.10
   except: pass
   # BAKE-186 R906 +0.00119 (/R908 (loop, peg<1.5 × QQQ_dn3 × close>5d SMA × decline∈(.02)
   try:
    _v = f_(_vr_z.peg_ratio)
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_qqq_dn3 and _above and (decline > .02) and (decline < .06): score *= 1.10
   except: pass
   # BAKE-187 R916 +0.00119 (loop, NO COHORT × HYG_dn3 × close>5d SMA × decline∈(.04,.08))
   try:
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if self._reg_hyg_dn3 and _above and (decline > .04) and (decline < .08): score *= 1.08
   except: pass
   # BAKE-188 R918 +0.00128 (loop, NO COHORT × HYG_dn3 × close>5d SMA × HAMMER × decline∈)
   try:
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    _bo = f_(bar.open); _bl = f_(bar.low)
    _body = abs(_bc - _bo) if _bc and _bo else 0
    _ls = (min(_bo, _bc) - _bl) if _bo and _bc and _bl else 0
    _hammer = _body > 0 and _ls > 2 * _body
    if self._reg_hyg_dn3 and _above and _hammer and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-189 R942 +0.00128 (loop, SECTOR_206 × HYG_dn3 × close>5d SMA × decline∈(.02,.06)
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if _v == 206 and self._reg_hyg_dn3 and _above and (decline > .02) and (decline < .06): score *= 1.08
   except: pass
   # BAKE-153 R777 +0.00188 (loop, UNTOUCHED morningstar value_score)
   score = _try_score_bake_v1(score, _ac_z, ('value_score',), '>', 50.0, decline, 0.05, 0.1, 1.05)
   # BAKE-156 R782 +0.00149 (loop, cf_yield × value_score STACK)
   try:
    _v1 = f_(_vr_z.cf_yield)
    _v2 = f_(_ac_z.value_score)
    if _v1 is not None and _v1 > 0.05 and _v2 is not None and _v2 > 50 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-142 R768 +0.00188 (loop, sector_309 × low-goodwill stack)
   try:
    _s = f_(_ac_z.morningstar_sector_code)
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    if _s == 309 and _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and (decline > .04) and (decline < .08): score *= 1.10
   except: pass
   # BAKE-97 R661 +0.0213
   score = _try_score_bake_v1(score, _ops_z, ('roic', 'three_months'), '>', 0.18, decline, 0.03, None, 1.14)
   # BAKE-107 R672 +0.0160
   score = _try_score_bake_v1(score, _ops_z, ('operation_margin', 'three_months'), '>', 0.35, decline, 0.03, None, 1.1)
   # BAKE-114 R684 +0.0201
   score = _try_score_bake_v1(score, _ops_z, ('tax_rate', 'six_months'), '<', 0.18, decline, 0.03, None, 1.1)
   # BAKE-111 R678 +0.0081
   score = _try_score_bake_v2f(score, _vr_z, ('cape_ratio',), '<', 25.0, _ops_z, ('operation_margin', 'three_months'), '>', 0.35, decline, 0.03, None, 1.3, True)
   # BAKE-103 R668 +0.0934
   score = _try_score_bake_v1(score, _ops_z, ('roic', 'three_months'), '>', 0.15, decline, None, None, 1.2, self._reg_qqq_dn3)
   # BAKE-104 R668 +0.1561
   score = _try_score_bake_v1(score, _vr_z, ('peg_ratio',), '<', 1.5, decline, None, None, 1.2, self._reg_hyg_dn5)
   # BAKE-105 R670 +0.0134
   score = _try_score_bake_v1(score, _vr_z, ('cash_return',), '>', 0.1, decline, None, None, 1.4, self._reg_qqq_dn5)
   # BAKE-106 R672 +0.0266
   score = _try_score_bake_v1(score, _ops_z, ('roic', 'three_months'), '>', 0.15, decline, None, None, 1.2, self._reg_hyg_dn3)
   # BAKE-108 R674 +0.0090
   score = _try_score_bake_v1(score, _ops_z, ('roic', 'three_months'), '>', 0.15, decline, None, None, 1.2, self._reg_qqq_dn7)
   # BAKE-109 R676 +0.0209
   score = _try_score_bake_v1(score, _vr_z, ('peg_ratio',), '<', 1.5, decline, None, None, 1.2, self._reg_qqq_up3)
   # BAKE-110 R677 +0.0121
   score = _try_score_bake_v1(score, _ops_z, ('roic', 'three_months'), '>', 0.15, decline, None, None, 1.4, self._reg_hyg_up5)
   # BAKE-112 R679 +0.0061
   score = _try_score_bake_v1(score, _ops_z, ('roic', 'three_months'), '>', 0.15, decline, None, None, 1.4, self._reg_hyg_up3)
   # BAKE-98 R662 +0.0104
   score = _try_score_bake_v2f(score, _vr_z, ('peg_ratio',), '<', 1.5, _vr_z, ('forward_pe_ratio',), '<', 12.0, decline, 0.05, None, 1.3, True)
   # BAKE-99 R662 +0.0090
   score = _try_score_bake_v1(score, _vr_z, ('cash_return',), '>', 0.1, decline, 0.03, None, 1.15)
   # BAKE-101 R664 +0.0143
   score = _try_score_bake_v2f(score, _vr_z, ('cash_return',), '>', 0.1, _vr_z, ('peg_ratio',), '<', 1.5, decline, 0.03, None, 1.25, True)
   # BAKE-102 R664 +0.0115
   score = _try_score_bake_v2f(score, _vr_z, ('peg_ratio',), '<', 1.5, _vr_z, ('pe_ratio',), '<', 12.0, decline, 0.07, None, 1.3, True)
   # BAKE-89 R651 +0.0011
   if _try_skip_2f(_ops_z, ('tax_rate', 'one_year'), '>', 0.35, _ops_z, ('cfo_growth', 'one_year'), '<', -0.15, decline, 0.03, None): continue
   # BAKE-92 R654 +0.0067
   if _try_skip_2f(_ops_z, ('tax_rate', 'one_year'), '>', 0.35, _ops_z, ('cfo_growth', 'one_year'), '<', -0.15, decline, None, None): continue
   # BAKE-94 R658 +0.0421
   if _try_skip_bake(_ops_z, ('cfo_growth', 'one_year'), (('<', -0.4),), decline, None, None, True): continue
   # BAKE-96 R660 +0.0250
   if _try_skip_bake(_ops_z, ('fcf_growth', 'one_year'), (('<', -0.7),), decline, None, None, True): continue
   # BAKE-100 R663 +0.0100
   if _try_skip_bake(_ops_z, ('net_income_growth', 'three_months'), (('<', -0.5),), decline, None, None, True): continue
   # BAKE-90 R651 +0.0045
   score = _try_score_bake_v1(score, _ops_z, ('fcf_sales_ratio', 'one_year'), '>', 0.25, decline, 0.03, None, 1.1)
   # BAKE-190 R959 +0.00327
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and (decline > .12) and (decline < .20): score *= 1.80
   except: pass
   # BAKE-191 R967 +0.00307
   try:
    _v = f_(_vr_z.peg_ratio); _p = _bc
    if _v is not None and _v > 0 and _v < 1.5 and _p is not None and _p > 50 and _p < 100 and self._reg_hyg_dn3 and (decline > .12) and (decline < .20): score *= 1.50
   except: pass
   # BAKE-192 R974 +0.00128
   try:
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 5 and _v < 20 and self._reg_hyg_dn3 and (decline > .12) and (decline < .20): score *= 0.70
   except: pass
   # BAKE-193 R978 +0.00188
   try:
    _v = f_(_ac_z.morningstar_sector_code); _p = _bc
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if _v == 206 and _p is not None and _p > 100 and _p < 200 and self._reg_hyg_dn3 and _above and (decline > .02) and (decline < .06): score *= 1.50
   except: pass
   # BAKE-194 R985 +0.00179
   try:
    _v = f_(_vr_z.peg_ratio); _p = _bc
    if _v is not None and _v > 0 and _v < 1.5 and _p is not None and _p > 100 and _p < 200 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.08
   except: pass
   # BAKE-195 R1000 +0.00128
   try:
    _v = f_(_vr_z.peg_ratio)
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _accel is not None and _accel > -0.10 and _accel < -0.02 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.18
   except: pass
   # BAKE-196 R1001 +0.00377
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v == 206 and _accel is not None and _accel > -0.10 and _accel < -0.02 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.10
   except: pass
   # BAKE-197 R1006 +0.00118
   try:
    _v = f_(_vr_z.peg_ratio)
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v is not None and _v > 0 and _v < 1.0 and _accel is not None and _accel > -0.10 and _accel < -0.02 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.18
   except: pass
   # BAKE-198 R1021 +0.00377
   try:
    _v = f_(_vr_z.peg_ratio)
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _accel is not None and _accel > 0.05 and _accel < 0.15 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 0.70
   except: pass
   # BAKE-199 R1023 +0.00584
   score = _try_score_bake_qaccel(score, _vr_z, ('peg_ratio',), (('>', 0.0), ('<', 1.5)), self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.2, self._reg_hyg_dn3)
   # BAKE-200 R1024 +0.00475
   score = _try_score_bake_qaccel(score, _vr_z, ('peg_ratio',), (('>', 0.0), ('<', 1.5)), self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.65, self._reg_hyg_dn3)
   # BAKE-201 R1025 +0.00238
   score = _try_score_bake_qaccel(score, _vr_z, ('peg_ratio',), (('>', 0.0), ('<', 1.0)), self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.3, self._reg_hyg_dn3)
   # BAKE-202 R1029 +0.00128
   score = _try_score_bake_qaccel(score, _ops_z, ('roic', 'three_months'), (('>', 0.1),), self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.2, self._reg_hyg_dn3)
   # BAKE-203 R1030 +0.00347
   score = _try_score_bake_qaccel(score, _ops_z, ('interest_coverage', 'one_year'), (('>', 20.0),), self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.1, self._reg_hyg_dn3)
   # BAKE-204 R1031 +0.00168
   score = _try_score_bake_qaccel(score, _ops_z, ('interest_coverage', 'one_year'), (('>', 50.0),), self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.05, self._reg_hyg_dn3)
   # BAKE-205 R1032 +0.00188
   score = _try_score_bake_qaccel(score, _ops_z, ('roic', 'three_months'), (('>', 0.1),), self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.8, self._reg_hyg_dn3)
   # BAKE-206 R1040 +0.00119
   try:
    _v = f_(_ops_z.interest_coverage.one_year)
    ha = self._ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _v is not None and _v > 20 and _haccel is not None and _haccel > 0.01 and _haccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.14
   except: pass
   # BAKE-207 R1045 +0.00119
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 206, _vr_z, ('peg_ratio',), 0.0, 1.5, self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.3, self._reg_hyg_dn3)
   # BAKE-208 R1046 +0.00168
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 206, _vr_z, ('peg_ratio',), 0.0, 1.5, self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.5, self._reg_hyg_dn3)
   # BAKE-209 R1050 +0.00307
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 206, _vr_z, ('peg_ratio',), 0.0, 1.5, self._qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.6, self._reg_hyg_dn3)
   # BAKE-210 R1051 +0.00258
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _qaccel = self._qaccel
    if _v == 206 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 0.95
   except: pass
   # BAKE-211 R1052 +0.00158
   try:
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    ha = self._ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _haccel is not None and _haccel > -0.05 and _haccel < -0.01 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 0.70
   except: pass
   # BAKE-212 R1053 +0.00149
   score = _try_score_bake_qaccel(score, _ops_z, ('interest_coverage', 'one_year'), (('>', 20.0),), self._qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.93, self._reg_hyg_dn3)
   # BAKE-213 R1058 +0.00178
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 102, _vr_z, ('peg_ratio',), 0.0, 1.0, self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.4, self._reg_hyg_dn3)
   # BAKE-215 R1064 +0.00119
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 102, _vr_z, ('peg_ratio',), 0.0, 1.0, self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.07, True)
   # BAKE-216 R1065 +0.00495
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 102, _vr_z, ('peg_ratio',), 0.0, 1.0, self._qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.7, True)
   # BAKE-217 R1066 +0.01406
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 206, _vr_z, ('peg_ratio',), 0.0, 1.5, self._qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.7, True)
   # BAKE-218 R1067 +0.00446
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 206, _vr_z, ('peg_ratio',), 0.0, 1.5, self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.08, True)
   # BAKE-219 R1068 +0.00545
   score = _try_score_bake_qaccel(score, _vr_z, ('peg_ratio',), (('>', 0.0), ('<', 1.0)), self._qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.8, True)
   # BAKE-220 R1069 +0.00386
   try:
    _v = f_(_vr_z.peg_ratio)
    ha = self._ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.0 and _haccel is not None and _haccel > -0.05 and _haccel < -0.01 and (decline > .02) and (decline < .06): score *= 0.95
   except: pass
   # BAKE-221 R1070 +0.00386
   try:
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    ha = self._ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _haccel is not None and _haccel > -0.05 and _haccel < -0.01 and (decline > .02) and (decline < .06): score *= 0.90
   except: pass
   # BAKE-222 R1075 +0.00713
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 102, _vr_z, ('peg_ratio',), 0.0, 1.0, self._qaccel, -0.05, -0.01, decline, 0.06, 0.12, 0.5, True)
   # BAKE-223 R1076 +0.00455
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 206, _vr_z, ('peg_ratio',), 0.0, 1.5, self._qaccel, -0.05, -0.01, decline, 0.06, 0.12, 0.7, True)
   # BAKE-224 R1077 +0.00634
   try:
    _v = f_(_vr_z.peg_ratio)
    _qaccel = self._qaccel
    if _v is not None and _v > 0 and _v < 1.5 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and decline > .12: score *= 0.55
   except: pass
   # BAKE-225 R1078 +0.00267
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 102, _vr_z, ('peg_ratio',), 0.0, 1.0, self._qaccel, 0.01, 0.05, decline, 0.06, 0.12, 2.2, True)
   # BAKE-226 R1080 +0.00426
   try:
    _vp = f_(_vr_z.peg_ratio); _ic = f_(_ops_z.interest_coverage.one_year)
    _qaccel = self._qaccel
    if _vp is not None and _vp > 0 and _vp < 1.5 and _ic is not None and _ic > 20 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.80
   except: pass
   # BAKE-227 R1081 +0.00416
   try:
    _vp = f_(_vr_z.peg_ratio); _ic = f_(_ops_z.interest_coverage.one_year)
    _qaccel = self._qaccel
    if _vp is not None and _vp > 0 and _vp < 1.5 and _ic is not None and _ic > 50 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.65
   except: pass
   # BAKE-228 R1082 +0.00277
   try:
    _vp = f_(_vr_z.peg_ratio); _ic = f_(_ops_z.interest_coverage.one_year)
    _qaccel = self._qaccel
    if _vp is not None and _vp > 0 and _vp < 1.5 and _ic is not None and _ic > 100 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.55
   except: pass
   # BAKE-229 R1085 +0.00267
   try:
    _vp = f_(_vr_z.peg_ratio); _pe = f_(_vr_z.pe_ratio)
    _qaccel = self._qaccel
    if _vp is not None and _vp > 0 and _vp < 1.5 and _pe is not None and _pe > 0 and _pe < 15 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.65
   except: pass
   # BAKE-230 R1087 +0.00238
   try:
    _vp = f_(_vr_z.peg_ratio); _ev = f_(_vr_z.ev_to_revenue)
    _qaccel = self._qaccel
    if _vp is not None and _vp > 0 and _vp < 1.5 and _ev is not None and _ev > 0 and _ev < 2 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.85
   except: pass
   # BAKE-231 R1098 +0.00366
   score = _try_score_bake_qaccel(score, _vr_z, ('peg_ratio',), (('>', 0.0), ('<', 1.5)), self._qaccel, -0.05, -0.01, decline, 0.06, 0.12, 0.7, self._reg_double_panic)
   # BAKE-232 R1099 +0.00257
   score = _try_score_bake_qaccel(score, _vr_z, ('peg_ratio',), (('>', 0.0), ('<', 1.5)), self._qaccel, -0.05, -0.01, decline, 0.06, 0.12, 0.93, self._reg_hyg_dn14)
   # BAKE-233 R1103 +0.00168
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 206, _vr_z, ('peg_ratio',), 0.0, 1.5, self._qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.95, self._reg_hyg_dn14)
   # BAKE-234 R1104 +0.00178
   score = _try_score_qaccel_2f(score, _ac_z, ('morningstar_sector_code',), 206, _vr_z, ('peg_ratio',), 0.0, 1.5, self._qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.2, self._reg_hyg_dn14)
   # BAKE-235 R1122 +0.00317
   score = _try_score_bake_qaccel(score, _ac_z, ('value_score',), (('>', 50.0),), self._qaccel, 0.01, 0.05, decline, 0.06, 0.12, 1.3, True)
   # BAKE-236 R1123 +0.00119
   score = _try_score_bake_qaccel(score, _ac_z, ('value_score',), (('>', 70.0),), self._qaccel, 0.01, 0.05, decline, 0.06, 0.12, 1.4, True)
   # BAKE-237 R1143 +0.00248 — SKIP lever: drop high-value names (vs>60) in deep declines
   # (d12_20) during QQQ accel up. Pattern: high-vs names with deep declines DON'T
   # mean-revert as expected — entry suppression on this cohort lifts car_mdd.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v > 60 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .12) and (decline < .20): continue
   except: pass
   # BAKE-244 R1164 +0.00119 — SKIP top-decile value names (vs>85) in SHALLOW d4_8 declines
   # × QQQ accel up. Sharp threshold: vs>80 = -0.00901, vs>85 = +0.00119, vs>90 = -0.00188.
   # Sister to BAKE-237 — top-decile premium names don't mean-revert from shallow dips either.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v > 85 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .04) and (decline < .08): continue
   except: pass
   # BAKE-245 R1165 +0.00129 — SKIP top-decile (vs>85) in ULTRA-SHALLOW d2_4 declines × QQQ
   # accel up. Stacks with BAKE-244 (d4_8 same cohort). Together cover all shallow d2_8.
   # Sweet spot: vs>85 +0.00129; vs>80 = -0.00564; vs>90 = -0.00198 (cohort too small).
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v > 85 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .02) and (decline < .04): continue
   except: pass
   # BAKE-246 R1168 +0.00218 — SKIP high-vs (vs>80) × QQQ FLAT regime (qaccel ∈ [-0.01, 0.01])
   # × d2_6 shallow. Sharp sweet spot: vs<80 catastrophic (-0.06 to -0.17), vs>80 +0.00218,
   # vs>85 -0.00248. NEW regime — flat-market skip for premium names; sister to BAKE-244/245.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v > 80 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .02) and (decline < .06): continue
   except: pass
   # BAKE-247 R1169 +0.01941 — HUGE: SKIP vs>60 × QQQ FLAT regime × d6_12 normal decline.
   # Biggest single bake since BAKE-238. Sharp inversion:
   #   vs>60 SKIP: +0.01941 ← winner
   #   vs>70 SKIP: -0.01663 (over-skip removes vs ∈ [60,70] mean-reverters via 80+ score-mult bias)
   #   vs>85 SKIP: +0.00436 (BAKE-244/245 cohort, smaller effect)
   # Pattern: in flat regime, the score-multiplier stack massively over-weights vs>60 cohort;
   # those names don't mean-revert in flat-market normal-decline. Excluding all vs>60 frees
   # budget for vs<60 cohort which DOES mean-revert. Critical sweet spot at vs>60 threshold.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v > 60 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): continue
   except: pass
   # BAKE-249 R1175 +0.02325 — HUGE: SCORE×1.20 on narrow vs ∈ [15, 30] middle band ×
   # QQQ FLAT × d6_12. Third-biggest bake ever (after BAKE-238 and BAKE-247). Sharp threshold:
   #   vs ∈ [15,30] m120: +0.02325 ← winner
   #   vs ∈ [15,40] m120: -0.00260 (band too wide)
   #   vs ∈ [15,60] m120: -0.00220
   #   vs ∈ [20,50] m120: -0.00110
   # Sandwich: above BAKE-238's vs<15 deep-value, below BAKE-247's vs>60 skip cohort.
   # In flat regime, this narrow band IS the under-weighted mean-revert sweet spot.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v >= 15 and _v < 30 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 1.20
   except: pass
   # BAKE-250 R1178 +0.02886 — HUGE: SOFT-SKIP via score×0.5 on vs ∈ [50, 60] × QQQ FLAT × d6_12.
   # Fourth-biggest bake ever (after BAKE-238/247/249). Sharp asymmetric pattern:
   #   m50 (heavy demote): +0.02886 ← winner
   #   m70: -0.01647 (partial demote insufficient)
   #   m85-95: -0.0064 (mild demote hurts)
   #   m105-110: NOOP
   #   m114+: catastrophic (boosting this cohort destroys the strategy)
   # Cohort = "near-skipped band" — just below BAKE-247's vs>60 SKIP threshold. The
   # score-multiplier stack over-weights this band; heavy demotion (soft-skip) makes
   # them rank low and rarely picked. Different from outright SKIP — keeps optionality.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v >= 50 and _v < 60 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 0.5
   except: pass
   # BAKE-251 R1183 +0.00917 — ADDITIONAL score×1.20 on vs ∈ [25, 30] sub-band of BAKE-249.
   # BAKE-249 already boosts vs ∈ [15, 30] × q_flat × d6_12 by 1.20. This stacks an additional
   # 1.20 on the [25, 30] sub-band, making total effective multiplier 1.44 for [25, 30].
   # The [15, 25] sub-band keeps the original 1.20. Sub-band-specific tilt within BAKE-249.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v >= 25 and _v < 30 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 1.20
   except: pass
   # BAKE-252 R1191 +0.00598 — SCORE DEMOTE×0.85 on vs ∈ [50, 60] × QQQ FLAT × d4_8.
   # BAKE-250 SISTER at shallower decline range. Same near-skip cohort, different decline depth.
   # m85 winner (+0.00598), m95 +0.00567, m75 +0.00423 — smooth peak at 0.85.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v >= 50 and _v < 60 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 0.85
   except: pass
   # BAKE-253 R1190 +0.00278 — ADDITIONAL score×1.20 on vs ∈ [25, 30] × q_flat × d6_12.
   # Same gate as BAKE-251 — stacks another 1.20 on the [25, 30] sub-band. Effective on
   # [25, 30] now 1.20 × 1.20 × 1.20 = 1.728 (BAKE-249 + BAKE-251 + BAKE-253). Saturated
   # cluster: 6+ specs at +0.00278 across mags 1.20-2.00 — likely WT_CAP-bound.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v >= 25 and _v < 30 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 1.20
   except: pass
   # BAKE-254 R1194 +0.00670 — SCORE DEMOTE×0.95 on vs[15,30] × q_flat × d4_8.
   # BAKE-249 SHALLOW SISTER: BAKE-249 boosts vs[15,30] in d6_12 (×1.20); shallow d4_8
   # cohort wants mild demote instead. m95 winner; the cohort under-mean-reverts at
   # shallow declines, so reducing weight slightly improves portfolio.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v >= 15 and _v < 30 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 0.95
   except: pass
   # BAKE-255 R1196 +0.00412 — sector 206 (Healthcare) × q_flat × d6_12 × score×0.85.
   # Healthcare names in flat regime under-mean-revert at normal declines; demote.
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _qaccel = self._qaccel
    if _v is not None and _v == 206 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 0.85
   except: pass
   # BAKE-256 R1194 +0.00351 — sector 102 (Consumer Cyclical) × q_flat × d6_12 × score×0.95.
   # Mild demote of consumer cyclical in flat regime; smaller effect than Healthcare.
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _qaccel = self._qaccel
    if _v is not None and _v == 102 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 0.95
   except: pass
   # BAKE-257 R1198 +0.00474 — sector 308 (Communication Services) × q_flat × d6_12 × score×1.05.
   # Comm Services BOOST (opposite of Healthcare/Consumer Cyclical demotes). Sector-specific
   # mean-reversion: comm-svc names in flat regime mean-revert better than baseline.
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _qaccel = self._qaccel
    if _v is not None and _v == 308 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 1.05
   except: pass
   # BAKE-258 R1200 +0.00753 — sector 308 × q_flat × d2_4 × score×1.05 (BAKE-257 SHALLOWER SISTER).
   # Comm-svc boost extends to ULTRA-SHALLOW declines. Even bigger lift than BAKE-257 (d6_12).
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _qaccel = self._qaccel
    if _v is not None and _v == 308 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .02) and (decline < .04): score *= 1.05
   except: pass
   # BAKE-259 R1200 +0.00619 — sector 311 (Technology) × q_neg × d6_12 × score×1.25 (TECH-NEG BOOST).
   # Tech names in NEG regime at normal declines mean-revert strongly when boosted. Different
   # regime than BAKE-257/258 (q_neg vs q_flat). Sector-specific NEG-regime alpha.
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _qaccel = self._qaccel
    if _v is not None and _v == 311 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .06) and (decline < .12): score *= 1.25
   except: pass
   # BAKE-260 R1200 +0.00186 — sector 309 (Energy) × q_flat × d4_8 × score×1.50.
   # Energy at shallow declines in flat regime needs heavy boost. Different cohort dynamics
   # than tech/comm — energy under-mean-reverts unless aggressively scored up.
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _qaccel = self._qaccel
    if _v is not None and _v == 309 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 1.50
   except: pass
   # BAKE-261 R1199 +0.00113 — sector 308 × q_flat × d4_8 × score×0.95 (mild demote).
   # Comm-svc at MID-shallow d4_8 wants slight demote, even though d2_4 (BAKE-258) and d6_12
   # (BAKE-257) want boost. Non-monotonic decline-range response.
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    _qaccel = self._qaccel
    if _v is not None and _v == 308 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 0.95
   except: pass
   # BAKE-262 R1202 +0.00134 — vs<5 × q_flat × d4_8 × score×0.95 (deepest deep-value mild demote).
   # vs<5 is the extreme deep-value sub-band of BAKE-238 (vs<15 boost cohort). At shallow
   # d4_8, this sub-band wants mild demote — distress-signal interpretation: extreme low vs
   # in shallow declines may indicate fundamental rot rather than mean-revert opportunity.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 5 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 0.95
   except: pass
   # BAKE-263 R1203 +0.00680 — vs<5 × q_flat × d2_4 × score×0.55 (HEAVY distress demote).
   # BAKE-262 SHALLOWER SISTER. At ULTRA-shallow d2_4, the distress signal is even stronger.
   # m55 winner; m75/m85 +0.0033 (mild demote insufficient); m105+ near-noise.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 5 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .02) and (decline < .04): score *= 0.55
   except: pass
   # BAKE-264 R1203 +0.00155 — vs<5 × q_neg × d4_8 × score×0.85 (NEG regime distress demote).
   # BAKE-262 NEG sister. In NEG regime, distress signal still applies but milder demote
   # suffices (m75/m85 tied at +0.00155). Picked m85 for conservatism.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 5 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .04) and (decline < .08): score *= 0.85
   except: pass
   # BAKE-265 R1204 +0.01155 — vs<10 × q_flat × d2_4 × score×1.05 (HUGE shallow boost on
   # wider deep-value cohort). m105 is sharp peak: m95=-0.0038, m115/m130 positive but lower.
   # STACKS with BAKE-263 (vs<5 × d2_4 × 0.55): vs<5 effective = 0.5775 (preserves heavy
   # demote), vs[5,10] effective = 1.05 (boost — the new alpha source).
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 10 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .02) and (decline < .04): score *= 1.05
   except: pass
   # BAKE-266 R1204 +0.00134 — vs<10 × q_flat × d4_8 × score×1.05 (BAKE-265 deeper sister).
   # STACKS with BAKE-262 (vs<5 × d4_8 × 0.95): vs<5 effective = 0.9975, vs[5,10] = 1.05.
   # Borderline lift — kept because pattern matches BAKE-265 exactly.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 10 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-310 R1248 +0.00196 — vs<10 × q_neg × d4_8 × score×1.05 (BAKE-266 NEG sister).
   # Extends vs<10 boost from q_flat to q_neg regime. m105 winner. Confirms vs<10 cohort
   # mean-reverts in shallow declines regardless of regime direction.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 10 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-311 R1249 +0.00381 — vs<10 × q_as × d6_12 × score×1.50 (vs<10 q_as completion).
   # Sub-band of BAKE-238 (vs<15 q_as d6_12 ×1.20). For vs<10 sub-band, stacks to 1.20×1.50=1.80.
   # Completes vs<10 regime grid: q_flat (BAKE-266 d4_8 +1.05), q_neg (BAKE-310 d4_8 +1.05),
   # q_as (BAKE-311 d6_12 +1.80 effective).
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 10 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .06) and (decline < .12): score *= 1.50
   except: pass
   # BAKE-312 R1249 +0.00351 — vs<5 × q_neg × d6_12 × score×0.55 (HEAVY DEMOTE).
   # vs<5 cohort × NEG regime × normal-decline = strong distress signal. m55 winner;
   # m114=+0.00175, m150=+0.00103 (non-monotone but m55 unique winner).
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 5 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .06) and (decline < .12): score *= 0.55
   except: pass
   # BAKE-313 R1251 +0.00433 — vs[15,30] × _r5>0.05 × d4_12 × score×1.50 (BAKE-249 × bounce HEAVY BOOST).
   # BAKE-249 boost cohort (vs[15,30] q_flat d6_12 ×1.20) + 5-day positive return signal =
   # confirmed mean-revert in progress; heavy boost. m150 winner; m125/m114 +0.00247.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 15 and _v < 30 and _r5 is not None and _r5 > 0.05 and _r5 < 0.20 and (decline > .04) and (decline < .12): score *= 1.50
   except: pass
   # BAKE-314 R1253 +0.00175 — vs[5,10] × _r5>0.05 × d2_4 × score×1.50 (BAKE-265 × bounce ultra-shallow).
   # BAKE-265 boost cohort + 5-day bounce signal at ultra-shallow declines = confirmed mean-revert.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 5 and _v < 10 and _r5 is not None and _r5 > 0.05 and _r5 < 0.20 and (decline > .02) and (decline < .04): score *= 1.50
   except: pass
   # BAKE-315 R1254 +0.00113 — vs[15,30] × _r5>0.05 × d6_12 × score×1.14 (BAKE-313 sub-band).
   # Sub-band of BAKE-313 (d4_12 ×1.50). For d6_12 sub-band, stacks to net 1.71 effective.
   # Tied cluster m114/m125/m150 saturated — picked m114 for parsimony.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 15 and _v < 30 and _r5 is not None and _r5 > 0.05 and _r5 < 0.20 and (decline > .06) and (decline < .12): score *= 1.14
   except: pass
   # BAKE-316 R1255 +0.00103 — sector 308 × _r5>0.05 × d4_12 × score×0.55 (HEAVY DEMOTE).
   # COUNTERINTUITIVE: sec 308 normally boosts (BAKE-257/258 ×1.05), but when ALREADY bounced
   # (5d return >5%), mean-revert opportunity is past — heavy demote avoids late entries.
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 308 and _r5 is not None and _r5 > 0.05 and _r5 < 0.20 and (decline > .04) and (decline < .12): score *= 0.55
   except: pass
   # BAKE-267 R1207 +0.00124 — close > $150 × q_flat × d6_12 × score×1.05 (high-price boost).
   # Large-cap / expensive names mean-revert better than baseline in flat regime. New axis:
   # PRICE TIER. Reads cached _bc (close already converted to float at MIN_PRICE filter).
   try:
    _qaccel = self._qaccel
    if _bc > 150 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 1.05
   except: pass
   # BAKE-268 R1208 +0.00227 — close > $150 × q_neg × d6_12 × score×0.95 (high-price demote in NEG).
   # REGIME-ASYMMETRIC: high-price BOOSTS in q_flat (BAKE-267) but DEMOTES in q_neg.
   # Pattern: in declining-momentum regime, expensive names continue to fall — mild demote.
   try:
    _qaccel = self._qaccel
    if _bc > 150 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .06) and (decline < .12): score *= 0.95
   except: pass
   # BAKE-269 R1209 +0.00412 — close > $150 × q_neg × d4_8 × score×0.75 (HEAVY demote at shallow).
   # BAKE-268 SHALLOWER SISTER. At shallow d4_8 in q_neg, high-price wants HEAVIER demote
   # (m75 vs m95). Distress-like signal: expensive names with shallow declines in NEG regime
   # are early-distress candidates — heavily demote rather than mild demote.
   try:
    _qaccel = self._qaccel
    if _bc > 150 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .04) and (decline < .08): score *= 0.75
   except: pass
   # BAKE-270 R1209 +0.00134 — bs.cash_equivalents > $100M × q_as × d6_12 × score×1.30.
   # Cash-rich names mean-revert better in POS regime at normal declines. New axis: balance
   # sheet liquidity strength.
   try:
    _v = f_(_bs_z.cash_equivalents.three_months)
    _qaccel = self._qaccel
    if _v is not None and _v > 1e8 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .06) and (decline < .12): score *= 1.30
   except: pass
   # BAKE-271 R1211 +0.00361 — _r7 < -0.10 × q_flat × d4_12 × score×0.85 (7-day cum-loss demote).
   # NEW AXIS: multi-day return signal. 7-day deep loss in flat regime signals exhaustion —
   # mean-revert is less likely; mild demote helps. Tied cluster m55/m75/m85/m114; picked
   # m85 for conservatism (lightest demote in tied band).
   try:
    _qaccel = self._qaccel
    if _r7 is not None and _r7 < -0.10 and _r7 > -0.30 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .12): score *= 0.85
   except: pass
   # BAKE-272 R1211 +0.00134 — self._qd5 < -0.05 × d4_12 × score×0.95 (deep QQQ-down demote).
   # When QQQ has dropped >5% in 5 days, even mean-revert candidates are riskier. Mild
   # demote at m95. Sister to BAKE-53/54/56/57/58 but with tighter qd5 threshold (-0.05 vs -0.03).
   # BAKE-305 R1238 +0.00268 — qd5<-0.05 × q_neg × d4_12 × score×0.85 (DOUBLE-DOWN BEAR DEMOTE).
   # Stacks with BAKE-272 (×0.95): when QQQ down >5% AND _qaccel also negative,
   # heavier demote (0.95 × 0.85 = 0.8075 effective). Bear-confirmed regime.
   # BAKE-306 R1239 +0.00155 — qd5<-0.05 × q_neg × _r5<0 × d4_12 × score×0.75 (TRIPLE-BEAR).
   # Stacks: 0.95 × 0.85 × 0.75 = 0.6056 effective (very heavy demote when 3 bear signals
   # confirm: 5d QQQ-down, NEG accel, AND stock-specific 5d loss).
   try:
    if self._qd5 is not None and self._qd5 < -0.05 and (decline > .04) and (decline < .12):
     score *= 0.95
     _qaccel = self._qaccel
     if _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05:
      score *= 0.85
      if _r5 is not None and _r5 < 0: score *= 0.75
   except: pass
   # BAKE-273 R1213 +0.00443 — _r7 < -0.05 × q_flat × d2_4 × score×0.55 (HEAVY demote).
   # BAKE-271 milder threshold (-0.05 vs -0.10) + ULTRA-SHALLOW decline (d2_4 vs d4_12).
   # Stocks with mild 7-day loss in flat regime AT shallow declines are early-distress —
   # heavy demote. Different cohort from BAKE-271 (deeper r7) — non-overlapping.
   try:
    _qaccel = self._qaccel
    if _r7 is not None and _r7 < -0.05 and _r7 > -0.20 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .02) and (decline < .04): score *= 0.55
   except: pass
   # BAKE-274 R1213 +0.00206 — price > $150 × sector 308 × d4_12 × score×1.25 (compound BOOST).
   # PRICE × SECTOR compound. Large-cap Comm-Services names mean-revert strongly. Stacks with
   # BAKE-257/258 (sector 308 boost) and BAKE-267 (price > 150 boost) — concentrated alpha
   # at intersection.
   try:
    _v = f_(_ac_z.morningstar_sector_code)
    if _bc > 150 and _v is not None and _v == 308 and (decline > .04) and (decline < .12): score *= 1.25
   except: pass
   # BAKE-275 R1213 +0.00186 — vs[5,10] × _r5 < -0.05 × d4_12 × score×0.95 (compound demote).
   # COHORT × MULTI-DAY RETURN compound. vs[5,10] (BAKE-265 boost cohort) when ALSO showing
   # 5-day cumulative loss — mild demote. Distress signal within otherwise-boosted cohort.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 5 and _v < 10 and _r5 is not None and _r5 < -0.05 and _r5 > -0.20 and (decline > .04) and (decline < .12): score *= 0.95
   except: pass
   # BAKE-276 R1214 +0.00165 — vs<5 × _r3 < -0.03 × d4_12 × score×1.05 (counter-distress BOOST).
   # COUNTERINTUITIVE: vs<5 normally distress-demoted (BAKE-262/263/264) but when ALSO showing
   # mild 3-day loss in mid-declines, WANTS MILD BOOST. Tied cluster m105/m114/m125/m150 = saturated;
   # picked m105 for parsimony. Different cohort from distress demotes (d4_12 not d2_4).
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v < 5 and _r3 is not None and _r3 < -0.03 and _r3 > -0.15 and (decline > .04) and (decline < .12): score *= 1.05
   except: pass
   # BAKE-277 R1214 +0.00134 — _r7 < -0.05 × q_flat × d4_8 × score×0.75 (BAKE-273 wider decline).
   # Mild 7-day loss in flat regime extends from d2_4 (BAKE-273 m55) to d4_8 with milder
   # demote (m75). Decline-tier-asymmetric: shallower ranges want heavier demote.
   try:
    _qaccel = self._qaccel
    if _r7 is not None and _r7 < -0.05 and _r7 > -0.20 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 0.75
   except: pass
   # BAKE-278 R1216 +0.00216 — vs[5,10] × _r3 < -0.02 × d4_12 × score×1.05 (compound BOOST).
   # Asymmetry vs BAKE-275 (vs[5,10] × _r5 < -0.05 × d4_12 × demote 0.95):
   # - Mild short-term loss (r3<-0.02) → BOOST (not yet hit, fresh mean-revert candidate)
   # - Deeper longer loss (r5<-0.05) → DEMOTE (distress signal accumulating)
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 5 and _v < 10 and _r3 is not None and _r3 < -0.02 and _r3 > -0.15 and (decline > .04) and (decline < .12): score *= 1.05
   except: pass
   # BAKE-279 R1216 +0.00165 — vs<5 × _r5 < 0 × d4_8 × score×1.50 (HEAVY BOOST).
   # COUNTER-DISTRESS: vs<5 × q_flat × d4_8 normally demoted by BAKE-262 (×0.95). When ALSO
   # showing any 5-day loss (_r5<0), wants HEAVY boost. Effective stack: 0.95 × 1.50 = 1.425.
   # Distress signal is reversed when multi-day loss confirms recent decline (vs broad sub-band
   # noise). m150 was unique winner — boost may extend higher with more probes.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v < 5 and _r5 is not None and _r5 < 0 and _r5 > -0.20 and (decline > .04) and (decline < .08): score *= 1.50
   except: pass
   # BAKE-280 R1216 +0.00124 — bar.open/prev_close < 0.95 × q_flat × d4_8 × score×0.55 (gap-down demote).
   # NEW DIMENSION: BAR-LEVEL gap signal. Gap-down opening (open < 95% prev close) signals
   # overnight bad news / capitulation that doesn't mean-revert; heavy demote at m55.
   try:
    _o = f_(bar.open); _pc = f_(mtf[-2].close)
    _qaccel = self._qaccel
    if _o > 0 and _pc > 0 and _o/_pc < 0.95 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 0.55
   except: pass
   # BAKE-281 R1217 +0.00103 — vs<5 × _r5 < 0 × d2_4 × score×0.95 (DECLINE-TIER-ASYMMETRIC).
   # Sharp peak at m95 (m85/m114 NOOP-tied). Decline-tier-asymmetric vs BAKE-279:
   # - d4_8 (BAKE-279): _r5<0 → BOOST 1.50
   # - d2_4 (BAKE-281): _r5<0 → DEMOTE 0.95
   # Ultra-shallow + 5-day loss in vs<5 cohort = persistent weakness, not mean-revert.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v < 5 and _r5 is not None and _r5 < 0 and _r5 > -0.20 and (decline > .02) and (decline < .04): score *= 0.95
   except: pass
   # BAKE-282 R1218 +0.00804 — close < $50 × q_neg × d4_8 × score×0.75 (HUGE low-price demote).
   # Sharp peak: m75 +0.00804, m85 +0.00340, m95 +0.00124 — heavier demote = bigger gain.
   # Low-price stocks in declining-momentum regime at shallow declines have lower mean-revert
   # probability — strong demote captures the negative cohort. Sister to BAKE-268/269 (high
   # price q_neg demotes) — symmetric: BOTH price tiers want demote in q_neg, but low-price
   # demote is much heavier than high-price.
   try:
    _qaccel = self._qaccel
    if _bc < 50 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .04) and (decline < .08): score *= 0.75
   except: pass
   # BAKE-283 R1219 +0.01062 — close ∈ [$50, $100] × q_neg × d4_8 × score×0.95 (HUGE mid-price demote).
   # Mid-price tier in NEG regime at shallow declines wants mild demote. Largest single-bake
   # win this session at this point. Connects with BAKE-282 (low-price q_neg d4_8 ×0.75) —
   # both price tiers demote in this regime/decline, with mild demote sufficient for mid-tier.
   try:
    _qaccel = self._qaccel
    if _bc > 50 and _bc < 100 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .04) and (decline < .08): score *= 0.95
   except: pass
   # BAKE-284 R1219 +0.00773 — close < $50 × q_neg × d6_12 × score×1.30 (low-price BOOST).
   # DECLINE-TIER-ASYMMETRIC vs BAKE-282 (low-price q_neg d4_8 → DEMOTE 0.75):
   # - d4_8 (BAKE-282): DEMOTE 0.75 (early-distress)
   # - d6_12 (BAKE-284): BOOST 1.30 (deep-decline mean-revert candidate)
   # The transition at d=0.06 — ultra-shallow distress flips to deeper-decline opportunity.
   try:
    _qaccel = self._qaccel
    if _bc < 50 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .06) and (decline < .12): score *= 1.30
   except: pass
   # BAKE-285 R1219 +0.00175 — close < $50 × q_flat × d4_8 × score×0.95 (low-price q_flat demote).
   # BAKE-282 q_flat sister. Mild demote in flat regime — softer than NEG regime demote (0.75 vs 0.95).
   try:
    _qaccel = self._qaccel
    if _bc < 50 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .04) and (decline < .08): score *= 0.95
   except: pass
   # BAKE-286 R1220 +0.00753 — close ∈ [$50, $100] × q_neg × d6_12 × score×1.05 (mid-price BOOST).
   # DECLINE-TIER-ASYMMETRIC (mirrors BAKE-282/284 low-price pattern):
   # - d4_8 (BAKE-283): mid-price q_neg → DEMOTE 0.95
   # - d6_12 (BAKE-286): mid-price q_neg → BOOST 1.05
   # Both price tiers show same d4_8-demote / d6_12-boost flip in q_neg regime.
   try:
    _qaccel = self._qaccel
    if _bc > 50 and _bc < 100 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .06) and (decline < .12): score *= 1.05
   except: pass
   # BAKE-287 R1221 +0.00268 — close > $150 × q_neg × d6_12 × score×1.14 (high-price BOOST).
   # Stacks with BAKE-268 (price>150 q_neg d6_12 demote 0.95) — net effective 1.083 (mild
   # boost). Confirms UNIVERSAL PATTERN: all price tiers want d6_12 BOOST in q_neg regime
   # (low: BAKE-284 ×1.30, mid: BAKE-286 ×1.05, high: BAKE-287 net ×1.083).
   try:
    _qaccel = self._qaccel
    if _bc > 150 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .06) and (decline < .12): score *= 1.14
   except: pass
   # BAKE-288 R1223 +0.00474 — close ∈ [$75, $100] × q_neg × d4_8 × score×0.85 (sub-band heavier demote).
   # Sub-band of BAKE-283 (price [50,100] q_neg d4_8 ×0.95). For [75,100] sub-band, stacks
   # to net effective 0.95 × 0.85 = 0.8075 (heavier demote). Upper-mid-tier wants more
   # aggressive demote than the broader cohort average.
   try:
    _qaccel = self._qaccel
    if _bc > 75 and _bc < 100 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .04) and (decline < .08): score *= 0.85
   except: pass
   # BAKE-289 R1223 +0.00124 — close ∈ [$30, $50] × q_neg × d4_8 × score×0.95 (sub-band).
   # Sub-band of BAKE-282 (price<\$50 q_neg d4_8 ×0.75). For [30,50] sub-band, stacks to
   # 0.75 × 0.95 = 0.7125 (slightly heavier than parent demote).
   try:
    _qaccel = self._qaccel
    if _bc > 30 and _bc < 50 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .04) and (decline < .08): score *= 0.95
   except: pass
   # BAKE-290 R1224 +0.00361 — close ∈ [$75, $100] × q_neg × d6_12 × score×0.55 (sub-band HEAVY DEMOTE).
   # COUNTERINTUITIVE: BAKE-286 boosts [50,100] q_neg d6_12 (×1.05). Sub-band [75,100] flips
   # to HEAVY DEMOTE (m55/m65 tied). Net effective on [75,100] = 1.05 × 0.55 = 0.5775.
   # Implication: [50,75] sub-band carries the BAKE-286 boost; [75,100] is actually negative.
   try:
    _qaccel = self._qaccel
    if _bc > 75 and _bc < 100 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .06) and (decline < .12): score *= 0.55
   except: pass
   # BAKE-291 R1224 +0.00268 — close ∈ [$25, $50] × q_neg × d6_12 × score×1.05 (sub-band BOOST).
   # Sub-band of BAKE-284 (price<\$50 q_neg d6_12 ×1.30). For [25,50] sub-band, stacks to
   # 1.30 × 1.05 = 1.365 (slight extra boost on top of parent).
   try:
    _qaccel = self._qaccel
    if _bc > 25 and _bc < 50 and _qaccel is not None and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .06) and (decline < .12): score *= 1.05
   except: pass
   # BAKE-299 R1232 +0.00526 — high per-stock vol (>4%) × q_flat × d4_12 × score×0.75 (DEMOTE).
   # NEW DIMENSION: 20d realized volatility. High-vol stocks whipsaw more than mean-revert.
   # Uses cached `window` (20-bar history from line 489) — no extra LEAN history call.
   # m75 winner: m85=+0.00464, m95=+0.00175, m55=+0.00052 (sharp peak at m75).
   # BAKE-300 R1233 +0.00206 — same vola gate × q_neg × d4_12 × score×0.85 (NEG sister, milder).
   # Both demote, but q_flat gets heavier demote (0.75) than q_neg (0.85).
   # BAKE-301 R1234 +0.01155 — vola>0.04 × q_flat × d2_4 × score×1.50 (BOOST! opposite of BAKE-299 d4_12).
   # DECLINE-TIER ASYMMETRY: high-vol at ultra-shallow d2_4 = early-opportunity (mean-revert
   # candidate); at d4_12 = whipsaw risk (demote). m150 winner; m125=+0.01052; m114=+0.00742.
   # BAKE-302 R1234 +0.00103 — vola>0.05 (stricter) × q_neg × d4_8 × score×0.85.
   # Stricter vol threshold version of BAKE-300 in shallower decline range.
   try:
    _qaccel = self._qaccel
    # _wcl already computed above (hoisted); reuse instead of re-iterating window
    _vola = (sum((_wcl[i]/_wcl[i-1]-1)**2 for i in range(1, 20) if _wcl[i-1] > 0) / 19) ** 0.5 if _wcl else None
    if _vola is not None and _qaccel is not None:
     if _vola > 0.04 and (decline > .04) and (decline < .12):
      if _qaccel > -0.01 and _qaccel < 0.01: score *= 0.75   # BAKE-299
      elif _qaccel < -0.01 and _qaccel > -0.05: score *= 0.85  # BAKE-300
     if _vola > 0.04 and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .02) and (decline < .04): score *= 1.50  # BAKE-301
     if _vola > 0.05 and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .04) and (decline < .08): score *= 0.85  # BAKE-302
     # BAKE-303 R1235 +0.00320 — vola>0.04 × q_neg × d2_4 × score×0.95 (regime-asymmetric to BAKE-301).
     # vol>0.04 × d2_4: q_flat → BOOST 1.50, q_neg → DEMOTE 0.95. Same vol cohort, opposite directions.
     if _vola > 0.04 and _qaccel < -0.01 and _qaccel > -0.05 and (decline > .02) and (decline < .04): score *= 0.95  # BAKE-303
     # BAKE-304 R1236 +0.00392 — vola>0.04 × vs<10 × d4_12 × score×0.75 (COMPOUND DEMOTE).
     # vol × cohort compound. Net for vs<10 × q_flat × d4_12 × vol>0.04 = 0.75 × 0.75 = 0.5625
     # (heavy demote — these names whipsaw AND distress-signal). m75 picked from tied cluster
     # m55/m75/m85 (+0.00412..+0.00392).
     if _vola > 0.04 and (decline > .04) and (decline < .12):
      _v304 = f_(_ac_z.value_score) if _ac_z else None
      if _v304 is not None and _v304 < 10: score *= 0.75
   except: pass
   # BAKE-307 R1240 +0.00103 — vs[5,10] × HYG_dn3 × d4_12 × score×0.55 (COHORT × HYG cross).
   # BAKE-265 (vs[5,10] q_flat d2_4 BOOST) cohort crosses strict HYG-down regime → heavy
   # demote. When bond market is in confirmed downtrend, the otherwise-boosted vs[5,10]
   # cohort actually under-mean-reverts.
   try:
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 5 and _v < 10 and self._reg_hyg_dn3 and (decline > .04) and (decline < .12): score *= 0.55
   except: pass
   # BAKE-308 R1243 +0.00113 — vs[55,60] × q_flat × d6_12 × score×1.50 (sub-band partial-undo).
   # Sub-band of BAKE-250 (vs[50,60] q_flat d6_12 ×0.5 demote). For [55,60] sub-band, stacks
   # to net 0.5 × 1.50 = 0.75 (lighter demote — top half of cohort wants less aggressive demote).
   # Implication: BAKE-250 alpha concentrated in [50,55] sub-band; [55,60] partially undoes.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v > 55 and _v < 60 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 1.50
   except: pass
   # BAKE-309 R1244 +0.00113 — vs[35,40] × q_flat × d6_12 × score×1.25 (mid-vs sub-band boost).
   # Independent of BAKE-242 (which is q_as cohort). In q_flat regime, mid-vs [35,40] cohort
   # wants mild boost. m114/m105 +0.00093 nearby; m125 unique winner.
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v > 35 and _v < 40 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): score *= 1.25
   except: pass
   # BAKE-238 R1146 +0.01327 — SCORE BOOST: deep-value names (vs<15) × QQQ accel up ×
   # normal decline d6_12 × score×1.20. Sharp threshold: vs<20 at m120 = -0.063,
   # only vs<15 benefits. These are the strongest mean-revert candidates and were
   # under-weighted by score-multiplier stack (which favors high-vs names).
   score = _try_score_bake_qaccel(score, _ac_z, ('value_score',), (('<', 15.0),), self._qaccel, 0.01, 0.05, decline, 0.06, 0.12, 1.2, True)
   # BAKE-242 R1153 +0.00416 — SCORE DEMOTE×0.85 on mid-vs cohort (vs ∈ [30, 50])
   # × QQQ accel up × d6_12. Mid-vs names are over-represented in selection by the
   # 80+ score multipliers; demoting opens slots for stronger mean-reverters.
   # Sharp threshold: m105 = +0.0008, m110 = -0.004 — only demotion direction works.
   score = _try_score_bake_qaccel(score, _ac_z, ('value_score',), (('>', 30.0), ('<', 50.0)), self._qaccel, 0.01, 0.05, decline, 0.06, 0.12, 0.85, True)
   # --- ENTRY INJECT POINT ---
   # BAKE-7 R177: f_growth (rg>.15 × decline>.05 × ×1.15) = +0.040 verified 5/5
   try:
    if _ops_z and decline > .05:
     _rg = f_(_ops_z.revenue_growth.one_year)
     if _rg > .15: score *= 1.15
   except: pass
   # BAKE-8 R183: rg_xhyg_no_decline_mag120 (rg>.15 × bond-down 5d → score×1.20, NO decline gate) = +0.080 verified 5/5
   try:
    if _ops_z:
     _rg8 = f_(_ops_z.revenue_growth.one_year)
     if _rg8 and _rg8>.15 and self._reg_hyg_dn5:
      score *= 1.20
   except: pass
   # BAKE-9 R184: skip_neg_roe_strict (roe<-.10 × QQQ consec3 lower closes → continue) = +0.040 verified 5/5
   try:
    if _ops_z:
     _roe9 = f_(_ops_z.roe.one_year)
     if _roe9 is not None and _roe9 < -.05 and self._reg_qqq_dn3:  # BAKE-50 R563: ROE -.10→-.05, +0.0055
      continue
   except: pass
   # BAKE-11 R187: garp_xhyg (peg<1.0 × bond-down 5d → score×1.15) = +0.016 verified 5/5
   try:
    if _vr_z:
     _peg11 = f_(_vr_z.peg_ratio)
     if _peg11 is not None and 0<_peg11<1.2 and self._reg_hyg_dn5:  # BAKE-48 R561: PEG <1.0→<1.2, +0.0109 no-verify auto-bake
      score *= 1.15
   except: pass
   # BAKE-12 R188-R189: qgp (gm>.40 × rg>.15 × decline>.15 → score×1.25) = +0.012 verified 5/5
   try:
    if _ops_z and decline > .18:  # BAKE-46 R558: .15→.18, +0.0033 verified 1x
     _gm12 = f_(_ops_z.gross_margin.one_year)
     _rg12 = f_(_ops_z.revenue_growth.one_year)
     if _gm12 and _gm12>.40 and _rg12 and _rg12>.15:
      score *= 1.25
   except: pass
   # BAKE-13 R192-R193: qgp tier-2 (gm>.40 × rg>.15 × decline>.20 → score×1.30) = +0.014 verified 5/5
   try:
    if _ops_z and decline > .18:  # BAKE-21 R221-R223: .20→.18 (4-way stack component)
     _gm13 = f_(_ops_z.gross_margin.one_year)
     _rg13 = f_(_ops_z.revenue_growth.one_year)
     if _gm13 and _gm13>.40 and _rg13 and _rg13>.15:
      score *= 1.40  # BAKE-43 R448-R449: 1.30→1.40 (joint with grad .0194 + b22xb .87)
   except: pass
   # BAKE-14 R195-R197: mom_5_20_oversold_growth (per-stock MA5<MA20×0.92 × rg>.15 → score×1.18) = +0.015 verified 5/5
   # PERFOPT: only fetch 20d history if rg>.15 gate passes (saves bars for ~70% of stocks)
   try:
    if _ops_z:
     _rg14 = f_(_ops_z.revenue_growth.one_year)
     if _rg14 and _rg14>.15:
      # PERFOPT 2026-05-05: reuse `window` (already 20 bars) — saves a per-symbol LEAN history call
      if window and len(window)>=20:
       _ma5 = sum(f_(b.close) for b in window[-5:])/5
       _ma20 = sum(f_(b.close) for b in window)/20
       if _ma5 < _ma20*0.92:
        score *= 1.25  # BAKE-23 R231: 1.22→1.25 (4-way stack with C1+C3+C4, +0.0148 joint)
   except: pass
   # BAKE-16 R206-R208: r_panic_combo_high_roe (qqq-dn 10d × hyg-dn 5d × roe>.30 → score×1.20) = +0.0121 verified 5/5
   try:
    if _ops_z:
     _roe16 = f_(_ops_z.roe.one_year)
     if _roe16 and _roe16>.20 and self._qa_scan and len(self._qa_scan)>=10 and self._ha_scan and len(self._ha_scan)>=5:  # BAKE-49 R562: ROE .35→.20, +0.0147 no-verify auto-bake (was BAKE-23: .30→.35)
      _qd16 = self._qd10
      _bd16 = self._bd5
      if _qd16<-.07 and _bd16<0:  # BAKE-21 R221-R223: qd<-.05→-.07 (4-way stack component)
       score *= 1.25  # BAKE-51 R564: 1.20→1.25, +0.0046
      # BAKE-17 R210-R211: tier-2 panic (qd<-.07 → extra ×1.25, stacks on BAKE-16) = +0.0114 verified 2/2
      # BAKE-31 R310-R311 dampened tier-2 mag 1.25→1.21 (min4_045 component, +0.0350 verified)
      if _qd16<-.07 and _bd16<0:
       score *= 1.21
   except: pass
   # BAKE-19 R213-R215: eps_super_growth_value (depsg>.40 × pe<15 → score×1.20) = +0.0106 verified 5/5
   try:
    if _ers_z and _vr_z:
     _depsg19 = f_(_ers_z.diluted_eps_growth.one_year)
     _pe19 = f_(_vr_z.pe_ratio)
     if _depsg19 is not None and _depsg19>.35 and _pe19 is not None and 0<_pe19<15:  # BAKE-37 R326-R327: depsg .40→.35, +0.0058 verified 3/3 deterministic
      score *= 1.20
   except: pass

   # BAKE-23 R230-R231: C1 (skip super-neg-rg) — joint with b14 1.22→1.25 + C3 + C4, +0.0148 (10/10 verified for C1+b14_125 alone at +0.0107)
   try:
    if _ops_z:
     _rg23 = f_(_ops_z.revenue_growth.one_year)
     if _rg23 is not None and _rg23<-.20 and decline>.10:
      continue  # C1: skip stocks with severe revenue collapse during decline
   except: pass
   # BAKE-22 R227-R228: E1+E2+E6 triple (+0.0105 joint, 10/10 verified). E2 = petgt_lo .04→.07 (above).
   try:
    if _inc_z and _cfs_z and _ops_z:
     _ni22 = f_(_inc_z.net_income.twelve_months)
     _fc22 = f_(_cfs_z.free_cash_flow.twelve_months)
     _de22 = f_(_ops_z.total_debt_equity_ratio.one_year)
     if _ni22 is not None and _ni22<0 and _fc22 is not None and _fc22<0 and _de22 is not None and _de22>2.0:
      continue  # E1: skip zombie/distress (neg-NI + neg-FCF + DE>2). BAKE-23 R231: de 3.0→2.0 (C3)
   except: pass
   try:
    if _ops_z:
     _rg22 = f_(_ops_z.revenue_growth.one_year)
     if _rg22 and _rg22>.20 and self._ha_scan and len(self._ha_scan)>=10:
      _bd22 = self._bd10
      if _bd22>.02:
       score *= 0.90  # BAKE-42 R446-R447: 0.85→0.90 (less aggressive E6 penalty), +0.0037 verified 5/5 deterministic
   except: pass
   # BAKE-24 R234: XB (bond-up 5d>.015 × gross_margin>.40 → score×0.85). Quality-gated variant of E6, +0.0162 verified 10/10.
   try:
    if _ops_z:
     _gm24 = f_(_ops_z.gross_margin.one_year)
     if _gm24 and _gm24>.40 and self._ha_scan and len(self._ha_scan)>=5:
      _bd24 = self._bd5
      if _bd24>.015:
       score *= 0.87  # BAKE-43 R450-R451: 0.85→0.87 (less aggressive XB, joint with grad .0194 + b13t2 1.40)
   except: pass
   # BAKE-25 R236-R237: triple stack Q1_QUAL + M1 + M3 (+0.0106 joint, 10/10 verified)
   try:
    if _ops_z and _vr_z:
     _gm25 = f_(_ops_z.gross_margin.one_year)
     _pe25 = f_(_vr_z.pe_ratio)
     # Q1_QUAL: qqq up 10d>.05 × gm>.40 → score×0.85 (mean-rev unlikely when qqq recovering)
     if _gm25 and _gm25>.40 and self._qa_scan and len(self._qa_scan)>=10:
      _qd25 = self._qd10
      if _qd25>.05:
       score *= 0.85
     # M1: gm>.50 × pe<10 × decline tiers (super-quality + super-value)
     if _gm25 and _gm25>.50 and _pe25 is not None and 0<_pe25<10:
      if decline>.15:
       score *= 1.13
      if decline>.30:
       score *= 1.20
     # M3: gm>.40 × pe<15 × decline tiers (quality + value, broader gates)
     if _gm25 and _gm25>.40 and _pe25 is not None and 0<_pe25<15:
      if decline>.20:
       score *= 1.13
      if decline>.35:
       score *= 1.20
   except: pass
   # BAKE-26 R241-R245: triple stack W1 + W2 + W3 (+0.0178 joint, 10/10 verified)
   try:
    if _ops_z:
     _qr26 = f_(_ops_z.quick_ratio.one_year)
     _rg26 = f_(_ops_z.revenue_growth.one_year)
     # W1: entry filter — skip stocks with low quick_ratio + low rev growth + already declining
     if _qr26 is not None and _qr26<.5 and _rg26 is not None and _rg26<.05 and decline>.05:
      continue
   except: pass
   try:
    if _ops_z:
     _rg26b = f_(_ops_z.revenue_growth.one_year)
     # W2: 120-day return < -.40 × growth>.30 → score×1.20 (deep multi-month decline + still growing fundamentals)
     if _rg26b and _rg26b>.30:
      _w120 = list(self.history[TradeBar](sym, 120, _RD))
      if _w120 and len(_w120)>=120:
       _r120 = (f_(_w120[-1].close)-f_(_w120[0].close))/f_(_w120[0].close)
       if _r120<-.30:    # BAKE-28 R255-R256: -.40→-.30 (W2_thr_30 + grad_019 joint, +0.0145)
        score *= 1.20
   except: pass
   # BAKE-27 R250-R252: per-stock vol filter (20d realized vol > .06 → conv×0.50). +0.0158 verified 10/10.
   # PERFOPT 2026-05-04: reuse `window` (now 20 bars) — saves one per-symbol history call.
   # PERFOPT 2026-05-05: reuse `_wcl` (window-close cache hoisted at entry-loop top).
   try:
    if _wcl:
     _r27 = [_wcl[i]/_wcl[i-1]-1 for i in range(1,20) if _wcl[i-1]>0]
     if _r27:
      _v27 = (sum(x*x for x in _r27)/len(_r27))**0.5
      if _v27>.06:
       conv *= 0.50  # BAKE-27: high-vol per-stock → reduce sizing
   except: pass
   # BAKE-29 R262-R263: BR (qqq up 20d>.10 × growth>.15 → score×0.85) + AB (bond 20d-vol<.002 × decline>.10 → score×1.10), +0.0141 verified
   try:
    if _ops_z:
     _rg29 = f_(_ops_z.revenue_growth.one_year)
     # BR: penalize growth names when QQQ in 20d strong recovery (mean-rev unlikely on momentum)
     if _rg29 and _rg29>.15 and self._qa_scan and len(self._qa_scan)>=20:
      _qd20br = self._qd20
      if _qd20br>.10 and decline<.10:    # BAKE-30 R264-R268: add decline<.10 + mag .85→.80, +0.0026 verified 5x
       score *= 0.80
   except: pass
   try:
    # AB: boost when bond 20d realized vol is unusually low and stock declining (panic-flight regime)
    if self._ha_scan and len(self._ha_scan)>=20:
     _bra = [f_(self._ha_scan[i].close)/f_(self._ha_scan[i-1].close)-1 for i in range(1,20) if f_(self._ha_scan[i-1].close)>0]
     if _bra:
      _bv = (sum(x*x for x in _bra)/len(_bra))**0.5
      if _bv<.002 and decline>.10:
       score *= 1.10
   except: pass
   # BAKE-44 R456-R457: change_in_account_payable > $1B × decline > .05 → score×1.06, +0.0052 verified 5/5 deterministic on BAKE-43
   try:
    if _cfs_z:
     _v44 = f_(_cfs_z.change_in_account_payable.twelve_months)
     if _v44 is not None and _v44 > 1e9 and decline > .05: score *= 1.06
   except: pass
   # BAKE-45 R461-R462: vr.first_year_estimated_eps_growth > 5 × decline > .10 → score×1.10, +0.0036 verified 3/3 deterministic on BAKE-44
   try:
    if _vr_z:
     _v45 = f_(_vr_z.first_year_estimated_eps_growth)
     if _v45 is not None and _v45 > 5 and decline > .10: score *= 1.10
   except: pass
   # BAKE-53 R569: QQQ-regime score boost — qd5<-.03 × decline>.03 → score×1.10, +0.0024
   try:
    if self._qa_scan and len(self._qa_scan) >= 5:
     _qd5 = self._qd5
     if _qd5 < -0.03 and decline > .03: score *= 1.25  # BAKE-54 R570: 1.10→1.25, +0.0264 (dd 10.4→10.3)
    # BAKE-56 R572: bond-down composite — qd5<-.03 × bd5<0 × decline>.05 → score×1.10, +0.0083
    if self._ha_scan and len(self._ha_scan) >= 5:
     _bd5x = self._bd5
     if _qd5 < -0.03 and _bd5x < 0 and decline > .05: score *= 1.20  # BAKE-57 R573: 1.10→1.20, +0.0030
   except: pass

   # BAKE-58 R583 part 2: Combo4 — qd5<-.03 × bd5<0 × decline>.07 × vol-spike → score×1.40, +0.0097 (joint with qr_hi=2.2)
   try:
    if (self._qa_scan and len(self._qa_scan) >= 5 and self._ha_scan and len(self._ha_scan) >= 5 and
        len(window) >= 10):
     _qd5c = self._qd5
     _bd5c = self._bd5
     # PERFOPT: reuse _wvol10 (10-bar volume cache from line 495) — same indices.
     _v_recent = sum(_wvol10[-3:])/3
     _v_avg = sum(_wvol10)/10
     if _qd5c < -0.04 and _bd5c < 0 and decline > .09 and _v_recent / max(.01, _v_avg) > 1.5:  # BAKE-62 R593: dec .07→.09
      score *= 2.20  # BAKE-62 R593: 1.85→2.20 (joint with dec .09), +0.0023
   except: pass

   # BAKE-63 R597: earning_ratios.book_value_per_share_growth.one_year > .10 × decline > .15 → score×1.15, +0.0099
   try:
    if _ers_z is not None and decline > .15:
     _v63 = f_(_ers_z.book_value_per_share_growth.one_year)
     if _v63 is not None and _v63 > 0.15: score *= 1.13  # BAKE-64 R600: thresh .10→.15, mag 1.15→1.13, +0.0024
   except: pass

   # BAKE-248 R1172 +0.00120 — wt_tilt × 0.7 on vs<60 × QQQ FLAT × d6_12 (the COHORT NOT
   # skipped by BAKE-247). Even within vs<60, score multipliers over-represent some names;
   # wt_tilt × 0.7 corrects the over-weighting. Sweet spot t70: +0.00120; t80: +0.00080;
   # t110+: NOOP-tied (no effect).
   try:
    _v = f_(_ac_z.value_score)
    _qaccel = self._qaccel
    if _v is not None and _v < 60 and _qaccel is not None and _qaccel > -0.01 and _qaccel < 0.01 and (decline > .06) and (decline < .12): wt_tilt *= 0.7
   except: pass
   # --- ENTRY WT_TILT INJECT POINT ---
   # Probes here can multiply wt_tilt to alter weight without affecting score-rank.
   # Default 1.0 → identical to 20260501 base. Hard cap WT_TILT_CAP=2.0 applied at selection.

   # --- ENTRY ALT_SCORE INJECT POINT ---
   # Probes here can set alt_score and alt_blend to introduce a secondary ranking dimension.
   # Default alt_blend=0 → alt_score ignored in selection. Probes that set alt_blend>0
   # cause selection to rank by score + alt_blend*alt_score.

   candidates.append((sym, score, conv, wt_tilt, alt_score, alt_blend))

  if not candidates: return

  # === Selection (by score, optionally blended with alt_score) + sizing (by conv*wt_tilt) ===
  WT_TILT_CAP = 2.0  # hard cap on per-symbol weight tilt
  def _rank_key(c):
   _, _score, _, _, _alt, _blend = c
   return _score + _blend * _alt
  ranked = sorted(candidates, key=_rank_key, reverse=True)
  total_value = f_(self.portfolio.total_portfolio_value) or 1
  existing_pct = sum(abs(f_(h.holdings_value))/total_value for h in self.portfolio.values()
                     if h.invested and h.symbol not in self._hedge_syms)
  remaining_budget = max(0, gross_target - existing_pct)
  if remaining_budget <= 0: return

  new_targets = []
  used = 0.0
  for sym, score, conv, wt_tilt, alt_score, alt_blend in ranked:
   if used >= remaining_budget: break
   _tilt = max(0.1, min(WT_TILT_CAP, wt_tilt))
   w = min(WT_CAP, conv * _tilt * WT_PER_CONV, remaining_budget - used)
   if w < MIN_WT: continue
   new_targets.append((sym, w))
   used += w

  if not new_targets: return
  self.pending_entries = [PortfolioTarget(sym, min(WT_CAP, w)) for sym, w in new_targets]

 @staticmethod
 def _fv(obj, attr, timeframe):
  if obj is None: return None
  try:
   field = getattr(obj, attr, None)
   if not field: return None
   val = getattr(field, timeframe, None) if timeframe else field
   if not val: return None
   return f_(val)
  except (AttributeError, TypeError, ValueError):
   return None

 def execute_pending_orders(self):
  for sym in list(self.pending_exits):
   self.liquidate(sym)
  if self.pending_entries:
   self.set_holdings(list(self.pending_entries))
  self.pending_exits = []
  self.pending_entries = []
