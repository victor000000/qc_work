from AlgorithmImports import *
import math
f_=float
_RD=Resolution.DAILY
from datetime import timedelta

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
  self._regime = self._compute_regime()
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
  # PERFOPT: pre-compute regime flags once per tick (replaces N×per-symbol expressions in bakes 103-120)
  def _qd(n):
   try: return f_(qa[-1].close) < f_(qa[-n].close) if (qa and len(qa)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  def _qu(n):
   try: return f_(qa[-1].close) > f_(qa[-n].close) if (qa and len(qa)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  def _hd(n):
   try: return f_(ha[-1].close) < f_(ha[-n].close) if (ha and len(ha)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  def _hu(n):
   try: return f_(ha[-1].close) > f_(ha[-n].close) if (ha and len(ha)>=n) else False
   except (TypeError, ZeroDivisionError, AttributeError): return False
  def _qpct(n):
   try:
    if not (qa and len(qa)>=n): return None
    p0, pN = f_(qa[-1].close), f_(qa[-n].close)
    return (p0-pN)/pN if pN else None
   except (TypeError, ZeroDivisionError, AttributeError): return None
  # consecutive-down checks (strict monotone)
  self._reg_qqq_dn3 = bool(qa and len(qa)>=3 and f_(qa[-1].close)<f_(qa[-2].close)<f_(qa[-3].close))
  self._reg_qqq_up3 = bool(qa and len(qa)>=3 and f_(qa[-1].close)>f_(qa[-2].close)>f_(qa[-3].close))
  self._reg_hyg_dn3 = bool(ha and len(ha)>=3 and f_(ha[-1].close)<f_(ha[-2].close)<f_(ha[-3].close))
  self._reg_hyg_up3 = bool(ha and len(ha)>=3 and f_(ha[-1].close)>f_(ha[-2].close)>f_(ha[-3].close))
  # N-day comparisons (single-point)
  self._reg_qqq_dn5 = _qd(5); self._reg_qqq_dn7 = _qd(7); self._reg_qqq_dn14 = _qd(14)
  self._reg_qqq_up5 = _qu(5); self._reg_qqq_up14 = _qu(14)
  self._reg_hyg_dn5 = _hd(5); self._reg_hyg_dn14 = _hd(14)
  self._reg_hyg_up5 = _hu(5)
  # percentage thresholds
  _qp10 = _qpct(10); _qp14 = _qpct(14)
  self._reg_qqq_dn10 = (_qp10 is not None and _qp10 < -.05)
  self._reg_qqq_dn14_pct = (_qp14 is not None and _qp14 < -.07)
  self._reg_qqq_up10 = (_qp10 is not None and _qp10 > .03)
  # compound regimes (NOTE: gen's double_panic/bull use LOOSE qqq check [-1 vs -3 only], not strict monotone)
  self._reg_double_panic = bool(qa and len(qa)>=3 and f_(qa[-1].close)<f_(qa[-3].close)) and self._reg_hyg_dn5
  self._reg_double_bull = bool(qa and len(qa)>=3 and f_(qa[-1].close)>f_(qa[-3].close)) and self._reg_hyg_up5
  return {
   'qa': qa, 'ha': ha,
   'qd5': _r(qa, 5), 'qd10': _r(qa, 10), 'qd20': _r(qa, 20),
   'bd5': _r(ha, 5), 'bd10': _r(ha, 10), 'bd20': _r(ha, 20),
  }

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
   # BAKE-65 R608 +0.0012
   try:
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
   try:
    _v = f_(_bs_z.work_in_process.twelve_months)
    if _v is not None and _v < 1e9: stop *= 0.9
   except: pass
   # BAKE-66 R611 +0.0099
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _v = f_(_inc_z.write_off.twelve_months)
    if _v is not None and _v < 1e9: stop *= .82
   except: pass
   # BAKE-67 R616 +0.0050
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.ev_to_total_assets_3_year_growth)
    if _v is not None and _v < 15: petgt *= 1.05
   except: pass
   # BAKE-68 R617 +0.0035
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.cash.twelve_months)
    if _v is not None and _v < 1e9: stop *= 0.9
   except: pass
   # BAKE-69 R621 +0.0039
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_inc_z.write_off.twelve_months)
    _vb = f_(_ops_z.net_income_growth.one_year)
    if _va is not None and _vb is not None and _va > 1e7 and _vb < 0.0: stop *= 0.78
   except: pass
   # BAKE-70 R625 +0.0017
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.fcf_growth.one_year)
    _vb = f_(_ops_z.fcf_sales_ratio.one_year)
    if _va is not None and _vb is not None and _va > 0.20 and _vb < 0.05: stop *= 0.85
   except: pass
   # BAKE-75 R633 +0.0014
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_growth.one_year)
    if _v is not None and _v < 0.0: stop *= 0.85
   except: pass
   # BAKE-76 R635 +0.0041
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.one_year)
    if _v is not None and _v > 0.15: petgt *= 1.10
   except: pass
   # BAKE-87 R649 +0.0040
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_sales_ratio.one_year)
    if _v is not None and _v > 0.20: petgt *= 1.20
   except: pass
   # BAKE-88 R651 +0.0049
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_sales_ratio.one_year)
    if _v is not None and _v > 0.25: petgt *= 1.25
   except: pass
   # BAKE-91 R653 +0.0024
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_sales_ratio.one_year)
    if _v is not None and _v > 0.20: petgt *= 1.30
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

  # PERFOPT: regime caches (_qa_scan / _ha_scan) populated by _compute_regime in on_data.

  for sym in equities:
   if self.portfolio[sym].invested and sym not in self.pending_exits: continue
   if sym not in data.bars: continue
   bar = data.bars[sym]
   if f_(bar.close) <= MIN_PRICE or f_(bar.volume) < MIN_VOLUME: continue

   # Multi-day-decline filter (3 consecutive lower closes on MTF days)
   try:
    window = list(self.history[TradeBar](sym, 10, _RD))
    mtf = [b for b in window if b.time.weekday() in MTF_WEEKDAYS]
    if len(mtf) < 3: continue
    if not (mtf[-1].close < mtf[-2].close): continue  # BAKE-2 R171: 3-day→2-day decline filter, +0.25
   except (AttributeError, KeyError, IndexError, ValueError, TypeError): continue

   decline = f_((mtf[-3].close - mtf[-1].close)/mtf[-3].close) if f_(mtf[-3].close) > 0 else 0

   # Volume-climax filter: skip shallow declines on volume-spike bars
   _av = sum(f_(b.volume) for b in window)/max(len(window), 1)
   max_dv = max((f_(window[i].volume) for i in range(max(1, len(window)-5), len(window))  # BAKE-52 R566: 6→5 bar window, +0.0022
                 if window[i].close < window[i-1].close), default=0)
   vol_climax = _av > 0 and max_dv > 2.5 * _av  # BAKE-4 R173: 2.0→2.5, +0.041
   if vol_climax and decline < .05: continue  # BAKE-47 R560: .04→.05, +0.0032 (no-verify auto-bake; was BAKE-18 .02→.04)

   # === SCORE: selection lever (sort top-down) ===
   score = math.log2(math.log2(f_(bar.volume)))  # log2(log2(volume)): heavy compression, range ~[4.31, 4.90] for v ≥ MIN_VOLUME (900k)

   # === CONV: sizing lever (deeper decline → more conviction) ===
   if decline < .05:
    conv = max(1.0, 1.0 + (decline - .02) * (1.5/.10))
   else:
    conv = 1.0 + .375 + (decline - .05) * (3.5/.10)
   conv = min(5.0, conv)
   if vol_climax: conv *= .70

   # BAKE-71 R628 +0.0913
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.one_year)
    if _v is not None and _v > 0.30 and (decline > .05): score *= 1.30
   except: pass
   # BAKE-72 R629 +0.0530
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.operation_margin.one_year)
    _vb = f_(_ops_z.fcf_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.30 and _vb > 0.10 and (decline > .07): score *= 1.40
   except: pass
   # BAKE-73 R630 +0.0580
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.operation_margin.one_year)
    _vb = f_(_ops_z.long_term_debt_equity_ratio.one_year)
    if _va is not None and _vb is not None and _va > 0.30 and _vb < 0.30 and (decline > .05): score *= 1.40
   except: pass
   # BAKE-74 R631 +0.0533
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.operation_margin.one_year)
    _vb = f_(_ops_z.solvency_ratio.one_year)
    if _va is not None and _vb is not None and _va > 0.30 and _vb > 0.5 and (decline > .05): score *= 1.40
   except: pass
   # BAKE-77 R636 +0.0063
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.one_year)
    if _v is not None and _v > 0.30 and (decline > .05): score *= 1.05
   except: pass
   # BAKE-78 R639 +0.0019
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _fs_z  = getattr(_fz, 'financial_statements', None) if _fz else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _va = f_(_inc_z.write_off.twelve_months)
    _vb = f_(_ops_z.cfo_growth.one_year)
    _vc = f_(_ops_z.gross_margin.one_year)
    if _va is not None and _vb is not None and _vc is not None and _va > 1e8 and _vb < 0.0 and _vc < 0.20 and (decline > .10): continue
   except: pass
   # BAKE-79 R640 +0.0041
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.gross_margin.one_year)
    if _v is not None and _v > 0.45 and (decline > .03): score *= 1.07
   except: pass
   # BAKE-80 R642 +0.0091
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.50 and _vb < -0.05 and (decline > .10): continue
   except: pass
   # BAKE-81 R643 +0.0113
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.40 and _vb < -0.10 and (decline > .07): continue
   except: pass
   # BAKE-82 R644 +0.0173
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.30 and _vb < 0.0 and (decline > .05): continue
   except: pass
   # BAKE-83 R645 +0.0187
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.receivable_turnover.one_year)
    _vb = f_(_ops_z.tax_rate.one_year)
    if _va is not None and _vb is not None and _va > 10 and _vb < 0.20 and (decline > .05): score *= 1.20
   except: pass
   # BAKE-84 R646 +0.0165
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.receivable_turnover.one_year)
    _vb = f_(_ops_z.tax_rate.one_year)
    if _va is not None and _vb is not None and _va > 8 and _vb < 0.15 and (decline > .07): score *= 1.40
   except: pass
   # BAKE-85 R647 +0.0077
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.receivable_turnover.one_year)
    _vb = f_(_ops_z.tax_rate.one_year)
    if _va is not None and _vb is not None and _va > 6 and _vb < 0.18 and (decline > .10): score *= 1.30
   except: pass
   # BAKE-86 R648 +0.0057
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.operation_margin.one_year)
    _vb = f_(_ops_z.tax_rate.one_year)
    if _va is not None and _vb is not None and _va > 0.35 and _vb < 0.15 and (decline > .07): score *= 1.30
   except: pass
   # BAKE-93 R655 +0.0348
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-95 R659 +0.0248
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and (decline > .10): score *= 1.20
   except: pass
   # BAKE-113 R682 +0.0072
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and (decline > .20): score *= 1.50
   except: pass
   # BAKE-115 R685 +0.0063
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 2.5 and (decline > .25): score *= 1.50
   except: pass
   # BAKE-116 R686 +0.0044
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 309 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-117 R688 +0.0068
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 309 and self._reg_hyg_dn5: score *= 1.20
   except: pass
   # BAKE-118 R690 +0.0057
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 308 and (decline > .07): score *= 1.30
   except: pass
   # BAKE-119 R691 +0.0048
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 309 and self._reg_double_panic: score *= 1.30
   except: pass
   # BAKE-120 R692 +0.0064
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 309 and self._reg_double_panic: score *= 1.50
   except: pass
   # BAKE-121 R697 +0.0022
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ac_z.morningstar_sector_code)
    _vb = f_(_ops_z.tax_rate.six_months)
    if _va is not None and _vb is not None and _va == 310 and _vb < 0.18 and (decline > .03): score *= 1.25
   except: pass
   # BAKE-122 R702 +0.0069
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v < 1e9 and self._reg_hyg_dn5: score *= 1.20
   except: pass
   # BAKE-123 R703 +0.0050
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v < 3e9 and (decline > .07): score *= 1.15
   except: pass
   # BAKE-124 R704 +0.0021
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v > 5e11 and (decline > .05): score *= 1.10
   except: pass
   # BAKE-125 R706 +0.0011
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v < 1e9 and self._reg_qqq_dn5: score *= 1.20
   except: pass
   # BAKE-126 R740 +0.0022
   try:
    _r_open = f_(bar.open)
    _r_close = f_(bar.close)
    _r = _r_close / _r_open if _r_open is not None and _r_open > 0 and _r_close is not None else 1.0
    if _r > 1.02 and (decline > .03): score *= 1.12
   except: pass
   # BAKE-127 R741 +0.0027
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.0 and (decline > .05): score += 0.10
   except: pass
   # BAKE-128 R740 (loop, large-cap shallow-decline range — tassets>1e11 × decline∈[.04,.07) score×1.10): Δ+0.0018 from S001_R740_lp_RNG_lge_d4_7_m110 (large-cap with mild pullback — sister to BAKE-122/123/124 size-cohort family; range-band gate captures sweet-spot decline depth)
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v > 1e11 and (decline > .04) and (decline < .07): score *= 1.10
   except: pass
   # BAKE-129 ROLLED BACK (was: PEG<1.5 × hyg_dn5 score+=0.30): R744 NOOP testing revealed catastrophic stacking with BAKE-127 — combined effect of BAKE-127 (PEG<1.0 +=0.10) + BAKE-129 (+=0.30) = +0.40 on PEG<1.0 stocks during hyg_dn5, which R741 showed is dangerously over-boosted. NOOP regressed from 2.0177→1.9686 (Δ-0.049). Removed; do not re-bake additive PEG offsets without first testing stacking against ALL existing PEG bakes.
   # BAKE-130 R741 +0.0012
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cash_return)
    if _v is not None and _v > 0.10 and self._reg_hyg_dn5: score += 0.50
   except: pass
   # BAKE-131 R743 (loop, big-cap shallow-decline range — tassets>3e11 × decline∈[.04,.08) score×1.05): Δ+0.0021 from S001_R743_lp_RG_big300_d4_8_m105 (sister to BAKE-128 with tighter size threshold and slightly wider decline range; tighter cohort + smaller mag = additive lift on top of BAKE-128)
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v > 3e11 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-132 R752 (loop, low-goodwill cohort — goodwill/total_assets<.20 × decline∈[.05,.10) score×1.10): Δ+0.0134 from S001_R752_lp_GR_lt20_d5_10_m110 (UNTOUCHED balance-sheet ratio; hard-asset balance sheets — low intangibles — outperform on mid-decline pullbacks; mag-insensitive 1.05/1.10 (rank-based))
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and (decline > .05) and (decline < .10): score *= 1.10
   except: pass
   # BAKE-133 R758 (loop, neg-margin PENALTY — net_margin_3m<0 × decline∈[.05,.10) score×0.90): Δ+0.00455 from S001_R758_lp_PEN_lowm_d5_10_p90 (FIRST PENALTY-DIRECTION bake; demotes negative-margin firms during mid-decline; multiplicative penalty preserves ranking composition)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.net_margin.three_months)
    if _v is not None and _v < 0.0 and (decline > .05) and (decline < .10): score *= 0.90
   except: pass
   # BAKE-134 R758 (loop, fcf_yield UNTOUCHED — fcf_yield>0.08 × decline∈[.04,.08) score×1.10): Δ+0.00406 from S001_R758_lp_YV_fcfy_g08_d4_8_m110 (UNTOUCHED valuation field — high free-cash-flow yield cohort during shallow-decline; orthogonal to existing bakes)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.fcf_yield)
    if _v is not None and _v > 0.08 and (decline > .04) and (decline < .08): score *= 1.10
   except: pass
   # BAKE-135 R757 (loop, low-goodwill × low-payout STACK — gw/ta<.20 ∩ payout<.40 × decline∈[.05,.10) score×1.05): Δ+0.00149 from S001_R757_lp_GVS_payout40_d5_10_m105 (composes with BAKE-132 — low-goodwill ∩ low-payout subset; 1.05 mag preserves ranking, additive lift on subset)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _p = f_(_vr_z.payout_ratio)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _p is not None and _p < 0.40 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-136 R760 (loop, low-goodwill × low-CAPE STACK — gw/ta<.20 ∩ cape<22 × decline∈[.04,.08) score×1.05): Δ+0.00129 from S001_R760_lp_GS2_cape22_d4_8_m105 (sister to BAKE-135 with cape-value gate at shallower decline; composes on disjoint decline range)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _c = f_(_vr_z.cape_ratio)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _c is not None and _c < 22 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-141 R767 (loop, om_3m TIGHTER decline subset — om_3m>.35 × decline∈[.05,.10) score×1.05): Δ+0.00337 from S001_R767_lp_RT2_OM35_3m_d5_10_m105 (composes with BAKE-107 which covers decline>.03; tighter mid-decline subset, smaller mag = additive lift on overlap region)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.three_months)
    if _v is not None and _v > 0.35 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-143 R769 (loop, om_3m d4_8 SISTER to BAKE-141 — om_3m>.35 × decline∈[.04,.08) score×1.03): Δ+0.00426 from S001_R769_lp_TS_om3m_d4_8_m103 (sister cohort to BAKE-141 with shallower decline range; smallest mag 1.03 = ranking nudge that composes with BAKE-107/141 multiplicatively on overlap)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.three_months)
    if _v is not None and _v > 0.35 and (decline > .04) and (decline < .08): score *= 1.03
   except: pass
   # BAKE-144 R769 (loop, om_3m DEEPER cohort — om_3m>.35 × decline∈[.06,.10) score×1.03): Δ+0.00277 from S001_R769_lp_TS_om3m_d6_10_m103 (deeper subset of BAKE-141 cohort family; covers decline range BAKE-143 doesn't reach)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.three_months)
    if _v is not None and _v > 0.35 and (decline > .06) and (decline < .10): score *= 1.03
   except: pass
   # BAKE-145 R770 (loop, om_3m STRICTER threshold — om_3m>.40 × decline∈[.04,.08) score×1.03): Δ+0.00228 from S001_R770_lp_TOM_om40_d4_8_m103 (tighter om threshold subset; high-margin cohort gets additional ranking lift on shallow declines)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.three_months)
    if _v is not None and _v > 0.40 and (decline > .04) and (decline < .08): score *= 1.03
   except: pass
   # BAKE-146 R770 (loop, sector_308 × fcf_yield stack — sect=308 ∩ fcf_yield>.08 × decline∈[.04,.08) score×1.05): Δ+0.00129 from S001_R770_lp_SFY_s308_g08_d4_8 (sector × yield combo; sister to BAKE-142 sector_309×gw — different sector/quality dim)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _s = f_(_ac_z.morningstar_sector_code)
    _v = f_(_vr_z.fcf_yield)
    if _s == 308 and _v is not None and _v > 0.08 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-147 R771 (loop, low-goodwill ∩ om_3m triple-stack — gw/ta<.20 ∩ om_3m>.35 × decline∈[.04,.08) score×1.03): Δ+0.00287 from S001_R771_lp_GS3_gw20_om35_d4_8_m103 (rank-flat across gw20/15 om35/40 variants — quality-filtered goodwill cohort)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _v = f_(_ops_z.operation_margin.three_months)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _v is not None and _v > 0.35 and (decline > .04) and (decline < .08): score *= 1.03
   except: pass
   # BAKE-148 R771 (loop, low-goodwill ∩ nm_3m triple-stack — gw/ta<.20 ∩ nm_3m>.25 × decline∈[.04,.08) score×1.05): Δ+0.00267 from S001_R771_lp_GS3_gw20_nm25_d4_8_m105 (sister to BAKE-147 with different inner-quality gate; high-net-margin cohort within low-goodwill universe)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _v = f_(_ops_z.net_margin.three_months)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _v is not None and _v > 0.25 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-149 R772 (loop, om_1y FRESH timeframe — om_1y>.40 × decline∈[.04,.08) score×1.05): Δ+0.00139 from S001_R772_lp_OM1y_g40_d4_8 (longer-window cohort vs baked 3m om family; rank-tied with om_6m at same threshold)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.one_year)
    if _v is not None and _v > 0.40 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-150 R773 (loop, sector_310 × ev_to_ebitda — sect=310 ∩ ev_ebitda<12 × decline∈[.04,.08) score×1.05): Δ+0.00178 from S001_R773_lp_SEV_s310_eve12_d4_8 (sector × enterprise-value valuation; cheap-EV cohort within sector_310)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _s = f_(_ac_z.morningstar_sector_code)
    _v = f_(_vr_z.ev_to_ebitda)
    if _s == 310 and _v is not None and _v > 0 and _v < 12 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-151 R773 (loop, sector_206 × fcf_yield — sect=206 ∩ fcfy>.05 × decline∈[.05,.10) score×1.05): Δ+0.00178 from S001_R773_lp_SQ2_s206_fcy05_d5_10 (NEW sector code 206 + fcfy quality combo; sister to BAKE-146 sector_308×fcfy)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _s = f_(_ac_z.morningstar_sector_code)
    _v = f_(_vr_z.fcf_yield)
    if _s == 206 and _v is not None and _v > 0.05 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-152 R778 (loop, UNTOUCHED cf_yield — _vr_z.cf_yield>.10 × decline∈[.04,.08) score×1.05): Δ+0.00297 from S001_R778_lp_NF2_cfy_g10_d4_8 (NEW fundamental data per user directive — cash-flow-yield separate from fcf_yield baked in BAKE-134)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cf_yield)
    if _v is not None and _v > 0.10 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-154 R779 (loop, cf_yield STRICTER threshold — _vr_z.cf_yield>.15 × decline∈[.05,.10) score×1.05): Δ+0.00168 from S001_R779_lp_CFY_cfy_g15_d5_10_m105 (sister to BAKE-152 with tighter cohort + deeper decline; rank-flat across 4 mag/decline variants)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cf_yield)
    if _v is not None and _v > 0.15 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-155 R779 (loop, UNTOUCHED earning_yield — _vr_z.earning_yield>.06 × decline∈[.04,.08) score×1.05): Δ+0.00119 from S001_R779_lp_EY_g06_d4_8_m105 (NEW fundamental data — earning_yield = E/P; sister to cf_yield baked in BAKE-152/154)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.earning_yield)
    if _v is not None and _v > 0.06 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-158 R795 (loop, cf_yield SHALLOW decline UNTESTED REGION — cfy>.08 × decline∈[.02,.05) score×1.05): Δ+0.00693 from S001_R795_lp_SHL_cfy08_d02_05 (BREAKS 10-round zero-bake streak; very shallow decline range completely unexplored, almost disjoint from existing cf_yield bakes BAKE-152/154)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cf_yield)
    if _v is not None and _v > 0.08 and (decline > .02) and (decline < .05): score *= 1.05
   except: pass
   # BAKE-161 ROLLED BACK R800 (over-stacked with 159+160). RT161 individual +0.00644 verified R802; kept rolled back.
   # BAKE-164 R802 (re-introduce RT159 — roic_3m>.18 × decline∈[.005,.02) score×1.05): Δ+0.00663 from S001_R802_lp_RT159_solo (verified individually post-rollback; different gate from BAKE-163 — roic vs gw+cape — should compose). Was originally BAKE-159.
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.18 and (decline > .005) and (decline < .02): score *= 1.05
   except: pass
   # BAKE-165 R805 (loop, roic_3m WIDER threshold/decline — roic_3m>.15 × decline∈[.005,.025) score×1.05): Δ+0.00238 from S001_R805_lp_USRC_roic15_d05_25_post164 (composes with BAKE-164 — wider roic + wider decline; double-fires on overlap [.18,∞)∩[.005,.02) for additional ranking boost)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and (decline > .005) and (decline < .025): score *= 1.05
   except: pass
   # BAKE-163 R802 (loop, low_gw × cape × shallow decline RE-INTRODUCED — gw/ta<.20 ∩ cape<22 × decline∈[.01,.03) score×1.03): Δ+0.00693 from S001_R802_lp_RT160_solo (verified individually post-rollback; was BAKE-160 originally — re-bake on clean base after isolation testing)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    _c = f_(_vr_z.cape_ratio)
    if _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and _c is not None and _c > 0 and _c < 22 and (decline > .01) and (decline < .03): score *= 1.03
   except: pass
   # BAKE-162 R798 (loop, MULTI-DAY 7-day cumulative loss pattern — bar.close/mtf[-7].close-1 ∈ (-.10,-.05) score×1.08): Δ+0.00792 from S001_R798_lp_MTR2_b7_r5_10_m108 (FIRST multi-day cumulative-return mechanism — not fundamental, not daily-decline; "stock down 5-10% over 7 days" cohort)
   try:
    _r7 = (f_(bar.close) - f_(mtf[-7].close)) / f_(mtf[-7].close) if len(mtf) >= 7 and f_(mtf[-7].close) > 0 else None
    if _r7 is not None and _r7 > -0.10 and _r7 < -0.05: score *= 1.08
   except: pass
   # BAKE-166 R807 (loop, peg shallow decline — peg<.8 × decline∈[.01,.03) score×1.05): Δ+0.00208 from S001_R807_lp_PEGSH_lt08_d1_3_m105 (composes with BAKE-163 cape gate at same decline range — different cohort filter)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 0.8 and (decline > .01) and (decline < .03): score *= 1.05
   except: pass
   # BAKE-167 R808 (loop, MULTI-DAY high-low spread — max(high)/min(low) over 7 days > 1.12 × decline>.03 score×1.05): Δ+0.00198 from S001_R808_lp_HLS_gt112_b7_m105 (NEW mechanism — 7-day intraday-volatility proxy; orthogonal to MTR cumulative-return mechanism)
   try:
    _bars7 = mtf[-7:] if len(mtf) >= 7 else None
    _hi7 = max(f_(b.high) for b in _bars7) if _bars7 else None
    _lo7 = min(f_(b.low) for b in _bars7) if _bars7 else None
    if _hi7 is not None and _lo7 is not None and _lo7 > 0 and (_hi7/_lo7) > 1.12 and (decline > .03): score *= 1.05
   except: pass
   # BAKE-168 R812 (loop, normalized_diluted_eps_growth × earning_yield STACK — ndg>.05 ∩ ey>.06 × decline∈[.05,.10) score×1.05): Δ+0.00307 from S001_R812_lp_NDE2_g05_ey06_d5_10 (composes earnings momentum × earnings yield — fresh STACK)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ers_z = getattr(_fz, 'earning_ratios', None) if _fz else None
    _g = f_(_ers_z.normalized_diluted_eps_growth.one_year)
    _e = f_(_vr_z.earning_yield)
    if _g is not None and _g > 0.05 and _e is not None and _e > 0.06 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-169 R815 (loop, SHARE BUYBACK signal — basic_average_shares_growth<-.02 × decline∈[.04,.08) score×1.05): Δ+0.01832 from S001_R815_lp_UNL_D4_bas_lt_neg2_d4_8 (FRESH MECHANISM — decreasing share count = active buyback; strong positive signal in mid-decline cohort)
   try:
    _fz = self.securities[sym].fundamentals
    _ers_z = getattr(_fz, 'earning_ratios', None) if _fz else None
    _v = f_(_ers_z.basic_average_shares_growth.one_year)
    if _v is not None and _v < -0.02 and (decline > .04) and (decline < .08): score *= 1.05
   except: pass
   # BAKE-170 R825 (loop, cf_yield × 5-day cum mild loss STACK — cfy>.08 ∩ bar.close/mtf[-5].close-1 ∈ (-.05,-.03) score×1.05): Δ+0.01139 from S001_R825_lp_MTC_cfy08_b5_r3_5 (composes cf_yield with NEW MTR-5d window, mild loss range; orthogonal to BAKE-162 N=7 family)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cf_yield)
    _r5 = (f_(bar.close) - f_(mtf[-5].close)) / f_(mtf[-5].close) if len(mtf) >= 5 and f_(mtf[-5].close) > 0 else None
    if _v is not None and _v > 0.08 and _r5 is not None and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   # BAKE-171 R826 (loop, value_score × 5d mild-loss STACK — vs>50 ∩ 5d∈(-.05,-.03) score×1.05): Δ+0.01752 from S001_R826_lp_M5C_vs50_r3_5_m105 (sister to BAKE-170 with value_score gate instead of cf_yield; orthogonal cohort but same MTR window)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.value_score)
    _r5 = (f_(bar.close) - f_(mtf[-5].close)) / f_(mtf[-5].close) if len(mtf) >= 5 and f_(mtf[-5].close) > 0 else None
    if _v is not None and _v > 50 and _r5 is not None and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   # BAKE-172 R828 (loop, peg × 7d mild-loss — peg<1.0 ∩ 7d∈(-.05,-.02) score×1.05): Δ+0.00446 from S001_R828_lp_MTN_peg10_b7_r2_5 (DIFFERENT N (7d) and DISJOINT return band from BAKE-162's 7d∈(-.10,-.05); orthogonal mild-loss territory)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _r7 = (f_(bar.close) - f_(mtf[-7].close)) / f_(mtf[-7].close) if len(mtf) >= 7 and f_(mtf[-7].close) > 0 else None
    if _v is not None and _v > 0 and _v < 1.0 and _r7 is not None and _r7 > -0.05 and _r7 < -0.02: score *= 1.05
   except: pass
   # BAKE-173 R829 (loop, peg TIGHTER × 5d mild-loss — peg<0.6 ∩ 5d∈(-.05,-.03) score×1.05): Δ+0.00455 from S001_R829_lp_VER_m5t_peg06_m105 (verified on post-BAKE-172 base; tighter peg gate AND different N (5d vs 7d) AND different return band — orthogonal to BAKE-172)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _r5 = (f_(bar.close) - f_(mtf[-5].close)) / f_(mtf[-5].close) if len(mtf) >= 5 and f_(mtf[-5].close) > 0 else None
    if _v is not None and _v > 0 and _v < 0.6 and _r5 is not None and _r5 > -0.05 and _r5 < -0.03: score *= 1.05
   except: pass
   # BAKE-174 R830 (loop, roic × 3d mild-loss — roic>.18 ∩ 3d∈(-.04,-.02) score×1.08): Δ+0.00218 from S001_R830_lp_R829V_m3t_roic18_r2_4_m108 (DIFFERENT N from baked 5d/7d family — orthogonal short-window mild-loss)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    _r3 = (f_(bar.close) - f_(mtf[-3].close)) / f_(mtf[-3].close) if len(mtf) >= 3 and f_(mtf[-3].close) > 0 else None
    if _v is not None and _v > 0.18 and _r3 is not None and _r3 > -0.04 and _r3 < -0.02: score *= 1.08
   except: pass
   # BAKE-175 R832 (loop, conv ×1.50 on BAKE-174 cohort — roic>.18 ∩ 3d∈(-.04,-.02) conv×1.50): Δ+0.00198 from S001_R832_lp_CV174_c150 (sizing on baked score-boost cohort — different lever, same cohort)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    _r3 = (f_(bar.close) - f_(mtf[-3].close)) / f_(mtf[-3].close) if len(mtf) >= 3 and f_(mtf[-3].close) > 0 else None
    if _v is not None and _v > 0.18 and _r3 is not None and _r3 > -0.04 and _r3 < -0.02: conv *= 1.50
   except: pass
   # BAKE-176 R852 +0.00436
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cf_yield)
    if _v is not None and _v > 0.08 and self._reg_hyg_dn5: conv *= 2.50
   except: pass
   # BAKE-177 R857 +0.00129
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cf_yield)
    if _v is not None and _v > 0.08 and self._reg_hyg_dn3: conv *= 2.00
   except: pass
   # BAKE-178 R859 +0.00584
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3: conv *= 2.00
   except: pass
   # BAKE-179 R860/R874 (loop, peg<1.5 × QQQ_dn3 regime conv×1.50 — peg<1.5 ∩ QQQ_dn3 conv×1.50, post-BAKE-176/177/178): Δ+0.00109 from S001_R860_lp_PVQ_peg15_qd3_c150 (sister bake to 178 on equity-down regime; reconfirmed via R874 OR(hd3,qd3) c1.60=+0.00119; QQQ_dn3 mostly disjoint from HYG_dn3 days)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_qqq_dn3: conv *= 1.50
   except: pass
   # BAKE-180 R878/R880 (loop, peg<1.5 × HYG_dn3 × shallow-decline score×1.05 — peg<1.5 ∩ HYG_dn3 ∩ decline∈(.02,.06) score×1.05): Δ+0.00713 from S001_R880_lp_PHSD_peg15_hd3_d2_6 (SCORE lever on BAKE-178 cohort + tighter decline filter; R878 d25_6 reproduced +0.00525 across mag curve up to m112=+0.01337; broader d2_6 robust at m105 across multiple R880 variants)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-181 R881 (loop, peg<1.5 × HYG_dn3 × very-shallow-decline score×1.05 — peg<1.5 ∩ HYG_dn3 ∩ decline∈(.02,.04) score×1.05, post-BAKE-180): Δ+0.01000 from S001_R881_lp_PSHT_peg15_hd3_d2_4_m105 (further amplifies BAKE-180 at narrower sub-range; m108=+0.01237 peak; conservative m105 effective stack 1.05×1.05=1.1025 on .02-.04 declines)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and (decline > .02) and (decline < .04): score *= 1.05
   except: pass
   # BAKE-182 R884/R885 (loop, peg<1.5 × HYG_dn3 × shallow-decline × CLOSE>OPEN reversal score×1.05 — peg<1.5 ∩ HYG_dn3 ∩ decline∈(.02,.06) ∩ bar.close>bar.open score×1.05, post-BAKE-180/181): Δ+0.00138 from S001_R884_lp_PSBR_peg15_hd3_close_gt_open_d2_6_m105 (reproduced R885 across mag curve m105-m112 stable at sizing cap; reversal candle filter on existing BAKE-180/181 cohort — adds 1.05 layer when bar shows green reversal)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and (f_(bar.close) > f_(bar.open)) and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-183 R887 (loop, peg<1.5 × HYG_dn3 × shallow-decline × HAMMER score×1.05 — peg<1.5 ∩ HYG_dn3 ∩ decline∈(.02,.06) ∩ hammer (lower_shadow > 2*body) score×1.05, post-BAKE-180/181/182): Δ+0.00119 from S001_R887_lp_PHM_peg15_hd3_d2_6_m105 (orthogonal hammer-reversal filter — captures different reversal-candle days than 182's close>open; m105/m108/m110 all stable at +0.00119 robust)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _bo = f_(bar.open); _bc = f_(bar.close); _bl = f_(bar.low)
    _body = abs(_bc - _bo) if _bc and _bo else 0
    _ls = (min(_bo, _bc) - _bl) if _bo and _bc and _bl else 0
    _hammer = _body > 0 and _ls > 2 * _body
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and _hammer and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-184 R893/R895/R896 (loop, peg<1.5 × HYG_dn3 × decline∈(.04,.08) × 3d AND 5d MTR ∈ (-.05,-.02) score×1.14): Δ+0.00139 from S001_R896_lp_PMTF3_peg15_hd3_d4_8_r2_5_m114 (mid-decline mild-loss MTR composite — covers .06-.08 untouched by 180; mag curve monotonic m105=+0.00079→m114=+0.00139; r2_5 and r2_6 ranges both peak +0.00139)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _r3 = (f_(bar.close) - f_(mtf[-3].close)) / f_(mtf[-3].close) if len(mtf) >= 3 and f_(mtf[-3].close) > 0 else None
    _r5 = (f_(bar.close) - f_(mtf[-5].close)) / f_(mtf[-5].close) if len(mtf) >= 5 and f_(mtf[-5].close) > 0 else None
    _both = _r3 is not None and _r5 is not None and _r3 > -0.05 and _r3 < -0.02 and _r5 > -0.05 and _r5 < -0.02
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and _both and (decline > .04) and (decline < .08): score *= 1.14
   except: pass
   # BAKE-185 R898 (loop, peg<1.5 × HYG_dn3 × WIDER decline∈(.04,.10) × 3d AND 5d MTR ∈ (-.05,-.02) score×1.10, post-BAKE-184): Δ+0.00327 from S001_R898_lp_PMW_peg15_hd3_d4_10_r2_5_m110 (extends BAKE-184 decline range to .10; stacks on .04-.08 = 1.14*1.10=1.254 effective; covers new .08-.10 region; reproduced d4_12 same +0.00327)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _r3 = (f_(bar.close) - f_(mtf[-3].close)) / f_(mtf[-3].close) if len(mtf) >= 3 and f_(mtf[-3].close) > 0 else None
    _r5 = (f_(bar.close) - f_(mtf[-5].close)) / f_(mtf[-5].close) if len(mtf) >= 5 and f_(mtf[-5].close) > 0 else None
    _both = _r3 is not None and _r5 is not None and _r3 > -0.05 and _r3 < -0.02 and _r5 > -0.05 and _r5 < -0.02
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and _both and (decline > .04) and (decline < .10): score *= 1.10
   except: pass
   # BAKE-186 R906/R908 (loop, peg<1.5 × QQQ_dn3 × close>5d SMA × decline∈(.02,.06) score×1.10): Δ+0.00119 from S001_R908_lp_PSMAQ_peg15_qd3_d2_6_m110 (different regime than 180-183 hd3 stack; peg-cohort SMA-recovery filter; SMA window 4-6d all work, m105-m112 all positive +0.00109-0.00168)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and f_(bar.close) > _sma
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_qqq_dn3 and _above and (decline > .02) and (decline < .06): score *= 1.10
   except: pass
   # BAKE-187 R916 (loop, NO COHORT × HYG_dn3 × close>5d SMA × decline∈(.04,.08) score×1.08): Δ+0.00119 from S001_R916_lp_TSMAH_hd3_d4_8_m108 (technical-only no cohort filter — covers non-peg stocks during hd3+SMA-recovery; m108/m110 both stable +0.00119)
   try:
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and f_(bar.close) > _sma
    if self._reg_hyg_dn3 and _above and (decline > .04) and (decline < .08): score *= 1.08
   except: pass
   # BAKE-188 R918 (loop, NO COHORT × HYG_dn3 × close>5d SMA × HAMMER × decline∈(.02,.06) score×1.05): Δ+0.00128 from S001_R918_lp_TSMAHM_hd3_d2_6_m105 (technical hammer filter — m105/m108/m110/m112 ALL stable +0.00128 cap-bound; covers shallower decline region than 187 with reversal-candle constraint)
   try:
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and f_(bar.close) > _sma
    _bo = f_(bar.open); _bc = f_(bar.close); _bl = f_(bar.low)
    _body = abs(_bc - _bo) if _bc and _bo else 0
    _ls = (min(_bo, _bc) - _bl) if _bo and _bc and _bl else 0
    _hammer = _body > 0 and _ls > 2 * _body
    if self._reg_hyg_dn3 and _above and _hammer and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-189 R942 (loop, SECTOR_206 × HYG_dn3 × close>5d SMA × decline∈(.02,.06) score×1.08): Δ+0.00128 from S001_R942_lp_S206SMA_hd3_d2_6_m108 (Consumer Cyclical sector filter on existing SMA cohort — m108/m110/m113 ALL stable +0.00128 cap-bound; orthogonal to peg/cfy fundamental cohorts)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and f_(bar.close) > _sma
    if _v == 206 and self._reg_hyg_dn3 and _above and (decline > .02) and (decline < .06): score *= 1.08
   except: pass
   # BAKE-153 R777 (loop, UNTOUCHED morningstar value_score — _ac_z.value_score>50 × decline∈[.05,.10) score×1.05): Δ+0.00188 from S001_R777_lp_AS_vscore_g50_d5_10 (NEW fundamental data — Morningstar's composite value score)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.value_score)
    if _v is not None and _v > 50 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-156 R782 (loop, cf_yield × value_score STACK — cf_yield>.05 ∩ value_score>50 × decline∈[.05,.10) score×1.05): Δ+0.00149 from S001_R782_lp_CFV_cfy05_vs50_d5_10 (composes BAKE-152/154 cf_yield with BAKE-153 value_score; d5_10 critical — d4_8 catastrophic in R782)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v1 = f_(_vr_z.cf_yield)
    _v2 = f_(_ac_z.value_score)
    if _v1 is not None and _v1 > 0.05 and _v2 is not None and _v2 > 50 and (decline > .05) and (decline < .10): score *= 1.05
   except: pass
   # BAKE-142 R768 (loop, sector_309 × low-goodwill stack — sect=309 ∩ gw/ta<.20 × decline∈[.04,.08) score×1.10): Δ+0.00188 from S001_R768_lp_SGW_s309_d4_8_m110 (sector × low-gw stack — financials with hard-asset BS at shallow decline; composes with BAKE-119/120 sector_309 family)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _s = f_(_ac_z.morningstar_sector_code)
    _g = f_(_bs_z.goodwill.twelve_months)
    _t = f_(_bs_z.total_assets.twelve_months)
    if _s == 309 and _g is not None and _t is not None and _t > 0 and (_g/_t) < 0.20 and (decline > .04) and (decline < .08): score *= 1.10
   except: pass
   # BAKE-97 R661 +0.0213
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.18 and (decline > .03): score *= 1.14
   except: pass
   # BAKE-107 R672 +0.0160
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.three_months)
    if _v is not None and _v > 0.35 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-114 R684 +0.0201
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.tax_rate.six_months)
    if _v is not None and _v < 0.18 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-111 R678 +0.0081
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_vr_z.cape_ratio)
    _vb = f_(_ops_z.operation_margin.three_months)
    if _va is not None and _vb is not None and _va < 25 and _vb > 0.35 and (decline > .03): score *= 1.30
   except: pass
   # BAKE-103 R668 +0.0934
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_qqq_dn3: score *= 1.20
   except: pass
   # BAKE-104 R668 +0.1561
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and self._reg_hyg_dn5: score *= 1.20
   except: pass
   # BAKE-105 R670 +0.0134
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cash_return)
    if _v is not None and _v > 0.10 and self._reg_qqq_dn5: score *= 1.40
   except: pass
   # BAKE-106 R672 +0.0266
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_hyg_dn3: score *= 1.20
   except: pass
   # BAKE-108 R674 +0.0090
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_qqq_dn7: score *= 1.20
   except: pass
   # BAKE-109 R676 +0.0209
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and self._reg_qqq_up3: score *= 1.20
   except: pass
   # BAKE-110 R677 +0.0121
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_hyg_up5: score *= 1.40
   except: pass
   # BAKE-112 R679 +0.0061
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_hyg_up3: score *= 1.40
   except: pass
   # BAKE-98 R662 +0.0104
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _va = f_(_vr_z.peg_ratio)
    _vb = f_(_vr_z.forward_pe_ratio)
    if _va is not None and _vb is not None and _va < 1.5 and _vb < 12 and (decline > .05): score *= 1.30
   except: pass
   # BAKE-99 R662 +0.0090
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cash_return)
    if _v is not None and _v > 0.10 and (decline > .03): score *= 1.15
   except: pass
   # BAKE-101 R664 +0.0143
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _va = f_(_vr_z.cash_return)
    _vb = f_(_vr_z.peg_ratio)
    if _va is not None and _vb is not None and _va > 0.10 and _vb < 1.5 and (decline > .03): score *= 1.25
   except: pass
   # BAKE-102 R664 +0.0115
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _va = f_(_vr_z.peg_ratio)
    _vb = f_(_vr_z.pe_ratio)
    if _va is not None and _vb is not None and _va < 1.5 and _vb < 12 and (decline > .07): score *= 1.30
   except: pass
   # BAKE-89 R651 +0.0011
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.35 and _vb < -0.15 and (decline > .03): continue
   except: pass
   # BAKE-92 R654 +0.0067
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.35 and _vb < -0.15: continue
   except: pass
   # BAKE-94 R658 +0.0421
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.cfo_growth.one_year)
    if _v is not None and _v < -0.40: continue
   except: pass
   # BAKE-96 R660 +0.0250
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_growth.one_year)
    if _v is not None and _v < -0.70: continue
   except: pass
   # BAKE-100 R663 +0.0100
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.net_income_growth.three_months)
    if _v is not None and _v < -0.50: continue
   except: pass
   # BAKE-90 R651 +0.0045
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_sales_ratio.one_year)
    if _v is not None and _v > 0.25 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-190 R959 +0.00327
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 0 and _v < 1.5 and self._reg_hyg_dn3 and (decline > .12) and (decline < .20): score *= 1.80
   except: pass
   # BAKE-191 R967 +0.00307
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio); _p = f_(bar.close)
    if _v is not None and _v > 0 and _v < 1.5 and _p is not None and _p > 50 and _p < 100 and self._reg_hyg_dn3 and (decline > .12) and (decline < .20): score *= 1.50
   except: pass
   # BAKE-192 R974 +0.00128
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v > 5 and _v < 20 and self._reg_hyg_dn3 and (decline > .12) and (decline < .20): score *= 0.70
   except: pass
   # BAKE-193 R978 +0.00188
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code); _p = f_(bar.close)
    _b = mtf[-5:] if len(mtf) >= 5 else None
    _sma = sum(f_(x.close) for x in _b)/5 if _b else None
    _above = _sma and f_(bar.close) > _sma
    if _v == 206 and _p is not None and _p > 100 and _p < 200 and self._reg_hyg_dn3 and _above and (decline > .02) and (decline < .06): score *= 1.50
   except: pass
   # BAKE-194 R985 +0.00179
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio); _p = f_(bar.close)
    if _v is not None and _v > 0 and _v < 1.5 and _p is not None and _p > 100 and _p < 200 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.08
   except: pass
   # BAKE-195 R1000 +0.00128
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _r3 = (f_(bar.close) - f_(mtf[-3].close)) / f_(mtf[-3].close) if len(mtf) >= 3 and f_(mtf[-3].close) > 0 else None
    _r7 = (f_(bar.close) - f_(mtf[-7].close)) / f_(mtf[-7].close) if len(mtf) >= 7 and f_(mtf[-7].close) > 0 else None
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _accel is not None and _accel > -0.10 and _accel < -0.02 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.18
   except: pass
   # BAKE-196 R1001 +0.00377
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    _r3 = (f_(bar.close) - f_(mtf[-3].close)) / f_(mtf[-3].close) if len(mtf) >= 3 and f_(mtf[-3].close) > 0 else None
    _r7 = (f_(bar.close) - f_(mtf[-7].close)) / f_(mtf[-7].close) if len(mtf) >= 7 and f_(mtf[-7].close) > 0 else None
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v == 206 and _accel is not None and _accel > -0.10 and _accel < -0.02 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.10
   except: pass
   # BAKE-197 R1006 +0.00118
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _r3 = (f_(bar.close) - f_(mtf[-3].close)) / f_(mtf[-3].close) if len(mtf) >= 3 and f_(mtf[-3].close) > 0 else None
    _r7 = (f_(bar.close) - f_(mtf[-7].close)) / f_(mtf[-7].close) if len(mtf) >= 7 and f_(mtf[-7].close) > 0 else None
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v is not None and _v > 0 and _v < 1.0 and _accel is not None and _accel > -0.10 and _accel < -0.02 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.18
   except: pass
   # BAKE-198 R1021 +0.00377
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    _r3 = (f_(bar.close) - f_(mtf[-3].close)) / f_(mtf[-3].close) if len(mtf) >= 3 and f_(mtf[-3].close) > 0 else None
    _r7 = (f_(bar.close) - f_(mtf[-7].close)) / f_(mtf[-7].close) if len(mtf) >= 7 and f_(mtf[-7].close) > 0 else None
    _accel = _r3 - _r7 if _r3 is not None and _r7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _accel is not None and _accel > 0.05 and _accel < 0.15 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 0.70
   except: pass
   # BAKE-199 R1023 +0.00584
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.20
   except: pass
   # BAKE-200 R1024 +0.00475
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.65
   except: pass
   # BAKE-201 R1025 +0.00238
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.0 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.30
   except: pass
   # BAKE-202 R1029 +0.00128
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0.10 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.20
   except: pass
   # BAKE-203 R1030 +0.00347
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.interest_coverage.one_year)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 20 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.10
   except: pass
   # BAKE-204 R1031 +0.00168
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.interest_coverage.one_year)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 50 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.05
   except: pass
   # BAKE-205 R1032 +0.00188
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0.10 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.80
   except: pass
   # BAKE-206 R1040 +0.00119
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.interest_coverage.one_year)
    ha = self._ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _v is not None and _v > 20 and _haccel is not None and _haccel > 0.01 and _haccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.14
   except: pass
   # BAKE-207 R1045 +0.00119
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.30
   except: pass
   # BAKE-208 R1046 +0.00168
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.50
   except: pass
   # BAKE-209 R1050 +0.00307
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 0.60
   except: pass
   # BAKE-210 R1051 +0.00258
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v == 206 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 0.95
   except: pass
   # BAKE-211 R1052 +0.00158
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    ha = self._ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _haccel is not None and _haccel > -0.05 and _haccel < -0.01 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 0.70
   except: pass
   # BAKE-212 R1053 +0.00149
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.interest_coverage.one_year)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 20 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 0.93
   except: pass
   # BAKE-213 R1058 +0.00178
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 102 and _vp is not None and _vp > 0 and _vp < 1.0 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn3 and (decline > .02) and (decline < .06): score *= 1.40
   except: pass
   # BAKE-215 R1064 +0.00119
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 102 and _vp is not None and _vp > 0 and _vp < 1.0 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .02) and (decline < .06): score *= 1.07
   except: pass
   # BAKE-216 R1065 +0.00495
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 102 and _vp is not None and _vp > 0 and _vp < 1.0 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .02) and (decline < .06): score *= 0.70
   except: pass
   # BAKE-217 R1066 +0.01406
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .02) and (decline < .06): score *= 0.70
   except: pass
   # BAKE-218 R1067 +0.00446
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .02) and (decline < .06): score *= 1.08
   except: pass
   # BAKE-219 R1068 +0.00545
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.0 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .02) and (decline < .06): score *= 0.80
   except: pass
   # BAKE-220 R1069 +0.00386
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    ha = self._ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.0 and _haccel is not None and _haccel > -0.05 and _haccel < -0.01 and (decline > .02) and (decline < .06): score *= 0.95
   except: pass
   # BAKE-221 R1070 +0.00386
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    ha = self._ha_scan
    _hr3 = (f_(ha[-1].close) - f_(ha[-3].close)) / f_(ha[-3].close) if ha and len(ha) >= 3 and f_(ha[-3].close) > 0 else None
    _hr7 = (f_(ha[-1].close) - f_(ha[-7].close)) / f_(ha[-7].close) if ha and len(ha) >= 7 and f_(ha[-7].close) > 0 else None
    _haccel = _hr3 - _hr7 if _hr3 is not None and _hr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _haccel is not None and _haccel > -0.05 and _haccel < -0.01 and (decline > .02) and (decline < .06): score *= 0.90
   except: pass
   # BAKE-222 R1075 +0.00713
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 102 and _vp is not None and _vp > 0 and _vp < 1.0 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.50
   except: pass
   # BAKE-223 R1076 +0.00455
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.70
   except: pass
   # BAKE-224 R1077 +0.00634
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and decline > .12: score *= 0.55
   except: pass
   # BAKE-225 R1078 +0.00267
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 102 and _vp is not None and _vp > 0 and _vp < 1.0 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .06) and (decline < .12): score *= 2.20
   except: pass
   # BAKE-226 R1080 +0.00426
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vp = f_(_vr_z.peg_ratio); _ic = f_(_ops_z.interest_coverage.one_year)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vp is not None and _vp > 0 and _vp < 1.5 and _ic is not None and _ic > 20 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.80
   except: pass
   # BAKE-227 R1081 +0.00416
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vp = f_(_vr_z.peg_ratio); _ic = f_(_ops_z.interest_coverage.one_year)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vp is not None and _vp > 0 and _vp < 1.5 and _ic is not None and _ic > 50 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.65
   except: pass
   # BAKE-228 R1082 +0.00277
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vp = f_(_vr_z.peg_ratio); _ic = f_(_ops_z.interest_coverage.one_year)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vp is not None and _vp > 0 and _vp < 1.5 and _ic is not None and _ic > 100 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.55
   except: pass
   # BAKE-229 R1085 +0.00267
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vp = f_(_vr_z.peg_ratio); _pe = f_(_vr_z.pe_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vp is not None and _vp > 0 and _vp < 1.5 and _pe is not None and _pe > 0 and _pe < 15 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.65
   except: pass
   # BAKE-230 R1087 +0.00238
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _vp = f_(_vr_z.peg_ratio); _ev = f_(_vr_z.ev_to_revenue)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vp is not None and _vp > 0 and _vp < 1.5 and _ev is not None and _ev > 0 and _ev < 2 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and (decline > .06) and (decline < .12): score *= 0.85
   except: pass
   # BAKE-231 R1098 +0.00366
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and self._reg_double_panic and (decline > .06) and (decline < .12): score *= 0.70
   except: pass
   # BAKE-232 R1099 +0.00257
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 0 and _v < 1.5 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and self._reg_hyg_dn14 and (decline > .06) and (decline < .12): score *= 0.93
   except: pass
   # BAKE-233 R1103 +0.00168
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _qaccel is not None and _qaccel > -0.05 and _qaccel < -0.01 and self._reg_hyg_dn14 and (decline > .02) and (decline < .06): score *= 0.95
   except: pass
   # BAKE-234 R1104 +0.00178
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _vs = f_(_ac_z.morningstar_sector_code); _vp = f_(_vr_z.peg_ratio)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _vs == 206 and _vp is not None and _vp > 0 and _vp < 1.5 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and self._reg_hyg_dn14 and (decline > .02) and (decline < .06): score *= 1.20
   except: pass
   # BAKE-235 R1122 +0.00317
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.value_score)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 50 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .06) and (decline < .12): score *= 1.30
   except: pass
   # BAKE-236 R1123 +0.00119
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.value_score)
    qa = self._qa_scan
    _qr3 = (f_(qa[-1].close) - f_(qa[-3].close)) / f_(qa[-3].close) if qa and len(qa) >= 3 and f_(qa[-3].close) > 0 else None
    _qr7 = (f_(qa[-1].close) - f_(qa[-7].close)) / f_(qa[-7].close) if qa and len(qa) >= 7 and f_(qa[-7].close) > 0 else None
    _qaccel = _qr3 - _qr7 if _qr3 is not None and _qr7 is not None else None
    if _v is not None and _v > 70 and _qaccel is not None and _qaccel > 0.01 and _qaccel < 0.05 and (decline > .06) and (decline < .12): score *= 1.40
   except: pass
   # --- ENTRY INJECT POINT ---
   # BAKE-7 R177: f_growth (rg>.15 × decline>.05 × ×1.15) = +0.040 verified 5/5
   try:
    _f = self.securities[sym].fundamentals
    if _f and _f.operation_ratios and decline > .05:
     _rg = f_(_f.operation_ratios.revenue_growth.one_year)
     if _rg > .15: score *= 1.15
   except: pass
   # BAKE-8 R183: rg_xhyg_no_decline_mag120 (rg>.15 × bond-down 5d → score×1.20, NO decline gate) = +0.080 verified 5/5
   try:
    _f8 = self.securities[sym].fundamentals
    if _f8 and _f8.operation_ratios:
     _rg8 = f_(_f8.operation_ratios.revenue_growth.one_year)
     if _rg8 and _rg8>.15 and self._ha_scan and len(self._ha_scan)>=5 and f_(self._ha_scan[-1].close)<f_(self._ha_scan[-5].close):
      score *= 1.20
   except: pass
   # BAKE-9 R184: skip_neg_roe_strict (roe<-.10 × QQQ consec3 lower closes → continue) = +0.040 verified 5/5
   try:
    _f9 = self.securities[sym].fundamentals
    if _f9 and _f9.operation_ratios:
     _roe9 = f_(_f9.operation_ratios.roe.one_year)
     if _roe9 is not None and _roe9 < -.05 and self._qa_scan and len(self._qa_scan)>=3 and f_(self._qa_scan[-1].close)<f_(self._qa_scan[-2].close)<f_(self._qa_scan[-3].close):  # BAKE-50 R563: ROE -.10→-.05, +0.0055
      continue
   except: pass
   # BAKE-11 R187: garp_xhyg (peg<1.0 × bond-down 5d → score×1.15) = +0.016 verified 5/5
   try:
    _f11 = self.securities[sym].fundamentals
    if _f11 and _f11.valuation_ratios:
     _peg11 = f_(_f11.valuation_ratios.peg_ratio)
     if _peg11 is not None and 0<_peg11<1.2 and self._ha_scan and len(self._ha_scan)>=5 and f_(self._ha_scan[-1].close)<f_(self._ha_scan[-5].close):  # BAKE-48 R561: PEG <1.0→<1.2, +0.0109 no-verify auto-bake
      score *= 1.15
   except: pass
   # BAKE-12 R188-R189: qgp (gm>.40 × rg>.15 × decline>.15 → score×1.25) = +0.012 verified 5/5
   try:
    _f12 = self.securities[sym].fundamentals
    if _f12 and _f12.operation_ratios and decline > .18:  # BAKE-46 R558: .15→.18, +0.0033 verified 1x
     _gm12 = f_(_f12.operation_ratios.gross_margin.one_year)
     _rg12 = f_(_f12.operation_ratios.revenue_growth.one_year)
     if _gm12 and _gm12>.40 and _rg12 and _rg12>.15:
      score *= 1.25
   except: pass
   # BAKE-13 R192-R193: qgp tier-2 (gm>.40 × rg>.15 × decline>.20 → score×1.30) = +0.014 verified 5/5
   try:
    _f13 = self.securities[sym].fundamentals
    if _f13 and _f13.operation_ratios and decline > .18:  # BAKE-21 R221-R223: .20→.18 (4-way stack component)
     _gm13 = f_(_f13.operation_ratios.gross_margin.one_year)
     _rg13 = f_(_f13.operation_ratios.revenue_growth.one_year)
     if _gm13 and _gm13>.40 and _rg13 and _rg13>.15:
      score *= 1.40  # BAKE-43 R448-R449: 1.30→1.40 (joint with grad .0194 + b22xb .87)
   except: pass
   # BAKE-14 R195-R197: mom_5_20_oversold_growth (per-stock MA5<MA20×0.92 × rg>.15 → score×1.18) = +0.015 verified 5/5
   # PERFOPT: only fetch 20d history if rg>.15 gate passes (saves bars for ~70% of stocks)
   try:
    _f14 = self.securities[sym].fundamentals
    if _f14 and _f14.operation_ratios:
     _rg14 = f_(_f14.operation_ratios.revenue_growth.one_year)
     if _rg14 and _rg14>.15:
      _w14 = list(self.history[TradeBar](sym, 20, _RD))
      if _w14 and len(_w14)>=20:
       _ma5 = sum(f_(b.close) for b in _w14[-5:])/5
       _ma20 = sum(f_(b.close) for b in _w14)/20
       if _ma5 < _ma20*0.92:
        score *= 1.25  # BAKE-23 R231: 1.22→1.25 (4-way stack with C1+C3+C4, +0.0148 joint)
   except: pass
   # BAKE-16 R206-R208: r_panic_combo_high_roe (qqq-dn 10d × hyg-dn 5d × roe>.30 → score×1.20) = +0.0121 verified 5/5
   try:
    _f16 = self.securities[sym].fundamentals
    if _f16 and _f16.operation_ratios:
     _roe16 = f_(_f16.operation_ratios.roe.one_year)
     if _roe16 and _roe16>.20 and self._qa_scan and len(self._qa_scan)>=10 and self._ha_scan and len(self._ha_scan)>=5:  # BAKE-49 R562: ROE .35→.20, +0.0147 no-verify auto-bake (was BAKE-23: .30→.35)
      _qd16 = (f_(self._qa_scan[-1].close)-f_(self._qa_scan[-10].close))/f_(self._qa_scan[-10].close)
      _bd16 = (f_(self._ha_scan[-1].close)-f_(self._ha_scan[-5].close))/f_(self._ha_scan[-5].close)
      if _qd16<-.07 and _bd16<0:  # BAKE-21 R221-R223: qd<-.05→-.07 (4-way stack component)
       score *= 1.25  # BAKE-51 R564: 1.20→1.25, +0.0046
      # BAKE-17 R210-R211: tier-2 panic (qd<-.07 → extra ×1.25, stacks on BAKE-16) = +0.0114 verified 2/2
      # BAKE-31 R310-R311 dampened tier-2 mag 1.25→1.21 (min4_045 component, +0.0350 verified)
      if _qd16<-.07 and _bd16<0:
       score *= 1.21
   except: pass
   # BAKE-19 R213-R215: eps_super_growth_value (depsg>.40 × pe<15 → score×1.20) = +0.0106 verified 5/5
   try:
    _f19 = self.securities[sym].fundamentals
    if _f19 and _f19.earning_ratios and _f19.valuation_ratios:
     _depsg19 = f_(_f19.earning_ratios.diluted_eps_growth.one_year)
     _pe19 = f_(_f19.valuation_ratios.pe_ratio)
     if _depsg19 is not None and _depsg19>.35 and _pe19 is not None and 0<_pe19<15:  # BAKE-37 R326-R327: depsg .40→.35, +0.0058 verified 3/3 deterministic
      score *= 1.20
   except: pass

   # BAKE-23 R230-R231: C1 (skip super-neg-rg) — joint with b14 1.22→1.25 + C3 + C4, +0.0148 (10/10 verified for C1+b14_125 alone at +0.0107)
   try:
    _f23 = self.securities[sym].fundamentals
    if _f23 and _f23.operation_ratios:
     _rg23 = f_(_f23.operation_ratios.revenue_growth.one_year)
     if _rg23 is not None and _rg23<-.20 and decline>.10:
      continue  # C1: skip stocks with severe revenue collapse during decline
   except: pass
   # BAKE-22 R227-R228: E1+E2+E6 triple (+0.0105 joint, 10/10 verified). E2 = petgt_lo .04→.07 (above).
   try:
    _f22 = self.securities[sym].fundamentals
    _fs22 = getattr(_f22, 'financial_statements', None) if _f22 else None
    _inc22 = getattr(_fs22, 'income_statement', None) if _fs22 else None
    _cfs22 = getattr(_fs22, 'cash_flow_statement', None) if _fs22 else None
    if _inc22 and _cfs22 and _f22.operation_ratios:
     _ni22 = f_(_inc22.net_income.twelve_months)
     _fc22 = f_(_cfs22.free_cash_flow.twelve_months)
     _de22 = f_(_f22.operation_ratios.total_debt_equity_ratio.one_year)
     if _ni22 is not None and _ni22<0 and _fc22 is not None and _fc22<0 and _de22 is not None and _de22>2.0:
      continue  # E1: skip zombie/distress (neg-NI + neg-FCF + DE>2). BAKE-23 R231: de 3.0→2.0 (C3)
   except: pass
   try:
    _f22r = self.securities[sym].fundamentals
    if _f22r and _f22r.operation_ratios:
     _rg22 = f_(_f22r.operation_ratios.revenue_growth.one_year)
     if _rg22 and _rg22>.20 and self._ha_scan and len(self._ha_scan)>=10:
      _bd22 = (f_(self._ha_scan[-1].close)-f_(self._ha_scan[-10].close))/f_(self._ha_scan[-10].close)
      if _bd22>.02:
       score *= 0.90  # BAKE-42 R446-R447: 0.85→0.90 (less aggressive E6 penalty), +0.0037 verified 5/5 deterministic
   except: pass
   # BAKE-24 R234: XB (bond-up 5d>.015 × gross_margin>.40 → score×0.85). Quality-gated variant of E6, +0.0162 verified 10/10.
   try:
    _f24 = self.securities[sym].fundamentals
    if _f24 and _f24.operation_ratios:
     _gm24 = f_(_f24.operation_ratios.gross_margin.one_year)
     if _gm24 and _gm24>.40 and self._ha_scan and len(self._ha_scan)>=5:
      _bd24 = (f_(self._ha_scan[-1].close)-f_(self._ha_scan[-5].close))/f_(self._ha_scan[-5].close)
      if _bd24>.015:
       score *= 0.87  # BAKE-43 R450-R451: 0.85→0.87 (less aggressive XB, joint with grad .0194 + b13t2 1.40)
   except: pass
   # BAKE-25 R236-R237: triple stack Q1_QUAL + M1 + M3 (+0.0106 joint, 10/10 verified)
   try:
    _f25 = self.securities[sym].fundamentals
    if _f25 and _f25.operation_ratios and _f25.valuation_ratios:
     _gm25 = f_(_f25.operation_ratios.gross_margin.one_year)
     _pe25 = f_(_f25.valuation_ratios.pe_ratio)
     # Q1_QUAL: qqq up 10d>.05 × gm>.40 → score×0.85 (mean-rev unlikely when qqq recovering)
     if _gm25 and _gm25>.40 and self._qa_scan and len(self._qa_scan)>=10:
      _qd25 = (f_(self._qa_scan[-1].close)-f_(self._qa_scan[-10].close))/f_(self._qa_scan[-10].close)
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
    _f26 = self.securities[sym].fundamentals
    if _f26 and _f26.operation_ratios:
     _qr26 = f_(_f26.operation_ratios.quick_ratio.one_year)
     _rg26 = f_(_f26.operation_ratios.revenue_growth.one_year)
     # W1: entry filter — skip stocks with low quick_ratio + low rev growth + already declining
     if _qr26 is not None and _qr26<.5 and _rg26 is not None and _rg26<.05 and decline>.05:
      continue
   except: pass
   try:
    _f26b = self.securities[sym].fundamentals
    if _f26b and _f26b.operation_ratios:
     _rg26b = f_(_f26b.operation_ratios.revenue_growth.one_year)
     # W2: 120-day return < -.40 × growth>.30 → score×1.20 (deep multi-month decline + still growing fundamentals)
     if _rg26b and _rg26b>.30:
      _w120 = list(self.history[TradeBar](sym, 120, _RD))
      if _w120 and len(_w120)>=120:
       _r120 = (f_(_w120[-1].close)-f_(_w120[0].close))/f_(_w120[0].close)
       if _r120<-.30:    # BAKE-28 R255-R256: -.40→-.30 (W2_thr_30 + grad_019 joint, +0.0145)
        score *= 1.20
   except: pass
   # BAKE-27 R250-R252: per-stock vol filter (20d realized vol > .06 → conv×0.50). +0.0158 verified 10/10.
   try:
    _w27 = list(self.history[TradeBar](sym, 20, _RD))
    if _w27 and len(_w27)>=20:
     _r27 = [f_(_w27[i].close)/f_(_w27[i-1].close)-1 for i in range(1,20) if f_(_w27[i-1].close)>0]
     if _r27:
      _v27 = (sum(x*x for x in _r27)/len(_r27))**0.5
      if _v27>.06:
       conv *= 0.50  # BAKE-27: high-vol per-stock → reduce sizing
   except: pass
   # BAKE-29 R262-R263: BR (qqq up 20d>.10 × growth>.15 → score×0.85) + AB (bond 20d-vol<.002 × decline>.10 → score×1.10), +0.0141 verified
   try:
    _f29a = self.securities[sym].fundamentals
    if _f29a and _f29a.operation_ratios:
     _rg29 = f_(_f29a.operation_ratios.revenue_growth.one_year)
     # BR: penalize growth names when QQQ in 20d strong recovery (mean-rev unlikely on momentum)
     if _rg29 and _rg29>.15 and self._qa_scan and len(self._qa_scan)>=20:
      _qd20br = (f_(self._qa_scan[-1].close)-f_(self._qa_scan[-20].close))/f_(self._qa_scan[-20].close)
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
    _f44 = self.securities[sym].fundamentals
    _fs44 = getattr(_f44, 'financial_statements', None) if _f44 else None
    _cfs44 = getattr(_fs44, 'cash_flow_statement', None) if _fs44 else None
    if _cfs44:
     _v44 = f_(_cfs44.change_in_account_payable.twelve_months)
     if _v44 is not None and _v44 > 1e9 and decline > .05: score *= 1.06
   except: pass
   # BAKE-45 R461-R462: vr.first_year_estimated_eps_growth > 5 × decline > .10 → score×1.10, +0.0036 verified 3/3 deterministic on BAKE-44
   try:
    _f45 = self.securities[sym].fundamentals
    _vr45 = getattr(_f45, 'valuation_ratios', None) if _f45 else None
    if _vr45:
     _v45 = f_(_vr45.first_year_estimated_eps_growth)
     if _v45 is not None and _v45 > 5 and decline > .10: score *= 1.10
   except: pass
   # BAKE-53 R569: QQQ-regime score boost — qd5<-.03 × decline>.03 → score×1.10, +0.0024
   try:
    if self._qa_scan and len(self._qa_scan) >= 5:
     _qd5 = (f_(self._qa_scan[-1].close)-f_(self._qa_scan[-5].close))/max(.01, f_(self._qa_scan[-5].close))
     if _qd5 < -0.03 and decline > .03: score *= 1.25  # BAKE-54 R570: 1.10→1.25, +0.0264 (dd 10.4→10.3)
    # BAKE-56 R572: bond-down composite — qd5<-.03 × bd5<0 × decline>.05 → score×1.10, +0.0083
    if self._ha_scan and len(self._ha_scan) >= 5:
     _bd5x = (f_(self._ha_scan[-1].close)-f_(self._ha_scan[-5].close))/max(.01, f_(self._ha_scan[-5].close))
     if _qd5 < -0.03 and _bd5x < 0 and decline > .05: score *= 1.20  # BAKE-57 R573: 1.10→1.20, +0.0030
   except: pass

   # BAKE-58 R583 part 2: Combo4 — qd5<-.03 × bd5<0 × decline>.07 × vol-spike → score×1.40, +0.0097 (joint with qr_hi=2.2)
   try:
    if (self._qa_scan and len(self._qa_scan) >= 5 and self._ha_scan and len(self._ha_scan) >= 5 and
        len(window) >= 10):
     _qd5c = (f_(self._qa_scan[-1].close)-f_(self._qa_scan[-5].close))/max(.01, f_(self._qa_scan[-5].close))
     _bd5c = (f_(self._ha_scan[-1].close)-f_(self._ha_scan[-5].close))/max(.01, f_(self._ha_scan[-5].close))
     _v_recent = sum(f_(window[i].volume) for i in range(-3, 0))/3
     _v_avg = sum(f_(window[i].volume) for i in range(-10, 0))/10
     if _qd5c < -0.04 and _bd5c < 0 and decline > .09 and _v_recent / max(.01, _v_avg) > 1.5:  # BAKE-62 R593: dec .07→.09
      score *= 2.20  # BAKE-62 R593: 1.85→2.20 (joint with dec .09), +0.0023
   except: pass

   # BAKE-63 R597: earning_ratios.book_value_per_share_growth.one_year > .10 × decline > .15 → score×1.15, +0.0099
   try:
    _f63 = self.securities[sym].fundamentals
    _ers63 = getattr(_f63, 'earning_ratios', None) if _f63 else None
    if _ers63 is not None and decline > .15:
     _v63 = f_(_ers63.book_value_per_share_growth.one_year)
     if _v63 is not None and _v63 > 0.15: score *= 1.13  # BAKE-64 R600: thresh .10→.15, mag 1.15→1.13, +0.0024
   except: pass

   candidates.append((sym, score, conv))

  if not candidates: return

  # === Selection (by score) + sizing (by conv), capped at WT_CAP, total ≤ gross_target ===
  ranked = sorted(candidates, key=lambda c: c[1], reverse=True)
  total_value = f_(self.portfolio.total_portfolio_value) or 1
  existing_pct = sum(abs(f_(h.holdings_value))/total_value for h in self.portfolio.values()
                     if h.invested and h.symbol not in self._hedge_syms)
  remaining_budget = max(0, gross_target - existing_pct)
  if remaining_budget <= 0: return

  new_targets = []
  used = 0.0
  for sym, score, conv in ranked:
   if used >= remaining_budget: break
   w = min(WT_CAP, conv * WT_PER_CONV, remaining_budget - used)
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
