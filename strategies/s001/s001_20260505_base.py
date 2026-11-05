from AlgorithmImports import *
import math
f_=float
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
def _try_score_bake_qaccel(score, alias, attrs, gates, qaccel, qa_lo, qa_hi, decline, d_lo, d_hi, mag, regime=True):
 if alias is None or not regime: return score
 if qaccel is None or not (qa_lo < qaccel < qa_hi): return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 try:
  obj = alias
  for p in attrs:
   obj = getattr(obj, p, None)
   if obj is None: return score
  v = float(obj)
  for op, thr in gates:
   if op == '>' and not (v > thr): return score
   if op == '<' and not (v < thr): return score
   if op == '==' and not (v == thr): return score
  score *= mag
 except: pass
 return score
def _try_score_bake_v2f(score, alias_a, attrs_a, op_a, thr_a, alias_b, attrs_b, op_b, thr_b, decline, d_lo, d_hi, mag, regime=True):
 if alias_a is None or alias_b is None or not regime: return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 try:
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
  ca = (op_a == '>' and va > thr_a) or (op_a == '<' and va < thr_a)
  cb = (op_b == '>' and vb > thr_b) or (op_b == '<' and vb < thr_b)
  if ca and cb:
   score *= mag
 except: pass
 return score
def _try_score_bake_v1(score, alias, attrs, op, thr, decline, d_lo, d_hi, mag, regime=True):
 if alias is None or not regime: return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 try:
  obj = alias
  for p in attrs:
   obj = getattr(obj, p, None)
   if obj is None: return score
  v = float(obj)
  if (op == '>' and v > thr) or (op == '<' and v < thr) or (op == '==' and v == thr):
   score *= mag
 except: pass
 return score
def _try_skip_bake(alias, attrs, gates, decline, d_lo, d_hi, regime=True):
 if alias is None or not regime: return False
 if d_lo is not None and not (decline > d_lo): return False
 if d_hi is not None and not (decline < d_hi): return False
 try:
  obj = alias
  for p in attrs:
   obj = getattr(obj, p, None)
   if obj is None: return False
  v = float(obj)
  for op, thr in gates:
   if op == '>' and not (v > thr): return False
   if op == '<' and not (v < thr): return False
   if op == '==' and not (v == thr): return False
  return True
 except: return False
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
def _try_score_v1c_gt(score, v, thr, decline, d_lo, d_hi, mag, regime=True):
 if v is None or not regime or not (v > thr): return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 return score * mag
def _try_score_v1c_lt(score, v, thr, decline, d_lo, d_hi, mag, regime=True):
 if v is None or not regime or not (v < thr): return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 return score * mag
def _try_score_v1c_eq(score, v, thr, decline, d_lo, d_hi, mag, regime=True):
 if v is None or not regime or v != thr: return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 return score * mag
def _try_score_qaccel_c_gt(score, v, thr, qaccel, qa_lo, qa_hi, decline, d_lo, d_hi, mag, regime=True):
 if v is None or not regime or not (v > thr): return score
 if qaccel is None or not (qa_lo < qaccel < qa_hi): return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 return score * mag
def _try_score_qaccel_c_lt(score, v, thr, qaccel, qa_lo, qa_hi, decline, d_lo, d_hi, mag, regime=True):
 if v is None or not regime or not (v < thr): return score
 if qaccel is None or not (qa_lo < qaccel < qa_hi): return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 return score * mag
def _try_score_qaccel_c_range(score, v, vlo, vhi, qaccel, qa_lo, qa_hi, decline, d_lo, d_hi, mag, regime=True):
 if v is None or not regime or not (vlo < v < vhi): return score
 if qaccel is None or not (qa_lo < qaccel < qa_hi): return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 return score * mag
def _try_score_bake_v2f_v(score, va, op_a, thr_a, vb, op_b, thr_b, decline, d_lo, d_hi, mag, regime=True):
 if va is None or vb is None or not regime: return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 ca = (op_a == '>' and va > thr_a) or (op_a == '<' and va < thr_a) or (op_a == '==' and va == thr_a)
 cb = (op_b == '>' and vb > thr_b) or (op_b == '<' and vb < thr_b) or (op_b == '==' and vb == thr_b)
 if ca and cb: score *= mag
 return score
def _try_score_qaccel_2f_sec_v(score, sec_v, sector_eq, fund_v, vlo, vhi, qaccel, qa_lo, qa_hi, decline, d_lo, d_hi, mag, regime=True):
 if sec_v is None or sec_v != sector_eq or fund_v is None or not regime: return score
 if qaccel is None or not (qa_lo < qaccel < qa_hi): return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 if not (vlo < fund_v < vhi): return score
 score *= mag
 return score
def _try_lever_bake_c(lever_val, v, op, thr, mag, regime=True):
 if v is None or not regime: return lever_val
 if not ((op == '>' and v > thr) or (op == '<' and v < thr) or (op == '==' and v == thr)): return lever_val
 lever_val *= mag
 return lever_val
def _try_score_qaccel_2f_sec(score, sec_v, sector_eq, alias_b, attrs_b, vlo, vhi, qaccel, qa_lo, qa_hi, decline, d_lo, d_hi, mag, regime=True):
 if sec_v is None or sec_v != sector_eq or alias_b is None or not regime: return score
 if qaccel is None or not (qa_lo < qaccel < qa_hi): return score
 if d_lo is not None and not (decline > d_lo): return score
 if d_hi is not None and not (decline < d_hi): return score
 try:
  obj = alias_b
  for p in attrs_b:
   obj = getattr(obj, p, None)
   if obj is None: return score
  vb = float(obj)
  if not (vlo < vb < vhi): return score
  score *= mag
 except: pass
 return score
def _try_skip_2f_v(va, op_a, thr_a, vb, op_b, thr_b, decline, d_lo, d_hi=None):
 if va is None or vb is None: return False
 if d_lo is not None and not (decline > d_lo): return False
 if d_hi is not None and not (decline < d_hi): return False
 if not ((op_a == '>' and va > thr_a) or (op_a == '<' and va < thr_a)): return False
 if not ((op_b == '>' and vb > thr_b) or (op_b == '<' and vb < thr_b)): return False
 return True
