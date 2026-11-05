"""s001 — QQQ mean-reversion strategy (compressed base, 2026-05-08).

ARCHITECTURE
============

  imports & null-safe helpers ........ lines 1-21
  load-bearing constants ............. lines 22-34
  score-mutation helpers _t00..._t16 . lines 35-192
  initialize() ....................... lines 193-228
  on_data() — bar dispatch ........... lines 229-249
  _compute_regime() — QQQ/HYG/VXX .... lines 250-311
  _dynamic_gross() — gross cap ....... lines 312-328
  _scan_exits() — exit decisions ..... lines 329-420
  _scan_entries() — main entry loop .. lines 421-1660
    [ENTRY 1] preflight + MTF .......
    [ENTRY 2] regime aliases ........
    [ENTRY 3] fundamental cache .....
    [ENTRY 4] entry_signal init .....
    [ENTRY 5] score modifiers .......  (mtf / regime / fund / sector)
    [ENTRY 6] active bakes ..........  (5 bakes preserved verbatim)
    [ENTRY 7] ENTRY INJECT POINT ....  (gen-script probe injection)
    [ENTRY 8] ranking + sizing ......
  _fv static helper .................. lines 1661-1671
  execute_pending_orders() ........... lines 1672-1677

UNIFIED ENTRY/EXIT SCORING (added 2026-05-09)
=============================================
Probes from gen scripts target FOUR additive accumulators that flow
into final score before ranking:

  entry_signal       — generic / fundamental probes
  entry_score_mtf    — multi-timeframe component probes
  entry_score_regime — regime component probes
  entry_score_conv   — conv-derived component probes

Final combination at end of _scan_entries inner loop:

  score += entry_signal + entry_score_mtf + entry_score_regime + entry_score_conv

The legacy multiplicative `score *= X` rules + `_tNN` helpers + 5 active
bakes ALSO mutate `score` — they are LOAD-BEARING. Reordering them is
catastrophic (memory: feedback_s001_structural_changes_destructive).

EXIT side: `exit_signal` accumulator votes for forced exit when sum
crosses EXIT_THRESHOLD=1.0 (currently driven by legacy
`close > prev_high` contributing 1.0).

LOAD-BEARING INVARIANTS (do not change without verification)
============================================================
- QQQ-only universe, daily resolution, 5h pre-market trade timing
- STARTING_CASH=70000, GROSS_HIGH=1.0, WT_CAP=0.07, MIN_PRICE=32
- MTF_WEEKDAYS={0,2,4} (Mon/Wed/Fri) — but ENTRIES Mon-only (weekday()==0)
- WT_TILT_CAP=2.0, vol_climax threshold 2.5×, MIN_VOLUME=810000
- 5 active bakes (WH/FC/FG/JBC/J0) at lines ~1426-1442
- ENTRY/EXIT INJECT POINT comment markers parsed by gen scripts
"""

from AlgorithmImports import *
import math
import collections
f_=float
g_=getattr
def _ngt(v,t):
 return v is not None and v>t
def _nlt(v,t):
 return v is not None and v<t
def _nrg(v,lo,hi):
 return v is not None and lo<v<hi
# === HELPERS ===
def _g1(z, *p):
 if z is None: return None
 try:
  o=z
  for k in p: o=g_(o,k,None)
  return f_(o) if o is not None else None
 except: return None
# ===================================================================
# CONSTANTS — load-bearing; do not change without verifier
# ===================================================================
_RD=Resolution.DAILY
from datetime import timedelta
STARTING_CASH = 70000
GROSS_HIGH    = 1.0
GROSS_LOW     = .62
GRAD_RANGE    = .0130
MA_PERIOD     = 170
BOND_SYMBOL   = "TIP"
WT_CAP        = .07
WT_PER_CONV   = .080
MIN_WT        = .02
MIN_PRICE     = 32
MIN_VOLUME    = 810000
MTF_WEEKDAYS  = {0,2,4}
WARMUP_DAYS   = 280
# ===================================================================
# SCORE-MUTATION HELPERS — _t00 through _t16 (15 helpers, _t02 retired)
# All used by _scan_entries; signature varies by gate semantics.
# ===================================================================
def _t03(sc, al, tr, gt, qa, qL, qH, dc, dL, dH, mg, rg=True):
 if al is None or not rg: return sc
 if qa is None or not (qL < qa < qH): return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 try:
  obj = al
  for p in tr:
   obj = g_(obj, p, None)
   if obj is None: return sc
  v = f_(obj)
  for op, th in gt:
   if op == '>' and not (v > th): return sc
   if op == '<' and not (v < th): return sc
   if op == '==' and not (v == th): return sc
  sc *= mg
 except: pass
 return sc
def _t07(sc, aA, tA, oA, rA, aB, tB, oB, rB, dc, dL, dH, mg, rg=True):
 if aA is None or aB is None or not rg: return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 try:
  obj = aA
  for p in tA:
   obj = g_(obj, p, None)
   if obj is None: return sc
  va = f_(obj)
  obj = aB
  for p in tB:
   obj = g_(obj, p, None)
   if obj is None: return sc
  vb = f_(obj)
  ca = (oA == '>' and va > rA) or (oA == '<' and va < rA)
  cb = (oB == '>' and vb > rB) or (oB == '<' and vb < rB)
  if ca and cb:
   sc *= mg
 except: pass
 return sc
def _t08(sc, al, tr, op, th, dc, dL, dH, mg, rg=True):
 if al is None or not rg: return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 try:
  obj = al
  for p in tr:
   obj = g_(obj, p, None)
   if obj is None: return sc
  v = f_(obj)
  if (op == '>' and v > th) or (op == '<' and v < th) or (op == '==' and v == th):
   sc *= mg
 except: pass
 return sc
def _t15(al, tr, gt, dc, dL, dH, rg=True):
 if al is None or not rg: return False
 if dL is not None and not (dc > dL): return False
 if dH is not None and not (dc < dH): return False
 try:
  obj = al
  for p in tr:
   obj = g_(obj, p, None)
   if obj is None: return False
  v = f_(obj)
  for op, th in gt:
   if op == '>' and not (v > th): return False
   if op == '<' and not (v < th): return False
   if op == '==' and not (v == th): return False
  return True
 except: return False
def _t14(lv, al, tr, op, th, mg, gt=None, rg=True):
 try:
  if al is None: return lv
  obj = al
  for p in tr:
   obj = g_(obj, p, None)
   if obj is None: return lv
  v = f_(obj)
  if not rg: return lv
  if gt:
   for op2, thr2 in gt:
    if op2 == '>' and not (v > thr2): return lv
    if op2 == '<' and not (v < thr2): return lv
  elif not ((op == '>' and v > th) or (op == '<' and v < th)):
   return lv
  lv *= mg
 except: pass
 return lv
def _t10(sc, v, th, dc, dL, dH, mg, rg=True):
 if v is None or not rg or not (v > th): return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 return sc * mg
def _t11(sc, v, th, dc, dL, dH, mg, rg=True):
 if v is None or not rg or not (v < th): return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 return sc * mg
def _t12(sc, v, th, dc, dL, dH, mg, rg=True):
 if v is None or not rg or v != th: return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 return sc * mg
def _t04(sc, v, th, qa, qL, qH, dc, dL, dH, mg, rg=True):
 if v is None or not rg or not (v > th): return sc
 if qa is None or not (qL < qa < qH): return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 return sc * mg
def _t05(sc, v, th, qa, qL, qH, dc, dL, dH, mg, rg=True):
 if v is None or not rg or not (v < th): return sc
 if qa is None or not (qL < qa < qH): return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 return sc * mg
def _t01(sc, v, vL, vH, qa, qL, qH, dc, dL, dH, mg, rg=True):
 if v is None or not rg or not (vL < v < vH): return sc
 if qa is None or not (qL < qa < qH): return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 return sc * mg
def _t06(sc, va, oA, rA, vb, oB, rB, dc, dL, dH, mg, rg=True):
 if va is None or vb is None or not rg: return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 ca = (oA == '>' and va > rA) or (oA == '<' and va < rA) or (oA == '==' and va == rA)
 cb = (oB == '>' and vb > rB) or (oB == '<' and vb < rB) or (oB == '==' and vb == rB)
 if ca and cb: sc *= mg
 return sc
def _t00(sc, sV, sE, fV, vL, vH, qa, qL, qH, dc, dL, dH, mg, rg=True):
 if sV is None or sV != sE or fV is None or not rg: return sc
 if qa is None or not (qL < qa < qH): return sc
 if dL is not None and not (dc > dL): return sc
 if dH is not None and not (dc < dH): return sc
 if not (vL < fV < vH): return sc
 sc *= mg
 return sc
def _t09(lv, v, op, th, mg, rg=True):
 if v is None or not rg: return lv
 if not ((op == '>' and v > th) or (op == '<' and v < th) or (op == '==' and v == th)): return lv
 lv *= mg
 return lv
def _t16(va, oA, rA, vb, oB, rB, dc, dL, dH=None):
 if va is None or vb is None: return False
 if dL is not None and not (dc > dL): return False
 if dH is not None and not (dc < dH): return False
 if not ((oA == '>' and va > rA) or (oA == '<' and va < rA)): return False
 if not ((oB == '>' and vb > rB) or (oB == '<' and vb < rB)): return False
 return True
def _t13(v, gt, dc, dL, dH, rg=True):
 if v is None or not rg: return False
 if dL is not None and not (dc > dL): return False
 if dH is not None and not (dc < dH): return False
 for op, th in gt:
  if op == '>' and not (v > th): return False
  if op == '<' and not (v < th): return False
  if op == '==' and not (v == th): return False
 return True
