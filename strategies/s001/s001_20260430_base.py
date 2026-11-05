from AlgorithmImports import *
import math
f_=float
_RD=Resolution.DAILY
from datetime import timedelta

# === Hard structural constants ===
STARTING_CASH = 70000   # User-directive 2026-04-27: fixed at 70k, no further cash sweeps
GROSS_HIGH    = 1.0     # max total gross exposure
GROSS_LOW     = .55     # min gross floor (BAKE-20 R217-R218: .60→.55 joint with grad .022, +0.0492 verified 5/5)
GRAD_RANGE    = .0142   # BAKE-61 R591: .0145→.0142 (joint with Combo4 mag 1.85), +0.0023
MA_PERIOD     = 170     # MA period for QQQ/bond ratio (BAKE-6 R175: 120→170, +0.076 on TIP base)
BOND_SYMBOL   = "TIP"   # BAKE-5 R174: HYG→TIP, +0.151 (largest single bond-symbol gain)
WT_CAP        = .07     # per-stock weight cap (HARD: do not exceed)
WT_PER_CONV   = .080    # weight scaling (BAKED R166: .025→.080, +0.17)
MIN_WT        = .02     # min weight to bother holding
MIN_PRICE     = 32      # min stock price filter (BAKED R166: 24→32, +0.10)
MIN_VOLUME    = 900000  # BAKE-35 R319-R320: 700k→900k on BAKE-34 base, +0.0057 verified 3/3 deterministic
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
   'stop_default':    .42,    # BAKE-38 R327-R328: .40→.42 (joint with stop_lowmargin .09), +0.0088 verified 3/3
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
   # BAKE-65 R608 (loop): Δ+0.0012 from S001_R608_lp_stop_m090_gN_work_in_process
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
   # BAKE-66 R611 (loop): Δ+0.0099 from S001_R611_lp_stop_m082_gN_write_off [container fix: cfs→inc]
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _v = f_(_inc_z.write_off.twelve_months)
    if _v is not None and _v < 1e9: stop *= .82
   except: pass
   # BAKE-67 R616 (loop, replicated R611+R614): Δ+0.0050 from S001_R616_lp_petgt_m105_gN_ev_to_total_assets_3_year_growth
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.ev_to_total_assets_3_year_growth)
    if _v is not None and _v < 15: petgt *= 1.05
   except: pass
   # BAKE-68 R617 (loop, replicated R611/R614/R616): Δ+0.0035 from S001_R617_lp_stop_m090_gN_cash
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.cash.twelve_months)
    if _v is not None and _v < 1e9: stop *= 0.9
   except: pass
   # BAKE-69 R621 (loop, multi-condition): Δ+0.0039 from S001_R621_lp_PAIR_stop_m078_gN_wo_high_ni_neg
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_inc_z.write_off.twelve_months)
    _vb = f_(_ops_z.net_income_growth.one_year)
    if _va is not None and _vb is not None and _va > 1e7 and _vb < 0.0: stop *= 0.78
   except: pass
   # BAKE-70 R625 (loop, period-mismatch): Δ+0.0017 from S001_R625_lp_M2_stop_m085_gN_fcf_up_fcfr_low
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.fcf_growth.one_year)
    _vb = f_(_ops_z.fcf_sales_ratio.one_year)
    if _va is not None and _vb is not None and _va > 0.20 and _vb < 0.05: stop *= 0.85
   except: pass
   # BAKE-75 R633 (loop, stop on fcf-decl): Δ+0.0014 from S001_R633_lp_S_stop_m085_gN_fcf_85_gN
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_growth.one_year)
    if _v is not None and _v < 0.0: stop *= 0.85
   except: pass
   # BAKE-76 R635 (loop, petgt on roic-strong): Δ+0.0041 from S001_R635_lp_S_petgt_m110_gN_roic_petgt_m110_gN
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.one_year)
    if _v is not None and _v > 0.15: petgt *= 1.10
   except: pass
   # BAKE-87 R649 (loop, fcfr-strong petgt): Δ+0.0040 from S001_R649_lp_S_petgt_m120_gN_fcfr020_petgt_m120_gN
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_sales_ratio.one_year)
    if _v is not None and _v > 0.20: petgt *= 1.20
   except: pass
   # BAKE-88 R651 (loop, fcfr-elite petgt): Δ+0.0049 from S001_R651_lp_S_petgt_m125_gN_fcfr025_petgt_m125_gN
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_sales_ratio.one_year)
    if _v is not None and _v > 0.25: petgt *= 1.25
   except: pass
   # BAKE-91 R653 (loop, fcfr-strong petgt extra layer): Δ+0.0024 from S001_R653_lp_S_petgt_m130_gN_fcfr020_petgt_m130_gN (extra ×1.30 on fcfr>.20 cohort, compounds with BAKE-87 ×1.20)
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

   # BAKE-71 R628 (loop, score-on-logvol): Δ+0.0913 from S001_R628_lp_S_score_m130_g05_om30_score
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.one_year)
    if _v is not None and _v > 0.30 and (decline > .05): score *= 1.30
   except: pass
   # BAKE-72 R629 (loop, score-pair on logvol): Δ+0.0530 from S001_R629_lp_M2_score_m140_g07_om_fcf_strong
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.operation_margin.one_year)
    _vb = f_(_ops_z.fcf_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.30 and _vb > 0.10 and (decline > .07): score *= 1.40
   except: pass
   # BAKE-73 R630 (loop, score-pair on logvol): Δ+0.0580 from S001_R630_lp_M2_score_m140_g05_om_lowdebt_remeas
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.operation_margin.one_year)
    _vb = f_(_ops_z.long_term_debt_equity_ratio.one_year)
    if _va is not None and _vb is not None and _va > 0.30 and _vb < 0.30 and (decline > .05): score *= 1.40
   except: pass
   # BAKE-74 R631 (loop, score-pair on logvol): Δ+0.0533 from S001_R631_lp_M2_score_m140_g05_om_sol5
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.operation_margin.one_year)
    _vb = f_(_ops_z.solvency_ratio.one_year)
    if _va is not None and _vb is not None and _va > 0.30 and _vb > 0.5 and (decline > .05): score *= 1.40
   except: pass
   # BAKE-77 R636 (loop, om-stack-extra): Δ+0.0063 from S001_R636_lp_S_score_m105_g05_om30_lowmag_105_g05 (compounds with BAKE-71 → effective ×1.365)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.one_year)
    if _v is not None and _v > 0.30 and (decline > .05): score *= 1.05
   except: pass
   # BAKE-78 R639 (loop, triple-stress skip): Δ+0.0019 from S001_R639_lp_M3_skip_sk_g10_wo_cfo_gm_collapse
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
   # BAKE-79 R640 (loop, gm-stack-fresh): Δ+0.0041 from S001_R640_lp_S_score_m107_g03_gm045_m107_g03
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.gross_margin.one_year)
    if _v is not None and _v > 0.45 and (decline > .03): score *= 1.07
   except: pass
   # BAKE-80 R642 (loop, tax+cfo distress skip): Δ+0.0091 from S001_R642_lp_M2_skip_sk_g10_tax_high_cfo_decl
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.50 and _vb < -0.05 and (decline > .10): continue
   except: pass
   # BAKE-81 R643 (loop, tax+cfo skip g.07 broader): Δ+0.0113 from S001_R643_lp_M2_skip_sk_g07_tax040_cfon010_g07 (companion to BAKE-80, looser tax thr + tighter gate)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.40 and _vb < -0.10 and (decline > .07): continue
   except: pass
   # BAKE-82 R644 (loop, tax+cfo skip g.05 broadest): Δ+0.0173 from S001_R644_lp_M2_skip_sk_g05_tax030_cfo00_g05 (broader than BAKE-80/81)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.30 and _vb < 0.0 and (decline > .05): continue
   except: pass
   # BAKE-83 R645 (loop, rturn+tax_low quality): Δ+0.0187 from S001_R645_lp_M2_score_m120_g05_rturn_tax_low
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.receivable_turnover.one_year)
    _vb = f_(_ops_z.tax_rate.one_year)
    if _va is not None and _vb is not None and _va > 10 and _vb < 0.20 and (decline > .05): score *= 1.20
   except: pass
   # BAKE-84 R646 (loop, rturn+tax_low refined): Δ+0.0165 from S001_R646_lp_M2_score_m140_g07_rturn8_tax015_m140_g07 (extends BAKE-83 with looser rturn + tighter tax + higher mag)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.receivable_turnover.one_year)
    _vb = f_(_ops_z.tax_rate.one_year)
    if _va is not None and _vb is not None and _va > 8 and _vb < 0.15 and (decline > .07): score *= 1.40
   except: pass
   # BAKE-85 R647 (loop, rturn+tax_low at deeper gate): Δ+0.0077 from S001_R647_lp_M2_score_m130_g10_rturn6_tax018_m130_g10
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.receivable_turnover.one_year)
    _vb = f_(_ops_z.tax_rate.one_year)
    if _va is not None and _vb is not None and _va > 6 and _vb < 0.18 and (decline > .10): score *= 1.30
   except: pass
   # BAKE-86 R648 (loop, om-tax_low refined): Δ+0.0057 from S001_R648_lp_M2_score_m130_g07_om035_tax015_m130_g07
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.operation_margin.one_year)
    _vb = f_(_ops_z.tax_rate.one_year)
    if _va is not None and _vb is not None and _va > 0.35 and _vb < 0.15 and (decline > .07): score *= 1.30
   except: pass
   # BAKE-93 R655 (loop, peg_ratio quality score — LARGEST single hit in 22 rounds): Δ+0.0348 from S001_R655_lp_S_score_m110_g03_peg15_score_m110_g03 (PEG<1.5 = quality+growth at reasonable price; modest score boost on broad cohort)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-95 R659 (loop, peg pushdose deeper-gate higher-mag): Δ+0.0248 from S001_R659_lp_S_score_m120_g10_peg15_score_m120_g10_pushdose (BAKE-93 cohort at deeper decline + higher mag stacks)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and (decline > .10): score *= 1.20
   except: pass
   # BAKE-113 R682 (loop, peg capitulation — deep decline gate score×1.50): Δ+0.0072 from S001_R682_lp_S_score_m150_g20_peg_g20_score_m150_capit (PEG<1.5 cohort at decline>.20 — capitulation candidates with fresh deep-gate)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and (decline > .20): score *= 1.50
   except: pass
   # BAKE-115 R685 (loop, peg-loose × deep capitulation): Δ+0.0063 from S001_R685_lp_S_score_m150_g25_peg25_g25_m150_capit (PEG<2.5 broader cohort at decline>.25 — extends BAKE-113 to wider peg universe + deeper gate)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 2.5 and (decline > .25): score *= 1.50
   except: pass
   # BAKE-116 R686 (loop, sector_309 consumer cyclical — FIRST sector-code bake): Δ+0.0044 from S001_R686_lp_S_score_m110_g03_NOVEL_sect309_g03 (replicated across R684/R685/R686; sector classification field never baked before)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 309 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-117 R688 (loop, sector_309 × HYG-dn-5 regime score): Δ+0.0068 from S001_R688_lp_R_score_m120_hyg_dn5_sect309_hyg_dn5_m120 (sector classification × bond panic regime cross — sister to BAKE-104 peg×hyg_dn5)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 309 and self._reg_hyg_dn5: score *= 1.20
   except: pass
   # BAKE-118 R690 (loop, sector_308 communication × decline>.07 score×1.30): Δ+0.0057 from S001_R690_lp_S_score_m130_g07_sect308_g07_m130 (second sector code; communication services with deeper decline gate)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 308 and (decline > .07): score *= 1.30
   except: pass
   # BAKE-119 R691 (loop, sect_309 × DOUBLE_PANIC compound regime score×1.30): Δ+0.0048 from S001_R691_lp_R_score_m130_double_panic_sect309_double_panic_m130 (replicated R690 +0.0048; first compound-regime bake — qqq_dn3 ∩ hyg_dn5)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 309 and self._reg_double_panic: score *= 1.30
   except: pass
   # BAKE-120 R692 (loop, sect_309 × DOUBLE_PANIC extra layer score×1.50): Δ+0.0064 from S001_R692_lp_R_score_m150_double_panic_sect309_double_panic_m150 (extra ×1.50 layer on BAKE-119 cohort = effective ×1.95)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _v = f_(_ac_z.morningstar_sector_code)
    if _v is not None and _v == 309 and self._reg_double_panic: score *= 1.50
   except: pass
   # BAKE-121 R697 (loop, sect_310 ∩ tax_6m valuation+sector pair): Δ+0.0022 from S001_R697_lp_M2_score_m125_g03_sect310_tax6m_score_m125 (industrials sector × low-tax efficiency; replicated R696/R697)
   try:
    _fz = self.securities[sym].fundamentals
    _ac_z = getattr(_fz, 'asset_classification', None) if _fz else None
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ac_z.morningstar_sector_code)
    _vb = f_(_ops_z.tax_rate.six_months)
    if _va is not None and _vb is not None and _va == 310 and _vb < 0.18 and (decline > .03): score *= 1.25
   except: pass
   # BAKE-122 R702 (loop, small-cap × HYG-dn-5 regime score×1.20): Δ+0.0069 from S001_R702_lp_R_score_m120_SMALL_tassets_hyg_dn5_lt1e9 (small-cap [tassets<1e9] cohort during bond-panic regime — washout-bounce pattern)
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v < 1e9 and self._reg_hyg_dn5: score *= 1.20
   except: pass
   # BAKE-123 R703 (loop, small-mid-cap × deep decline score×1.15): Δ+0.0050 from S001_R703_lp_S_score_m114_SMALL_tassets_lt3e9_g07_m114 (replicated R702 +0.0045; broader small-mid cap [tassets<3e9] at decline>.07 — extends BAKE-122 cohort)
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v < 3e9 and (decline > .07): score *= 1.15
   except: pass
   # BAKE-124 R704 (loop, mega-cap × decline>.05 score×1.10): Δ+0.0021 from S001_R704_lp_S_score_m110_MEGA_tassets_gt5e11_m110 (replicated R702/R703/R704 ~+0.0021 each; mega-cap [tassets>5e11] cohort during pullback — opposite end of size spectrum vs BAKE-122/123)
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v > 5e11 and (decline > .05): score *= 1.10
   except: pass
   # BAKE-125 R706 (loop, small-cap × QQQ-dn-5 regime score×1.20): Δ+0.0011 from S001_R706_lp_R_score_m120_SIZE_small_1e9_qqq_dn5 (small-cap [tassets<1e9] cohort during equity panic — sister to BAKE-122 hyg_dn5 with QQQ regime)
   try:
    _fz = self.securities[sym].fundamentals
    _fs_z = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _v = f_(_bs_z.total_assets.twelve_months)
    if _v is not None and _v < 1e9 and self._reg_qqq_dn5: score *= 1.20
   except: pass
   # BAKE-97 R661 (loop, roic 3-month quality score — UNTOUCHED 3m timeframe field): Δ+0.0213 from S001_R661_lp_S_score_m114_g03_roic3m018_g03_score_m114 (3m roic captures sharper quality signal than 1y)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.18 and (decline > .03): score *= 1.14
   except: pass
   # BAKE-107 R672 (loop, om_3m quality score — UNTOUCHED 3m operation_margin): Δ+0.0160 from S001_R672_lp_S_score_m110_g03_om3m_g03_score_m110 (replicated R673 +0.0059; new 3m om field)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.operation_margin.three_months)
    if _v is not None and _v > 0.35 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-114 R684 (loop, tax_6m low-tax score — UNTOUCHED 6m tax_rate field): Δ+0.0201 from S001_R684_lp_S_score_m110_g03_tax6m018_g03_m110 (6m timeframe tax<.18 cohort = sustained low-tax efficiency; new 6m field)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.tax_rate.six_months)
    if _v is not None and _v < 0.18 and (decline > .03): score *= 1.10
   except: pass
   # BAKE-111 R678 (loop, cape ∩ om_3m valuation+quality pair): Δ+0.0081 from S001_R678_lp_M2_score_m130_g03_cape25_om3m035_m130 (cape<25 ∩ om_3m>.35 = cheap valuation × high 3m operating margin)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_vr_z.cape_ratio)
    _vb = f_(_ops_z.operation_margin.three_months)
    if _va is not None and _vb is not None and _va < 25 and _vb > 0.35 and (decline > .03): score *= 1.30
   except: pass
   # BAKE-103 R668 (loop, roic_3m × QQQ-dn-3 regime score — LARGEST hit on log2log2v base): Δ+0.0934 from S001_R668_lp_R_score_m120_qqq_dn3_roic3m_x_qqq_dn3_m120 (high-quality cohort during QQQ panic regime; NEW regime+fundamental cross)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_qqq_dn3: score *= 1.20
   except: pass
   # BAKE-104 R668 (loop, peg × HYG-dn-5 regime — BIGGEST single hit in entire loop arc): Δ+0.1561 from S001_R668_lp_R_score_m120_hyg_dn5_peg_x_hyg_dn5_m120 (PEG<1.5 cohort during bond panic; replicated R669 +0.0690 on BAKE-103 base)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and self._reg_hyg_dn5: score *= 1.20
   except: pass
   # BAKE-105 R670 (loop, cashr × QQQ-dn-5 regime score): Δ+0.0134 from S001_R670_lp_R_score_m140_qqq_dn5_cashr_qqq_dn5_m140 (cash_return>.10 cohort during medium QQQ panic; new qqq_dn5 regime not previously baked)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cash_return)
    if _v is not None and _v > 0.10 and self._reg_qqq_dn5: score *= 1.40
   except: pass
   # BAKE-106 R672 (loop, roic_3m × HYG-dn-3 regime score): Δ+0.0266 from S001_R672_lp_R_score_m120_hyg_dn3_roic3m_hyg_dn3_m120 (sister to BAKE-103 roic_3m×qqq_dn3, with hyg_dn3 regime — short bond panic)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_hyg_dn3: score *= 1.20
   except: pass
   # BAKE-108 R674 (loop, roic_3m × QQQ-dn-7 regime score): Δ+0.0090 from S001_R674_lp_R_score_m120_qqq_dn7_roic3m_qqq_dn7_m120 (third roic_3m regime variant; longer QQQ panic 7d)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_qqq_dn7: score *= 1.20
   except: pass
   # BAKE-109 R676 (loop, peg × QQQ-UP-3 BULL regime score — first bull-regime bake): Δ+0.0209 from S001_R676_lp_R_score_m120_qqq_up3_peg_qqq_up3_m120 (PEG<1.5 cohort during QQQ uptrend; sister to BAKE-104 hyg_dn5 but BULL regime — counter-intuitive but works)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.peg_ratio)
    if _v is not None and _v < 1.5 and self._reg_qqq_up3: score *= 1.20
   except: pass
   # BAKE-110 R677 (loop, roic_3m × HYG-UP-5 BULL bond regime score): Δ+0.0121 from S001_R677_lp_R_score_m140_hyg_up5_roic3m_hyg_up5_m140 (high-roic_3m cohort during bond uptrend — fourth roic_3m regime variant after BAKE-103/106/108)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_hyg_up5: score *= 1.40
   except: pass
   # BAKE-112 R679 (loop, roic_3m × HYG-UP-3 short bull bond regime score): Δ+0.0061 from S001_R679_lp_R_score_m140_hyg_up3_roic3m_hyg_up3_m140 (fifth roic_3m regime variant — short bond uptrend complement to BAKE-110)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.roic.three_months)
    if _v is not None and _v > 0.15 and self._reg_hyg_up3: score *= 1.40
   except: pass
   # BAKE-98 R662 (loop, peg ∩ cheap forward-pe score): Δ+0.0104 from S001_R662_lp_M2_score_m130_g05_peg15_fwdpe12_g05_m130_refine (peg<1.5 ∩ fwdpe<12 = quality+cheap-on-forward intersection)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _va = f_(_vr_z.peg_ratio)
    _vb = f_(_vr_z.forward_pe_ratio)
    if _va is not None and _vb is not None and _va < 1.5 and _vb < 12 and (decline > .05): score *= 1.30
   except: pass
   # BAKE-99 R662 (loop, cash_return valuation score — UNTOUCHED): Δ+0.0090 from S001_R662_lp_S_score_m114_g03_cashr010_g03_score_m114 (cash_return>.10 = high cash-yield cohort, NEW valuation_ratios field)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _v = f_(_vr_z.cash_return)
    if _v is not None and _v > 0.10 and (decline > .03): score *= 1.15
   except: pass
   # BAKE-101 R664 (loop, cashr ∩ peg quality+cash valuation pair): Δ+0.0143 from S001_R664_lp_M2_score_m125_g03_cashr_peg_score_m125_g03 (cash_return>.10 ∩ peg<1.5 = high-cash-yield + quality-growth at reasonable price)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _va = f_(_vr_z.cash_return)
    _vb = f_(_vr_z.peg_ratio)
    if _va is not None and _vb is not None and _va > 0.10 and _vb < 1.5 and (decline > .03): score *= 1.25
   except: pass
   # BAKE-102 R664 (loop, peg ∩ pe pair at deeper gate): Δ+0.0115 from S001_R664_lp_M2_score_m130_g07_peg15_pe12_score_m130_g07 (peg<1.5 ∩ pe<12 at decline>.07 — sister to BAKE-98 peg+fwdpe but with trailing pe)
   try:
    _fz = self.securities[sym].fundamentals
    _vr_z = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _va = f_(_vr_z.peg_ratio)
    _vb = f_(_vr_z.pe_ratio)
    if _va is not None and _vb is not None and _va < 1.5 and _vb < 12 and (decline > .07): score *= 1.30
   except: pass
   # BAKE-89 R651 (loop, tax+cfo deep-distress skip at shallow decline): Δ+0.0011 from S001_R651_lp_M2_skip_sk_g03_tax035_cfon015_g03 (replicated R649 +0.0010; tighter cfo (-.15) + looser decline (.03) than BAKE-80/81/82)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.35 and _vb < -0.15 and (decline > .03): continue
   except: pass
   # BAKE-92 R654 (loop, early-warning distress skip — no decline gate): Δ+0.0067 from S001_R654_lp_M2_skip_sk_g00_tax035_cfon015_g00_early (BAKE-89 cohort but fires regardless of decline depth — early entry rejection)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _va = f_(_ops_z.tax_rate.one_year)
    _vb = f_(_ops_z.cfo_growth.one_year)
    if _va is not None and _vb is not None and _va > 0.35 and _vb < -0.15: continue
   except: pass
   # BAKE-94 R658 (loop, cfo_growth solo deep-distress skip — 2nd-largest hit ever): Δ+0.0421 from S001_R658_lp_S_skip_sk_gN_cfo_solo_n040_nogate (cfo<-.40 solo, no tax/decline conjunction; catches symbols even when tax<.35)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.cfo_growth.one_year)
    if _v is not None and _v < -0.40: continue
   except: pass
   # BAKE-96 R660 (loop, fcf_growth solo deep-distress skip): Δ+0.0250 from S001_R660_lp_S_skip_sk_gN_fcf_g_solo_n70_nogate (fcf collapse beyond -.70 — solo distress sibling to BAKE-94 cfo)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_growth.one_year)
    if _v is not None and _v < -0.70: continue
   except: pass
   # BAKE-100 R663 (loop, ni_growth 3m solo distress skip — UNTOUCHED 3m timeframe): Δ+0.0100 from S001_R663_lp_S_skip_sk_gN_ni3m_solon050_nogate (sharper 3m signal than 1y net_income_growth)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.net_income_growth.three_months)
    if _v is not None and _v < -0.50: continue
   except: pass
   # BAKE-90 R651 (loop, fcfr-elite score-side complement of BAKE-88 petgt): Δ+0.0045 from S001_R651_lp_S_score_m110_g03_fcfr025_m110_g03 (independent score lever on same fcfr>.25 cohort)
   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _v = f_(_ops_z.fcf_sales_ratio.one_year)
    if _v is not None and _v > 0.25 and (decline > .03): score *= 1.10
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
