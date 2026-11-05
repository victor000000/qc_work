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
# === STRATEGY ===
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
   score = math.log2(math.log2(_bv))
   if decline < .05:
    conv = max(1.0, 1.0 + (decline - .02) * (1.5/.10))
   else:
    conv = 1.0 + .375 + (decline - .05) * (3.5/.10)
   conv = min(5.0, conv)
   if vol_climax: conv *= .70
   wt_tilt = 1.0
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
   try:
    if -0.10<_r7<-0.05: score *= 1.08
   except: pass
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
   try:
    if _bc > 150 and _qzero and _d6_12: score *= 1.05
   except: pass
   try:
    if _bc > 150 and -0.05<_qa<-0.01 and _d6_12: score *= 0.95
   except: pass
   try:
    if _bc > 150 and -0.05<_qa<-0.01 and _d4_8: score *= 0.75
   except: pass
   try:
    _v = f_(_bs_z.cash_equivalents.three_months)
    if _v > 1e8 and _qpos and _d6_12: score *= 1.30
   except: pass
   try:
    if -0.30<_r7<-0.10 and _qzero and _d4_12: score *= 0.85
   except: pass
   try:
    if _nlt(_qd5,-0.05) and _d4_12:
     score *= 0.95
     if -0.05<_qa<-0.01:
      score *= 0.85
      if _r5 < 0: score *= 0.75
   except: pass
   try:
    if -0.20<_r7<-0.05 and _qzero and _d2_4: score *= 0.55
   except: pass
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
   try:
    if -0.20<_r7<-0.05 and _qzero and _d4_8: score *= 0.75
   except: pass
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
   try:
    if _bc < 50 and -0.05<_qa<-0.01 and _d4_8: score *= 0.75
   except: pass
   try:
    if 50<_bc<100 and -0.05<_qa<-0.01 and _d4_8: score *= 0.95
   except: pass
   try:
    if _bc < 50 and -0.05<_qa<-0.01 and _d6_12: score *= 1.30
   except: pass
   try:
    if _bc < 50 and _qzero and _d4_8: score *= 0.95
   except: pass
   try:
    if 50<_bc<100 and -0.05<_qa<-0.01 and _d6_12: score *= 1.05
   except: pass
   try:
    if _bc > 150 and -0.05<_qa<-0.01 and _d6_12: score *= 1.14
   except: pass
   try:
    if 75<_bc<100 and -0.05<_qa<-0.01 and _d4_8: score *= 0.85
   except: pass
   try:
    if 30<_bc<50 and -0.05<_qa<-0.01 and _d4_8: score *= 0.95
   except: pass
   try:
    if 75<_bc<100 and -0.05<_qa<-0.01 and _d6_12: score *= 0.55
   except: pass
   try:
    if 25<_bc<50 and -0.05<_qa<-0.01 and _d6_12: score *= 1.05
   except: pass
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
   try:
    if _ngt(_vol20,0.06) and _qzero and _r3_md and _r5_up and _d4_12: score *= 0.50
   except: pass
   try:
    _v = _vsc
    if _v > 50 and _qzero and _r3_md and _r5_up and _d4_12: score *= 1.05
   except: pass
   try:
    if _nrg(_r7,0,0.20) and _qzero and _r3_md and _r5_up and _d4_12: score *= 1.14
   except: pass
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
   try:
    if _qsneg and _nlt(_r5,-0.05) and _hyg_dn3 and decline > 0.04: continue
   except: pass
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
   candidates.append((sym, score, conv, wt_tilt))
  if not candidates: return
  WT_TILT_CAP = 2.0
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