# ===================================================================
# STRATEGY CLASS — MeanReversionAlgorithm
#   initialize()        — universe, schedule, tune dict
#   on_data()           — bar dispatch (Mon-only entries)
#   _compute_regime()   — QQQ/HYG/VXX state aliases for entry/exit gates
#   _dynamic_gross()    — gross exposure cap based on QQQ/TIP MA
#   _scan_exits()       — exit decisions (uses exit_signal accumulator)
#   _scan_entries()     — entry scoring + ranking (uses 4-component
#                          accumulators, ENTRY INJECT POINT for probes)
#   _fv()               — fundamental field value helper (exits only)
#   execute_pending_orders() — pre-market trade execution
# ===================================================================
class MeanReversionAlgorithm(QCAlgorithm):
 def initialize(self):
  self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
  self.set_start_date(2009, 8, 1)
  self.set_end_date(2026, 6, 1)
  self.set_cash(STARTING_CASH)
  self.set_warm_up(timedelta(days=WARMUP_DAYS), _RD)
  self.universe_settings.resolution = _RD
  self.add_equity("QQQ", _RD)
  self.add_equity(BOND_SYMBOL, _RD)
  self.add_equity("VXX", _RD)
  self.add_universe_selection(ETFConstituentsUniverseSelectionModel("QQQ"))
  self.set_benchmark("QQQ")
  self._initialized = False
  self._hedge_syms = set()
  self._close_cache = {}
  self.pending_entries = []
  self.pending_exits = []
  self.schedule.on(
   self.date_rules.every_day("QQQ"),
   self.time_rules.before_market_open("QQQ", 300),
   self.execute_pending_orders
  )
  self.tune = {
   'stop_default':    .40,
   'stop_lowmargin':  .09,
   'petgt_hi':        .12,
   'petgt_mid':       .11,
   'petgt_lo':        .0275,
   'nm_low_thresh':   .04,
   'qr_hi_thresh':    2.2,
   'nm_mid_thresh':   .05,
   'momentum_haircut_thresh': -.045,
   'momentum_haircut': 1.344,
  }
 # ─── on_data ──────────────────────────────────────────────────────
 # Bar dispatch. Always scans exits; entries are Mon-only (load-bearing
 # invariant — memory: feedback_s001_structural_changes_destructive).
 # ──────────────────────────────────────────────────────────────────
 def on_data(self, data):
  if not self._initialized:
   self._qqq_sym = self.securities["QQQ"].symbol
   self._bond_sym = self.securities[BOND_SYMBOL].symbol
   self._vxx_sym = self.securities["VXX"].symbol
   self._hedge_syms = {self._bond_sym, self._vxx_sym}
   self._initialized = True
  equities = [s for s in data.bars.keys() if s.security_type == SecurityType.EQUITY and s not in self._hedge_syms]
  _cc = self._close_cache
  for _s in equities:
   _b = data.bars.get(_s)
   if _b is not None:
    _q = _cc.get(_s)
    if _q is None:
     _q = collections.deque(maxlen=260)
     _cc[_s] = _q
    _q.append(f_(_b.close))
  self._compute_regime()
  self._scan_exits(data, equities)
  if self.time.weekday() == 0:
   self._scan_entries(data, equities)
 # ─── _compute_regime ──────────────────────────────────────────────
 # Builds self._reg_* attribute aliases used by entry/exit probes.
 # Available aliases (entry/exit scopes — use `self._reg_*` form):
 #   QQQ:  _reg_qqq_dn3/dn5/dn7, _reg_qqq_up3/up5
 #   HYG:  _reg_hyg_dn3/dn5/dn14, _reg_hyg_up3/up5
 #   VXX:  _reg_vxx_low/high/xhigh, _reg_vxx_falling3/7
 #   meta: _reg_double_panic, _reg_haccel
 # See feedback_s001_regime_aliases for which can be used as bare locals.
 # ──────────────────────────────────────────────────────────────────
 def _compute_regime(self):
  try: qa = list(self.history[TradeBar](self._qqq_sym, 60, _RD))
  except (AttributeError, KeyError, ValueError): qa = []
  try: ha = list(self.history[TradeBar](self._bond_sym, 30, _RD))
  except (AttributeError, KeyError, ValueError): ha = []
  try: va = list(self.history[TradeBar](self._vxx_sym, 30, _RD))
  except (AttributeError, KeyError, ValueError): va = []
  qc = [f_(b.close) for b in qa]
  hc = [f_(b.close) for b in ha]
  vc_list = [f_(b.close) for b in va]
  qlen, hlen, vlen = len(qc), len(hc), len(vc_list)
  def _r(closes, n):
   if len(closes) <= n or closes[-n] <= 0: return None
   return (closes[-1] - closes[-n]) / closes[-n]
  self._qs = qa
  self._hs = ha
  self._qa_closes = qc
  self._ha_closes = hc
  self._qd5 = _r(qc, 5)
  self._qd10 = _r(qc, 10)
  self._qd20 = _r(qc, 20)
  self._bd5 = _r(hc, 5)
  self._bd10 = _r(hc, 10)
  q1 = qc[-1] if qlen >= 1 else None
  q2 = qc[-2] if qlen >= 2 else None
  q3 = qc[-3] if qlen >= 3 else None
  q5 = qc[-5] if qlen >= 5 else None
  q7 = qc[-7] if qlen >= 7 else None
  h1 = hc[-1] if hlen >= 1 else None
  h2 = hc[-2] if hlen >= 2 else None
  h3 = hc[-3] if hlen >= 3 else None
  h5 = hc[-5] if hlen >= 5 else None
  h7 = hc[-7] if hlen >= 7 else None
  h14 = hc[-14] if hlen >= 14 else None
  if q3 is not None and q7 is not None and q3 > 0 and q7 > 0:
   self._qa = (q1 - q3) / q3 - (q1 - q7) / q7
  else:
   self._qa = None
  if h3 is not None and h7 is not None and h3 > 0 and h7 > 0:
   self._reg_haccel = (h1 - h3) / h3 - (h1 - h7) / h7
  else:
   self._reg_haccel = None
  self._reg_qqq_dn3 = bool(q3 is not None and q1<q2<q3)
  self._reg_qqq_up3 = bool(q3 is not None and q1>q2>q3)
  self._reg_hyg_dn3 = bool(h3 is not None and h1<h2<h3)
  self._reg_hyg_up3 = bool(h3 is not None and h1>h2>h3)
  self._reg_qqq_dn5 = bool(q5 is not None and q1<q5)
  self._reg_qqq_dn7 = bool(q7 is not None and q1<q7)
  self._reg_hyg_dn5 = bool(h5 is not None and h1<h5)
  self._reg_hyg_dn14 = bool(h14 is not None and h1<h14)
  self._reg_hyg_up5 = bool(h5 is not None and h1>h5)
  self._reg_double_panic = bool(q3 is not None and q1<q3) and self._reg_hyg_dn5
  if vlen:
   _vc_now = vc_list[-1]
   self._reg_vxx_high = _vc_now > 25
   self._reg_vxx_xhigh = _vc_now > 35
   self._reg_vxx_low = _vc_now < 15
   self._reg_vxx_rising3 = bool(vlen>=3 and vc_list[-1]>vc_list[-2]>vc_list[-3])
   self._reg_vxx_falling3 = bool(vlen>=3 and vc_list[-1]<vc_list[-2]<vc_list[-3])
   self._reg_vxx_spike5 = bool(vlen>=5 and vc_list[-5]>0 and vc_list[-1] > 1.20*vc_list[-5])
  else:
   self._reg_vxx_high = self._reg_vxx_xhigh = self._reg_vxx_low = False
   self._reg_vxx_rising3 = self._reg_vxx_falling3 = self._reg_vxx_spike5 = False

 # ─── _dynamic_gross ───────────────────────────────────────────────
 # Daily gross-exposure cap derived from QQQ/TIP MA + momentum haircut.
 # Returns value in [GROSS_LOW, GROSS_HIGH]. Used by _scan_exits to
 # constrain remaining_budget before sizing entries.
 # ──────────────────────────────────────────────────────────────────
 def _dynamic_gross(self) -> float:
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
 # ===================================================================
 # _scan_exits — exit decisions for currently-held positions
 # ===================================================================
 # Per-symbol flow:
 #   1. Pull fundamentals (_ops_z, _vr_z, _bs_z, _inc_z, etc.)
 #   2. Compute stop / petgt thresholds based on regime + fundamentals
 #   3. Init `exit_signal = 0.0` accumulator
 #   4. EXIT INJECT POINT (gen-script probes contribute to exit_signal)
 #   5. Legacy rule: close > prev_high contributes 1.0 to exit_signal
 #   6. If exit_signal >= EXIT_THRESHOLD (1.0): force exit
 #   7. Stop-loss / profit-target shortcuts also force exit (direct path)
 # ──────────────────────────────────────────────────────────────────
 def _scan_exits(self, data, equities):
  for sym in equities:
   pos = self.portfolio[sym]
   if not pos.invested: continue
   pnl = f_(pos.unrealized_profit_percent)
   stop = self.tune['stop_default']
   petgt = self.tune['petgt_mid']
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = g_(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = g_(_fz, 'valuation_ratios', None) if _fz else None
    _ers_z = g_(_fz, 'earning_ratios', None) if _fz else None
    _ac_z  = g_(_fz, 'asset_classification', None) if _fz else None
    _er_z  = g_(_fz, 'earning_reports', None) if _fz else None
    _sr_z  = g_(_fz, 'security_reference', None) if _fz else None
    _fs_z  = g_(_fz, 'financial_statements', None) if _fz else None
    _bs_z  = g_(_fs_z, 'balance_sheet', None) if _fs_z else None
    _inc_z = g_(_fs_z, 'income_statement', None) if _fs_z else None
    _cfs_z = g_(_fs_z, 'cash_flow_statement', None) if _fs_z else None
    if _ops_z:
     nm = self._fv(_ops_z, 'net_margin', 'value')
     qr = self._fv(_ops_z, 'quick_ratio', 'value')
     if nm is not None and nm < self.tune['nm_low_thresh']: stop = self.tune['stop_lowmargin']
     if qr is not None and qr > self.tune['qr_hi_thresh']: petgt = self.tune['petgt_hi']
     elif nm is not None and nm > self.tune['nm_mid_thresh']: petgt = self.tune['petgt_mid']
     else: petgt = self.tune['petgt_lo']
   except: _fz=_ops_z=_vr_z=_ers_z=_ac_z=_er_z=_sr_z=_fs_z=_bs_z=_inc_z=_cfs_z=None
   _vsc=_g1(_ac_z, 'value_score')
   _fcfg1yc=_g1(_ops_z, 'fcf_growth', 'one_year')
   _wipc=_g1(_bs_z, 'work_in_process', 'twelve_months')
   _woc=_g1(_inc_z, 'write_off', 'twelve_months')
   _evta3yc=_g1(_vr_z, 'ev_to_total_assets_3_year_growth')
   _cashc=_g1(_bs_z, 'cash', 'twelve_months')
   _roic1yc=_g1(_ops_z, 'roic', 'one_year')
   _fcfsr1yc=_g1(_ops_z, 'fcf_sales_ratio', 'one_year')
   _nig1yc=_g1(_ops_z, 'net_income_growth', 'one_year')
   _capec=_g1(_vr_z, 'cape_ratio')
   _hi_cape = _ngt(_capec,50)
   _lo_cape = _nrg(_capec,0,22)
   stop = _t09(stop, _wipc, '<', 1e9, 0.9)
   stop = _t09(stop, _woc, '<', 1e9, .82)
   petgt = _t09(petgt, _evta3yc, '<', 15, 1.05)
   stop = _t09(stop, _cashc, '<', 1e9, 0.9)
   try:
    _va = _woc
    _vb = _nig1yc
    if _va is not None and _vb is not None and _va > 1e7 and _vb < 0.0: stop *= 0.78
   except: pass
   try:
    _va = _fcfg1yc
    _vb = _fcfsr1yc
    if _va is not None and _vb is not None and _va > 0.20 and _vb < 0.05: stop *= 0.85
   except: pass
   stop = _t09(stop, _fcfg1yc, '<', 0.0, 0.85)
   petgt = _t09(petgt, _roic1yc, '>', 0.15, 1.10)
   petgt = _t09(petgt, _fcfsr1yc, '>', 0.20, 1.56)
   petgt = _t09(petgt, _fcfsr1yc, '>', 0.25, 1.25)
   petgt = _t09(petgt, _vsc, '<', 15, 0.85)
   stop = _t09(stop, _vsc, '<', 15, 0.95)
   if _vsc is not None:
    if _vsc < 5: stop *= 0.85
    elif 5<_vsc<10: stop *= 1.05
    elif 10<_vsc<15: stop *= 1.05
    elif 15<_vsc<25: stop *= 1.50
    elif 25<_vsc<30: stop *= 1.05
    elif 30<_vsc<50: petgt *= 1.50; stop *= 1.12
   try: _p = f_(self.securities[sym].close)
   except: _p=None
   if _p > 150: stop *= 1.50
   if _p < 50: petgt *= 1.10
   try:
    if self._reg_hyg_up5 and pnl is not None and pnl > 0.05: petgt *= 1.20
    if self._reg_qqq_up3 and self._reg_hyg_up5 and pnl is not None and pnl > 0.005: petgt *= 1.30
    if self._reg_qqq_up3 and self._reg_hyg_dn14 and pnl is not None and pnl < -0.15: stop *= 0.50
   except: pass
   # ================================================================
   # EXIT-SIGNAL SCORING — DIMINISHED TO 0.5 PER USER 2026-05-09 v9.
   # ================================================================
   # User: "diminish close > prev_high < exit threshold and dont revert".
   # close>prev_high vote = 0.5 < EXIT_THRESHOLD = 0.6 (legacy no longer
   # fires alone). Strategy now relies on:
   #   - stop/petgt direct path (always)
   #   - exit_signal probes that ADD to close>prev_high vote pushing past
   #     threshold (legacy 0.5 + probe 0.1+ = 0.6+ fires)
   # Memory R1715: at 0.3 vote NOOP catastrophe (0.57). At 0.5 we're just
   # below threshold; probes can rescue specific cohorts.
   exit_signal = 0.0
   # User 2026-05-09: max bake mag = 0.05 (more space for new fund gates).
   # Legacy 0.49 + 0.05 = 0.54 < threshold 0.6 — single bake DOESN'T fire alone.
   # Need 3+ bakes firing on a stock to push exit_signal to 0.6+.
   # BAKE-LOWCR-R1723: current_ratio<1.0
   if pnl is not None and _nlt(_g1(_ops_z, 'current_ratio', 'one_year'),1.0): exit_signal += 0.05
   # BAKE-HIPB3-R1726: pb_ratio>3
   if pnl is not None and _ngt(_vr_z.pb_ratio,3): exit_signal += 0.05
   # BAKE-TOTEXP-R1727: total_expenses>1e7 (capped 0.15 → 0.05 per user)
   if pnl is not None and _ngt(_g1(_inc_z, 'total_expenses', 'twelve_months'),10000000): exit_signal += 0.05
   # BAKE BAKE-XF_TOTASSETS-R1731 (+0.61489)
   if pnl is not None and _ngt(_g1(_bs_z, 'total_assets', 'twelve_months'),1000000000): exit_signal += 0.05
   # BAKE BAKE-XF_TOTREV-R1731 (+0.83391)
   if pnl is not None and _ngt(_g1(_inc_z, 'total_revenue', 'twelve_months'),10000000): exit_signal += 0.04
   # BAKE BAKE-XS_HIPS_5-R1733 (+0.15259)
   if pnl is not None and _ngt(_vr_z.ps_ratio,5): exit_signal += 0.04
   # BAKE BAKE-SS_HD14-R1738 (+0.00726)
   try:
    if self._reg_hyg_dn14 and pnl is not None and pnl < -0.3: stop *= 1.05
   except: pass
   # --- EXIT INJECT POINT ---
   if pnl < -stop or pnl > petgt:
    self.pending_exits.append(sym); continue
   try:
    bars = list(self.history[TradeBar](sym, 2, _RD))
    if len(bars) >= 2 and bars[-1].close > bars[-2].high:
     exit_signal += 0.6  # SET to 0.6 per user 'recover exit_signal 0.6' (= EXIT_THRESHOLD)
   except: pass
   EXIT_THRESHOLD = 0.6
   if exit_signal >= EXIT_THRESHOLD:
    self.pending_exits.append(sym)
 # ===================================================================
 # _scan_entries — main entry scoring + ranking + sizing
 # ===================================================================
 # Outline:
 #   [1] Regime aliases (local rebinds for performance)
 #   [2] Per-symbol loop:
 #       a. Preflight (price/volume/MTF/decline/vol_climax)
 #       b. Fundamental cache (_ops_z/_vr_z/_bs_z/_inc_z/_cfs_z/...)
 #       c. base score = log2(log2(volume))
 #       d. Init four entry-component accumulators (= 0.0)
 #       e. Score modifiers: ~291 ops mixing _tNN + score *= + score +=
 #          (LOAD-BEARING ORDER — never reorder)
 #       f. Active bakes (5): WH/FC/FG/JBC/J0 — additive lifts
 #       g. ENTRY INJECT POINT (gen-script probes contribute here)
 #       h. score += entry_signal + entry_score_mtf + regime + conv
 #       i. Append (sym, score, conv, wt_tilt) to candidates
 #   [3] weight_score per candidate = clamp(conv * wt_tilt * WT_PER_CONV, WT_CAP)
 #   [4] Rank by score DESC; size by weight_score; budget by gross_target
 # ──────────────────────────────────────────────────────────────────
 def _scan_entries(self, data, equities):
  self.pending_entries = []
  candidates = []
  gross_target = self._dynamic_gross()
  _qao = self._qa
  _hyg_dn3 = self._reg_hyg_dn3
  _haccel = self._reg_haccel
  _hyg_dn5 = self._reg_hyg_dn5
  _hyg_dn14 = self._reg_hyg_dn14
  _hyg_up3 = self._reg_hyg_up3
  _hyg_up5 = self._reg_hyg_up5
  _qqq_dn3 = self._reg_qqq_dn3
  _qqq_dn5 = self._reg_qqq_dn5
  _qqq_dn7 = self._reg_qqq_dn7
  _qqq_up3 = self._reg_qqq_up3
  _qs = self._qs
  _hs = self._hs
  _qd5 = self._qd5
  _qd10 = self._qd10
  _qd20 = self._qd20
  _bd5 = self._bd5
  _bd10 = self._bd10
  _qpos = _nrg(_qao,0.01,0.05)
  _qzero = _nrg(_qao,-0.01,0.01)
  _qsneg = _nlt(_qao,-0.05)
  _qneg = _nrg(_qao,-0.05,-0.01)
  _q_dn = _nlt(_qao,-0.01)
  _r60_bakes_active = (
   (_qpos and _hyg_up5) or
   (_qzero and _hyg_dn14) or
   (_qsneg and _hyg_dn14)
  )
  for sym in equities:
   if self.portfolio[sym].invested and sym not in self.pending_exits: continue
   if sym not in data.bars: continue
   bar = data.bars[sym]
   _bc = f_(bar.close); _bv = f_(bar.volume)
   if _bc <= MIN_PRICE or _bv < MIN_VOLUME: continue
   try:
    window = list(self.history[TradeBar](sym, 20, _RD))
    _w10 = window[-10:] if len(window) >= 10 else window
    mtf = [b for b in _w10 if b.time.weekday() in MTF_WEEKDAYS]
    if len(mtf) < 3: continue
    if not (mtf[-1].close < mtf[-2].close): continue
   except (AttributeError, KeyError, IndexError, ValueError, TypeError): continue
   _m3 = f_(mtf[-3].close)
   decline = (_m3 - f_(mtf[-1].close))/_m3 if _m3 > 0 else 0
   _wvol10 = [f_(b.volume) for b in _w10]
   _av = sum(_wvol10)/max(len(_w10), 1)
   max_dv = max((_wvol10[i] for i in range(max(1, len(_w10)-5), len(_w10))
                 if _w10[i].close < _w10[i-1].close), default=0)
   vol_climax = _av > 0 and max_dv > 2.5 * _av
   if vol_climax and decline < .05: continue
   _m5 = f_(mtf[-5].close) if len(mtf) >= 5 else 0
   _m7 = f_(mtf[-7].close) if len(mtf) >= 7 else 0
   _r3 = (_bc - _m3) / _m3 if _m3 > 0 else None
   _r5 = (_bc - _m5) / _m5 if _m5 > 0 else None
   _r7 = (_bc - _m7) / _m7 if _m7 > 0 else None
   _r3_md = _r3 is not None and -0.10 < _r3 < 0
   _r5_up = _r5 is not None and _r5 > 0
   _hl_closes = self._close_cache.get(sym)
   _hl_len = len(_hl_closes) if _hl_closes is not None else 0
   if _r60_bakes_active and _hl_len >= 21:
    _ref20 = _hl_closes[-21]
    _r20 = (_bc - _ref20) / _ref20 if _ref20 > 0 else None
    if _hl_len >= 61:
     _ref60 = _hl_closes[-61]
     _r60 = (_bc - _ref60) / _ref60 if _ref60 > 0 else None
    else: _r60 = None
    if _hl_len >= 253:
     _ref252 = _hl_closes[-253]
     _r252 = (_bc - _ref252) / _ref252 if _ref252 > 0 else None
    else: _r252 = None
   else:
    _r20 = _r60 = _r252 = None
   _r20_dn = _nlt(_r20,-0.10)
   _r60_dn = _nlt(_r60,-0.20)
   _r252_up = _ngt(_r252,0.30)
   _r252_dn = _nlt(_r252,-0.20)
   if window and len(window) >= 20:
    _wcl = [f_(b.close) for b in window]
    _vol20_sumsq = 0.0
    _vol20_n = 0
    for i in range(1, 20):
     _p = _wcl[i-1]
     if _p > 0:
      _r = _wcl[i] / _p - 1
      _vol20_sumsq += _r * _r
      _vol20_n += 1
    _vol20 = (_vol20_sumsq / _vol20_n) ** 0.5 if _vol20_n > 0 else None
   else:
    _wcl = None
    _vol20 = None
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = g_(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = g_(_fz, 'valuation_ratios', None) if _fz else None
    _ers_z = g_(_fz, 'earning_ratios', None) if _fz else None
    _ac_z  = g_(_fz, 'asset_classification', None) if _fz else None
    _er_z  = g_(_fz, 'earning_reports', None) if _fz else None
    _sr_z  = g_(_fz, 'security_reference', None) if _fz else None
    _fs_z  = g_(_fz, 'financial_statements', None) if _fz else None
    _bs_z  = g_(_fs_z, 'balance_sheet', None) if _fs_z else None
    _inc_z = g_(_fs_z, 'income_statement', None) if _fs_z else None
    _cfs_z = g_(_fs_z, 'cash_flow_statement', None) if _fs_z else None
   except: _fz=_ops_z=_vr_z=_ers_z=_ac_z=_er_z=_sr_z=_fs_z=_bs_z=_inc_z=_cfs_z=None
   _qa = _qao
   _d2_4 = decline > .02 and decline < .04
   _d2_5 = decline > .02 and decline < .05
   _d2_6 = decline > .02 and decline < .06
   _d4_8 = decline > .04 and decline < .08
   _d4_12 = decline > .04 and decline < .12
   _d6_12 = decline > .06 and decline < .12
   _d8_12 = decline > .08 and decline < .12
   _d5_10 = decline > .05 and decline < .10
   _d12_20 = decline > .12 and decline < .20
   _d1_3 = decline > .01 and decline < .03
   _d4_10 = decline > .04 and decline < .10
   _pegr=_g1(_vr_z, 'peg_ratio')
   _fcfy_c=_g1(_vr_z, 'fcf_yield')
   _ey_c=_g1(_vr_z, 'earning_yield')
   _pegpb_c=_g1(_vr_z, 'peg_payback')
   _ndepsg3m_c=_g1(_ers_z, 'normalized_diluted_eps_growth', 'three_months')
   _pti3m_c=_g1(_inc_z, 'pretax_income', 'three_months')
   _fcta3m_c=_g1(_bs_z, 'foreign_currency_translation_adjustments', 'three_months')
   _roe1y_c=_g1(_ops_z, 'roe', 'one_year')
   _intexp12m_c=_g1(_inc_z, 'interest_expense', 'twelve_months')
   _gp3m_c=_g1(_inc_z, 'gross_profit', 'three_months')
   _ps12m_c=_g1(_bs_z, 'preferred_stock', 'twelve_months')
   _secc=_g1(_ac_z, 'morningstar_sector_code')
   _gw=_g1(_bs_z, 'goodwill', 'twelve_months')
   _tac=_g1(_bs_z, 'total_assets', 'twelve_months')
   _vsc=_g1(_ac_z, 'value_score')
   _rg1yc=_g1(_ops_z, 'revenue_growth', 'one_year')
   _gm1yc=_g1(_ops_z, 'gross_margin', 'one_year')
   _ic1yc=_g1(_ops_z, 'interest_coverage', 'one_year')
   _pec=_g1(_vr_z, 'pe_ratio')
   _roic3mc=_g1(_ops_z, 'roic', 'three_months')
   _tr1yc=_g1(_ops_z, 'tax_rate', 'one_year')
   _om1yc=_g1(_ops_z, 'operation_margin', 'one_year')
   _om3mc=_g1(_ops_z, 'operation_margin', 'three_months')
   _cfog1yc=_g1(_ops_z, 'cfo_growth', 'one_year')
   _cfyc=_g1(_vr_z, 'cf_yield')
   _fcfg1yc=_g1(_ops_z, 'fcf_growth', 'one_year')
   _rt1yc=_g1(_ops_z, 'receivable_turnover', 'one_year')
   _crc=_g1(_vr_z, 'cash_return')
   _capec=_g1(_vr_z, 'cape_ratio')
   _cashc=_g1(_bs_z, 'cash', 'twelve_months')
   _fpec=_g1(_vr_z, 'forward_pe_ratio')
   _lowgwr = (_gw is not None and _ngt(_tac,0) and (_gw/_tac) < 0.20)
   _icp = (_ngt(_ic1yc,10) and _nrg(_pec,0,15) and _d4_8)
   _fcp = (_ngt(_fcfg1yc,0.10) and _nrg(_pec,0,12) and _d4_8)
   _hi_vol = _ngt(_vol20,0.04)
   _lo_vol = _nlt(_vol20,0.015)
   _hi_cape = _ngt(_capec,50)
   _lo_cape = _nrg(_capec,0,22)
   score = 1.0 * math.log(math.log(_bv))  # VOL_SCORE_WEIGHT=1.0 default; tunable via grid search
   # ================================================================
   # ENTRY-SIGNAL ACCUMULATORS (probe targets, summed into score below)
   # ================================================================
   # FIVE additive channels that gen-script probes target via
   # lever='entry_signal' / 'entry_score_mtf' / 'entry_score_regime' /
   # 'entry_score_conv' / 'entry_score_quality'. Each starts at 0.0
   # (preserves prior behavior). Final summation after ENTRY INJECT.
   entry_signal         = 0.0  # generic / fundamental fund-gate probes
   entry_score_mtf      = 0.0  # multi-timeframe (_r3_md/_r5_up/_r60_dn/_r252_*)
   entry_score_regime   = 0.0  # regime (self._reg_qqq/_hyg/_vxx — use self. form)
   entry_score_conv     = 0.0  # conv-derived (decline + sizing signal)
   entry_score_quality  = 0.0  # added 2026-05-09 — fundamental quality
                               # (margin/ROE/debt-ratio compound signals)
   entry_score_gate     = 0.0  # added 2026-05-10 (P4) — MULTIPLICATIVE.
                               # Probes contribute += small_value (e.g. 0.01).
                               # Final: score *= (1 + entry_score_gate).
                               # 0.0 = no-op, safe default. Symmetric for both
                               # negative (rank-demote) and positive (rank-boost).
   if decline < .05:
    conv = max(1.0, 1.0 + (decline - .02) * (1.5/.10))
   else:
    conv = 1.0 + .375 + (decline - .05) * (3.5/.10)
   conv = min(5.0, conv)
   if vol_climax: conv *= .70
   wt_tilt = 1.0
   # BAKE BAKE-WD2G_QZERO_S102_HA_HD14_2F_QZ_TOFC-R2200 (+0.00755)
   try:
    if _qzero and _secc == 102 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_inc_z.net_income.twelve_months,1e6) and _ngt(_inc_z.total_other_finance_cost.twelve_months,1e7): wt_tilt *= 0.3
   except: pass
   # BAKE BAKE-WD2G_QPOS_S205_HA_HD14_2F_RT_S205-R2197 (+0.00564)
   try:
    if _qpos and _secc == 205 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_cfs_z.operating_cash_flow.twelve_months,1e6) and _ngt(_ops_z.receivable_turnover.one_year,5): wt_tilt *= 0.75
   except: pass
   # BAKE BAKE-WD2G_QZERO_S102_HA_HD14_2F_QZ_QR05-R2170 (+0.00202)
   try:
    if _qzero and _secc == 102 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_cfs_z.operating_cash_flow.twelve_months,1e6) and _nlt(_ops_z.quick_ratio.one_year,0.5): wt_tilt *= 0.45
   except: pass
   # BAKE BAKE-WD2G_QZERO_S206_HA_HD14_2F_QZ_PE50-R2169 (+0.00223)
   try:
    if _qzero and _secc == 206 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_inc_z.net_income.twelve_months,1e6) and _ngt(_vr_z.pe_ratio,50): wt_tilt *= 0.75
   except: pass
   # BAKE BAKE-WD2G_QPOS_S102_HA_HD14_2F_PE50_NRW-R2167 (+0.00128)
   try:
    if _qpos and _secc == 102 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_inc_z.net_income.twelve_months,1e6) and _ngt(_vr_z.pe_ratio,50): wt_tilt *= 0.55
   except: pass
   # BAKE BAKE-WD2G_QPOS_S308_HA_HD14_2F_PS10_FCF-R2165 (+0.00138)
   try:
    if _qpos and _secc == 308 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_cfs_z.free_cash_flow.twelve_months,1e6) and _ngt(_vr_z.ps_ratio,10): wt_tilt *= 0.55
   except: pass
   # BAKE BAKE-WD3G_QZERO_S308_HA_HD14_DC003_QZ_ROA_DEM-R2122 (+0.00362)
   if _qzero and decline > 0.03 and _secc == 308 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_g1(_ops_z, 'roa', 'one_year'),0.20): wt_tilt *= 0.45
   # BAKE BAKE-WB2G_QPOS_S102_HA_HD5_2F_RT_CSE_HD5-R2116 (+0.00372)
   if _qpos and _secc == 102 and self._reg_haccel and self._reg_hyg_dn5 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_g1(_bs_z, 'common_stock_equity', 'twelve_months'),1e10): wt_tilt *= 1.5
   # BAKE BAKE-WD2G_QPOS_S206_HA_HD14_2F_EBITDA_CASH-R2113 (+0.00128)
   if _qpos and _secc == 206 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_inc_z, 'ebitda', 'twelve_months'),1e6) and _nlt(_g1(_ops_z, 'cash_ratio', 'one_year'),0.3): wt_tilt *= 0.45
   # BAKE BAKE-WD2G_QPOS_S311_HA_Q3_2F_RT_CASH_HAQ3-R2109 (+0.00117)
   if _qpos and _secc == 311 and self._reg_haccel and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _nlt(_g1(_ops_z, 'cash_ratio', 'one_year'),0.3): wt_tilt *= 0.85
   # BAKE BAKE-WD2G_QPOS_S308_HD5_Q3_2F_PS_FCF_VRG_REG-R2106 (+0.00074)
   if _qpos and _secc == 308 and self._reg_hyg_dn5 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_vr_z.ps_ratio,5): wt_tilt *= 0.75
   # BAKE BAKE-WD2G_QPOS_S102_HA_HD14_2F_QPOS_PS_FCF-R2103 (+0.00862)
   if _qpos and _secc == 102 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_vr_z.ps_ratio,5): wt_tilt *= 0.45
   # BAKE BAKE-WD2G_QPOS_S311_HD3_Q3_2F_QPOS_PS_NI-R2101 (+0.00489)
   if _qpos and _secc == 311 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_vr_z.ps_ratio,5): wt_tilt *= 0.45
   # BAKE BAKE-WD2G_QZERO_S206_HD3_Q3_2F_PS_NI_DEEP-R2096 (+0.00096)
   if _qzero and _secc == 206 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_vr_z.ps_ratio,5): wt_tilt *= 0.7
   # BAKE BAKE-WD2G_QZERO_S102_HA_HD14_2F_PS_NI_NRW_S102-R2095 (+0.00117)
   if _qzero and _secc == 102 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_vr_z.ps_ratio,5): wt_tilt *= 0.85
   # BAKE BAKE-WD2G_QZERO_S311_HD14_Q3_2F_QR_OCF-R2091 (+0.00074 quick_ratio<0.5 × OCF on S311)
   if _qzero and _secc == 311 and self._reg_hyg_dn14 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'operating_cash_flow', 'twelve_months'),1e6) and _nlt(_g1(_ops_z, 'quick_ratio', 'one_year'),0.5): wt_tilt *= 0.45
   # BAKE BAKE-WD2G_QZERO_S206_HD3_Q3_2F_PB_OCF-R2089 (+0.00054 clean monotonic 5-mag)
   if _qzero and _secc == 206 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'operating_cash_flow', 'twelve_months'),1e6) and _ngt(_vr_z.pb_ratio,3): wt_tilt *= 0.45
   # BAKE BAKE-WD2G_QZERO_S311_HA_HD14_2F_QR-R2082 (+0.00096 quick_ratio<0.5 wt_tilt)
   if _qzero and _secc == 311 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _nlt(_g1(_ops_z, 'quick_ratio', 'one_year'),0.5): wt_tilt *= 0.75
   # BAKE BAKE-WD2G_QZERO_S311_HD3_Q3_2F_NI_DPSG-R2076 (+0.00064 _ers_z dps_growth)
   if _qzero and _secc == 311 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_g1(_ers_z, 'dps_growth', 'one_year'),0.05): wt_tilt *= 0.55
   # BAKE BAKE-WB_QPOS_S308_HA_HD5_2F_D-R2060 (+0.00085)
   if _qpos and _secc == 308 and self._reg_haccel and self._reg_hyg_dn5 and _ngt(_g1(_cfs_z, 'operating_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): wt_tilt *= 1.2
   # BAKE BAKE-WB_QPOS_S308_DP_HA_2F-R2059 (+0.00096)
   if _qpos and _secc == 308 and self._reg_double_panic and self._reg_haccel and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): wt_tilt *= 1.1
   # BAKE BAKE-WD_QZERO_S309_HD14_Q3_2F_D-R2059 (+0.00298)
   if _qzero and _secc == 309 and self._reg_hyg_dn14 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'operating_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): wt_tilt *= 0.45
   # BAKE BAKE-WD_QZERO_S205_HD3_Q3_2F_D-R2056 (+0.00107 wt_tilt × PAIR_D 2F)
   if _qzero and _secc == 205 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'operating_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): wt_tilt *= 0.45
   # BAKE BAKE-WB_QPOS_S206_HA_HD5_2F-R2055 (+0.00075 wt_tilt BOOST compound 2F)
   if _qpos and _secc == 206 and self._reg_haccel and self._reg_hyg_dn5 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): wt_tilt *= 1.2
   # BAKE BAKE-WD_QZERO_S309_HD14_VF_2F-R2053 (+0.00159 wt_tilt × compound 2F)
   if _qzero and _secc == 309 and self._reg_hyg_dn14 and self._reg_vxx_falling3 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): wt_tilt *= 0.55
   # BAKE BAKE-WD_QZERO_S308_DP_HD3_2F-R2051 (+0.00117 wt_tilt × compound 2F)
   if _qzero and _secc == 308 and self._reg_double_panic and self._reg_hyg_dn3 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): wt_tilt *= 0.55
   # BAKE BAKE-G_WZ_S310_DP_1-R1943 (+0.00074)
   if _qzero and _secc == 310 and self._reg_double_panic and _ngt(_g1(_bs_z, 'capital_lease_obligations', 'twelve_months'),1e6): wt_tilt *= 0.7
   # BAKE BAKE-A_S311_HD3_2-R1940 (+0.00138)
   if _qpos and _secc == 311 and self._reg_hyg_dn3 and _ngt(_g1(_cfs_z, 'sale_of_ppe', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-F_S311_HD5_0-R1939 (+0.00372)
   if _qpos and _secc == 311 and self._reg_hyg_dn5 and _ngt(_g1(_cfs_z, 'net_investment_purchase_and_sale', 'twelve_months'),1e6): wt_tilt *= 0.8
   # BAKE BAKE-B_BST_S310_Q3_0-R1935 (+0.00061)
   if _qpos and _secc == 310 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'gain_loss_on_sale_of_ppe', 'twelve_months'),1e6): wt_tilt *= 1.2
   # BAKE BAKE-O_WT_BST_VFH14_S310_0-R1934 (+0.00181)
   if _qpos and _secc == 310 and self._reg_vxx_falling3 and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'sale_of_ppe', 'twelve_months'),1e6): wt_tilt *= 1.5
   # BAKE BAKE-A_BST_WZ_S310_HA_0-R1932 (+0.00072)
   if _qzero and _secc == 310 and self._reg_haccel and _ngt(_g1(_cfs_z, 'sale_of_investment', 'twelve_months'),1e6): wt_tilt *= 1.3
   # BAKE BAKE-B_BST_S311_VF_0-R1931 (+0.00117)
   if _qpos and _secc == 311 and self._reg_vxx_falling3 and _ngt(_g1(_cfs_z, 'gain_loss_on_sale_of_ppe', 'twelve_months'),1e6): wt_tilt *= 1.3
   # BAKE BAKE-D_BST_WZ_S311_HD14_2-R1930 (+0.00298)
   if _qzero and _secc == 311 and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'earnings_losses_from_equity_investments', 'twelve_months'),1e6): wt_tilt *= 1.7
   # BAKE BAKE-E_BST_WZ_S311_HA_0-R1928 (+0.00223)
   if _qzero and _secc == 311 and self._reg_haccel and _ngt(_g1(_inc_z, 'gain_on_sale_of_security', 'twelve_months'),1e6): wt_tilt *= 1.1
   # BAKE BAKE-K_S310_HA_2-R1920 (+0.00074)
   if _qpos and _secc == 310 and self._reg_haccel and _ngt(_g1(_bs_z, 'long_term_investments', 'twelve_months'),1e6): wt_tilt *= 0.8
   # BAKE BAKE-C_S311_HD14_1-R1919 (+0.00149)
   if _qpos and _secc == 311 and self._reg_hyg_dn14 and _ngt(_g1(_inc_z, 'gain_on_sale_of_business', 'twelve_months'),1e6): wt_tilt *= 0.8
   # BAKE BAKE-M_WZ_S311_Q3_1-R1918 (+0.00340)
   if _qzero and _secc == 311 and self._reg_qqq_up3 and _ngt(_g1(_inc_z, 'earnings_from_equity_interest', 'twelve_months'),1e6): wt_tilt *= 0.8
   # BAKE BAKE-B_WZ_S311_DP_0-R1917 (+0.00106)
   if _qzero and _secc == 311 and self._reg_double_panic and _ngt(_g1(_cfs_z, 'amortization_of_securities', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-L_WZ_S311_VF_0-R1916 (+0.00426)
   if _qzero and _secc == 311 and self._reg_vxx_falling3 and _ngt(_g1(_cfs_z, 'net_ppe_purchase_and_sale', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-D_S311_Q3_1-R1912 (+0.00628)
   if _qpos and _secc == 311 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'gain_loss_on_investment_securities', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-B_S311_DP_1-R1909 (+0.00479)
   if _qpos and _secc == 311 and self._reg_double_panic and _ngt(_g1(_inc_z, 'gain_on_sale_of_security', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-A_S313_HA_0-R1901 (+0.00234)
   if _qsneg and _secc == 313 and decline > 0.020 and decline < 0.050 and self._reg_haccel and _ngt(_g1(_inc_z, 'other_taxes', 'twelve_months'),1e6): wt_tilt *= 0.9
   # BAKE BAKE-H_WZ_VFQ3_0-R1897 (+0.00234)
   if _qzero and decline > 0.020 and decline < 0.050 and self._reg_vxx_falling3 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'net_other_investing_changes', 'twelve_months'),1e6): wt_tilt *= 0.6
   # BAKE BAKE-WDPHD5_1-R1886 (+0.00191)
   if _qpos and self._reg_double_panic and self._reg_hyg_dn5 and _ngt(_g1(_cfs_z, 'operating_gains_losses', 'twelve_months'),1e6): wt_tilt *= 0.8
   # BAKE BAKE-WQD5VF_2-R1884 (+0.00223)
   if _qpos and self._reg_qqq_dn5 and self._reg_vxx_falling3 and _ngt(_g1(_cfs_z, 'net_other_financing_charges', 'twelve_months'),1e6): wt_tilt *= 0.8
   # BAKE BAKE-WQD7_1-R1875 (+0.00245)
   if _qpos and self._reg_qqq_dn7 and _ngt(_g1(_cfs_z, 'short_term_debt_payments', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-WTHD14_2-R1872 (+0.00106)
   if _qpos and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'cash_from_discontinued_operating_activities', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-WVF3_2-R1868 (+0.00160)
   if _qpos and self._reg_vxx_falling3 and decline > 0.020 and decline < 0.050 and _ngt(_g1(_inc_z, 'impairment_of_capital_assets', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-WHDP_2-R1865 (+0.00160)
   if _qpos and self._reg_haccel is not None and self._reg_haccel > 0 and self._reg_double_panic and _ngt(_g1(_bs_z, 'preferred_stock_equity', 'twelve_months'),1e6): wt_tilt *= 0.6
   # BAKE BAKE-WTHU3_2-R1863 (+0.00266)
   if _qpos and self._reg_haccel is not None and self._reg_haccel > 0 and self._reg_qqq_up3 and decline > 0.020 and decline < 0.050 and _ngt(_g1(_bs_z, 'current_deferred_revenue', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-WTZM5_2-R1857 (+0.00138)
   if _qzero and self._reg_haccel is not None and self._reg_haccel > 0 and decline > 0.020 and decline < 0.050 and _ngt(_g1(_cfs_z, 'asset_impairment_charge', 'twelve_months'),1e6): wt_tilt *= 0.5
   # BAKE BAKE-WTH_7-R1847 (+0.00330)
   if _qpos and self._reg_haccel is not None and self._reg_haccel > 0 and _ngt(_g1(_bs_z, 'raw_materials', 'twelve_months'),1e6): wt_tilt *= 0.7
   # ────── EARLY BAKE (sizing) ───────────────────────────────────
   # BAKE-WH-R1650 (+0.00287): wt_tilt boost in small-decline cohort.
   # Placed early because subsequent _tNN rules may read wt_tilt-derived
   # state. Note: clamped at WT_TILT_CAP=2.0 in ranking section.
   if decline > 0.020 and decline < 0.050: wt_tilt *= 1.60
   # ────── SCORE MODIFIERS (load-bearing order; do not reorder) ──
   score = _t10(score, _om1yc, 0.3, decline, 0.05, None, 1.365)
   score = _t06(score, _om1yc, '>', 0.3, _fcfg1yc, '>', 0.1, decline, 0.07, None, 1.4)
   score = _t07(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, _ops_z, ('long_term_debt_equity_ratio', 'one_year'), '<', 0.3, decline, 0.05, None, 1.4)
   score = _t07(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, _ops_z, ('solvency_ratio', 'one_year'), '>', 0.5, decline, 0.05, None, 1.4)
   try:
    _va = f_(_inc_z.write_off.twelve_months)
    _vb = _cfog1yc
    _vc = _gm1yc
    if _va is not None and _vb is not None and _vc is not None and _va > 1e8 and _vb < 0.0 and _vc < 0.20 and decline > .10: continue
   except: pass
   score = _t10(score, _gm1yc, 0.45, decline, 0.03, None, 1.07)
   if _t16(_tr1yc, '>', 0.5, _cfog1yc, '<', -0.05, decline, 0.1, None): continue
   if _t16(_tr1yc, '>', 0.4, _cfog1yc, '<', -0.1, decline, 0.07, None): continue
   if _t16(_tr1yc, '>', 0.3, _cfog1yc, '<', 0.0, decline, 0.05, None): continue
   score = _t06(score, _rt1yc, '>', 10.0, _tr1yc, '<', 0.2, decline, 0.05, None, 1.2)
   score = _t06(score, _rt1yc, '>', 8.0, _tr1yc, '<', 0.15, decline, 0.07, None, 1.4)
   score = _t06(score, _rt1yc, '>', 6.0, _tr1yc, '<', 0.18, decline, 0.1, None, 1.3)
   score = _t06(score, _om1yc, '>', 0.35, _tr1yc, '<', 0.15, decline, 0.07, None, 1.3)
   score = _t11(score, _pegr, 1.5, decline, 0.03, None, 1.1)
   score = _t11(score, _pegr, 1.5, decline, 0.1, None, 1.2)
   score = _t11(score, _pegr, 1.5, decline, 0.2, None, 1.5)
   score = _t11(score, _pegr, 2.5, decline, 0.25, None, 1.5)
   score = _t12(score, _secc, 309, decline, 0.03, None, 1.10)
   score = _t12(score, _secc, 309, decline, None, None, 1.20, _hyg_dn5)
   score = _t12(score, _secc, 308, decline, 0.07, None, 1.30)
   score = _t12(score, _secc, 309, decline, None, None, 1.95, self._reg_double_panic)
   try:
    _va = _secc
    _vb = f_(_ops_z.tax_rate.six_months)
    if _va is not None and _vb is not None and _va == 310 and _vb < 0.18 and decline > .03: score *= 1.25
   except: pass
   score = _t11(score, _tac, 1000000000.0, decline, None, None, 1.2, _hyg_dn5)
   score = _t11(score, _tac, 3000000000.0, decline, 0.07, None, 1.15)
   score = _t10(score, _tac, 500000000000.0, decline, 0.05, None, 1.1)
   score = _t11(score, _tac, 1000000000.0, decline, None, None, 1.2, _qqq_dn5)
   try:
    _r_open = f_(bar.open)
    _r = _bc / _r_open if _r_open > 0 else 1.0
    if _r > 1.02 and decline > .03: score *= 1.12
   except: pass
   try:
    _v = _pegr
    if _v < 1.0 and decline > .05: score += 0.10
   except: pass
   score = _t10(score, _tac, 100000000000.0, decline, 0.04, 0.07, 1.1)
   try:
    _v = _crc
    if _v > 0.10 and _hyg_dn5: score += 0.50
   except: pass
   score = _t10(score, _tac, 300000000000.0, decline, 0.04, 0.08, 1.05)
   if _lowgwr and _d5_10: score *= 1.10
   score = _t08(score, _ops_z, ('net_margin', 'three_months'), '<', 0.0, decline, 0.05, 0.1, 0.9)
   score = _t08(score, _vr_z, ('fcf_yield',), '>', 0.08, decline, 0.04, 0.08, 1.1)
   try:
    _p = f_(_vr_z.payout_ratio)
    if _lowgwr and _p < 0.40 and _d5_10: score *= 1.05
   except: pass
   if _lowgwr and _nlt(_capec,22) and _d4_8: score *= 1.05
   score = _t10(score, _om3mc, 0.35, decline, 0.05, 0.1, 1.05)
   score = _t10(score, _om3mc, 0.35, decline, 0.04, 0.08, 1.03)
   score = _t10(score, _om3mc, 0.35, decline, 0.06, 0.1, 1.03)
   score = _t10(score, _om3mc, 0.4, decline, 0.04, 0.08, 1.03)
   try:
    _s = _secc
    _v = _fcfy_c
    if _s == 308 and _ngt(_v,0.08) and _d4_8: score *= 1.05
   except: pass
   if _lowgwr and _ngt(_om3mc,0.35) and _d4_8: score *= 1.03
   try:
    _v = f_(_ops_z.net_margin.three_months)
    if _lowgwr and _ngt(_v,0.25) and _d4_8: score *= 1.05
   except: pass
   score = _t10(score, _om1yc, 0.4, decline, 0.04, 0.08, 1.05)
   try:
    _s = _secc
    _v = f_(_vr_z.ev_to_ebitda)
    if _s == 310 and _nrg(_v,0,12) and _d4_8: score *= 1.05
   except: pass
   try:
    _s = _secc
    _v = _fcfy_c
    if _s == 206 and _ngt(_v,0.05) and _d5_10: score *= 1.05
   except: pass
   score = _t10(score, _cfyc, 0.1, decline, 0.04, 0.08, 1.05)
   score = _t10(score, _cfyc, 0.15, decline, 0.05, 0.1, 1.05)
   score = _t08(score, _vr_z, ('earning_yield',), '>', 0.06, decline, 0.04, 0.08, 1.05)
   score = _t10(score, _cfyc, 0.08, decline, 0.02, 0.05, 1.05)
   score = _t10(score, _roic3mc, 0.18, decline, 0.005, 0.02, 1.05)
   score = _t10(score, _roic3mc, 0.15, decline, 0.005, 0.025, 1.05)
   if _lowgwr and _nrg(_capec,0,22) and _d1_3: score *= 1.03
   if _nrg(_r7,-0.10,-0.05): score *= 1.08
   try:
    _v = _pegr
    if 0<_v<0.8 and _d1_3: score *= 1.05
   except: pass
   try:
    _bars7 = mtf[-7:] if len(mtf) >= 7 else None
    _hi7 = max(f_(b.high) for b in _bars7) if _bars7 else None
    _lo7 = min(f_(b.low) for b in _bars7) if _bars7 else None
    if _hi7 is not None and _ngt(_lo7,0) and (_hi7/_lo7) > 1.12 and decline > .03: score *= 1.05
   except: pass
   try:
    _g = f_(_ers_z.normalized_diluted_eps_growth.one_year)
    _e = _ey_c
    if _ngt(_g,0.05) and _ngt(_e,0.06) and _d5_10: score *= 1.05
   except: pass
   score = _t08(score, _ers_z, ('basic_average_shares_growth', 'one_year'), '<', -0.02, decline, 0.04, 0.08, 1.05)
   try:
    _v = _cfyc
    if _v > 0.08 and -0.05<_r5<-0.03: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v > 50 and -0.05<_r5<-0.03: score *= 1.05
   except: pass
   try:
    _v = _pegr
    if 0<_v<1.0 and -0.05<_r7<-0.02: score *= 1.05
   except: pass
   try:
    _v = _pegr
    if 0<_v<0.6 and -0.05<_r5<-0.03: score *= 1.05
   except: pass
   try:
    _v = _roic3mc
    if _v > 0.18 and -0.04<_r3<-0.02: score *= 1.08
   except: pass
   try:
    _v = _roic3mc
    if _v > 0.18 and -0.04<_r3<-0.02: conv *= 1.50
   except: pass
   conv = _t14(conv, _vr_z, ('cf_yield',), None, None, 2.5, gt=(('>', 0.08),), rg=_hyg_dn5)
   conv = _t14(conv, _vr_z, ('cf_yield',), None, None, 2.0, gt=(('>', 0.08),), rg=_hyg_dn3)
   conv = _t14(conv, _vr_z, ('peg_ratio',), None, None, 2.0, gt=(('>', 0.0), ('<', 1.5)), rg=_hyg_dn3)
   conv = _t14(conv, _vr_z, ('peg_ratio',), None, None, 1.5, gt=(('>', 0.0), ('<', 1.5)), rg=_qqq_dn3)
   try:
    _v_piS = _pti3m_c
    _v_ndegS = _ndepsg3m_c
    if _ngt(_v_piS,1e10) and _ngt(_v_ndegS,0.10) and _qzero and _hyg_dn14: conv *= 0.85
   except: pass
   try:
    _v = _pegr
    if 0<_v<1.5 and _hyg_dn3 and _d2_6: score *= 1.05
   except: pass
   try:
    _v = _pegr
    if 0<_v<1.5 and _hyg_dn3 and _d2_4: score *= 1.05
   except: pass
   try:
    _v = _pegr
    if 0<_v<1.5 and _hyg_dn3 and (_bc > f_(bar.open)) and _d2_6: score *= 1.05
   except: pass
   try:
    _v = _pegr
    _bo = f_(bar.open); _bl = f_(bar.low)
    _body = abs(_bc - _bo) if _bc and _bo else 0
    _ls = (min(_bo, _bc) - _bl) if _bo and _bc and _bl else 0
    _hammer = _body > 0 and _ls > 2 * _body
    if 0<_v<1.5 and _hyg_dn3 and _hammer and _d2_6: score *= 1.05
   except: pass
   try:
    _v = _pegr
    _both = _r3 is not None and _r5 is not None and -0.05<_r3<-0.02 and -0.05<_r5<-0.02
    if 0<_v<1.5 and _hyg_dn3 and _both and _d4_8: score *= 1.14
   except: pass
   try:
    _v = _pegr
    _both = _r3 is not None and _r5 is not None and -0.05<_r3<-0.02 and -0.05<_r5<-0.02
    if 0<_v<1.5 and _hyg_dn3 and _both and _d4_10: score *= 1.10
   except: pass
   try:
    _v = _pegr
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if 0<_v<1.5 and _qqq_dn3 and _above and _d2_6: score *= 1.10
   except: pass
   try:
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if _hyg_dn3 and _above and _d4_8: score *= 1.08
   except: pass
   try:
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    _bo = f_(bar.open); _bl = f_(bar.low)
    _body = abs(_bc - _bo) if _bc and _bo else 0
    _ls = (min(_bo, _bc) - _bl) if _bo and _bc and _bl else 0
    _hammer = _body > 0 and _ls > 2 * _body
    if _hyg_dn3 and _above and _hammer and _d2_6: score *= 1.05
   except: pass
   try:
    _v = _secc
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if _v == 206 and _hyg_dn3 and _above and _d2_6: score *= 1.08
   except: pass
   score = _t10(score, _vsc, 50.0, decline, 0.05, 0.1, 1.05)
   try:
    _v1 = _cfyc
    _v2 = _vsc
    if _ngt(_v1,0.05) and _ngt(_v2,50) and _d5_10: score *= 1.05
   except: pass
   if _secc == 309 and _lowgwr and _d4_8: score *= 1.10
   score = _t10(score, _roic3mc, 0.18, decline, 0.03, None, 1.14)
   score = _t10(score, _om3mc, 0.35, decline, 0.03, None, 1.1)
   score = _t08(score, _ops_z, ('tax_rate', 'six_months'), '<', 0.18, decline, 0.03, None, 1.1)
   score = _t06(score, _capec, '<', 25.0, _om3mc, '>', 0.35, decline, 0.03, None, 1.3)
   score = _t10(score, _roic3mc, 0.15, decline, None, None, 1.2, _qqq_dn3)
   score = _t11(score, _pegr, 1.5, decline, None, None, 1.2, _hyg_dn5)
   score = _t10(score, _crc, 0.1, decline, None, None, 1.4, _qqq_dn5)
   score = _t10(score, _roic3mc, 0.15, decline, None, None, 1.2, _hyg_dn3)
   score = _t10(score, _roic3mc, 0.15, decline, None, None, 1.2, _qqq_dn7)
   score = _t11(score, _pegr, 1.5, decline, None, None, 1.2, _qqq_up3)
   score = _t10(score, _roic3mc, 0.15, decline, None, None, 1.4, _hyg_up5)
   score = _t10(score, _roic3mc, 0.15, decline, None, None, 1.4, _hyg_up3)
   score = _t06(score, _pegr, '<', 1.5, _fpec, '<', 12.0, decline, 0.05, None, 1.3)
   score = _t10(score, _crc, 0.1, decline, 0.03, None, 1.15)
   score = _t06(score, _crc, '>', 0.1, _pegr, '<', 1.5, decline, 0.03, None, 1.25)
   score = _t06(score, _pegr, '<', 1.5, _pec, '<', 12.0, decline, 0.07, None, 1.3)
   if _t16(_tr1yc, '>', 0.35, _cfog1yc, '<', -0.15, decline, 0.03, None): continue
   if _t16(_tr1yc, '>', 0.35, _cfog1yc, '<', -0.15, decline, None, None): continue
   if _t13(_cfog1yc, (('<', -0.4),), decline, None, None, True): continue
   if _t15(_ops_z, ('fcf_growth', 'one_year'), (('<', -0.7),), decline, None, None, True): continue
   if _t15(_ops_z, ('net_income_growth', 'three_months'), (('<', -0.5),), decline, None, None, True): continue
   score = _t08(score, _ops_z, ('fcf_sales_ratio', 'one_year'), '>', 0.25, decline, 0.03, None, 1.1)
   try:
    _v = _pegr
    if 0<_v<1.5 and _hyg_dn3 and _d12_20: score *= 1.80
   except: pass
   try:
    _v = _pegr; _p = _bc
    if 0<_v<1.5 and 50<_p<100 and _hyg_dn3 and _d12_20: score *= 1.50
   except: pass
   try:
    _v = _pegr
    if 5<_v<20 and _hyg_dn3 and _d12_20: score *= 0.70
   except: pass
   try:
    _v = _secc; _p = _bc
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if _v == 206 and 100<_p<200 and _hyg_dn3 and _above and _d2_6: score *= 1.50
   except: pass
   try:
    _v = _pegr; _p = _bc
    if 0<_v<1.5 and 100<_p<200 and _hyg_dn3 and _d2_6: score *= 1.08
   except: pass
   try:
    _v = _pegr
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if 0<_v<1.5 and _nrg(_accel,-0.10,-0.02) and _hyg_dn3 and _d2_6: score *= 1.18
   except: pass
   try:
    _v = _secc
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v == 206 and _nrg(_accel,-0.10,-0.02) and _hyg_dn3 and _d2_6: score *= 1.10
   except: pass
   try:
    _v = _pegr
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if 0<_v<1.0 and _nrg(_accel,-0.10,-0.02) and _hyg_dn3 and _d2_6: score *= 1.18
   except: pass
   try:
    _v = _pegr
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if 0<_v<1.5 and _nrg(_accel,0.05,0.15) and _hyg_dn3 and _d2_6: score *= 0.70
   except: pass
   score = _t01(score, _pegr, 0.0, 1.5, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.98, _hyg_dn3)
   score = _t01(score, _pegr, 0.0, 1.0, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.3, _hyg_dn3)
   score = _t04(score, _roic3mc, 0.1, _qa, 0.01, 0.05, decline, 0.02, 0.06, 2.16, _hyg_dn3)
   score = _t04(score, _ic1yc, 20.0, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.1, _hyg_dn3)
   score = _t04(score, _ic1yc, 50.0, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.05, _hyg_dn3)
   try:
    _v = _ic1yc
    if _v > 20 and _nrg(_haccel,0.01,0.05) and _hyg_dn3 and _d2_6: score *= 1.14
   except: pass
   score = _t00(score, _secc, 206, _pegr, 0.0, 1.5, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.95, _hyg_dn3)
   score = _t00(score, _secc, 206, _pegr, 0.0, 1.5, _qa, -0.05, -0.01, decline, 0.02, 0.06, 0.6, _hyg_dn3)
   try:
    _v = _secc
    if _v == 206 and _qneg and _hyg_dn3 and _d2_6: score *= 0.95
   except: pass
   try:
    _vs = _secc; _vp = _pegr
    if _vs == 206 and _nrg(_vp,0,1.5) and _nrg(_haccel,-0.05,-0.01) and _hyg_dn3 and _d2_6: score *= 0.70
   except: pass
   score = _t04(score, _ic1yc, 20.0, _qa, -0.05, -0.01, decline, 0.02, 0.06, 0.93, _hyg_dn3)
   score = _t00(score, _secc, 102, _pegr, 0.0, 1.0, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.4, _hyg_dn3)
   score = _t00(score, _secc, 102, _pegr, 0.0, 1.0, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.07)
   score = _t00(score, _secc, 102, _pegr, 0.0, 1.0, _qa, -0.05, -0.01, decline, 0.02, 0.06, 0.7)
   score = _t00(score, _secc, 102, _cashc, 5e9, 1e15, _qa, 0.01, 0.05, decline, 0.04, 0.08, 1.5)
   score = _t00(score, _secc, 308, _cashc, 5e9, 1e15, _qa, -0.05, -0.01, decline, 0.04, 0.08, 1.5)
   score = _t00(score, _secc, 102, _cashc, 5e9, 1e15, _qa, -0.05, -0.01, decline, 0.04, 0.08, 0.95)
   score = _t03(score, _bs_z, ('dividends_payable', 'twelve_months'), (('>', 5e8),), _qa, 0.01, 0.05, decline, 0.04, 0.08, 1.30)
   if _qsneg and _d4_8: score *= 1.50
   if _secc == 308 and _qsneg and _d2_5: score *= 1.30
   if _secc == 102 and _qsneg and _d2_5: score *= 1.50
   if _secc == 206 and _nlt(_vol20,0.020) and _qpos and _d4_8: score *= 0.85
   try:
    _v_npe = f_(_vr_z.normalized_pe_ratio)
    if _nrg(_v_npe,0,12) and _q_dn and _d4_8: score *= 1.30
   except: pass
   if _lo_vol and _q_dn and _d4_8: score *= 0.70
   if _secc == 311 and _nrg(_pec,0,12) and _hyg_dn3 and _d4_12: score *= 1.50
   if _qqq_dn7 and _nrg(_pec,0,12) and _q_dn and _d4_12: score *= 0.85
   if _secc == 102 and _nlt(_vol20,0.015) and _qqq_dn3 and _d4_12: score *= 1.14
   if _icp: score *= 0.85
   if _fcp: score *= 0.85
   if _icp and _q_dn: score *= 1.30
   if _icp and _hyg_dn3: score *= 1.14
   if _icp and _nrg(_pegr,0,1.5): score *= 1.14
   if _fcp and _hyg_dn3: score *= 1.30
   if _icp and _qpos: score *= 1.50
   try:
    _v_fdy = f_(_vr_z.forward_dividend_yield)
    if _ngt(_v_fdy,0.04) and _qpos and _d4_8: score *= 0.85
   except: pass
   try:
    _v_da = f_(_inc_z.depreciation_and_amortization.twelve_months)
    if _ngt(_v_da,1e9) and _q_dn and _d4_8: score *= 1.30
   except: pass
   if vol_climax and _nlt(_r5,-0.10) and _d4_8: score *= 1.30
   if _secc == 205 and _qpos and _d4_8: score *= 1.40
   try:
    _v_fcfy = _fcfy_c
    if _ngt(_v_fcfy,0.06) and _qpos and _hyg_dn3: score *= 1.14
    if _ngt(_v_fcfy,0.06) and _qpos and _hyg_dn14: score *= 1.30
   except: pass
   try:
    _v_ps = _ps12m_c
    if _ngt(_v_ps,0) and _qpos and _hyg_dn3: score *= 1.14
   except: pass
   try:
    _v_ndeg = _ndepsg3m_c
    if _ngt(_v_ndeg,0.10) and _qpos and _hyg_dn3: score *= 1.14
   except: pass
   try:
    _v_jfc = _fcfy_c
    if _ngt(_v_jfc,0.06) and _qsneg and _hyg_dn5: score *= 0.90
   except: pass
   try:
    _v_cor = f_(_inc_z.cost_of_revenue.twelve_months)
    if _nlt(_v_cor,1e10) and _qpos and _hyg_dn3: score *= 1.14
    if _nlt(_v_cor,1e10) and _qsneg and _hyg_dn3: score *= 1.14
   except: pass
   try:
    _v_psn = _ps12m_c
    if _ngt(_v_psn,0) and _qsneg and _hyg_dn3: score *= 1.40
    if _ngt(_v_psn,0) and _qsneg and _hyg_dn5: score *= 0.85
   except: pass
   try:
    _v_nbeg1y = f_(_ers_z.normalized_basic_eps_growth.one_year)
    if _ngt(_v_nbeg1y,0.10) and _qpos and _hyg_dn3: score *= 0.90
   except: pass
   try:
    _v_iexp = _intexp12m_c
    if _nlt(_v_iexp,1e8) and _qpos and _hyg_dn3: score *= 1.20
   except: pass
   try:
    _v_pt3m = f_(_ops_z.payment_turnover.three_months)
    if _ngt(_v_pt3m,5.0) and _qpos and _hyg_dn3: score *= 1.14
   except: pass
   try:
    _v_pegLT1 = _pegr
    if _nrg(_v_pegLT1,0,1.0) and _qpos and _hyg_dn3: score *= 0.85
    if _nrg(_v_pegLT1,0,1.0) and _qsneg and _hyg_dn3: score *= 1.20
    if _nrg(_v_pegLT1,0,1.0) and _qzero and _hyg_dn3: score *= 0.85
    if _nrg(_v_pegLT1,0,0.8) and _qzero and _hyg_dn3: score *= 1.14
   except: pass
   try:
    _v_dpsg = f_(_ers_z.dps_growth.three_months)
    if _ngt(_v_dpsg,0.10) and _qzero and _hyg_dn3: score *= 0.80
   except: pass
   try:
    _v_ndegC = _ndepsg3m_c
    _v_fcfyC = _fcfy_c
    if _ngt(_v_ndegC,0.10) and _ngt(_v_fcfyC,0.06) and _qzero and _hyg_dn3: score *= 1.50
   except: pass
   try:
    _v_gpQ = f_(_inc_z.gross_profit.twelve_months)
    if _ngt(_v_gpQ,5e10) and _qzero and _hyg_dn3: score *= 1.14
   except: pass
   try:
    _v_ndegB = _ndepsg3m_c
    _v_fcfyB = _fcfy_c
    if _ngt(_v_ndegB,0.10) and _ngt(_v_fcfyB,0.06) and _qpos and _hyg_dn14: score *= 0.90
    if _ngt(_v_ndegB,0.10) and _ngt(_v_fcfyB,0.06) and _qsneg and _hyg_dn14: score *= 0.85
   except: pass
   try:
    _v_gpJ = _gp3m_c
    _v_ndegJ = _ndepsg3m_c
    if _ngt(_v_gpJ,1e10) and _ngt(_v_ndegJ,0.10) and _qzero and _hyg_dn14: score *= 1.14
    if _ngt(_v_gpJ,1e10) and _ngt(_v_ndegJ,0.10) and _qpos and _hyg_dn3: score *= 1.14
   except: pass
   try:
    _v_ebK = f_(_inc_z.ebitda.three_months)
    _v_fyK = _fcfy_c
    if _ngt(_v_ebK,1e10) and _ngt(_v_fyK,0.06) and _qzero and _hyg_dn14: score *= 1.30
   except: pass
   try:
    _v_piL = _pti3m_c
    if _ngt(_v_piL,1e10) and _qzero and _hyg_dn14: score *= 1.50
   except: pass
   try:
    _v_gpM = _gp3m_c
    _v_ndegM = _ndepsg3m_c
    if _ngt(_v_gpM,1e10) and _ngt(_v_ndegM,0.10) and _qsneg and _hyg_dn14: score *= 1.14
   except: pass
   try:
    _v_fctN = _fcta3m_c
    if _nlt(_v_fctN,-1e9) and _qzero and _hyg_dn14: score *= 1.20
   except: pass
   try:
    _v_psO = f_(_bs_z.preferred_stock.three_months)
    if _ngt(_v_psO,1e9) and _qzero and _hyg_dn14: score *= 1.30
   except: pass
   try:
    _v_piP = _pti3m_c
    _v_ndegP = _ndepsg3m_c
    if _ngt(_v_piP,1e10) and _ngt(_v_ndegP,0.10) and _qzero and _hyg_dn14: score *= 0.70
   except: pass
   try:
    _v_fctQ = _fcta3m_c
    if _nlt(_v_fctQ,-1e9) and _qzero and _hyg_dn14: score *= 1.10
   except: pass
   try:
    _v_fctR = _fcta3m_c
    _v_ndegR = _ndepsg3m_c
    if _nlt(_v_fctR,-1e9) and _ngt(_v_ndegR,0.10) and _qsneg and _hyg_dn14: score *= 1.30
   except: pass
   try:
    _v_amrtT = f_(_inc_z.amortization.three_months)
    if _ngt(_v_amrtT,1e9) and _qzero and _hyg_dn14: score *= 1.20
   except: pass
   try:
    _v_fyU = _fcfy_c
    _v_pgU = _pegr
    if _ngt(_v_fyU,0.08) and _nrg(_v_pgU,0,1.0) and _qpos and _hyg_dn3: score *= 1.30
    if _ngt(_v_fyU,0.08) and _nrg(_v_pgU,0,1.0) and _qzero and _hyg_dn14: score *= 1.14
    if _ngt(_v_fyU,0.08) and _nrg(_v_pgU,0,1.0) and _qsneg and _hyg_dn14: score *= 1.14
   except: pass
   try:
    _v_fy12 = _fcfy_c
    if _ngt(_v_fy12,0.12) and _qsneg and _hyg_dn14: score *= 1.30
   except: pass
   try:
    _v_eyV = _ey_c
    if _ngt(_v_eyV,0.08) and _qsneg and _hyg_dn14: score *= 1.16
    if _ngt(_v_eyV,0.08) and _hi_cape and _hyg_dn14: score *= 1.28
    if _ngt(_v_eyV,0.08) and _lo_cape and self.time.day <= 5: score *= 0.85
   except: pass
   try:
    if _secc == 308 and _lo_cape and _qsneg: score *= 1.14
    if self.time.day >= 25 and _lo_vol and _qsneg and _hyg_dn14: score *= 1.30
    if _secc == 308 and self.time.day >= 25 and _qsneg: score *= 1.14
    if _secc == 103 and _lo_cape and _qzero: score *= 0.70
    if _qpos and _secc == 103 and _hyg_up5: score *= 1.20
    try:
     _v_e414 = _ey_c
     _v_f414 = _fcfy_c
     if _qpos and _ngt(_v_e414,0.08) and _ngt(_v_f414,0.08) and _hyg_up5: score *= 1.14
    except: pass
    if _r60_dn and _qpos and _hyg_up5: score *= 1.10
    if _r60_dn and _qzero and _hyg_dn14: score *= 0.88
    if _r60_dn and _qsneg and _hyg_dn14: score *= 1.03
    if 1 <= self.time.day <= 5 and _r60_dn and _qpos and _hyg_up5: score *= 1.20
   except: pass
   try:
    _v_pegpb = _pegpb_c
    if _nlt(_v_pegpb,4.0) and _qzero and _hyg_dn3: score *= 1.10
    if _nlt(_v_pegpb,3.0) and _qzero and _hyg_dn3: score *= 1.10
   except: pass
   try:
    _v_iexpQ = _intexp12m_c
    if _nlt(_v_iexpQ,1e8) and _qzero and _hyg_dn3: score *= 1.14
   except: pass
   try:
    _v_fcfyQ = _fcfy_c
    if _ngt(_v_fcfyQ,0.10) and _qzero and _hyg_dn3: score *= 0.85
   except: pass
   try:
    _v_tr3m = f_(_ops_z.tax_rate.three_months)
    if _nlt(_v_tr3m,0.20) and _qpos and _hyg_dn3: score *= 1.05
   except: pass
   score = _t00(score, _secc, 206, _pegr, 0.0, 1.5, _qa, -0.05, -0.01, decline, 0.02, 0.06, 0.7)
   score = _t00(score, _secc, 206, _pegr, 0.0, 1.5, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.08)
   score = _t01(score, _pegr, 0.0, 1.0, _qa, -0.05, -0.01, decline, 0.02, 0.06, 0.8)
   try:
    _v = _pegr
    if 0<_v<1.0 and _nrg(_haccel,-0.05,-0.01) and _d2_6: score *= 0.95
   except: pass
   try:
    _vs = _secc; _vp = _pegr
    if _vs == 206 and _nrg(_vp,0,1.5) and _nrg(_haccel,-0.05,-0.01) and _d2_6: score *= 0.90
   except: pass
   score = _t00(score, _secc, 102, _pegr, 0.0, 1.0, _qa, -0.05, -0.01, decline, 0.06, 0.12, 0.5)
   score = _t00(score, _secc, 206, _pegr, 0.0, 1.5, _qa, -0.05, -0.01, decline, 0.06, 0.12, 0.7)
   try:
    _v = _pegr
    if 0<_v<1.5 and _qneg and decline > .12: score *= 0.55
   except: pass
   score = _t00(score, _secc, 102, _pegr, 0.0, 1.0, _qa, 0.01, 0.05, decline, 0.06, 0.12, 2.2)
   try:
    _vp = _pegr; _ic = _ic1yc
    if _nrg(_vp,0,1.5) and _ngt(_ic,20) and _qneg and _d6_12: score *= 0.80
   except: pass
   try:
    _vp = _pegr; _ic = _ic1yc
    if _nrg(_vp,0,1.5) and _ngt(_ic,50) and _qneg and _d6_12: score *= 0.65
   except: pass
   try:
    _vp = _pegr; _ic = _ic1yc
    if _nrg(_vp,0,1.5) and _ngt(_ic,100) and _qneg and _d6_12: score *= 0.55
   except: pass
   try:
    _vp = _pegr; _pe = _pec
    if _nrg(_vp,0,1.5) and _nrg(_pe,0,15) and _qneg and _d6_12: score *= 0.65
   except: pass
   try:
    _vp = _pegr; _ev = f_(_vr_z.ev_to_revenue)
    if _nrg(_vp,0,1.5) and _nrg(_ev,0,2) and _qneg and _d6_12: score *= 0.85
   except: pass
   score = _t01(score, _pegr, 0.0, 1.5, _qa, -0.05, -0.01, decline, 0.06, 0.12, 0.7, self._reg_double_panic)
   score = _t01(score, _pegr, 0.0, 1.5, _qa, -0.05, -0.01, decline, 0.06, 0.12, 0.93, _hyg_dn14)
   score = _t00(score, _secc, 206, _pegr, 0.0, 1.5, _qa, -0.05, -0.01, decline, 0.02, 0.06, 0.95, _hyg_dn14)
   score = _t00(score, _secc, 206, _pegr, 0.0, 1.5, _qa, 0.01, 0.05, decline, 0.02, 0.06, 1.2, _hyg_dn14)
   score = _t04(score, _vsc, 50.0, _qa, 0.01, 0.05, decline, 0.06, 0.12, 1.3)
   score = _t04(score, _vsc, 70.0, _qa, 0.01, 0.05, decline, 0.06, 0.12, 1.4)
   try:
    _v = _vsc
    if _v > 60 and _qpos and _d12_20: continue
   except: pass
   try:
    _v = _vsc
    if _v > 85 and _qpos and _d4_8: continue
   except: pass
   try:
    _v = _vsc
    if _v > 85 and _qpos and _d2_4: continue
   except: pass
   try:
    _v = _vsc
    if _v > 80 and _qzero and _d2_6: continue
   except: pass
   try:
    _v = _vsc
    if _v > 60 and _qzero and _d6_12: continue
   except: pass
   try:
    _v = _vsc
    if _v >= 15 and _v < 30 and _qzero and _d6_12: score *= 1.20
   except: pass
   try:
    _v = _vsc
    if _v >= 50 and _v < 60 and _qzero and _d6_12: score *= 0.5
   except: pass
   try:
    _v = _vsc
    if _v >= 25 and _v < 30 and _qzero and _d6_12: score *= 1.20
   except: pass
   try:
    _v = _vsc
    if _v >= 50 and _v < 60 and _qzero and _d4_8: score *= 0.85
   except: pass
   try:
    _v = _vsc
    if _v >= 25 and _v < 30 and _qzero and _d6_12: score *= 1.20
   except: pass
   try:
    _v = _vsc
    if _v >= 15 and _v < 30 and _qzero and _d4_8: score *= 0.95
   except: pass
   try:
    _v = _secc
    if _v == 206 and _qzero and _d6_12: score *= 0.85
   except: pass
   try:
    _v = _secc
    if _v == 102 and _qzero and _d6_12: score *= 0.95
   except: pass
   try:
    _v = _secc
    if _v == 308 and _qzero and _d6_12: score *= 1.05
   except: pass
   try:
    _v = _secc
    if _v == 308 and _qzero and _d2_4: score *= 1.05
   except: pass
   try:
    _v = _secc
    if _v == 311 and -0.05<_qa<-0.01 and _d6_12: score *= 1.25
   except: pass
   try:
    _v = _secc
    if _v == 309 and _qzero and _d4_8: score *= 1.50
   except: pass
   try:
    _v = _secc
    if _v == 308 and _qzero and _d4_8: score *= 0.95
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _qzero and _d4_8: score *= 0.95
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _qzero and _d2_4: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if _v < 5 and -0.05<_qa<-0.01 and _d4_8: score *= 0.85
   except: pass
   try:
    _v = _vsc
    if _v < 10 and _qzero and _d2_4: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v < 10 and _qzero and _d4_8: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v < 10 and -0.05<_qa<-0.01 and _d4_8: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v < 10 and _qpos and _d6_12: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if _v < 5 and -0.05<_qa<-0.01 and _d6_12: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if 15<_v<30 and 0.05<_r5<0.20 and _d4_12: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if 5<_v<10 and 0.05<_r5<0.20 and _d2_4: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if 15<_v<30 and 0.05<_r5<0.20 and _d6_12: score *= 1.14
   except: pass
   try:
    _v = _secc
    if _v == 308 and 0.05<_r5<0.20 and _d4_12: score *= 0.55
   except: pass
   if _ngt(_bc,150) and _qzero and _d6_12: score *= 1.05
   if _ngt(_bc,150) and _nrg(_qa,-0.05,-0.01) and _d6_12: score *= 0.95
   if _ngt(_bc,150) and _nrg(_qa,-0.05,-0.01) and _d4_8: score *= 0.75
   try:
    _v = f_(_bs_z.cash_equivalents.three_months)
    if _v > 1e8 and _qpos and _d6_12: score *= 1.30
   except: pass
   if _nrg(_r7,-0.30,-0.10) and _qzero and _d4_12: score *= 0.85
   try:
    if _nlt(_qd5,-0.05) and _d4_12:
     score *= 0.95
     if -0.05<_qa<-0.01:
      score *= 0.85
      if _r5 < 0: score *= 0.75
   except: pass
   if _nrg(_r7,-0.20,-0.05) and _qzero and _d2_4: score *= 0.55
   try:
    _v = _secc
    if _bc > 150 and _v is not None and _v == 308 and _d4_12: score *= 1.25
   except: pass
   try:
    _v = _vsc
    if 5<_v<10 and -0.20<_r5<-0.05 and _d4_12: score *= 0.95
   except: pass
   try:
    _v = _vsc
    if _v < 5 and -0.15<_r3<-0.03 and _d4_12: score *= 1.05
   except: pass
   if _nrg(_r7,-0.20,-0.05) and _qzero and _d4_8: score *= 0.75
   try:
    _v = _vsc
    if 5<_v<10 and -0.15<_r3<-0.02 and _d4_12: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v < 5 and -0.20<_r5<0 and _d4_8: score *= 1.50
   except: pass
   try:
    _o = f_(bar.open); _pc = f_(mtf[-2].close)
    if _o > 0 and _pc > 0 and _o/_pc < 0.95 and _qzero and _d4_8: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if _v < 5 and -0.20<_r5<0 and _d2_4: score *= 0.95
   except: pass
   if _nlt(_bc,50) and _nrg(_qa,-0.05,-0.01) and _d4_8: score *= 0.75
   if _nrg(_bc,50,100) and _nrg(_qa,-0.05,-0.01) and _d4_8: score *= 0.95
   if _nlt(_bc,50) and _nrg(_qa,-0.05,-0.01) and _d6_12: score *= 1.30
   if _nlt(_bc,50) and _qzero and _d4_8: score *= 0.95
   if _nrg(_bc,50,100) and _nrg(_qa,-0.05,-0.01) and _d6_12: score *= 1.05
   if _ngt(_bc,150) and _nrg(_qa,-0.05,-0.01) and _d6_12: score *= 1.14
   if _nrg(_bc,75,100) and _nrg(_qa,-0.05,-0.01) and _d4_8: score *= 0.85
   if _nrg(_bc,30,50) and _nrg(_qa,-0.05,-0.01) and _d4_8: score *= 0.95
   if _nrg(_bc,75,100) and _nrg(_qa,-0.05,-0.01) and _d6_12: score *= 0.55
   if _nrg(_bc,25,50) and _nrg(_qa,-0.05,-0.01) and _d6_12: score *= 1.05
   try:
    _vola = _vol20
    if _vola is not None and _qa is not None:
     if _vola > 0.04 and _d4_12:
      if _qzero: score *= 0.75
      elif -0.05<_qa<-0.01: score *= 0.85
     if _vola > 0.04 and _qzero and _d2_4: score *= 1.50
     if _vola > 0.05 and -0.05<_qa<-0.01 and _d4_8: score *= 0.85
     if _vola > 0.04 and -0.05<_qa<-0.01 and _d2_4: score *= 0.95
     if _vola > 0.04 and _d4_12:
      _v304 = _vsc if _ac_z else None
      if _v304 < 10: score *= 0.75
     if _vola > 0.04 and _hyg_up3 and _d4_12: score *= 0.85
     if _vola > 0.04 and _hyg_up5 and _d4_12: score *= 0.95
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _hyg_up3 and _d4_12: score *= 1.14
   except: pass
   try:
    _v = _vsc
    if 5<_v<10 and _hyg_dn3 and _d4_12: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if 55<_v<60 and _qzero and _d6_12: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if 35<_v<40 and _qzero and _d6_12: score *= 1.25
   except: pass
   score = _t05(score, _vsc, 15.0, _qa, 0.01, 0.05, decline, 0.06, 0.12, 1.2)
   score = _t01(score, _vsc, 30.0, 50.0, _qa, 0.01, 0.05, decline, 0.06, 0.12, 0.85)
   try:
    _v = _vsc
    if 15<_v<30 and _qzero and _r3_md and _r5_up and _d4_12: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if 10<_v<15 and _qzero and _r3_md and _r5_up and _d4_12: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if 15<_v<30 and _qzero and _r3_md and _r5_up and _d2_4: score *= 0.65
   except: pass
   try:
    _v = _secc
    if _v == 311 and _qzero and _r3_md and _r5_up and _d4_12: score *= 0.85
   except: pass
   try:
    _v = _vsc
    if 10<_v<15 and _qzero and _r3_md and _r5_up and _d2_4: score *= 1.14
   except: pass
   if _ngt(_vol20,0.06) and _qzero and _r3_md and _r5_up and _d4_12: score *= 0.50
   try:
    _v = _vsc
    if _v > 50 and _qzero and _r3_md and _r5_up and _d4_12: score *= 1.05
   except: pass
   if _nrg(_r7,0,0.20) and _qzero and _r3_md and _r5_up and _d4_12: score *= 1.14
   try:
    _v = _vsc
    if _v > 50 and _qpos and _r3_md and _r5_up and _d4_12: score *= 0.85
   except: pass
   try:
    _v = _vsc
    if _nlt(_v,10) and _qneg and _r3_md and _r5_up and _d4_12: score *= 0.55
   except: pass
   try:
    _v = _secc
    if _v is not None and _v == 311 and _qpos and _r3_md and _r5_up and _d4_12: score *= 1.50
   except: pass
   try:
    _v = _secc
    if _v is not None and _v == 206 and _qpos and _r3_md and _r5_up and _d4_12: score *= 1.50
   except: pass
   try:
    _v = _cashc
    if _ngt(_v,5e9) and _qpos and _d4_8: score *= 0.85
   except: pass
   if _qsneg and _hyg_up3 and decline > 0.08: continue
   if _qpos and _hi_cape and _hyg_up3 and decline > 0.20: continue
   if _qsneg and _hi_vol and decline > 0.12: continue
   if _qsneg and _nlt(_r5,-0.05) and _hyg_dn3 and decline > 0.04: continue
   # ================================================================
   # ACTIVE BAKES — verified additive lifts on _qpos × decline cohorts.
   # All are wrapped in try/except to tolerate missing fundamentals.
   # Audit gate: ≥+0.0007 car_mdd lift with multi-mag confirmation
   # OR ≥+0.001 single-mag (memory: feedback_s001_hard_constraints).
   # ================================================================
   # BAKE-FC-R1657 (+0.00128): high operation-margin × small decline
   if _qpos and decline > 0.020 and decline < 0.050 and _ngt(_g1(_ops_z, 'operation_margin', 'six_months'),0.20): score += 0.04
   # BAKE-FG-R1664 (+0.00297): positive net-income-cont-ops growth × small decline
   if _qpos and decline > 0.020 and decline < 0.050 and _ngt(_g1(_ops_z, 'net_income_cont_ops_growth', 'one_year'),0.05): score += 0.02
   # BAKE-JBC-R1666 (+0.00138): has current deferred revenue × micro-decline
   if _qpos and decline > 0.015 and decline < 0.020 and _ngt(_g1(_bs_z, 'current_deferred_revenue', 'twelve_months'),0): score += 0.02
   # BAKE-J0-R1682 (+0.00106): has preferred-stock equity × micro-decline
   if _qpos and decline > 0.015 and decline < 0.020 and _ngt(_g1(_bs_z, 'preferred_stock_equity', 'twelve_months'),0): score += 0.04
   # BAKE BAKE-QNA1-R1699 (+0.00223): excise_taxes × _qneg × small-decline
   if _qneg and decline > 0.020 and decline < 0.050 and _ngt(_g1(_inc_z, 'excise_taxes', 'twelve_months'),1000000.0): score += 0.04
   # BAKE BAKE-DE-R1709 (+0.00415)
   try:
    if _qpos and decline > 0.060 and self._reg_double_panic: score *= 0.85
   except: pass
   # BAKE BAKE-QZJB1-R1749 (+0.00543)
   if _qzero and decline > 0.015 and decline < 0.020 and _ngt(_g1(_inc_z, 'impairment_of_capital_assets', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-QZMI2-R1750 (+0.00202)
   if _qzero and decline > 0.005 and decline < 0.012 and _ngt(_g1(_cfs_z, 'short_term_debt_issuance', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-QZA5-R1751 (+0.00500)
   if _qzero and decline > 0.012 and decline < 0.015 and _ngt(_g1(_bs_z, 'raw_materials', 'twelve_months'),1e6): score += 0.04
   # BAKE BAKE-QZX6-R1755 (+0.01117)
   if _qzero and decline > 0.020 and decline < 0.050 and _ngt(_g1(_bs_z, 'duefrom_related_parties_current', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-QZX2_1-R1756 (+0.01202)
   if _qzero and decline > 0.020 and decline < 0.050 and _ngt(_g1(_inc_z, 'insurance_and_claims', 'twelve_months'),1e6): score *= 1.1
   # BAKE BAKE-QSNX5-R1756 (+0.00128)
   if _qsneg and decline > 0.020 and decline < 0.050 and _ngt(_g1(_cfs_z, 'changes_in_account_receivables', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-QMIX5-R1758 (+0.00734)
   if _qzero and decline > 0.005 and decline < 0.012 and _ngt(_g1(_bs_z, 'total_deferred_credits_and_other_non_current_liabilities', 'twelve_months'),1e6): score *= 1.1
   # BAKE BAKE-QMIA11-R1759 (+0.00734)
   if _qzero and decline > 0.005 and decline < 0.012 and _ngt(_g1(_bs_z, 'electric_utility_plant', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-QJBA6-R1759 (+0.00351)
   if _qzero and decline > 0.015 and decline < 0.020 and _ngt(_g1(_cfs_z, 'net_ppe_purchase_and_sale', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-QMDA3-R1759 (+0.00319)
   if _qzero and decline > 0.040 and decline < 0.060 and _ngt(_g1(_bs_z, 'investmentin_financial_assets', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-QMDA6-R1759 (+0.00191)
   if _qzero and decline > 0.040 and decline < 0.060 and _ngt(_g1(_cfs_z, 'net_ppe_purchase_and_sale', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-QDPA1-R1759 (+0.00160)
   if _qzero and decline > 0.075 and decline < 0.150 and _ngt(_g1(_inc_z, 'other_special_charges', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-QPB3-R1760 (+0.00170)
   if _qpos and decline > 0.020 and decline < 0.050 and _ngt(_g1(_bs_z, 'dueto_related_parties_current', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-RGZ_VFL3-R1764 (+0.00340)
   if _qzero and decline > 0.020 and decline < 0.050 and self._reg_vxx_falling3 and _ngt(_g1(_cfs_z, 'earnings_losses_from_equity_investments', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-RGZ_VFL3_0-R1764 (+0.00745)
   if _qzero and decline > 0.020 and decline < 0.050 and self._reg_vxx_falling3 and _ngt(_g1(_cfs_z, 'sale_of_ppe', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-NRP_HD3_3-R1767 (+0.00191)
   if _qpos and decline > 0.020 and decline < 0.050 and self._reg_hyg_dn3 and _ngt(_g1(_bs_z, 'capital_lease_obligations', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-NRP_VRA3_3-R1767 (+0.00117)
   if _qpos and decline > 0.020 and decline < 0.050 and self._reg_vxx_rising3 and _ngt(_g1(_bs_z, 'capital_lease_obligations', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-TRP_HU3_6-R1769 (+0.00415)
   if _qpos and decline > 0.020 and decline < 0.050 and self._reg_hyg_up3 and _ngt(_g1(_inc_z, 'earnings_from_equity_interest', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-SEC310_QA_0-R1777 (+0.00479)
   if _qzero and decline > 0.012 and decline < 0.015 and _secc == 310 and _ngt(_g1(_inc_z, 'other_income_expense', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-FB5-R1780 (+0.00245)
   if _qpos and _d4_8 and _ngt(_g1(_cfs_z, 'net_investment_purchase_and_sale', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-F61213-R1781 (+0.00106)
   if _qpos and _d6_12 and _ngt(_g1(_cfs_z, 'gain_loss_on_sale_of_ppe', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-NV_V_GE1000_D2_4-R1788 (+0.00394)
   if _qpos and _v is not None and _v >= 1000 and _d2_4: score *= 1.05
   # BAKE BAKE-BC_BC_GT150_D6_12-R1791 (+0.00181)
   if _qpos and _bc is not None and _bc >= 150 and _d6_12: score *= 1.05
   # BAKE BAKE-A311BC2_BZ_4-R1797 (+0.00128)
   if _qpos and _secc == 311 and _bc >= 150 and decline > 0.020 and decline < 0.050 and _ngt(_g1(_bs_z, 'raw_materials', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-PA_SEC310_2-R1807 (+0.00138)
   if _qpos and _secc == 310 and _ngt(_g1(_bs_z, 'current_deferred_revenue', 'twelve_months'),1e6): score *= 1.05
   # BAKE BAKE-PZS_SEC311_4-R1811 (+0.00702)
   if _qzero and _secc == 311 and _ngt(_g1(_inc_z, 'other_income_expense', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-FPV_6-R1814 (+0.00340)
   if _qpos and _v >= 1000 and _ngt(_g1(_cfs_z, 'amortization_of_securities', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-FPV_2-R1814 (+0.00128)
   if _qpos and _v >= 1000 and _ngt(_g1(_cfs_z, 'proceeds_from_stock_option_exercised', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-PZV_5-R1815 (+0.00106)
   if _qzero and _v >= 1000 and _ngt(_g1(_inc_z, 'excise_taxes', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-FZV_4-R1816 (+0.00798)
   if _qzero and _v >= 1000 and _ngt(_g1(_bs_z, 'other_non_current_liabilities', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-FPV4_0-R1817 (+0.00138)
   if _qpos and _v >= 1000 and _ngt(_g1(_bs_z, 'investmentin_financial_assets', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-PZV3_3-R1817 (+0.00106)
   if _qzero and _v >= 1000 and _ngt(_g1(_cfs_z, 'earnings_losses_from_equity_investments', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-FZS_6-R1818 (+0.00191)
   if _qzero and _secc == 311 and _ngt(_g1(_cfs_z, 'change_in_other_current_assets', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-PZS4_SEC310_2-R1818 (+0.00106)
   if _qzero and _secc == 310 and _ngt(_g1(_cfs_z, 'changes_in_account_receivables', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-FPPS_4-R1820 (+0.00266)
   if _qpos and _secc == 311 and _ngt(_g1(_bs_z, 'preferred_shares_number', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-PZV5_3-R1824 (+0.00117)
   if _qzero and _v >= 1000 and _ngt(_g1(_cfs_z, 'earnings_losses_from_equity_investments', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-PZS9_SEC311_1-R1828 (+0.00106)
   if _qzero and _secc == 311 and _ngt(_g1(_bs_z, 'other_payable', 'twelve_months'),1e6): score += 0.02
   # BAKE BAKE-GTI_ZH_4-R1842 (+0.01181)
   if _qzero and self._reg_haccel is not None and self._reg_haccel > 0 and _ngt(_g1(_inc_z, 'excise_taxes', 'twelve_months'),1e6): entry_score_gate += -0.2
   # BAKE BAKE-GTI_HA-R1842 (+0.00170)
   if _qpos and self._reg_haccel is not None and self._reg_haccel > 0 and _ngt(_g1(_inc_z, 'excise_taxes', 'twelve_months'),1e6): entry_score_gate += -0.05
   # BAKE BAKE-GTI_HA005_6-R1843 (+0.00181)
   if _qpos and self._reg_haccel is not None and self._reg_haccel > 0.005 and _ngt(_g1(_bs_z, 'raw_materials', 'twelve_months'),1e6): entry_score_gate += -0.1
   # BAKE BAKE-EQ_9-R1851 (+0.00277)
   if _qpos and self._reg_haccel is not None and self._reg_haccel > 0 and _ngt(_g1(_inc_z, 'insurance_and_claims', 'twelve_months'),1e6): entry_score_quality += -0.1
   # BAKE BAKE-H_SCM_S311_HA_1-R1933 (+0.00287)
   if _qpos and _secc == 311 and self._reg_haccel and _ngt(_g1(_cfs_z, 'cash_from_discontinued_investing_activities', 'twelve_months'),1e6): score *= 1.14
   # BAKE BAKE-A_SD_S205_DP_HD14_0-R1974 (+0.00287)
   if _qpos and _secc == 205 and self._reg_double_panic and self._reg_hyg_dn14 and _ngt(_g1(_er_z, 'diluted_average_shares', 'twelve_months'),1e6): score *= 0.8
   # BAKE BAKE-B_SD_WZ_S308_DP_HD5_0-R1976 (+0.00128)
   if _qzero and _secc == 308 and self._reg_double_panic and self._reg_hyg_dn5 and _ngt(_g1(_inc_z, 'depreciation', 'twelve_months'),1e6): score *= 0.9
   # BAKE BAKE-B_SD_S309_DP_HD3_0-R1977 (+0.00128)
   if _qpos and _secc == 309 and self._reg_double_panic and self._reg_hyg_dn3 and _ngt(_g1(_inc_z, 'fee_revenue_and_other_income', 'twelve_months'),1e6): score *= 0.95
   # BAKE BAKE-SD_QPOS_S103_VF_HD5_0-R1996 (+0.00096)
   if _qpos and _secc == 103 and self._reg_vxx_falling3 and self._reg_hyg_dn5 and _ngt(_g1(_bs_z, 'stockholders_equity', 'twelve_months'),1e6): score *= 0.85
   # BAKE BAKE-SD_QZERO_S103_VF_HD14_2-R1999 (+0.00096)
   if _qzero and _secc == 103 and self._reg_vxx_falling3 and self._reg_hyg_dn14 and _ngt(_g1(_inc_z, 'total_expenses', 'twelve_months'),1e6): score *= 0.95
   # BAKE BAKE-SD_QPOS_S102_DP_VF_0-R2003 (+0.00202)
   if _qpos and _secc == 102 and self._reg_double_panic and self._reg_vxx_falling3 and _ngt(_g1(_cfs_z, 'amortization', 'twelve_months'),1e6): score *= 0.95
   # BAKE BAKE-SD_QZERO_S309_DP_Q3_0-R2013 (+0.00096)
   if _qzero and _secc == 309 and self._reg_double_panic and self._reg_qqq_up3 and _ngt(_g1(_inc_z, 'general_and_administrative_expense', 'twelve_months'),1e6): score *= 0.85
   # BAKE BAKE-SD_QZERO_S309_HA_HD5_1-R2018 (+0.00128)
   if _qzero and _secc == 309 and self._reg_haccel and self._reg_hyg_dn5 and _ngt(_g1(_inc_z, 'total_revenue', 'twelve_months'),1e6): score *= 0.95
   # BAKE BAKE-B_SD_WZ_S206_HD3_Q3_2-R2025 (+0.00245)
   if _qzero and _secc == 206 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_inc_z, 'impairment_of_capital_assets', 'twelve_months'),1e6): score *= 0.8
   # BAKE BAKE-SD_QZERO_S308_HD3_VF_1-R2033 (+0.00202)
   if _qzero and _secc == 308 and self._reg_hyg_dn3 and self._reg_vxx_falling3 and _ngt(_g1(_cfs_z, 'operating_gains_losses', 'twelve_months'),1e6): score *= 0.91
   # BAKE BAKE-SD_QZERO_S102_HA_HD3_1-R2036 (+0.00149)
   if _qzero and _secc == 102 and self._reg_haccel and self._reg_hyg_dn3 and _ngt(_g1(_cfs_z, 'net_other_financing_charges', 'twelve_months'),1e6): score *= 0.94
   # BAKE BAKE-SD2_QZERO_S206_HD14_Q3_2F-R2043 (+0.00064 compound 2-factor lever-transfer)
   if _qzero and _secc == 206 and self._reg_hyg_dn14 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'operating_gains_losses', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): score *= 0.92
   # BAKE BAKE-SD2_QZERO_S205_HD3_Q3_2F-R2045 (+0.00255 compound 2F new sector)
   if _qzero and _secc == 205 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): score *= 0.91
   # BAKE BAKE-SD2G_QZERO_S102_HD3_Q3_2F_QR-R2081 (+0.00064 quick_ratio<0.5 gate)
   if _qzero and _secc == 102 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _nlt(_g1(_ops_z, 'quick_ratio', 'one_year'),0.5): score *= 0.94
   # BAKE BAKE-CV_MM_D07-R2172 (+0.00074)
   try:
    if _qpos and self._reg_haccel and decline > 0.07: conv *= 1.12
   except: pass
   # BAKE BAKE-CV_D006_NRW-R2173 (+0.00117)
   try:
    if _qpos and self._reg_haccel and decline > 0.06: conv *= 1.1
   except: pass
   # BAKE BAKE-CV_S102_HD14-R2174 (+0.00096)
   try:
    if _qpos and _secc == 102 and self._reg_hyg_dn14 and decline > 0.05: conv *= 1.1
   except: pass
   # BAKE BAKE-CV_D02_HD14-R2175 (+0.00128)
   try:
    if _qpos and self._reg_hyg_dn14 and decline > 0.02: conv *= 1.13
   except: pass
   # BAKE BAKE-CV_QZ_S311_HD14_D04-R2176 (+0.00074)
   try:
    if _qzero and _secc == 311 and self._reg_hyg_dn14 and decline > 0.04: conv *= 1.13
   except: pass
   # BAKE BAKE-CV_VXXF_HARVEST-R2178 (+0.00106)
   try:
    if _qpos and self._reg_vxx_falling3 and decline > 0.05: conv *= 1.15
   except: pass
   # BAKE BAKE-CV_QZ_HD3_DEEPER-R2179 (+0.00085)
   try:
    if _qzero and self._reg_hyg_dn3 and decline > 0.05: conv *= 1.25
   except: pass
   # BAKE BAKE-CV_HD14_HD3_D04-R2180 (+0.00074)
   try:
    if _qpos and self._reg_hyg_dn14 and self._reg_hyg_dn3 and decline > 0.04: conv *= 1.15
   except: pass
   # BAKE BAKE-CV_HA_HD5_D04-R2182 (+0.00447)
   try:
    if _qpos and self._reg_haccel and self._reg_hyg_dn5 and decline > 0.04: conv *= 1.12
   except: pass
   # BAKE BAKE-CV_QZ_Q3_D04-R2194 (+0.00511)
   try:
    if _qzero and self._reg_qqq_up3 and decline > 0.04: conv *= 1.08
   except: pass
   # --- ENTRY INJECT POINT ---  ← gen scripts insert probe code below
   try:
    if _ops_z and decline > .05:
     _rg = _rg1yc
     if _rg > .15: score *= 1.15
   except: pass
   try:
    if _ops_z:
     _rg8 = _rg1yc
     if _rg8 and _rg8>.15 and _hyg_dn5:
      score *= 1.20
   except: pass
   try:
    if _ops_z:
     _roe9 = _roe1y_c
     if _roe9 is not None and _roe9 < -.05 and _qqq_dn3:
      continue
   except: pass
   try:
    if _vr_z:
     _peg11 = _pegr
     if _peg11 is not None and 0<_peg11<1.2 and _hyg_dn5:
      score *= 1.15
   except: pass
   try:
    if _ops_z and decline > .18:
     _gm12 = _gm1yc
     _rg12 = _rg1yc
     if _gm12 and _gm12>.40 and _rg12 and _rg12>.15:
      score *= 1.25
   except: pass
   try:
    if _ops_z and decline > .18:
     _gm13 = _gm1yc
     _rg13 = _rg1yc
     if _gm13 and _gm13>.40 and _rg13 and _rg13>.15:
      score *= 1.40
   except: pass
   try:
    if _ops_z:
     _rg14 = _rg1yc
     if _rg14 and _rg14>.15:
      if window and len(window)>=20:
       _ma5 = sum(f_(b.close) for b in window[-5:])/5
       _ma20 = sum(f_(b.close) for b in window)/20
       if _ma5 < _ma20*0.92:
        score *= 1.25
   except: pass
   try:
    if _ops_z:
     _roe16 = _roe1y_c
     if _roe16 and _roe16>.20 and _qs and len(_qs)>=10 and _hs and len(_hs)>=5:
      _qd16 = _qd10
      _bd16 = _bd5
      if _qd16<-.07 and _bd16<0:
       score *= 1.25
      if _qd16<-.07 and _bd16<0:
       score *= 1.21
   except: pass
   try:
    if _ers_z and _vr_z:
     _depsg19 = f_(_ers_z.diluted_eps_growth.one_year)
     _pe19 = _pec
     if _depsg19 is not None and _depsg19>.35 and _pe19 is not None and 0<_pe19<15:
      score *= 1.20
   except: pass
   try:
    if _ops_z:
     _rg23 = _rg1yc
     if _rg23 is not None and _rg23<-.20 and decline>.10:
      continue
   except: pass
   try:
    if _inc_z and _cfs_z and _ops_z:
     _ni22 = f_(_inc_z.net_income.twelve_months)
     _fc22 = f_(_cfs_z.free_cash_flow.twelve_months)
     _de22 = f_(_ops_z.total_debt_equity_ratio.one_year)
     if _ni22 is not None and _ni22<0 and _fc22 is not None and _fc22<0 and _de22 is not None and _de22>2.0:
      continue
   except: pass
   try:
    if _ops_z:
     _rg22 = _rg1yc
     if _rg22 and _rg22>.20 and _hs and len(_hs)>=10:
      _bd22 = _bd10
      if _bd22>.02:
       score *= 0.90
   except: pass
   try:
    if _ops_z:
     _gm24 = _gm1yc
     if _gm24 and _gm24>.40 and _hs and len(_hs)>=5:
      _bd24 = _bd5
      if _bd24>.015:
       score *= 0.87
   except: pass
   try:
    if _ops_z and _vr_z:
     _gm25 = _gm1yc
     _pe25 = _pec
     if _gm25 and _gm25>.40 and _qs and len(_qs)>=10:
      _qd25 = _qd10
      if _qd25>.05:
       score *= 0.85
     if _gm25 and _gm25>.50 and _pe25 is not None and 0<_pe25<10:
      if decline>.15:
       score *= 1.13
      if decline>.30:
       score *= 1.20
     if _gm25 and _gm25>.40 and _pe25 is not None and 0<_pe25<15:
      if decline>.20:
       score *= 1.13
      if decline>.35:
       score *= 1.20
   except: pass
   try:
    if _ops_z:
     _qr26 = f_(_ops_z.quick_ratio.one_year)
     _rg26 = _rg1yc
     if _qr26 is not None and _qr26<.5 and _rg26 is not None and _rg26<.05 and decline>.05:
      continue
   except: pass
   try:
    if _ops_z:
     _rg26b = _rg1yc
     if _rg26b and _rg26b>.30:
      if _hl_closes is not None and _hl_len>=120:
       _w120_first = _hl_closes[-120]
       if _w120_first > 0:
        _r120 = (_bc - _w120_first) / _w120_first
        if _r120<-.30:
         score *= 1.20
   except: pass
   if _vol20 is not None and _vol20 > .06: conv *= 0.50
   try:
    if _ops_z:
     _rg29 = _rg1yc
     if _rg29 and _rg29>.15 and _qs and len(_qs)>=20:
      _qd20br = _qd20
      if _qd20br>.10 and decline<.10:
       score *= 0.80
   except: pass
   try:
    if _hs and len(_hs)>=20:
     _bra = [f_(_hs[i].close)/f_(_hs[i-1].close)-1 for i in range(1,20) if f_(_hs[i-1].close)>0]
     if _bra:
      _bv = (sum(x*x for x in _bra)/len(_bra))**0.5
      if _bv<.002 and decline>.10:
       score *= 1.10
   except: pass
   try:
    if _cfs_z:
     _v44 = f_(_cfs_z.change_in_account_payable.twelve_months)
     if _v44 > 1e9 and decline > .05: score *= 1.06
   except: pass
   try:
    if _vr_z:
     _v45 = f_(_vr_z.first_year_estimated_eps_growth)
     if _v45 > 5 and decline > .10: score *= 1.10
   except: pass
   try:
    if _qs and len(_qs) >= 5:
     if _qd5 < -0.03 and decline > .03: score *= 1.25
    if _hs and len(_hs) >= 5:
     _bd5x = _bd5
     if _qd5 < -0.03 and _bd5x < 0 and decline > .05: score *= 1.20
   except: pass
   try:
    if (_qs and len(_qs) >= 5 and _hs and len(_hs) >= 5 and
        len(window) >= 10):
     _qd5c = _qd5
     _bd5c = _bd5
     _v_recent = sum(_wvol10[-3:])/3
     _v_avg = sum(_wvol10)/10
     if _qd5c < -0.04 and _bd5c < 0 and decline > .09 and _v_recent / max(.01, _v_avg) > 1.5:
      score *= 2.20
   except: pass
   try:
    if _ers_z is not None and decline > .15:
     _v63 = f_(_ers_z.book_value_per_share_growth.one_year)
     if _v63 > 0.15: score *= 1.13
   except: pass
   try:
    _v = _vsc
    if _v < 60 and _qzero and _d6_12: wt_tilt *= 0.7
   except: pass
   # ================================================================
   # ENTRY-SIGNAL BAKE BLOCK — new bakes (post-2026-05-09) inject HERE
   # via apply_bake_to_base. Each is additive on entry_signal, summed
   # into score below. UNLIKE legacy score+= bakes (mid-chain), these
   # are NOT amplified by the post-INJECT multiplicative tail — their
   # delta from search reflects the position they live in. This is the
   # canonical "score-system" path that gen scripts target via
   # lever='entry_signal'.
   # BAKE BAKE-ERDP_1-R1880 (+0.00138)
   if _qpos and self._reg_double_panic and _ngt(_g1(_cfs_z, 'other_non_cash_items', 'twelve_months'),1e6): entry_score_regime += -0.025
   # BAKE BAKE-A_EQ_S311_DP_1-R1944 (+0.00074)
   if _qpos and _secc == 311 and self._reg_double_panic and _ngt(_g1(_cfs_z, 'net_investment_purchase_and_sale', 'twelve_months'),1e6): entry_score_quality += -0.1
   # BAKE BAKE-H_EQ_WZ_S311_DP_1-R1945 (+0.00064)
   if _qzero and _secc == 311 and self._reg_double_panic and _ngt(_g1(_inc_z, 'other_income_expense', 'twelve_months'),1e6): entry_score_quality += -0.1
   # BAKE BAKE-A_EM_S311_HA_1-R1947 (+0.00064)
   if _qpos and _secc == 311 and self._reg_haccel and _ngt(_g1(_inc_z, 'excise_taxes', 'twelve_months'),1e6): entry_score_mtf += -0.667
   # BAKE BAKE-D_EM_WZ_S311_DP_2-R1948 (+0.00500)
   if _qzero and _secc == 311 and self._reg_double_panic and _ngt(_g1(_cfs_z, 'short_term_debt_payments', 'twelve_months'),1e6): entry_score_mtf += -0.25
   # BAKE BAKE-D_EM_WZ_S310_DP_0-R1950 (+0.00511)
   if _qzero and _secc == 310 and self._reg_double_panic and _ngt(_g1(_bs_z, 'total_debt', 'twelve_months'),1e6): entry_score_mtf += -0.5
   # BAKE BAKE-B_EM_WZ_S311_HD5_1-R1951 (+0.00479)
   if _qzero and _secc == 311 and self._reg_hyg_dn5 and _ngt(_g1(_inc_z, 'impairment_of_capital_assets', 'twelve_months'),1e6): entry_score_mtf += -0.333
   # BAKE BAKE-C_EG_WZ_S310_DP_2-R1958 (+0.00138)
   if _qzero and _secc == 310 and self._reg_double_panic and _ngt(_g1(_cfs_z, 'proceeds_from_stock_option_exercised', 'twelve_months'),1e6): entry_score_gate += -0.125
   # BAKE BAKE-D_EM_WZ_S205_HA_2-R1961 (+0.00170)
   if _qzero and _secc == 205 and self._reg_haccel and _ngt(_g1(_bs_z, 'preferred_stock_equity', 'twelve_months'),1e6): entry_score_mtf += -0.5
   # BAKE BAKE-F_EM_WZ_S308_DP_1-R1963 (+0.00074)
   if _qzero and _secc == 308 and self._reg_double_panic and _ngt(_g1(_bs_z, 'other_payable', 'twelve_months'),1e6): entry_score_mtf += -0.15
   # BAKE BAKE-C_EM_S205_DP_HD14_2-R1967 (+0.00053)
   if _qpos and _secc == 205 and self._reg_double_panic and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'proceeds_from_stock_option_exercised', 'twelve_months'),1e6): entry_score_mtf += -0.5
   # BAKE BAKE-D_EM_WZ_S205_HD5_HD14_1-R1973 (+0.00202)
   if _qzero and _secc == 205 and self._reg_hyg_dn5 and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'short_term_debt_issuance', 'twelve_months'),1e6): entry_score_mtf += -0.2
   # BAKE BAKE-G_EM_WZ_S206_DP_HD14_1-R1978 (+0.00245)
   if _qzero and _secc == 206 and self._reg_double_panic and self._reg_hyg_dn14 and _ngt(_g1(_inc_z, 'other_income_expense', 'twelve_months'),1e6): entry_score_mtf += -0.25
   # BAKE BAKE-E_EM_S205_HA_HD14_HD5_1-R1983 (+0.00106)
   if _qpos and _secc == 205 and self._reg_haccel and self._reg_hyg_dn14 and self._reg_hyg_dn5 and _ngt(_g1(_bs_z, 'raw_materials', 'twelve_months'),1e6): entry_score_mtf += -0.2
   # BAKE BAKE-E_EM_WZ_S103_VF_HD5_0-R1997 (+0.00096)
   if _qzero and _secc == 103 and self._reg_vxx_falling3 and self._reg_hyg_dn5 and _ngt(_ops_z.capital_expenditure_annual_5_yr_growth.one_year,1e6): entry_score_mtf += -0.2
   # BAKE BAKE-F_EM_WZ_S102_DP_HD5_2-R1998 (+0.00120)
   if _qzero and _secc == 102 and self._reg_double_panic and self._reg_hyg_dn5 and _ngt(_g1(_bs_z, 'capital_lease_obligations', 'twelve_months'),1e6): entry_score_mtf += -0.075
   # BAKE BAKE-F_EM_WZ_S102_HA_Q3_1-R2001 (+0.00202)
   if _qzero and _secc == 102 and self._reg_haccel and self._reg_qqq_up3 and _ngt(_g1(_bs_z, 'other_payable', 'twelve_months'),1e6): entry_score_mtf += -0.1
   # BAKE BAKE-I_EQ_WZ_S102_HA_HD14_2-R2011 (+0.00096)
   if _qzero and _secc == 102 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'net_other_financing_charges', 'twelve_months'),1e6): entry_score_quality += -0.075
   # BAKE BAKE-H_EM_WZ_S311_VF_HD3_0-R2016 (+0.00085)
   if _qzero and _secc == 311 and self._reg_vxx_falling3 and self._reg_hyg_dn3 and _ngt(_g1(_bs_z, 'cash_and_cash_equivalents', 'twelve_months'),1e6): entry_score_mtf += -0.25
   # REVERTED BAKE-F_EM_S206_HA_Q3_1-R2026 (false-positive: silent bake, fingerprint matched NOOP)
   # BAKE BAKE-J_EG_WZ_S308_HD14_HD3_1-R2027 (+0.00128)
   if _qzero and _secc == 308 and self._reg_hyg_dn14 and self._reg_hyg_dn3 and _ngt(_g1(_cfs_z, 'gain_loss_on_investment_securities', 'twelve_months'),1e6): entry_score_gate += -0.1
   # BAKE BAKE-EM2_QZERO_S311_HD3_Q3_2F-R2040 (+0.00117 compound 2-factor)
   if _qzero and _secc == 311 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'operating_gains_losses', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): entry_score_mtf += -0.2
   # BAKE BAKE-EM2_QZERO_S310_HA_Q3_2F_VRFY-R2045 (+0.00181 R2044 verified)
   if _qzero and _secc == 310 and self._reg_haccel and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6): entry_score_mtf += -0.075
   # BAKE BAKE-EM2R_QZERO_S311_HD3_Q3_2F_PB-R2065 (+0.00128 valuation-ratio 2F)
   if _qzero and _secc == 311 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_vr_z.pb_ratio,3): entry_score_mtf += -0.15
   # BAKE BAKE-EM2R_QZERO_S102_HA_HD14_2F_NI_PS-R2067 (+0.00074 valuation-ratio NI×ps)
   if _qzero and _secc == 102 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_vr_z.ps_ratio,5): entry_score_mtf += -0.2
   # BAKE BAKE-EM2G_QZERO_S311_HA_HD14_2F_NM-R2079 (+0.00128 NM compound, R2077 verified)
   if _qzero and _secc == 311 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _nlt(_g1(_ops_z, 'net_margin', 'three_months'),0.05): entry_score_mtf += -0.15
   # BAKE BAKE-EG2G_QZERO_S308_HA_HD14_2F_ROA_NI_EG-R2098 (+0.00383)
   if _qzero and _secc == 308 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_g1(_ops_z, 'roa', 'one_year'),0.20): entry_score_gate += -0.05
   # BAKE BAKE-EG2G_QPOS_S102_HA_Q3_2F_ROA_NI_VRG-R2107 (+0.00085)
   if _qpos and _secc == 102 and self._reg_haccel and self._reg_qqq_up3 and _ngt(_g1(_inc_z, 'net_income', 'twelve_months'),1e6) and _ngt(_g1(_ops_z, 'roa', 'one_year'),0.20): entry_score_gate += -0.1
   # BAKE BAKE-EG2G_QPOS_S102_VF_Q3_2F_ROA_OCF_VRG-R2108 (+0.00128)
   if _qpos and _secc == 102 and self._reg_vxx_falling3 and self._reg_qqq_up3 and _ngt(_g1(_cfs_z, 'operating_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_ops_z, 'roa', 'one_year'),0.20): entry_score_gate += -0.1
   # BAKE BAKE-EG2G_QPOS_S102_HA_HD14_2F_TR_OCF_EG-R2131 (+0.00191)
   if _qpos and _secc == 102 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'operating_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_ops_z, 'tax_rate', 'six_months'),0.35): entry_score_gate += -0.05
   # BAKE BAKE-EG2G_QPOS_S308_HA_HD14_2F_TR_FCF_EG-R2132 (+0.00255)
   if _qpos and _secc == 308 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_ops_z, 'tax_rate', 'six_months'),0.35): entry_score_gate += -0.125
   # BAKE BAKE-EG2G_QPOS_S206_HA_HD14_2F_PAYOUT_FCF_EG-R2136 (+0.00128)
   if _qpos and _secc == 206 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'free_cash_flow', 'twelve_months'),1e6) and _ngt(_vr_z.payout_ratio,0.7): entry_score_gate += -0.075
   # BAKE BAKE-EG2G_QPOS_S308_HA_HD14_2F_DPO_OCF_EG-R2139 (+0.00064)
   if _qpos and _secc == 308 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_g1(_cfs_z, 'operating_cash_flow', 'twelve_months'),1e6) and _ngt(_g1(_ops_z, 'days_in_payment', 'one_year'),60): entry_score_gate += -0.075
   # BAKE BAKE-EG2G_QPOS_S206_HD3_Q3_2F_COR_HOT_125-R2157 (+0.00064)
   try:
    if _qpos and _secc == 206 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_cfs_z.operating_cash_flow.twelve_months,1e6) and _ngt(_inc_z.cost_of_revenue.twelve_months,1e10): entry_score_gate += -0.13
   except: pass
   # BAKE BAKE-EG2G_QPOS_S206_HA_HD14_2F_COR_OCF_DEEP-R2159 (+0.00064)
   try:
    if _qpos and _secc == 206 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_cfs_z.operating_cash_flow.twelve_months,1e6) and _ngt(_inc_z.cost_of_revenue.twelve_months,1e10): entry_score_gate += -0.125
   except: pass
   # BAKE BAKE-EG2G_QPOS_S206_HD3_Q3_2F_NBEG_RETEST-R2162 (+0.00319)
   try:
    if _qpos and _secc == 206 and self._reg_hyg_dn3 and self._reg_qqq_up3 and _ngt(_inc_z.net_income.twelve_months,1e6) and _ngt(_ers_z.normalized_basic_eps_growth.one_year,0.10): entry_score_gate += -0.125
   except: pass
   # BAKE BAKE-EG2G_QPOS_S308_HA_HD14_2F_CRG_OCF-R2163 (+0.00064)
   try:
    if _qpos and _secc == 308 and self._reg_haccel and self._reg_hyg_dn14 and _ngt(_cfs_z.operating_cash_flow.twelve_months,1e6) and _ngt(_ops_z.cash_ratio_growth.one_year,0.10): entry_score_gate += -0.125
   except: pass
   # --- ENTRY SIGNAL BAKE INSERT ---
   # ================================================================
   # ACCUMULATOR SUMMATION (2026-05-09 v8 — R1718 weight explore 3/5):
   # entry_signal       × 1.0  (baseline)
   # entry_score_mtf    × 0.3  (DIMINISHED per user — kept low)
   # entry_score_regime × 10.0 (AMPLIFIED — regime-dominant)
   # entry_score_conv   × 1.0
   # entry_score_quality× 1.0
   # 5-round weight-explore plan:
   #   R1716/R1717: cancelled mid-flight (close>prev_high diminish broke
   #                strategy; NOOP 0.570 vs 3.229 baseline)
   #   R1718 (this): regime × 10 with close>prev_high RESTORED to 1.0
   #   R1719: conv × 10
   #   R1720: quality × 10
   # ================================================================
   score += (1.0 * entry_signal
             + 0.3 * entry_score_mtf
             + 10.0 * entry_score_regime
             + 1.0 * entry_score_conv
             + 1.0 * entry_score_quality)
   # P4 (2026-05-10): multiplicative gate applied AFTER additive sum.
   # entry_score_gate=0.0 default → no-op. Probes contribute small +=values.
   # CLAMP to [-0.5, 0.5] so a single mis-fired stack can't blow score out.
   score *= (1.0 + max(-0.5, min(0.5, entry_score_gate)))
   candidates.append((sym, score, conv, wt_tilt))
  if not candidates: return
  # ===================================================================
  # RANKING + SIZING — pure score DESC; weight_score per candidate.
  # weight_score = min(WT_CAP, conv * tilt_clamped * WT_PER_CONV)
  # is GUARANTEED < WT_CAP=0.07 by construction. Inner loop uses
  # weight_score directly (no softmax — user 2026-05-09).
  # ===================================================================
  WT_TILT_CAP = 2.0
  # Compute weight_score per candidate (deployable weight, capped at WT_CAP).
  candidates_w = []
  for sym, score, conv, wt_tilt in candidates:
   _tilt_clamped = max(0.1, min(WT_TILT_CAP, wt_tilt))
   weight_score = min(WT_CAP, conv * _tilt_clamped * WT_PER_CONV)
   candidates_w.append((sym, score, conv, wt_tilt, weight_score))
  ranked = sorted(candidates_w, key=lambda c: c[1], reverse=True)
  total_value = f_(self.portfolio.total_portfolio_value) or 1
  existing_pct = sum(abs(f_(h.holdings_value))/total_value for h in self.portfolio.values()
                     if h.invested and h.symbol not in self._hedge_syms)
  remaining_budget = max(0, gross_target - existing_pct)
  if remaining_budget <= 0: return
  # Allocate top-ranked candidates greedily until budget exhausted.
  new_targets = []
  used = 0.0
  for sym, score, conv, wt_tilt, weight_score in ranked:
   if used >= remaining_budget: break
   w = min(weight_score, remaining_budget - used)
   if w < MIN_WT: continue
   new_targets.append((sym, w))
   used += w
  if not new_targets: return
  self.pending_entries = [PortfolioTarget(sym, min(WT_CAP, w)) for sym, w in new_targets]
 @staticmethod
 def _fv(obj, attr, timeframe):
  if obj is None: return None
  try:
   field = g_(obj, attr, None)
   if not field: return None
   val = g_(field, timeframe, None) if timeframe else field
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