def _try_skip_bake_c(v, gates, decline, d_lo, d_hi, regime=True):
 if v is None or not regime: return False
 if d_lo is not None and not (decline > d_lo): return False
 if d_hi is not None and not (decline < d_hi): return False
 for op, thr in gates:
  if op == '>' and not (v > thr): return False
  if op == '<' and not (v < thr): return False
  if op == '==' and not (v == thr): return False
 return True
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
  try: qa = list(self.history[TradeBar](self._qqq_sym, 60, _RD))
  except (AttributeError, KeyError, ValueError): qa = []
  try: ha = list(self.history[TradeBar](self._bond_sym, 30, _RD))
  except (AttributeError, KeyError, ValueError): ha = []
  def _r(bars, n):
   if len(bars) <= n or f_(bars[-n].close) <= 0: return None
   return (f_(bars[-1].close) - f_(bars[-n].close)) / f_(bars[-n].close)
  self._qa_scan = qa
  self._ha_scan = ha
  self._qd5 = _r(qa, 5)
  self._qd10 = _r(qa, 10)
  self._qd20 = _r(qa, 20)
  self._bd5 = _r(ha, 5)
  self._bd10 = _r(ha, 10)
  try:
   if qa and len(qa) >= 7 and f_(qa[-3].close) > 0 and f_(qa[-7].close) > 0:
    _qr3c = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close)
    _qr7c = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close)
    self._qaccel = _qr3c - _qr7c
   else:
    self._qaccel = None
  except (TypeError, ZeroDivisionError, AttributeError, IndexError): self._qaccel = None
  def _qd(n):
   try: return f_(qa[-1].close) < f_(qa[-n].close) if (qa and len(qa)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  def _hd(n):
   try: return f_(ha[-1].close) < f_(ha[-n].close) if (ha and len(ha)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  def _hu(n):
   try: return f_(ha[-1].close) > f_(ha[-n].close) if (ha and len(ha)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  self._reg_qqq_dn3 = bool(qa and len(qa)>=3 and f_(qa[-1].close)<f_(qa[-2].close)<f_(qa[-3].close))
  self._reg_qqq_up3 = bool(qa and len(qa)>=3 and f_(qa[-1].close)>f_(qa[-2].close)>f_(qa[-3].close))
  self._reg_hyg_dn3 = bool(ha and len(ha)>=3 and f_(ha[-1].close)<f_(ha[-2].close)<f_(ha[-3].close))
  self._reg_hyg_up3 = bool(ha and len(ha)>=3 and f_(ha[-1].close)>f_(ha[-2].close)>f_(ha[-3].close))
  self._reg_qqq_dn5 = _qd(5); self._reg_qqq_dn7 = _qd(7)
  self._reg_hyg_dn5 = _hd(5); self._reg_hyg_dn14 = _hd(14)
  self._reg_hyg_up5 = _hu(5)
  self._reg_double_panic = bool(qa and len(qa)>=3 and f_(qa[-1].close)<f_(qa[-3].close)) and self._reg_hyg_dn5
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
 def _scan_exits(self, data, equities):
  for sym in equities:
   pos = self.portfolio[sym]
   if not pos.invested: continue
   pnl = f_(pos.unrealized_profit_percent)
   stop = self.tune['stop_default']
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
   try: _vsc = float(_ac_z.value_score) if _ac_z else None
   except: _vsc=None
   try: _fcfg1yc = float(_ops_z.fcf_growth.one_year) if _ops_z else None
   except: _fcfg1yc=None
   try: _wipc = float(_bs_z.work_in_process.twelve_months) if _bs_z else None
   except: _wipc=None
   try: _woc = float(_inc_z.write_off.twelve_months) if _inc_z else None
   except: _woc=None
   try: _evta3yc = float(_vr_z.ev_to_total_assets_3_year_growth) if _vr_z else None
   except: _evta3yc=None
   try: _cashc = float(_bs_z.cash.twelve_months) if _bs_z else None
   except: _cashc=None
   try: _roic1yc = float(_ops_z.roic.one_year) if _ops_z else None
   except: _roic1yc=None
   try: _fcfsr1yc = float(_ops_z.fcf_sales_ratio.one_year) if _ops_z else None
   except: _fcfsr1yc=None
   try: _nig1yc = float(_ops_z.net_income_growth.one_year) if _ops_z else None
   except: _nig1yc=None
   stop = _try_lever_bake_c(stop, _wipc, '<', 1e9, 0.9)
   stop = _try_lever_bake_c(stop, _woc, '<', 1e9, .82)
   petgt = _try_lever_bake_c(petgt, _evta3yc, '<', 15, 1.05)
   stop = _try_lever_bake_c(stop, _cashc, '<', 1e9, 0.9)
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
   stop = _try_lever_bake_c(stop, _fcfg1yc, '<', 0.0, 0.85)
   petgt = _try_lever_bake_c(petgt, _roic1yc, '>', 0.15, 1.10)
   petgt = _try_lever_bake_c(petgt, _fcfsr1yc, '>', 0.20, 1.56)
   petgt = _try_lever_bake_c(petgt, _fcfsr1yc, '>', 0.25, 1.25)
   petgt = _try_lever_bake_c(petgt, _vsc, '<', 15, 0.85)
   stop = _try_lever_bake_c(stop, _vsc, '<', 15, 0.95)
   if _vsc is not None:
    if _vsc < 5: stop *= 0.85
    elif _vsc > 5 and _vsc < 10: stop *= 1.05
    elif _vsc > 10 and _vsc < 15: stop *= 1.05
    elif _vsc > 15 and _vsc < 25: stop *= 1.50
    elif _vsc > 25 and _vsc < 30: stop *= 1.05
    elif _vsc > 30 and _vsc < 50: petgt *= 1.50; stop *= 1.12
   try: _p = f_(self.securities[sym].close)
   except: _p=None
   if _p > 150: stop *= 1.50
   if _p < 50: petgt *= 1.10
   try:
    if self._reg_hyg_up5 and pnl is not None and pnl > 0.05: petgt *= 1.20  # BAKE-361 R1404 +0.0017
   except: pass
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
   decline = f_((mtf[-3].close - mtf[-1].close)/mtf[-3].close) if f_(mtf[-3].close) > 0 else 0
   _wvol10 = [f_(b.volume) for b in _w10]
   _av = sum(_wvol10)/max(len(_w10), 1)
   max_dv = max((_wvol10[i] for i in range(max(1, len(_w10)-5), len(_w10))
                 if _w10[i].close < _w10[i-1].close), default=0)
   vol_climax = _av > 0 and max_dv > 2.5 * _av
   if vol_climax and decline < .05: continue
   _m3 = f_(mtf[-3].close) if len(mtf) >= 3 else 0
   _m5 = f_(mtf[-5].close) if len(mtf) >= 5 else 0
   _m7 = f_(mtf[-7].close) if len(mtf) >= 7 else 0
   _r3 = (_bc - _m3) / _m3 if _m3 > 0 else None
   _r5 = (_bc - _m5) / _m5 if _m5 > 0 else None
   _r7 = (_bc - _m7) / _m7 if _m7 > 0 else None
   _wcl = [f_(b.close) for b in window] if window and len(window) >= 20 else None
   if _wcl:
    _returns20 = [_wcl[i]/_wcl[i-1]-1 for i in range(1, 20) if _wcl[i-1] > 0]
    _vol20 = (sum(r*r for r in _returns20) / 19) ** 0.5 if _returns20 else None
   else:
    _returns20 = None
    _vol20 = None
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
   _qaccel = self._qaccel
   _hyg_dn3 = self._reg_hyg_dn3
   _hyg_dn5 = self._reg_hyg_dn5
   _hyg_dn14 = self._reg_hyg_dn14
   _hyg_up3 = self._reg_hyg_up3
   _hyg_up5 = self._reg_hyg_up5
   _qqq_dn3 = self._reg_qqq_dn3
   _qqq_dn5 = self._reg_qqq_dn5
   _qqq_dn7 = self._reg_qqq_dn7
   _qqq_up3 = self._reg_qqq_up3
   _dpanic = self._reg_double_panic
   _qa_scan = self._qa_scan
   _ha_scan = self._ha_scan
   _qd5 = self._qd5
   _qd10 = self._qd10
   _qd20 = self._qd20
   _bd5 = self._bd5
   _bd10 = self._bd10
   _d2_4 = decline > .02 and decline < .04
   _d2_5 = decline > .02 and decline < .05
   _d2_6 = decline > .02 and decline < .06
   _d4_8 = decline > .04 and decline < .08
   _d4_12 = decline > .04 and decline < .12
   _d6_12 = decline > .06 and decline < .12
   _d8_12 = decline > .08 and decline < .12
   _qpos = _qaccel is not None and 0.01 < _qaccel < 0.05
   _qneg = _qaccel is not None and -0.05 < _qaccel < -0.01
   _qsneg = _qaccel is not None and _qaccel < -0.05
   _qzero = _qaccel is not None and -0.01 < _qaccel < 0.01
   _q_dn = _qaccel is not None and _qaccel < -0.01
   try: _pegr = float(_vr_z.peg_ratio) if _vr_z else None
   except: _pegr=None
   try: _secc = float(_ac_z.morningstar_sector_code) if _ac_z else None
   except: _secc=None
   try: _gw = float(_bs_z.goodwill.twelve_months) if _bs_z else None
   except: _gw=None
   try: _tac = float(_bs_z.total_assets.twelve_months) if _bs_z else None
   except: _tac=None
   try: _vsc = float(_ac_z.value_score) if _ac_z else None
   except: _vsc=None
   try: _rg1yc = float(_ops_z.revenue_growth.one_year) if _ops_z else None
   except: _rg1yc=None
   try: _gm1yc = float(_ops_z.gross_margin.one_year) if _ops_z else None
   except: _gm1yc=None
   try: _ic1yc = float(_ops_z.interest_coverage.one_year) if _ops_z else None
   except: _ic1yc=None
   try: _pec = float(_vr_z.pe_ratio) if _vr_z else None
   except: _pec=None
   try: _roic3mc = float(_ops_z.roic.three_months) if _ops_z else None
   except: _roic3mc=None
   try: _tr1yc = float(_ops_z.tax_rate.one_year) if _ops_z else None
   except: _tr1yc=None
   try: _om1yc = float(_ops_z.operation_margin.one_year) if _ops_z else None
   except: _om1yc=None
   try: _om3mc = float(_ops_z.operation_margin.three_months) if _ops_z else None
   except: _om3mc=None
   try: _cfog1yc = float(_ops_z.cfo_growth.one_year) if _ops_z else None
   except: _cfog1yc=None
   try: _cfyc = float(_vr_z.cf_yield) if _vr_z else None
   except: _cfyc=None
   try: _fcfg1yc = float(_ops_z.fcf_growth.one_year) if _ops_z else None
   except: _fcfg1yc=None
   try: _rt1yc = float(_ops_z.receivable_turnover.one_year) if _ops_z else None
   except: _rt1yc=None
   try: _crc = float(_vr_z.cash_return) if _vr_z else None
   except: _crc=None
   try: _capec = float(_vr_z.cape_ratio) if _vr_z else None
   except: _capec=None
   try: _cashc = float(_bs_z.cash.twelve_months) if _bs_z else None
   except: _cashc=None
   try: _fpec = float(_vr_z.forward_pe_ratio) if _vr_z else None
   except: _fpec=None
   _lowgwr = (_gw is not None and _tac is not None and _tac > 0 and (_gw/_tac) < 0.20)
   _icp = (_ic1yc is not None and _ic1yc > 10 and _pec is not None and 0 < _pec < 15 and _d4_8)
   _fcp = (_fcfg1yc is not None and _fcfg1yc > 0.10 and _pec is not None and 0 < _pec < 12 and _d4_8)
   _hi_vol = _vol20 is not None and _vol20 > 0.04
   _lo_vol = _vol20 is not None and _vol20 < 0.015
   _hi_cape = _capec is not None and _capec > 50
   score = math.log2(math.log2(_bv))
   if decline < .05:
    conv = max(1.0, 1.0 + (decline - .02) * (1.5/.10))
   else:
    conv = 1.0 + .375 + (decline - .05) * (3.5/.10)
   conv = min(5.0, conv)
   if vol_climax: conv *= .70
   wt_tilt = 1.0
   score = _try_score_v1c_gt(score, _om1yc, 0.3, decline, 0.05, None, 1.365)
   score = _try_score_bake_v2f_v(score, _om1yc, '>', 0.3, _fcfg1yc, '>', 0.1, decline, 0.07, None, 1.4, True)
   score = _try_score_bake_v2f(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, _ops_z, ('long_term_debt_equity_ratio', 'one_year'), '<', 0.3, decline, 0.05, None, 1.4, True)
   score = _try_score_bake_v2f(score, _ops_z, ('operation_margin', 'one_year'), '>', 0.3, _ops_z, ('solvency_ratio', 'one_year'), '>', 0.5, decline, 0.05, None, 1.4, True)
   try:
    _va = f_(_inc_z.write_off.twelve_months)
    _vb = _cfog1yc
    _vc = _gm1yc
    if _va is not None and _vb is not None and _vc is not None and _va > 1e8 and _vb < 0.0 and _vc < 0.20 and decline > .10: continue
   except: pass
   score = _try_score_v1c_gt(score, _gm1yc, 0.45, decline, 0.03, None, 1.07)
   if _try_skip_2f_v(_tr1yc, '>', 0.5, _cfog1yc, '<', -0.05, decline, 0.1, None): continue
   if _try_skip_2f_v(_tr1yc, '>', 0.4, _cfog1yc, '<', -0.1, decline, 0.07, None): continue
   if _try_skip_2f_v(_tr1yc, '>', 0.3, _cfog1yc, '<', 0.0, decline, 0.05, None): continue
   score = _try_score_bake_v2f_v(score, _rt1yc, '>', 10.0, _tr1yc, '<', 0.2, decline, 0.05, None, 1.2, True)
   score = _try_score_bake_v2f_v(score, _rt1yc, '>', 8.0, _tr1yc, '<', 0.15, decline, 0.07, None, 1.4, True)
   score = _try_score_bake_v2f_v(score, _rt1yc, '>', 6.0, _tr1yc, '<', 0.18, decline, 0.1, None, 1.3, True)
   score = _try_score_bake_v2f_v(score, _om1yc, '>', 0.35, _tr1yc, '<', 0.15, decline, 0.07, None, 1.3, True)
   score = _try_score_v1c_lt(score, _pegr, 1.5, decline, 0.03, None, 1.1)
   score = _try_score_v1c_lt(score, _pegr, 1.5, decline, 0.1, None, 1.2)
   score = _try_score_v1c_lt(score, _pegr, 1.5, decline, 0.2, None, 1.5)
   score = _try_score_v1c_lt(score, _pegr, 2.5, decline, 0.25, None, 1.5)
   score = _try_score_v1c_eq(score, _secc, 309, decline, 0.03, None, 1.10, True)
   score = _try_score_v1c_eq(score, _secc, 309, decline, None, None, 1.20, _hyg_dn5)
   score = _try_score_v1c_eq(score, _secc, 308, decline, 0.07, None, 1.30, True)
   score = _try_score_v1c_eq(score, _secc, 309, decline, None, None, 1.95, _dpanic)
   try:
    _va = _secc
    _vb = f_(_ops_z.tax_rate.six_months)
    if _va is not None and _vb is not None and _va == 310 and _vb < 0.18 and decline > .03: score *= 1.25
   except: pass
   score = _try_score_v1c_lt(score, _tac, 1000000000.0, decline, None, None, 1.2, _hyg_dn5)
   score = _try_score_v1c_lt(score, _tac, 3000000000.0, decline, 0.07, None, 1.15)
   score = _try_score_v1c_gt(score, _tac, 500000000000.0, decline, 0.05, None, 1.1)
   score = _try_score_v1c_lt(score, _tac, 1000000000.0, decline, None, None, 1.2, _qqq_dn5)
   try:
    _r_open = f_(bar.open)
    _r = _bc / _r_open if _r_open > 0 else 1.0
    if _r > 1.02 and decline > .03: score *= 1.12
   except: pass
   try:
    _v = _pegr
    if _v < 1.0 and decline > .05: score += 0.10
   except: pass
   score = _try_score_v1c_gt(score, _tac, 100000000000.0, decline, 0.04, 0.07, 1.1)
   try:
    _v = _crc
    if _v > 0.10 and _hyg_dn5: score += 0.50
   except: pass
   score = _try_score_v1c_gt(score, _tac, 300000000000.0, decline, 0.04, 0.08, 1.05)
   if _lowgwr and decline > .05 and decline < .10: score *= 1.10
   score = _try_score_bake_v1(score, _ops_z, ('net_margin', 'three_months'), '<', 0.0, decline, 0.05, 0.1, 0.9)
   score = _try_score_bake_v1(score, _vr_z, ('fcf_yield',), '>', 0.08, decline, 0.04, 0.08, 1.1)
   try:
    _p = f_(_vr_z.payout_ratio)
    if _lowgwr and _p < 0.40 and decline > .05 and decline < .10: score *= 1.05
   except: pass
   if _lowgwr and _capec is not None and _capec < 22 and _d4_8: score *= 1.05
   score = _try_score_v1c_gt(score, _om3mc, 0.35, decline, 0.05, 0.1, 1.05)
   score = _try_score_v1c_gt(score, _om3mc, 0.35, decline, 0.04, 0.08, 1.03)
   score = _try_score_v1c_gt(score, _om3mc, 0.35, decline, 0.06, 0.1, 1.03)
   score = _try_score_v1c_gt(score, _om3mc, 0.4, decline, 0.04, 0.08, 1.03)
   try:
    _s = _secc
    _v = f_(_vr_z.fcf_yield)
    if _s == 308 and _v is not None and _v > 0.08 and _d4_8: score *= 1.05
   except: pass
   if _lowgwr and _om3mc is not None and _om3mc > 0.35 and _d4_8: score *= 1.03
   try:
    _v = f_(_ops_z.net_margin.three_months)
    if _lowgwr and _v is not None and _v > 0.25 and _d4_8: score *= 1.05
   except: pass
   score = _try_score_v1c_gt(score, _om1yc, 0.4, decline, 0.04, 0.08, 1.05)
   try:
    _s = _secc
    _v = f_(_vr_z.ev_to_ebitda)
    if _s == 310 and _v is not None and 0 < _v < 12 and _d4_8: score *= 1.05
   except: pass
   try:
    _s = _secc
    _v = f_(_vr_z.fcf_yield)
    if _s == 206 and _v is not None and _v > 0.05 and decline > .05 and decline < .10: score *= 1.05
   except: pass
   score = _try_score_v1c_gt(score, _cfyc, 0.1, decline, 0.04, 0.08, 1.05)
   score = _try_score_v1c_gt(score, _cfyc, 0.15, decline, 0.05, 0.1, 1.05)
   score = _try_score_bake_v1(score, _vr_z, ('earning_yield',), '>', 0.06, decline, 0.04, 0.08, 1.05)
   score = _try_score_v1c_gt(score, _cfyc, 0.08, decline, 0.02, 0.05, 1.05)
   score = _try_score_v1c_gt(score, _roic3mc, 0.18, decline, 0.005, 0.02, 1.05)
   score = _try_score_v1c_gt(score, _roic3mc, 0.15, decline, 0.005, 0.025, 1.05)
   if _lowgwr and _capec is not None and 0 < _capec < 22 and decline > .01 and decline < .03: score *= 1.03
   try:
    if _r7 > -0.10 and _r7 < -0.05: score *= 1.08
   except: pass
   try:
    _v = _pegr
    if _v > 0 and _v < 0.8 and decline > .01 and decline < .03: score *= 1.05
   except: pass
   try:
    _bars7 = mtf[-7:] if len(mtf) >= 7 else None
    _hi7 = max(f_(b.high) for b in _bars7) if _bars7 else None
    _lo7 = min(f_(b.low) for b in _bars7) if _bars7 else None
    if _hi7 is not None and _lo7 is not None and _lo7 > 0 and (_hi7/_lo7) > 1.12 and decline > .03: score *= 1.05
   except: pass
   try:
    _g = f_(_ers_z.normalized_diluted_eps_growth.one_year)
    _e = f_(_vr_z.earning_yield)
    if _g is not None and _g > 0.05 and _e is not None and _e > 0.06 and decline > .05 and decline < .10: score *= 1.05
   except: pass
   score = _try_score_bake_v1(score, _ers_z, ('basic_average_shares_growth', 'one_year'), '<', -0.02, decline, 0.04, 0.08, 1.05)
   try:
    _v = _cfyc
    if _v > 0.08 and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v > 50 and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   try:
    _v = _pegr
    if _v > 0 and _v < 1.0 and _r7 > -0.05 and _r7 < -0.02: score *= 1.05
   except: pass
   try:
    _v = _pegr
    if _v > 0 and _v < 0.6 and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   try:
    _v = _roic3mc
    if _v > 0.18 and _r3 > -0.04 and _r3 < -0.02: score *= 1.08
   except: pass
   try:
    _v = _roic3mc
    if _v > 0.18 and _r3 > -0.04 and _r3 < -0.02: conv *= 1.50
   except: pass
   conv = _try_lever_bake(conv, _vr_z, ('cf_yield',), None, None, 2.5, gates=(('>', 0.08),), regime=_hyg_dn5)
   conv = _try_lever_bake(conv, _vr_z, ('cf_yield',), None, None, 2.0, gates=(('>', 0.08),), regime=_hyg_dn3)
   conv = _try_lever_bake(conv, _vr_z, ('peg_ratio',), None, None, 2.0, gates=(('>', 0.0), ('<', 1.5)), regime=_hyg_dn3)
   conv = _try_lever_bake(conv, _vr_z, ('peg_ratio',), None, None, 1.5, gates=(('>', 0.0), ('<', 1.5)), regime=_qqq_dn3)
   try:
    _v = _pegr
    if _v > 0 and _v < 1.5 and _hyg_dn3 and _d2_6: score *= 1.05
   except: pass
   try:
    _v = _pegr
    if _v > 0 and _v < 1.5 and _hyg_dn3 and _d2_4: score *= 1.05
   except: pass
   try:
    _v = _pegr
    if _v > 0 and _v < 1.5 and _hyg_dn3 and (_bc > f_(bar.open)) and _d2_6: score *= 1.05
   except: pass
   try:
    _v = _pegr
    _bo = f_(bar.open); _bl = f_(bar.low)
    _body = abs(_bc - _bo) if _bc and _bo else 0
    _ls = (min(_bo, _bc) - _bl) if _bo and _bc and _bl else 0
    _hammer = _body > 0 and _ls > 2 * _body
    if _v > 0 and _v < 1.5 and _hyg_dn3 and _hammer and _d2_6: score *= 1.05
   except: pass
   try:
    _v = _pegr
    _both = _r3 is not None and _r5 is not None and _r3 > -0.05 and _r3 < -0.02 and _r5 > -0.05 and _r5 < -0.02
    if _v > 0 and _v < 1.5 and _hyg_dn3 and _both and _d4_8: score *= 1.14
   except: pass
   try:
    _v = _pegr
    _both = _r3 is not None and _r5 is not None and _r3 > -0.05 and _r3 < -0.02 and _r5 > -0.05 and _r5 < -0.02
    if _v > 0 and _v < 1.5 and _hyg_dn3 and _both and decline > .04 and decline < .10: score *= 1.10
   except: pass
   try:
    _v = _pegr
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if _v > 0 and _v < 1.5 and _qqq_dn3 and _above and _d2_6: score *= 1.10
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
   score = _try_score_v1c_gt(score, _vsc, 50.0, decline, 0.05, 0.1, 1.05)
   try:
    _v1 = _cfyc
    _v2 = _vsc
    if _v1 is not None and _v1 > 0.05 and _v2 is not None and _v2 > 50 and decline > .05 and decline < .10: score *= 1.05
   except: pass
   if _secc == 309 and _lowgwr and _d4_8: score *= 1.10
   score = _try_score_v1c_gt(score, _roic3mc, 0.18, decline, 0.03, None, 1.14)
   score = _try_score_v1c_gt(score, _om3mc, 0.35, decline, 0.03, None, 1.1)
   score = _try_score_bake_v1(score, _ops_z, ('tax_rate', 'six_months'), '<', 0.18, decline, 0.03, None, 1.1)
   score = _try_score_bake_v2f_v(score, _capec, '<', 25.0, _om3mc, '>', 0.35, decline, 0.03, None, 1.3, True)
   score = _try_score_v1c_gt(score, _roic3mc, 0.15, decline, None, None, 1.2, _qqq_dn3)
   score = _try_score_v1c_lt(score, _pegr, 1.5, decline, None, None, 1.2, _hyg_dn5)
   score = _try_score_v1c_gt(score, _crc, 0.1, decline, None, None, 1.4, _qqq_dn5)
   score = _try_score_v1c_gt(score, _roic3mc, 0.15, decline, None, None, 1.2, _hyg_dn3)
   score = _try_score_v1c_gt(score, _roic3mc, 0.15, decline, None, None, 1.2, _qqq_dn7)
   score = _try_score_v1c_lt(score, _pegr, 1.5, decline, None, None, 1.2, _qqq_up3)
   score = _try_score_v1c_gt(score, _roic3mc, 0.15, decline, None, None, 1.4, _hyg_up5)
   score = _try_score_v1c_gt(score, _roic3mc, 0.15, decline, None, None, 1.4, _hyg_up3)
   score = _try_score_bake_v2f_v(score, _pegr, '<', 1.5, _fpec, '<', 12.0, decline, 0.05, None, 1.3, True)
   score = _try_score_v1c_gt(score, _crc, 0.1, decline, 0.03, None, 1.15)
   score = _try_score_bake_v2f_v(score, _crc, '>', 0.1, _pegr, '<', 1.5, decline, 0.03, None, 1.25, True)
   score = _try_score_bake_v2f_v(score, _pegr, '<', 1.5, _pec, '<', 12.0, decline, 0.07, None, 1.3, True)
   if _try_skip_2f_v(_tr1yc, '>', 0.35, _cfog1yc, '<', -0.15, decline, 0.03, None): continue
   if _try_skip_2f_v(_tr1yc, '>', 0.35, _cfog1yc, '<', -0.15, decline, None, None): continue
   if _try_skip_bake_c(_cfog1yc, (('<', -0.4),), decline, None, None, True): continue
   if _try_skip_bake(_ops_z, ('fcf_growth', 'one_year'), (('<', -0.7),), decline, None, None, True): continue
   if _try_skip_bake(_ops_z, ('net_income_growth', 'three_months'), (('<', -0.5),), decline, None, None, True): continue
   score = _try_score_bake_v1(score, _ops_z, ('fcf_sales_ratio', 'one_year'), '>', 0.25, decline, 0.03, None, 1.1)
   try:
    _v = _pegr
    if _v > 0 and _v < 1.5 and _hyg_dn3 and decline > .12 and decline < .20: score *= 1.80
   except: pass
   try:
    _v = _pegr; _p = _bc
    if _v > 0 and _v < 1.5 and _p > 50 and _p < 100 and _hyg_dn3 and decline > .12 and decline < .20: score *= 1.50
   except: pass
   try:
    _v = _pegr
    if _v > 5 and _v < 20 and _hyg_dn3 and decline > .12 and decline < .20: score *= 0.70
   except: pass
   try:
    _v = _secc; _p = _bc
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and _bc > _sma
    if _v == 206 and _p > 100 and _p < 200 and _hyg_dn3 and _above and _d2_6: score *= 1.50
   except: pass
   try:
    _v = _pegr; _p = _bc
    if _v > 0 and _v < 1.5 and _p > 100 and _p < 200 and _hyg_dn3 and _d2_6: score *= 1.08
   except: pass
   try:
    _v = _pegr
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v > 0 and _v < 1.5 and _accel is not None and -0.10 < _accel < -0.02 and _hyg_dn3 and _d2_6: score *= 1.18
   except: pass
   try:
    _v = _secc
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v == 206 and _accel is not None and -0.10 < _accel < -0.02 and _hyg_dn3 and _d2_6: score *= 1.10
   except: pass
   try:
    _v = _pegr
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v > 0 and _v < 1.0 and _accel is not None and -0.10 < _accel < -0.02 and _hyg_dn3 and _d2_6: score *= 1.18
   except: pass
   try:
    _v = _pegr
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v > 0 and _v < 1.5 and _accel is not None and 0.05 < _accel < 0.15 and _hyg_dn3 and _d2_6: score *= 0.70
   except: pass
   score = _try_score_qaccel_c_range(score, _pegr, 0.0, 1.5, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.98, _hyg_dn3)
   score = _try_score_qaccel_c_range(score, _pegr, 0.0, 1.0, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.3, _hyg_dn3)
   score = _try_score_qaccel_c_gt(score, _roic3mc, 0.1, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 2.16, _hyg_dn3)
   score = _try_score_qaccel_c_gt(score, _ic1yc, 20.0, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.1, _hyg_dn3)
   score = _try_score_qaccel_c_gt(score, _ic1yc, 50.0, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.05, _hyg_dn3)
   try:
    _v = _ic1yc
    ha = _ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _v > 20 and _haccel is not None and 0.01 < _haccel < 0.05 and _hyg_dn3 and _d2_6: score *= 1.14
   except: pass
   score = _try_score_qaccel_2f_sec_v(score, _secc, 206, _pegr, 0.0, 1.5, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.95, _hyg_dn3)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 206, _pegr, 0.0, 1.5, _qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.6, _hyg_dn3)
   try:
    _v = _secc
    if _v == 206 and _qaccel > -0.05 and _qaccel < -0.01 and _hyg_dn3 and _d2_6: score *= 0.95
   except: pass
   try:
    _vs = _secc; _vp = _pegr
    ha = _ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _vs == 206 and _vp is not None and 0 < _vp < 1.5 and _haccel is not None and -0.05 < _haccel < -0.01 and _hyg_dn3 and _d2_6: score *= 0.70
   except: pass
   score = _try_score_qaccel_c_gt(score, _ic1yc, 20.0, _qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.93, _hyg_dn3)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 102, _pegr, 0.0, 1.0, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.4, _hyg_dn3)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 102, _pegr, 0.0, 1.0, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.07, True)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 102, _pegr, 0.0, 1.0, _qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.7, True)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 102, _cashc, 5e9, 1e15, _qaccel, 0.01, 0.05, decline, 0.04, 0.08, 1.5, True)  # BAKE-333 R1294 +0.0017
   score = _try_score_qaccel_2f_sec_v(score, _secc, 308, _cashc, 5e9, 1e15, _qaccel, -0.05, -0.01, decline, 0.04, 0.08, 1.5, True)  # BAKE-334 R1297 +0.0062
   score = _try_score_qaccel_2f_sec_v(score, _secc, 102, _cashc, 5e9, 1e15, _qaccel, -0.05, -0.01, decline, 0.04, 0.08, 0.95, True)  # BAKE-335 R1297 +0.0020
   score = _try_score_bake_qaccel(score, _bs_z, ('dividends_payable', 'twelve_months'), (('>', 5e8),), _qaccel, 0.01, 0.05, decline, 0.04, 0.08, 1.30, True)  # BAKE-336 R1299 +0.0025
   if _qsneg and _d4_8: score *= 1.50  # BAKE-337 R1302 +0.0042
   if _secc == 308 and _qsneg and _d2_5: score *= 1.30  # BAKE-338 R1317 +0.0059
   if _secc == 102 and _qsneg and _d2_5: score *= 1.50  # BAKE-339 R1317 +0.0037
   if _secc == 206 and _vol20 is not None and _vol20 < 0.020 and _qpos and _d4_8: score *= 0.85  # BAKE-340 R1337 +0.0024
   try:
    _v_npe = f_(_vr_z.normalized_pe_ratio)
    if _v_npe is not None and 0 < _v_npe < 12 and _q_dn and _d4_8: score *= 1.30  # BAKE-341 R1339 +0.0040
   except: pass
   if _lo_vol and _q_dn and _d4_8: score *= 0.70  # BAKE-342 R1340 +0.0078
   if _secc == 311 and _pec is not None and 0 < _pec < 12 and _hyg_dn3 and decline > .04 and decline < .12: score *= 1.50  # BAKE-343 R1344 +0.0044
   if _qqq_dn7 and _pec is not None and 0 < _pec < 12 and _q_dn and decline > .04 and decline < .12: score *= 0.85  # BAKE-344 R1344-R1347 +0.0077
   if _secc == 102 and _vol20 is not None and _vol20 < 0.015 and _qqq_dn3 and decline > .04 and decline < .12: score *= 1.14  # BAKE-345 R1351 +0.0029
   if _icp: score *= 0.85  # BAKE-346 R1357 +0.0242
   if _fcp: score *= 0.85  # BAKE-347 R1357 +0.0292
   if _icp and _q_dn: score *= 1.30  # BAKE-348 R1358 +0.0041
   if _icp and _hyg_dn3: score *= 1.14  # BAKE-349 R1358 +0.0040
   if _icp and _pegr is not None and 0 < _pegr < 1.5: score *= 1.14  # BAKE-350 R1358 +0.0093
   if _fcp and _hyg_dn3: score *= 1.30  # BAKE-351 R1359 +0.0015
   if _icp and _qpos: score *= 1.50  # BAKE-352 R1359/R1361 +0.0040-0.0045 multi-mag m150/m165
   try:
    _v_fdy = f_(_vr_z.forward_dividend_yield)
    if _v_fdy is not None and _v_fdy > 0.04 and _qpos and _d4_8: score *= 0.85  # BAKE-353 R1368 +0.0014
   except: pass
   try:
    _v_da = f_(_inc_z.depreciation_and_amortization.twelve_months)
    if _v_da is not None and _v_da > 1e9 and _q_dn and _d4_8: score *= 1.30  # BAKE-354 R1369 +0.0014
   except: pass
   if vol_climax and _r5 is not None and _r5 < -0.10 and _d4_8: score *= 1.30  # BAKE-355 R1376 +0.0071
   if _secc == 205 and _qpos and _d4_8: score *= 1.40  # BAKE-356 R1382/R1385 +0.0012-0.0020 multi-mag m140/m150/m160/m185
   try:
    _v_fcfy = f_(_vr_z.fcf_yield)
    if _v_fcfy is not None and _v_fcfy > 0.06 and _qpos and _hyg_dn3: score *= 1.14  # BAKE-358 R1390 +0.0071
    if _v_fcfy is not None and _v_fcfy > 0.06 and _qpos and _hyg_dn14: score *= 1.30  # BAKE-362 R1406 +0.0046
   except: pass
   try:
    _v_ps = f_(_bs_z.preferred_stock.twelve_months)
    if _v_ps is not None and _v_ps > 0 and _qpos and _hyg_dn3: score *= 1.14  # BAKE-363 R1408 +0.0041 (multi-mag m114/m130/m150 confirmed; conservative m114)
   except: pass
   try:
    _v_ndeg = f_(_ers_z.normalized_diluted_eps_growth.three_months)
    if _v_ndeg is not None and _v_ndeg > 0.10 and _qpos and _hyg_dn3: score *= 1.14  # BAKE-364 R1408 +0.0015 (multi-mag m114/m130 confirmed; conservative m114)
   except: pass
   try:
    _v_jfc = f_(_vr_z.fcf_yield)
    if _v_jfc is not None and _v_jfc > 0.06 and _qsneg and _hyg_dn5: score *= 0.90  # BAKE-365 R1408/R1410/R1411 +0.0044/+0.0063/+0.0030 (3-round multi-mag dampener m75-m92 confirmed)
   except: pass
   score = _try_score_qaccel_2f_sec_v(score, _secc, 206, _pegr, 0.0, 1.5, _qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.7, True)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 206, _pegr, 0.0, 1.5, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.08, True)
   score = _try_score_qaccel_c_range(score, _pegr, 0.0, 1.0, _qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.8, True)
   try:
    _v = _pegr
    ha = _ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _v > 0 and _v < 1.0 and _haccel is not None and -0.05 < _haccel < -0.01 and _d2_6: score *= 0.95
   except: pass
   try:
    _vs = _secc; _vp = _pegr
    ha = _ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _vs == 206 and _vp is not None and 0 < _vp < 1.5 and _haccel is not None and -0.05 < _haccel < -0.01 and _d2_6: score *= 0.90
   except: pass
   score = _try_score_qaccel_2f_sec_v(score, _secc, 102, _pegr, 0.0, 1.0, _qaccel, -0.05, -0.01, decline, 0.06, 0.12, 0.5, True)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 206, _pegr, 0.0, 1.5, _qaccel, -0.05, -0.01, decline, 0.06, 0.12, 0.7, True)
   try:
    _v = _pegr
    if _v > 0 and _v < 1.5 and _qaccel > -0.05 and _qaccel < -0.01 and decline > .12: score *= 0.55
   except: pass
   score = _try_score_qaccel_2f_sec_v(score, _secc, 102, _pegr, 0.0, 1.0, _qaccel, 0.01, 0.05, decline, 0.06, 0.12, 2.2, True)
   try:
    _vp = _pegr; _ic = _ic1yc
    if _vp is not None and 0 < _vp < 1.5 and _ic is not None and _ic > 20 and _qaccel > -0.05 and _qaccel < -0.01 and _d6_12: score *= 0.80
   except: pass
   try:
    _vp = _pegr; _ic = _ic1yc
    if _vp is not None and 0 < _vp < 1.5 and _ic is not None and _ic > 50 and _qaccel > -0.05 and _qaccel < -0.01 and _d6_12: score *= 0.65
   except: pass
   try:
    _vp = _pegr; _ic = _ic1yc
    if _vp is not None and 0 < _vp < 1.5 and _ic is not None and _ic > 100 and _qaccel > -0.05 and _qaccel < -0.01 and _d6_12: score *= 0.55
   except: pass
   try:
    _vp = _pegr; _pe = _pec
    if _vp is not None and 0 < _vp < 1.5 and _pe is not None and 0 < _pe < 15 and _qaccel > -0.05 and _qaccel < -0.01 and _d6_12: score *= 0.65
   except: pass
   try:
    _vp = _pegr; _ev = f_(_vr_z.ev_to_revenue)
    if _vp is not None and 0 < _vp < 1.5 and _ev is not None and 0 < _ev < 2 and _qaccel > -0.05 and _qaccel < -0.01 and _d6_12: score *= 0.85
   except: pass
   score = _try_score_qaccel_c_range(score, _pegr, 0.0, 1.5, _qaccel, -0.05, -0.01, decline, 0.06, 0.12, 0.7, _dpanic)
   score = _try_score_qaccel_c_range(score, _pegr, 0.0, 1.5, _qaccel, -0.05, -0.01, decline, 0.06, 0.12, 0.93, _hyg_dn14)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 206, _pegr, 0.0, 1.5, _qaccel, -0.05, -0.01, decline, 0.02, 0.06, 0.95, _hyg_dn14)
   score = _try_score_qaccel_2f_sec_v(score, _secc, 206, _pegr, 0.0, 1.5, _qaccel, 0.01, 0.05, decline, 0.02, 0.06, 1.2, _hyg_dn14)
   score = _try_score_qaccel_c_gt(score, _vsc, 50.0, _qaccel, 0.01, 0.05, decline, 0.06, 0.12, 1.3, True)
   score = _try_score_qaccel_c_gt(score, _vsc, 70.0, _qaccel, 0.01, 0.05, decline, 0.06, 0.12, 1.4, True)
   try:
    _v = _vsc
    if _v > 60 and _qaccel > 0.01 and _qaccel < 0.05 and decline > .12 and decline < .20: continue
   except: pass
   try:
    _v = _vsc
    if _v > 85 and _qaccel > 0.01 and _qaccel < 0.05 and _d4_8: continue
   except: pass
   try:
    _v = _vsc
    if _v > 85 and _qaccel > 0.01 and _qaccel < 0.05 and _d2_4: continue
   except: pass
   try:
    _v = _vsc
    if _v > 80 and _qaccel > -0.01 and _qaccel < 0.01 and _d2_6: continue
   except: pass
   try:
    _v = _vsc
    if _v > 60 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: continue
   except: pass
   try:
    _v = _vsc
    if _v >= 15 and _v < 30 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 1.20
   except: pass
   try:
    _v = _vsc
    if _v >= 50 and _v < 60 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 0.5
   except: pass
   try:
    _v = _vsc
    if _v >= 25 and _v < 30 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 1.20
   except: pass
   try:
    _v = _vsc
    if _v >= 50 and _v < 60 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 0.85
   except: pass
   try:
    _v = _vsc
    if _v >= 25 and _v < 30 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 1.20
   except: pass
   try:
    _v = _vsc
    if _v >= 15 and _v < 30 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 0.95
   except: pass
   try:
    _v = _secc
    if _v == 206 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 0.85
   except: pass
   try:
    _v = _secc
    if _v == 102 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 0.95
   except: pass
   try:
    _v = _secc
    if _v == 308 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 1.05
   except: pass
   try:
    _v = _secc
    if _v == 308 and _qaccel > -0.01 and _qaccel < 0.01 and _d2_4: score *= 1.05
   except: pass
   try:
    _v = _secc
    if _v == 311 and _qaccel < -0.01 and _qaccel > -0.05 and _d6_12: score *= 1.25
   except: pass
   try:
    _v = _secc
    if _v == 309 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 1.50
   except: pass
   try:
    _v = _secc
    if _v == 308 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 0.95
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 0.95
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _qaccel > -0.01 and _qaccel < 0.01 and _d2_4: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _qaccel < -0.01 and _qaccel > -0.05 and _d4_8: score *= 0.85
   except: pass
   try:
    _v = _vsc
    if _v < 10 and _qaccel > -0.01 and _qaccel < 0.01 and _d2_4: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v < 10 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v < 10 and _qaccel < -0.01 and _qaccel > -0.05 and _d4_8: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v < 10 and _qaccel > 0.01 and _qaccel < 0.05 and _d6_12: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _qaccel < -0.01 and _qaccel > -0.05 and _d6_12: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if _v > 15 and _v < 30 and _r5 > 0.05 and _r5 < 0.20 and _d4_12: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if _v > 5 and _v < 10 and _r5 > 0.05 and _r5 < 0.20 and _d2_4: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if _v > 15 and _v < 30 and _r5 > 0.05 and _r5 < 0.20 and _d6_12: score *= 1.14
   except: pass
   try:
    _v = _secc
    if _v == 308 and _r5 > 0.05 and _r5 < 0.20 and _d4_12: score *= 0.55
   except: pass
   try:
    if _bc > 150 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 1.05
   except: pass
   try:
    if _bc > 150 and _qaccel < -0.01 and _qaccel > -0.05 and _d6_12: score *= 0.95
   except: pass
   try:
    if _bc > 150 and _qaccel < -0.01 and _qaccel > -0.05 and _d4_8: score *= 0.75
   except: pass
   try:
    _v = f_(_bs_z.cash_equivalents.three_months)
    if _v > 1e8 and _qaccel > 0.01 and _qaccel < 0.05 and _d6_12: score *= 1.30
   except: pass
   try:
    if _r7 < -0.10 and _r7 > -0.30 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_12: score *= 0.85
   except: pass
   try:
    if _qd5 is not None and _qd5 < -0.05 and _d4_12:
     score *= 0.95
     if _qaccel < -0.01 and _qaccel > -0.05:
      score *= 0.85
      if _r5 < 0: score *= 0.75
   except: pass
   try:
    if _r7 < -0.05 and _r7 > -0.20 and _qaccel > -0.01 and _qaccel < 0.01 and _d2_4: score *= 0.55
   except: pass
   try:
    _v = _secc
    if _bc > 150 and _v is not None and _v == 308 and _d4_12: score *= 1.25
   except: pass
   try:
    _v = _vsc
    if _v > 5 and _v < 10 and _r5 < -0.05 and _r5 > -0.20 and _d4_12: score *= 0.95
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _r3 < -0.03 and _r3 > -0.15 and _d4_12: score *= 1.05
   except: pass
   try:
    if _r7 < -0.05 and _r7 > -0.20 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 0.75
   except: pass
   try:
    _v = _vsc
    if _v > 5 and _v < 10 and _r3 < -0.02 and _r3 > -0.15 and _d4_12: score *= 1.05
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _r5 < 0 and _r5 > -0.20 and _d4_8: score *= 1.50
   except: pass
   try:
    _o = f_(bar.open); _pc = f_(mtf[-2].close)
    if _o > 0 and _pc > 0 and _o/_pc < 0.95 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if _v < 5 and _r5 < 0 and _r5 > -0.20 and _d2_4: score *= 0.95
   except: pass
   try:
    if _bc < 50 and _qaccel < -0.01 and _qaccel > -0.05 and _d4_8: score *= 0.75
   except: pass
   try:
    if _bc > 50 and _bc < 100 and _qaccel < -0.01 and _qaccel > -0.05 and _d4_8: score *= 0.95
   except: pass
   try:
    if _bc < 50 and _qaccel < -0.01 and _qaccel > -0.05 and _d6_12: score *= 1.30
   except: pass
   try:
    if _bc < 50 and _qaccel > -0.01 and _qaccel < 0.01 and _d4_8: score *= 0.95
   except: pass
   try:
    if _bc > 50 and _bc < 100 and _qaccel < -0.01 and _qaccel > -0.05 and _d6_12: score *= 1.05
   except: pass
   try:
    if _bc > 150 and _qaccel < -0.01 and _qaccel > -0.05 and _d6_12: score *= 1.14
   except: pass
   try:
    if _bc > 75 and _bc < 100 and _qaccel < -0.01 and _qaccel > -0.05 and _d4_8: score *= 0.85
   except: pass
   try:
    if _bc > 30 and _bc < 50 and _qaccel < -0.01 and _qaccel > -0.05 and _d4_8: score *= 0.95
   except: pass
   try:
    if _bc > 75 and _bc < 100 and _qaccel < -0.01 and _qaccel > -0.05 and _d6_12: score *= 0.55
   except: pass
   try:
    if _bc > 25 and _bc < 50 and _qaccel < -0.01 and _qaccel > -0.05 and _d6_12: score *= 1.05
   except: pass
   try:
    _vola = _vol20
    if _vola is not None and _qaccel is not None:
     if _vola > 0.04 and _d4_12:
      if _qaccel > -0.01 and _qaccel < 0.01: score *= 0.75
      elif _qaccel < -0.01 and _qaccel > -0.05: score *= 0.85
     if _vola > 0.04 and _qaccel > -0.01 and _qaccel < 0.01 and _d2_4: score *= 1.50
     if _vola > 0.05 and _qaccel < -0.01 and _qaccel > -0.05 and _d4_8: score *= 0.85
     if _vola > 0.04 and _qaccel < -0.01 and _qaccel > -0.05 and _d2_4: score *= 0.95
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
    if _v > 5 and _v < 10 and _hyg_dn3 and _d4_12: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if _v > 55 and _v < 60 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if _v > 35 and _v < 40 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: score *= 1.25
   except: pass
   score = _try_score_qaccel_c_lt(score, _vsc, 15.0, _qaccel, 0.01, 0.05, decline, 0.06, 0.12, 1.2, True)
   score = _try_score_qaccel_c_range(score, _vsc, 30.0, 50.0, _qaccel, 0.01, 0.05, decline, 0.06, 0.12, 0.85, True)
   try:
    _v = _vsc
    if _v > 15 and _v < 30 and _qaccel > -0.01 and _qaccel < 0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 1.50
   except: pass
   try:
    _v = _vsc
    if _v > 10 and _v < 15 and _qaccel > -0.01 and _qaccel < 0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 0.55
   except: pass
   try:
    _v = _vsc
    if _v > 15 and _v < 30 and _qaccel > -0.01 and _qaccel < 0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d2_4: score *= 0.65
   except: pass
   try:
    _v = _secc
    if _v == 311 and _qaccel > -0.01 and _qaccel < 0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 0.85
   except: pass
   try:
    _v = _vsc
    if _v > 10 and _v < 15 and _qaccel > -0.01 and _qaccel < 0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d2_4: score *= 1.14
   except: pass
   try:
    if _vol20 is not None and _vol20 > 0.06 and _qaccel > -0.01 and _qaccel < 0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 0.50
   except: pass
   try:
    _v = _vsc
    if _v > 50 and _qaccel > -0.01 and _qaccel < 0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 1.05
   except: pass
   try:
    if _r7 is not None and 0 < _r7 < 0.20 and _qaccel > -0.01 and _qaccel < 0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 1.14
   except: pass
   try:
    _v = _vsc
    if _v > 50 and _qaccel > 0.01 and _qaccel < 0.05 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 0.85
   except: pass
   try:
    _v = _vsc
    if _v is not None and _v < 10 and _qaccel > -0.05 and _qaccel < -0.01 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 0.55
   except: pass
   try:
    _v = _secc
    if _v is not None and _v == 311 and _qaccel > 0.01 and _qaccel < 0.05 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 1.50
   except: pass
   try:
    _v = _secc
    if _v is not None and _v == 206 and _qaccel > 0.01 and _qaccel < 0.05 and _r3 < 0 and _r3 > -0.10 and _r5 > 0 and _d4_12: score *= 1.50
   except: pass
   try:
    _v = _cashc
    if _v is not None and _v > 5e9 and _qaccel > 0.01 and _qaccel < 0.05 and _d4_8: score *= 0.85
   except: pass
   if _qsneg and _hyg_up3 and decline > 0.08: continue  # BAKE-357 R1387 +0.0075
   if _qpos and _hi_cape and _hyg_up3 and decline > 0.20: continue  # BAKE-359 R1393 +0.0074
   if _qsneg and _hi_vol and decline > 0.12: continue  # BAKE-360 R1392/R1394 +0.0037/+0.0038
   # --- ENTRY INJECT POINT ---
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
     _roe9 = f_(_ops_z.roe.one_year)
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
     _roe16 = f_(_ops_z.roe.one_year)
     if _roe16 and _roe16>.20 and _qa_scan and len(_qa_scan)>=10 and _ha_scan and len(_ha_scan)>=5:
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
      continue  # C1: skip stocks with severe revenue collapse during decline
   except: pass
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
     _rg22 = _rg1yc
     if _rg22 and _rg22>.20 and _ha_scan and len(_ha_scan)>=10:
      _bd22 = _bd10
      if _bd22>.02:
       score *= 0.90
   except: pass
   try:
    if _ops_z:
     _gm24 = _gm1yc
     if _gm24 and _gm24>.40 and _ha_scan and len(_ha_scan)>=5:
      _bd24 = _bd5
      if _bd24>.015:
       score *= 0.87
   except: pass
   try:
    if _ops_z and _vr_z:
     _gm25 = _gm1yc
     _pe25 = _pec
     if _gm25 and _gm25>.40 and _qa_scan and len(_qa_scan)>=10:
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
      _w120 = list(self.history[TradeBar](sym, 120, _RD))
      if _w120 and len(_w120)>=120:
       _r120 = (f_(_w120[-1].close)-f_(_w120[0].close))/f_(_w120[0].close)
       if _r120<-.30:
        score *= 1.20
   except: pass
   try:
    if _returns20:
     _v27 = (sum(x*x for x in _returns20)/len(_returns20))**0.5
     if _v27>.06:
      conv *= 0.50
   except: pass
   try:
    if _ops_z:
     _rg29 = _rg1yc
     if _rg29 and _rg29>.15 and _qa_scan and len(_qa_scan)>=20:
      _qd20br = _qd20
      if _qd20br>.10 and decline<.10:
       score *= 0.80
   except: pass
   try:
    if _ha_scan and len(_ha_scan)>=20:
     _bra = [f_(_ha_scan[i].close)/f_(_ha_scan[i-1].close)-1 for i in range(1,20) if f_(_ha_scan[i-1].close)>0]
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
    if _qa_scan and len(_qa_scan) >= 5:
     _qd5 = _qd5
     if _qd5 < -0.03 and decline > .03: score *= 1.25
    if _ha_scan and len(_ha_scan) >= 5:
     _bd5x = _bd5
     if _qd5 < -0.03 and _bd5x < 0 and decline > .05: score *= 1.20
   except: pass
   try:
    if (_qa_scan and len(_qa_scan) >= 5 and _ha_scan and len(_ha_scan) >= 5 and
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
    if _v < 60 and _qaccel > -0.01 and _qaccel < 0.01 and _d6_12: wt_tilt *= 0.7
   except: pass
   # --- ENTRY WT_TILT INJECT POINT ---
   candidates.append((sym, score, conv, wt_tilt))
  if not candidates: return
  WT_TILT_CAP = 2.0  # hard cap on per-symbol weight tilt
  ranked = sorted(candidates, key=lambda c: c[1], reverse=True)
  total_value = f_(self.portfolio.total_portfolio_value) or 1
  existing_pct = sum(abs(f_(h.holdings_value))/total_value for h in self.portfolio.values()
                     if h.invested and h.symbol not in self._hedge_syms)
  remaining_budget = max(0, gross_target - existing_pct)
  if remaining_budget <= 0: return
  new_targets = []
  used = 0.0
  for sym, score, conv, wt_tilt in ranked:
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
