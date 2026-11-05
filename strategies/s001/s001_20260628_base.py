"""s001 base (compressed 2026-05-18)."""

from AlgorithmImports import *
import math
import collections
import warnings
_RETIRED_FUNDAMENTAL_FIELDS=set()
from decimal import Decimal as _Dec
f_=float;g_=getattr
def _ngt(v,t):return v is not None and v>t
def _nlt(v,t):return v is not None and v<t
def _nrg(v,lo,hi):return v is not None and lo<v<hi
def _AN(*vs):return all(v is not None for v in vs)
_gt=_ngt;_lt=_nlt
def _dR(dc,dL,dH):return (dL is None or dc>dL) and (dH is None or dc<dH)
def _qR(qa,qL,qH):return qa is not None and qL<qa<qH
def _g1(z,*p):
 if z is None:return None
 path=type(z).__name__+'.'+'.'.join(p)
 if path in _RETIRED_FUNDAMENTAL_FIELDS:return None
 o=z
 for k in p:
  if o is None:return None
  try:o=g_(o,k,None)
  except Exception as error:
   if 'was retired by Morningstar' not in str(error):raise
   if path not in _RETIRED_FUNDAMENTAL_FIELDS:
    _RETIRED_FUNDAMENTAL_FIELDS.add(path)
    warnings.warn(f'Retired fundamental field is unavailable: {path}',RuntimeWarning)
   return None
 return f_(o) if isinstance(o,(int,float,_Dec)) else None
TM='twelve_months'
OY='one_year'
TT='three_months'
SM='six_months'
_RD=Resolution.DAILY
from datetime import timedelta
STARTING_CASH=70000
UNAN_THR=.82
UNAN_SLOPE=2.5
GROSS_HIGH=1.0
GROSS_LOW=.62
GRAD_RANGE=.013
MA_PERIOD=170
BOND_SYMBOL="TIP"
WT_CAP=.07
WT_PER_CONV=.08
MIN_WT=.02
MIN_PRICE=32
MIN_VOLUME=8.1e5
MTF_WEEKDAYS={0,2,4}
WARMUP_DAYS=280
def _t03(sc,al,tr,gt,qa,qL,qH,dc,dL,dH,mg,rg=True):
 if al is None or not rg or not _qR(qa,qL,qH) or not _dR(dc,dL,dH):return sc
 v=_g1(al,*tr)
 if v is None:return sc
 for op,th in gt:
  if (op=='>' and not v>th) or (op=='<' and not v<th) or (op=='==' and v!=th):return sc
 return sc*mg
def _t07(sc,aA,tA,oA,rA,aB,tB,oB,rB,dc,dL,dH,mg,rg=True):
 if aA is None or aB is None or not rg or not _dR(dc,dL,dH):return sc
 va=_g1(aA,*tA); vb=_g1(aB,*tB)
 if va is None or vb is None:return sc
 ca=(oA=='>' and va>rA) or (oA=='<' and va<rA)
 cb=(oB=='>' and vb>rB) or (oB=='<' and vb<rB)
 return sc*mg if ca and cb else sc
def _t08(sc,al,tr,op,th,dc,dL,dH,mg,rg=True):
 if al is None or not rg or not _dR(dc,dL,dH):return sc
 v=_g1(al,*tr)
 if v is None:return sc
 return sc*mg if (op=='>' and v>th) or (op=='<' and v<th) or (op=='==' and v==th) else sc
def _t15(al,tr,gt,dc,dL,dH,rg=True):
 if al is None or not rg or not _dR(dc,dL,dH):return False
 v=_g1(al,*tr)
 if v is None:return False
 for op,th in gt:
  if (op=='>' and not v>th) or (op=='<' and not v<th) or (op=='==' and v!=th):return False
 return True
def _t14(lv,al,tr,op,th,mg,gt=None,rg=True):
 if al is None or not rg:return lv
 v=_g1(al,*tr)
 if v is None:return lv
 if gt:
  for op2,thr2 in gt:
   if (op2=='>' and not v>thr2) or (op2=='<' and not v<thr2):return lv
 elif not ((op=='>' and v>th) or (op=='<' and v<th)):return lv
 return lv*mg
def _t10(sc,v,th,dc,dL,dH,mg,rg=True):
 return sc*mg if v is not None and rg and v>th and _dR(dc,dL,dH) else sc
def _t11(sc,v,th,dc,dL,dH,mg,rg=True):
 return sc*mg if v is not None and rg and v<th and _dR(dc,dL,dH) else sc
def _t12(sc,v,th,dc,dL,dH,mg,rg=True):
 return sc*mg if v is not None and rg and v==th and _dR(dc,dL,dH) else sc
def _t04(sc,v,th,qa,qL,qH,dc,dL,dH,mg,rg=True):
 return sc*mg if v is not None and rg and v>th and _qR(qa,qL,qH) and _dR(dc,dL,dH) else sc
def _t05(sc,v,th,qa,qL,qH,dc,dL,dH,mg,rg=True):
 return sc*mg if v is not None and rg and v<th and _qR(qa,qL,qH) and _dR(dc,dL,dH) else sc
def _t01(sc,v,vL,vH,qa,qL,qH,dc,dL,dH,mg,rg=True):
 return sc*mg if v is not None and rg and vL<v<vH and _qR(qa,qL,qH) and _dR(dc,dL,dH) else sc
def _t06(sc,va,oA,rA,vb,oB,rB,dc,dL,dH,mg,rg=True):
 if va is None or vb is None or not rg or not _dR(dc,dL,dH):return sc
 ca=(oA=='>' and va>rA) or (oA=='<' and va<rA) or (oA=='==' and va==rA)
 cb=(oB=='>' and vb>rB) or (oB=='<' and vb<rB) or (oB=='==' and vb==rB)
 return sc*mg if ca and cb else sc
def _t00(sc,sV,sE,fV,vL,vH,qa,qL,qH,dc,dL,dH,mg,rg=True):
 return sc*mg if sV is not None and sV==sE and fV is not None and rg and _qR(qa,qL,qH) and _dR(dc,dL,dH) and vL<fV<vH else sc
def _t09(lv,v,op,th,mg,rg=True):
 return lv*mg if v is not None and rg and ((op=='>' and v>th) or (op=='<' and v<th) or (op=='==' and v==th)) else lv
def _t16(va,oA,rA,vb,oB,rB,dc,dL,dH=None):
 if va is None or vb is None or not _dR(dc,dL,dH):return False
 if not ((oA=='>' and va>rA) or (oA=='<' and va<rA)):return False
 return bool((oB=='>' and vb>rB) or (oB=='<' and vb<rB))
def _t13(v,gt,dc,dL,dH,rg=True):
 if v is None or not rg or not _dR(dc,dL,dH):return False
 for op,th in gt:
  if (op=='>' and not v>th) or (op=='<' and not v<th) or (op=='==' and v!=th):return False
 return True
class MeanReversionAlgorithm(QCAlgorithm):
 def initialize(self):
  self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.CASH)
  if not self.live_mode:
   self.set_start_date(2009,8,1)
   self.set_end_date(2026,7,1)
   self.set_cash(STARTING_CASH)
  self.set_warm_up(timedelta(days=WARMUP_DAYS),_RD)
  self.universe_settings.resolution=_RD
  self.add_equity("QQQ",_RD)
  self.add_equity(BOND_SYMBOL,_RD)
  self.add_equity("VXX",_RD)
  self.add_equity("SPY",_RD)
  self.add_universe_selection(ETFConstituentsUniverseSelectionModel("QQQ"))
  self.set_benchmark("QQQ")
  self._initialized=False
  self._hedge_syms=set()
  self._close_cache={}
  self.pending_entries=[]
  self.pending_exits=[]
  self.schedule.on(self.date_rules.every_day("SPY"),self.time_rules.before_market_open("SPY",300),self.execute_pending_orders)
  self.tune={'stop_default':.4,'stop_lowmargin':.09,'petgt_hi':.12,'petgt_mid':.11,'petgt_lo':.0275,'nm_low_thresh':.04,'qr_hi_thresh':2.2,'nm_mid_thresh':.05,'momentum_haircut_thresh':-.045,'momentum_haircut':1.344}
 def on_warmup_finished(self):
  self.pending_exits=[]
 def on_order_event(self,e):
  st=e.status
  if st==OrderStatus.INVALID or st==OrderStatus.CANCELED:
   self.error(f"ORDER REJECT {st} {e.symbol.value} q={e.quantity}: {e.message}")
   if self.live_mode and self.portfolio[e.symbol].invested and e.symbol not in [t.symbol for t in self.pending_entries] and e.symbol not in self.pending_exits:
    self.pending_exits.append(e.symbol)
 def on_data(self,data):
  if not self._initialized:
   self._qqq_sym=self.securities["QQQ"].symbol
   self._bond_sym=self.securities[BOND_SYMBOL].symbol
   self._vxx_sym=self.securities["VXX"].symbol
   self._spy_sym=self.securities["SPY"].symbol
   self._hedge_syms={self._bond_sym,self._vxx_sym,self._spy_sym}
   self._initialized=True
  equities=[s for s in data.bars.keys() if s.security_type==SecurityType.EQUITY and s not in self._hedge_syms]
  _cc=self._close_cache
  for _s in equities:
   _b=data.bars.get(_s)
   if _b is not None:
    _q=_cc.get(_s)
    if _q is None:
     _q=collections.deque(maxlen=260)
     _cc[_s]=_q
    _q.append(f_(_b.close))
  _udn=0;_utn=0
  for _us in equities:
   _uq=_cc.get(_us)
   if _uq is not None and len(_uq)>=2:
    _utn+=1
    if _uq[-1]<_uq[-2]:_udn+=1
  self._xmove=(_udn/_utn) if _utn>=20 else .0
  self._compute_regime()
  if not self.is_warming_up:
   self._scan_exits(data,equities)
  if self.time.weekday()==0:
   self._scan_entries(data,equities)
 def _compute_regime(self):
  qa=list(self.history[TradeBar](self._qqq_sym,60,_RD) or [])
  ha=list(self.history[TradeBar](self._bond_sym,30,_RD) or [])
  va=list(self.history[TradeBar](self._vxx_sym,30,_RD) or [])
  qc=[f_(b.close) for b in qa]
  hc=[f_(b.close) for b in ha]
  _vcl=[f_(b.close) for b in va]
  qlen,hlen,vlen=len(qc),len(hc),len(_vcl)
  def _r(closes,n):
   if len(closes)<=n or closes[-n]<=0:return None
   return (closes[-1]-closes[-n])/closes[-n]
  self._qs=qa
  self._hs=ha
  self._qd5=_r(qc,5)
  self._qd10=_r(qc,10)
  self._qd20=_r(qc,20)
  self._bd5=_r(hc,5)
  self._bd10=_r(hc,10)
  _qg=lambda n:qc[-n] if qlen>=n else None
  _hg=lambda n:hc[-n] if hlen>=n else None
  q1,q2,q3,q5,q7=_qg(1),_qg(2),_qg(3),_qg(5),_qg(7)
  h1,h2,h3,h5,h7,h14=_hg(1),_hg(2),_hg(3),_hg(5),_hg(7),_hg(14)
  self._qa=(q1-q3)/q3-(q1-q7)/q7 if _AN(q3,q7) and q3>0 and q7>0 else None
  self._reg_haccel=(h1-h3)/h3-(h1-h7)/h7 if _AN(h3,h7) and h3>0 and h7>0 else None
  self._reg_qqq_dn3=bool(_AN(q3) and q1<q2<q3)
  self._reg_qqq_up3=bool(_AN(q3) and q1>q2>q3)
  self._reg_hyg_dn3=bool(_AN(h3) and h1<h2<h3)
  self._reg_hyg_up3=bool(_AN(h3) and h1>h2>h3)
  self._reg_qqq_dn5=bool(_AN(q5) and q1<q5)
  self._reg_qqq_dn7=bool(_AN(q7) and q1<q7)
  self._reg_hyg_dn5=bool(_AN(h5) and h1<h5)
  self._reg_hyg_dn14=bool(_AN(h14) and h1<h14)
  self._reg_hyg_up5=bool(_AN(h5) and h1>h5)
  self._reg_double_panic=bool(_AN(q3) and q1<q3) and self._reg_hyg_dn5
  if vlen:
   self._reg_vxx_rising3=bool(vlen>=3 and _vcl[-1]>_vcl[-2]>_vcl[-3])
   self._reg_vxx_falling3=bool(vlen>=3 and _vcl[-1]<_vcl[-2]<_vcl[-3])
  else:
   self._reg_vxx_rising3=self._reg_vxx_falling3=False

 def _dynamic_gross(self) -> float:
  n=MA_PERIOD+1
  qqq_bars=list(self.history[TradeBar](self._qqq_sym,n,_RD) or [])
  bond_bars=list(self.history[TradeBar](self._bond_sym,n,_RD) or [])
  if len(qqq_bars)<MA_PERIOD or len(bond_bars)<MA_PERIOD:return GROSS_LOW if self.live_mode else GROSS_HIGH
  ratios=[f_(qqq_bars[i].close)/max(.01,f_(bond_bars[i].close)) for i in range(-MA_PERIOD,0)]
  if not ratios:return GROSS_LOW if self.live_mode else GROSS_HIGH
  ma_ratio=sum(ratios)/len(ratios)
  if ma_ratio==0:return GROSS_LOW if self.live_mode else GROSS_HIGH
  cur_ratio=f_(qqq_bars[-1].close)/max(.01,f_(bond_bars[-1].close))
  pct_above=(cur_ratio-ma_ratio)/ma_ratio
  base=max(GROSS_LOW,min(GROSS_HIGH,GROSS_LOW+(pct_above/GRAD_RANGE)*(GROSS_HIGH-GROSS_LOW)))
  if len(ratios)>=10:
   ratio_mom=(ratios[-1]-ratios[-10])/max(.01,ratios[-10])
   if ratio_mom<self.tune['momentum_haircut_thresh']:
    base=max(GROSS_LOW,base*self.tune['momentum_haircut'])
  return base
 def _scan_exits(self,data,equities):
  for sym in equities:
   pos=self.portfolio[sym]
   if not pos.invested:continue
   pnl=f_(pos.unrealized_profit_percent)
   stop=self.tune['stop_default']
   petgt=self.tune['petgt_mid']
   _sec=self.securities[sym] if sym in self.securities else None
   _fz=g_(_sec,'fundamentals',None) if _sec else None
   _ops_z=g_(_fz,'operation_ratios',None) if _fz else None
   _vr_z=g_(_fz,'valuation_ratios',None) if _fz else None
   _ers_z=g_(_fz,'earning_ratios',None) if _fz else None
   _ac_z=g_(_fz,'asset_classification',None) if _fz else None
   _er_z=g_(_fz,'earning_reports',None) if _fz else None
   _sr_z=g_(_fz,'security_reference',None) if _fz else None
   _fs_z=g_(_fz,'financial_statements',None) if _fz else None
   _bs_z=g_(_fs_z,'balance_sheet',None) if _fs_z else None
   _inc_z=g_(_fs_z,'income_statement',None) if _fs_z else None
   _cfs_z=g_(_fs_z,'cash_flow_statement',None) if _fs_z else None
   if _ops_z:
    nm=self._fv(_ops_z,'net_margin','value')
    qr=self._fv(_ops_z,'quick_ratio','value')
    if nm is not None and nm<self.tune['nm_low_thresh']:stop=self.tune['stop_lowmargin']
    if qr is not None and qr>self.tune['qr_hi_thresh']:petgt=self.tune['petgt_hi']
    elif nm is not None and nm>self.tune['nm_mid_thresh']:petgt=self.tune['petgt_mid']
    else:petgt=self.tune['petgt_lo']
   I=_inc_z;B=_bs_z;F=_cfs_z;O=_ops_z;V=_vr_z;Er=_ers_z
   _vs=_g1(_ac_z,'value_score')
   _fcfg1yc=_g1(O,'fcf_growth',OY)
   _wipc=_g1(B,'work_in_process',TM)
   _woc=_g1(I,'write_off',TM)
   _evt3y=_g1(V,'ev_to_total_assets_3_year_growth')
   _cashc=_g1(B,'cash',TM)
   _rc1y=_g1(O,'roic',OY)
   _fcfsr1yc=_g1(O,'fcf_sales_ratio',OY)
   _nig1yc=_g1(O,'net_income_growth',OY)
   _cpc=_g1(V,'cape_ratio')
   _hi_cape=_gt(_cpc,50)
   _lo_cape=_nrg(_cpc,0,22)
   stop=_t09(stop,_wipc,'<',1e9,.9)
   stop=_t09(stop,_woc,'<',1e9,.82)
   petgt=_t09(petgt,_evt3y,'<',15,1.05)
   stop=_t09(stop,_cashc,'<',1e9,.9)
   _va=_woc
   _vb=_nig1yc
   if _AN(_va,_vb) and (_AN(_va) and _va>1e7) and (_AN(_vb) and _vb<.0):stop*=.78
   _va=_fcfg1yc
   _vb=_fcfsr1yc
   if _AN(_va,_vb) and (_AN(_va) and _va>.2) and (_AN(_vb) and _vb<.05):stop*=.85
   stop=_t09(stop,_fcfg1yc,'<',.0,.85)
   petgt=_t09(petgt,_rc1y,'>',.15,1.1)
   petgt=_t09(petgt,_fcfsr1yc,'>',.2,1.56)
   petgt=_t09(petgt,_fcfsr1yc,'>',.25,1.25)
   petgt=_t09(petgt,_vs,'<',15,.85)
   stop=_t09(stop,_vs,'<',15,.95)
   if _vs is not None:
    if (_AN(_vs) and _vs<5):stop*=.85
    elif (_AN(_vs) and 5<_vs<10):stop*=1.05
    elif (_AN(_vs) and 10<_vs<15):stop*=1.05
    elif (_AN(_vs) and 15<_vs<25):stop*=1.5
    elif (_AN(_vs) and 25<_vs<30):stop*=1.05
    elif (_AN(_vs) and 30<_vs<50):petgt*=1.5; stop*=1.12
   _p=f_(self.securities[sym].close) if sym in self.securities else None
   if _p is not None and _p>150:stop*=1.5
   if _p is not None and _p<50:petgt*=1.1
   if self._reg_hyg_up5 and _gt(pnl,.05):petgt*=1.2
   if self._reg_qqq_up3 and self._reg_hyg_up5 and _gt(pnl,.005):petgt*=1.3
   if self._reg_qqq_up3 and self._reg_hyg_dn14 and _lt(pnl,-.15):stop*=.5
   exit_signal=.0
   if pnl is not None and _lt(_g1(O,'current_ratio',OY),1.0):exit_signal+=.05
   if pnl is not None and _gt(V.pb_ratio,3):exit_signal+=.05
   if pnl is not None and _gt(_g1(I,'total_expenses',TM),1e7):exit_signal+=.05
   if pnl is not None and _gt(_g1(B,'total_assets',TM),1e9):exit_signal+=.05
   if pnl is not None and _gt(_g1(I,'total_revenue',TM),1e7):exit_signal+=.04
   if pnl is not None and _gt(V.ps_ratio,5):exit_signal+=.04
   if self._reg_hyg_dn14 and _lt(pnl,-.3):stop*=1.05
   # --- EXIT INJECT POINT ---
   if pnl<-stop or pnl>petgt:
    self.pending_exits.append(sym); continue
   bars=list(self.history[TradeBar](sym,2,_RD) or [])
   if len(bars)>=2 and bars[-1].close>bars[-2].high:
    exit_signal+=.6
   if exit_signal>=.6:
    self.pending_exits.append(sym)
 def _scan_entries(self,data,equities):
  self.pending_entries=[]
  candidates=[]
  gross_target=self._dynamic_gross()
  _qao=self._qa
  D3=self._reg_hyg_dn3
  HA=self._reg_haccel
  D5=self._reg_hyg_dn5
  D14=self._reg_hyg_dn14
  H3=self._reg_hyg_up3
  H5=self._reg_hyg_up5
  Qd3=self._reg_qqq_dn3
  Qd5=self._reg_qqq_dn5
  Qd7=self._reg_qqq_dn7
  Q3=self._reg_qqq_up3
  DP=self._reg_double_panic
  VF=self._reg_vxx_falling3
  VR=self._reg_vxx_rising3
  _qs=self._qs
  _hs=self._hs
  _qd5=self._qd5
  _qd10=self._qd10
  _qd20=self._qd20
  _bd5=self._bd5
  _bd10=self._bd10
  _qpos=_nrg(_qao,.01,.05)
  _qzero=_nrg(_qao,-.01,.01)
  _qsneg=_lt(_qao,-.05)
  _qneg=_nrg(_qao,-.05,-.01)
  Z=_qzero;P=_qpos;N=_qsneg;Q=_qneg
  _q_dn=_lt(_qao,-.01)
  _r60_bakes_active=(
   (P and H5) or
   (Z and D14) or
   (N and D14)
  )
  for sym in equities:
   if self.portfolio[sym].invested and sym not in self.pending_exits:continue
   if sym not in data.bars:continue
   bar=data.bars[sym]
   _bc=f_(bar.close); _bv=f_(bar.volume)
   if _bc<=MIN_PRICE or _bv<MIN_VOLUME:continue
   window=list(self.history[TradeBar](sym,20,_RD) or [])
   if not window:continue
   _w10=window[-10:] if len(window)>=10 else window
   mtf=[b for b in _w10 if b.time.weekday() in MTF_WEEKDAYS]
   if len(mtf)<3:continue
   if not (mtf[-1].close<mtf[-2].close):continue
   _m3=f_(mtf[-3].close)
   decline=(_m3-f_(mtf[-1].close))/_m3 if _m3>0 else 0
   d=decline
   _wvol10=[f_(b.volume) for b in _w10]
   _av=sum(_wvol10)/max(len(_w10),1)
   max_dv=max((_wvol10[i] for i in range(max(1,len(_w10)-5),len(_w10))
                 if _w10[i].close<_w10[i-1].close),default=0)
   vol_climax=_av>0 and max_dv>2.5*_av
   if vol_climax and d<.05:continue
   _m5=f_(mtf[-5].close) if len(mtf)>=5 else 0
   _m7=f_(mtf[-7].close) if len(mtf)>=7 else 0
   _r3=(_bc-_m3)/_m3 if _m3>0 else None
   _r5=(_bc-_m5)/_m5 if _m5>0 else None
   _r7=(_bc-_m7)/_m7 if _m7>0 else None
   _r3_md=_r3 is not None and -.1<_r3<0
   _r5_up=_gt(_r5,0)
   _RU=_r3_md and _r5_up
   _hlc=self._close_cache.get(sym)
   _hl_len=len(_hlc) if _hlc is not None else 0
   if _r60_bakes_active and _hl_len>=61:
    _ref60=_hlc[-61]
    _r60=(_bc-_ref60)/_ref60 if _ref60>0 else None
   else:_r60=None
   _r60_dn=_lt(_r60,-.2)
   if window and len(window)>=20:
    _wcl=[f_(b.close) for b in window]
    _vol20_sumsq=.0
    _vol20_n=0
    for i in range(1,20):
     _p=_wcl[i-1]
     if (_AN(_p) and _p>0):
      _r=_wcl[i] / _p-1
      _vol20_sumsq+=_r*_r
      _vol20_n+=1
    _vol20=(_vol20_sumsq/_vol20_n) ** .5 if _vol20_n>0 else None
   else:
    _wcl=None
    _vol20=None
   _sec=self.securities[sym] if sym in self.securities else None
   _fz=g_(_sec,'fundamentals',None) if _sec else None
   _ops_z=g_(_fz,'operation_ratios',None) if _fz else None
   _vr_z=g_(_fz,'valuation_ratios',None) if _fz else None
   _ers_z=g_(_fz,'earning_ratios',None) if _fz else None
   _ac_z=g_(_fz,'asset_classification',None) if _fz else None
   _er_z=g_(_fz,'earning_reports',None) if _fz else None
   _sr_z=g_(_fz,'security_reference',None) if _fz else None
   _fs_z=g_(_fz,'financial_statements',None) if _fz else None
   _bs_z=g_(_fs_z,'balance_sheet',None) if _fs_z else None
   _inc_z=g_(_fs_z,'income_statement',None) if _fs_z else None
   _cfs_z=g_(_fs_z,'cash_flow_statement',None) if _fs_z else None
   I=_inc_z;B=_bs_z;F=_cfs_z;O=_ops_z;V=_vr_z;Er=_ers_z
   _aoi3=_g1(I,'amortization_of_intangibles',TT)
   _aoi6=_g1(I,'amortization_of_intangibles',SM)
   _aoi12=_g1(I,'amortization_of_intangibles',TM)
   _nim12=_g1(I,'net_income',TM)
   _ocf12=_g1(F,'operating_cash_flow',TM)
   _fcf12=_g1(F,'free_cash_flow',TM)
   _hac12=_g1(B,'hedging_assets_current',TM)
   _ey=_g1(V,'earning_yield')
   _evf=_g1(V,'ev_to_fcf_3_yr_avg')
   _eve=_g1(V,'ev_to_ebit_3_yr_avg')
   _ps_=_g1(V,'ps_ratio')
   _pb_=_g1(V,'pb_ratio')
   _pe_=_g1(V,'pe_ratio')
   _EY5=_gt(_ey,.05);_NIM6=_gt(_nim12,1e6);_FCF6=_gt(_fcf12,1e6);_OCF6=_gt(_ocf12,1e6)
   _HA0=_gt(HA,0);_PS5=_gt(_ps_,5);_NIM7=_gt(_nim12,1e7);_FCF7=_gt(_fcf12,1e7)
   _x_ex=_g1(I,'excise_taxes',TM)
   _x_rm=_g1(B,'raw_materials',TM)
   _x_el=_g1(F,'earnings_losses_from_equity_investments',TM)
   _x_ic=_g1(I,'impairment_of_capital_assets',TM)
   _x_cl=_g1(B,'capital_lease_obligations',TM)
   _x_og=_g1(F,'operating_gains_losses',TM)
   _x_oe=_g1(I,'other_income_expense',TM)
   _gpro=_g1(F,'proceeds_from_stock_option_exercised',TM)
   _gnet=_g1(F,'net_investment_purchase_and_sale',TM)
   _gnet1=_g1(F,'net_other_financing_charges',TM)
   _gnet2=_g1(F,'net_ppe_purchase_and_sale',TM)
   _ggai=_g1(F,'gain_loss_on_sale_of_ppe',TM)
   _gcur=_g1(B,'current_deferred_revenue',TM)
   _gpre=_g1(B,'preferred_stock_equity',TM)
   _ggai1=_g1(F,'gain_loss_on_investment_securities',TM)
   _goth=_g1(B,'other_payable',TM)
   _gsal=_g1(F,'sale_of_ppe',TM)
   _gcha=_g1(F,'changes_in_account_receivables',TM)
   _gear=_g1(I,'earnings_from_equity_interest',TM)
   _groa=_g1(O,'roa',OY)
   _ginv=_g1(B,'investmentin_financial_assets',TM)
   _gamo=_g1(F,'amortization_of_securities',TM)
   _gqui=_g1(O,'quick_ratio',OY)
   _ggai2=_g1(I,'gain_on_sale_of_security',TM)
   _gsho=_g1(F,'short_term_debt_payments',TM)
   _gsho1=_g1(F,'short_term_debt_issuance',TM)
   _gins=_g1(I,'insurance_and_claims',TM)
   _gtot=_g1(I,'total_expenses',TM)
   _gtot1=_g1(I,'total_revenue',TM)
   _gtot2=_g1(B,'total_assets',TM)
   _gfcf=_g1(O,'fcf_growth',OY)
   _gcas=_g1(O,'cash_ratio',OY)
   _gtax=_g1(O,'tax_rate',SM)
   _gcas1=_g1(B,'cash',TM)
   _gval=_g1(_ac_z,'value_score')
   _gcap=_g1(V,'cape_ratio')
   _qa=_qao
   _EVF20=_lt(_evf,20)
   _AOI3K=_gt(_aoi3,1e5)
   _AOI6K=_gt(_aoi6,1e5)
   _AOI12K=_gt(_aoi12,1e5)
   _EVE15=_lt(_eve,15)
   _HAC4=_gt(_hac12,1e4)
   _INV8=_lt(_g1(_bs_z,'inventory',TM),1e8)
   _XRM6=_gt(_x_rm,1e6)
   _XCL6=_gt(_x_cl,1e6)
   _XEL6=_gt(_x_el,1e6)
   _XOG6=_gt(_x_og,1e6)
   _XIC6=_gt(_x_ic,1e6)
   _XOE6=_gt(_x_oe,1e6)
   _XEX6=_gt(_x_ex,1e6)
   _QN=_nrg(_qa,-.05,-.01)
   _BC150=_gt(_bc,150)
   _GROA20=_gt(_groa,.2)
   D24=.02<d<.04
   D25=.02<d<.05
   D26=.02<d<.06
   D48=.04<d<.08
   D412=.04<d<.12
   D612=.06<d<.12
   D510=.05<d<.1
   D1220=.12<d<.2
   D13=.01<d<.03
   D410=.04<d<.1
   _pg=_g1(V,'peg_ratio')
   _fy_c=_g1(V,'fcf_yield')
   _ey_c=_ey
   _pp_c=_g1(V,'peg_payback')
   _nd3=_g1(Er,'normalized_diluted_eps_growth',TT)
   _pt3=_g1(I,'pretax_income',TT)
   _ft3=_g1(B,'foreign_currency_translation_adjustments',TT)
   _rey=_g1(O,'roe',OY)
   _ie12c=_g1(I,'interest_expense',TM)
   _gp3=_g1(I,'gross_profit',TT)
   _ps12=_g1(B,'preferred_stock',TM)
   _sc=_g1(_ac_z,'morningstar_sector_code')
   S311=_sc==311;S102=_sc==102;S308=_sc==308;S206=_sc==206;S310=_sc==310;S205=_sc==205;S309=_sc==309;S103=_sc==103
   _ZSh=Z and S102 and HA;_PSh=P and S102 and HA;_PSe=P and S308 and HA
   _PS3=P and S311 and HA;_PS6=P and S206 and HA;_D26b=D3 and D26
   _gw=_g1(B,'goodwill',TM)
   _tac=_gtot2
   _vs=_gval
   _rg1y=_g1(O,'revenue_growth',OY)
   _gm1=_g1(O,'gross_margin',OY)
   _ic1y=_g1(O,'interest_coverage',OY)
   _pec=_pe_
   _rc3=_g1(O,'roic',TT)
   _tr1y=_g1(O,'tax_rate',OY)
   _om1=_g1(O,'operation_margin',OY)
   _om3mc=_g1(O,'operation_margin',TT)
   _cfg1=_g1(O,'cfo_growth',OY)
   _cfyc=_g1(V,'cf_yield')
   _fcfg1yc=_gfcf
   _rt1yc=_g1(O,'receivable_turnover',OY)
   _crc=_g1(V,'cash_return')
   _cpc=_gcap
   _cashc=_gcas1
   _fpec=_g1(V,'forward_pe_ratio')
   _lowgwr=(_gw is not None and _gt(_tac,0) and (_AN(_gw) and (_AN(_tac) and (_gw/_tac)<.2)))
   _icp=(_gt(_ic1y,10) and _nrg(_pec,0,15) and D48)
   _fcp=(_gt(_fcfg1yc,.1) and _nrg(_pec,0,12) and D48)
   _hi_vol=_gt(_vol20,.04)
   _lo_vol=_lt(_vol20,.015)
   _hi_cape=_gt(_cpc,50)
   _lo_cape=_nrg(_cpc,0,22)
   S=1.0*math.log(math.log(_bv))
   ES=EM=ER=EC=EQ=EG=.0
   if d<.05:
    C=max(1.0,1.0+(d-.02)*(1.5/.1))
   else:
    C=1.0+.375+(d-.05)*(3.5/.1)
   C=min(5.0,C)
   if vol_climax:C*=.7
   W=1.0
   if Z and H3 and .02<d<.022 and _AOI6K:W*=.84
   if Z and H3 and .014<d<.015 and _AOI12K:W*=.76
   if Z and H3 and .014<d<.015 and _AOI6K:W*=.76
   if P and H3 and .01<d<.014 and _HAC4:W*=1.0
   if Z and H3 and .015<d<.016 and _AOI12K:W*=.82
   if Z and H3 and .015<d<.016 and _AOI6K:W*=.82
   if Z and H3 and .015<d<.016 and _AOI3K:W*=.8
   if P and H5 and .01<d<.014 and _HAC4:W*=.65
   if Z and H3 and .014<d<.017 and _AOI3K:W*=.88
   if Z and H3 and .014<d<.02 and _AOI12K:W*=.82
   if Z and H3 and .014<d<.02 and _AOI6K:W*=.82
   if Z and H3 and .014<d<.02 and _AOI3K:W*=.82
   if Z and H5 and .01<d<.014 and _HAC4:W*=.78
   if Z and Q3 and .01<d<.014 and _EVF20:W*=.94
   if Z and Q3 and .01<d<.014 and _EVF20:W*=.9
   if Z and H5 and .01<d<.014 and _gt(_g1(I,'other_income_expense',TT),1e4):W*=.8
   if Z and H5 and .01<d<.014 and _gt(_g1(I,'other_income_expense',TT),1e4):W*=.78
   if Z and D3 and .002<d<.005 and _EY5:W*=.72
   if Z and D3 and .002<d<.005 and _EVF20:W*=.65
   if Z and D3 and .007<d<.009 and _EY5:W*=.72
   if Z and S310 and D14 and .01<d<.02 and _EY5:W*=.72
   if Z and S102 and D5 and .02<d<.05 and _EVE15:W*=.65
   if Z and S205 and HA and .01<d<.02 and _EVF20:W*=.72
   if Z and S102 and D5 and .02<d<.05 and _EVF20:W*=.7
   if Z and S205 and D14 and .01<d<.02 and _EY5:W*=.78
   if _ZSh and .005<d<.01 and _EVF20:W*=.72
   if Z and D5 and .007<d<.009 and _EY5:W*=.72
   if Z and HA and .005<d<.01 and _EVE15:W*=.7
   if Z and HA and .005<d<.01 and _EVF20:W*=.75
   if Z and D14 and .01<d<.02 and _lt(_pb_,3):W*=.77
   if Z and D5 and .01<d<.02 and _lt(_pb_,3):W*=.8
   if Z and D14 and .01<d<.02 and _EY5:W*=.8
   pass
   if Z and D3 and .01<d<.02 and _EVF20:W*=.75
   if Z and HA and .01<d<.02 and _EVE15:W*=.65
   if Z and D14 and .01<d<.02 and _EVE15:W*=.65
   if Z and D5 and .01<d<.02 and _EVF20:W*=.78
   if Z and D5 and .02<d<.05 and _EVF20:W*=.75
   if _PSh and .04<d<.08:W*=1.1
   if _PS3 and .01<d<.02:W*=1.09
   if P and D5 and .01<d<.02 and _gt(_g1(_ac_z,'style_box'),5):W*=.65
   if Z and HA and .01<d<.02 and _gt(_g1(V,'expected_dividend_growth_rate'),0):W*=.7
   if Z and D5 and .02<d<.05 and _EVE15:W*=.65
   if N and D14 and .01<d<.02 and _gt(_g1(O,'cashto_total_assets',OY),.1):W*=.75
   if P and D14 and .01<d<.02 and _gt(_g1(_er_z,'reported_normalized_diluted_eps',TM),1.0):W*=.65
   if Z and D14 and .005<d<.01 and _FCF7:W*=1.55
   if P and D14 and .005<d<.01 and _NIM7:W*=1.25
   if P and D14 and .03<d<.04 and _gt(_pe_,15):W*=1.3
   if P and D5 and .03<d<.04 and _gt(_ocf12,1e7):W*=1.5
   if P and D3 and .02<d<.05 and _NIM7:W*=1.35
   if P and DP and .02<d<.05 and _NIM7:W*=1.5
   if P and D14 and .02<d<.05 and _FCF7:W*=1.15
   if _ZSh and D14 and _NIM6 and _gt(_g1(I,'total_other_finance_cost',TM),1e7):W*=.3
   if P and S205 and HA and D14 and _OCF6 and _gt(_g1(O,'receivable_turnover',OY),5):W*=.75
   if _ZSh and D14 and _OCF6 and _lt(_g1(O,'quick_ratio',OY),.5):W*=.45
   if Z and S206 and HA and D14 and _NIM6 and _gt(_pe_,50):W*=.75
   if _PSh and D14 and _NIM6 and _gt(_pe_,50):W*=.55
   if _PSe and D14 and _FCF6 and _gt(_ps_,10):W*=.55
   if Z and d>.03 and S308 and HA and D14 and _NIM6 and _GROA20:W*=.45
   if _PSh and D5 and _NIM6 and _gt(_g1(B,'common_stock_equity',TM),1e10):W*=1.5
   if _PS6 and D14 and _gt(_g1(I,'ebitda',TM),1e6) and _lt(_gcas,.3):W*=.45
   if _PS3 and Q3 and _FCF6 and _lt(_gcas,.3):W*=.85
   if P and S308 and D5 and Q3 and _FCF6 and _PS5:W*=.75
   if _PSh and D14 and _FCF6 and _PS5:W*=.45
   if P and S311 and D3 and Q3 and _NIM6 and _PS5:W*=.45
   if Z and S206 and D3 and Q3 and _NIM6 and _PS5:W*=.7
   if _ZSh and D14 and _NIM6 and _PS5:W*=.85
   if Z and S311 and D14 and Q3 and _OCF6 and _lt(_gqui,.5):W*=.45
   if Z and S206 and D3 and Q3 and _OCF6 and _gt(_pb_,3):W*=.45
   if Z and S311 and HA and D14 and _FCF6 and _lt(_gqui,.5):W*=.75
   if Z and S311 and D3 and Q3 and _NIM6 and _gt(_g1(Er,'dps_growth',OY),.05):W*=.55
   if _PSe and D5 and _OCF6 and _NIM6:W*=1.2
   if P and S308 and DP and HA and _FCF6 and _NIM6:W*=1.1
   if Z and S309 and D14 and Q3 and _OCF6 and _NIM6:W*=.45
   if Z and S205 and D3 and Q3 and _OCF6 and _NIM6:W*=.45
   if _PS6 and D5 and _FCF6 and _NIM6:W*=1.2
   if Z and S309 and D14 and VF and _FCF6 and _NIM6:W*=.55
   if Z and S308 and DP and D3 and _FCF6 and _NIM6:W*=.55
   if Z and S310 and DP and _XCL6:W*=.7
   if P and S311 and D3 and _gt(_gsal,1e6):W*=.5
   if P and S311 and D5 and _gt(_gnet,1e6):W*=.8
   if P and S310 and Q3 and _gt(_ggai,1e6):W*=1.2
   if P and S310 and VF and D14 and _gt(_gsal,1e6):W*=1.5
   if Z and S310 and HA and _gt(_g1(F,'sale_of_investment',TM),1e6):W*=1.3
   if P and S311 and VF and _gt(_ggai,1e6):W*=1.3
   if Z and S311 and D14 and _XEL6:W*=1.7
   if Z and S311 and HA and _gt(_ggai2,1e6):W*=1.1
   if P and S310 and HA and _gt(_g1(B,'long_term_investments',TM),1e6):W*=.8
   if P and S311 and D14 and _gt(_g1(I,'gain_on_sale_of_business',TM),1e6):W*=.8
   if Z and S311 and Q3 and _gt(_gear,1e6):W*=.8
   if Z and S311 and DP and _gt(_gamo,1e6):W*=.5
   if Z and S311 and VF and _gt(_gnet2,1e6):W*=.5
   if P and S311 and Q3 and _gt(_ggai1,1e6):W*=.5
   if P and S311 and DP and _gt(_ggai2,1e6):W*=.5
   if N and _sc==313 and .02<d<.05 and HA and _gt(_g1(I,'other_taxes',TM),1e6):W*=.9
   if Z and .02<d<.05 and VF and Q3 and _gt(_g1(F,'net_other_investing_changes',TM),1e6):W*=.6
   if P and DP and D5 and _XOG6:W*=.8
   if P and Qd5 and VF and _gt(_gnet1,1e6):W*=.8
   if P and Qd7 and _gt(_gsho,1e6):W*=.5
   if P and D14 and _gt(_g1(F,'cash_from_discontinued_operating_activities',TM),1e6):W*=.5
   if P and VF and .02<d<.05 and _XIC6:W*=.5
   if P and _HA0 and DP and _gt(_gpre,1e6):W*=.6
   if P and _HA0 and Q3 and .02<d<.05 and _gt(_gcur,1e6):W*=.5
   if Z and _HA0 and .02<d<.05 and _gt(_g1(F,'asset_impairment_charge',TM),1e6):W*=.5
   if P and _HA0 and _XRM6:W*=.7
   if .02<d<.05:W*=1.6
   S=_t10(S,_om1,.3,d,.05,None,1.365)
   S=_t06(S,_om1,'>',.3,_fcfg1yc,'>',.1,d,.07,None,1.4)
   S=_t07(S,O,('operation_margin',OY),'>',.3,O,('long_term_debt_equity_ratio',OY),'<',.3,d,.05,None,1.4)
   S=_t07(S,O,('operation_margin',OY),'>',.3,O,('solvency_ratio',OY),'>',.5,d,.05,None,1.4)
   _va=_g1(I,'write_off',TM)
   _vb=_cfg1
   _vc=_gm1
   if _AN(_va,_vb,_vc) and (_AN(_va) and _va>1e8) and (_AN(_vb) and _vb<.0) and (_AN(_vc) and _vc<.2) and d>.1:continue
   S=_t10(S,_gm1,.45,d,.03,None,1.07)
   if _t16(_tr1y,'>',.5,_cfg1,'<',-.05,d,.1,None):continue
   if _t16(_tr1y,'>',.4,_cfg1,'<',-.1,d,.07,None):continue
   if _t16(_tr1y,'>',.3,_cfg1,'<',.0,d,.05,None):continue
   S=_t06(S,_rt1yc,'>',10.0,_tr1y,'<',.2,d,.05,None,1.2)
   S=_t06(S,_rt1yc,'>',8.0,_tr1y,'<',.15,d,.07,None,1.4)
   S=_t06(S,_rt1yc,'>',6.0,_tr1y,'<',.18,d,.1,None,1.3)
   S=_t06(S,_om1,'>',.35,_tr1y,'<',.15,d,.07,None,1.3)
   S=_t11(S,_pg,1.5,d,.03,None,1.1)
   S=_t11(S,_pg,1.5,d,.1,None,1.2)
   S=_t11(S,_pg,1.5,d,.2,None,1.5)
   S=_t11(S,_pg,2.5,d,.25,None,1.5)
   S=_t12(S,_sc,309,d,.03,None,1.1)
   S=_t12(S,_sc,309,d,None,None,1.2,D5)
   S=_t12(S,_sc,308,d,.07,None,1.3)
   S=_t12(S,_sc,309,d,None,None,1.95,DP)
   _va=_sc
   _vb=_g1(O,'tax_rate',SM)
   if _AN(_va,_vb) and _va==310 and (_AN(_vb) and _vb<.18) and d>.03:S*=1.25
   S=_t11(S,_tac,1e9,d,None,None,1.2,D5)
   S=_t11(S,_tac,3e9,d,.07,None,1.15)
   S=_t10(S,_tac,5e11,d,.05,None,1.1)
   S=_t11(S,_tac,1e9,d,None,None,1.2,Qd5)
   _r_open=f_(bar.open)
   _r=_bc/_r_open if _r_open>0 else 1.0
   if _r>1.02 and d>.03:S*=1.12
   if (_AN(_pg) and _pg<1.0) and d>.05:S+=.1
   S=_t10(S,_tac,1e11,d,.04,.07,1.1)
   if (_AN(_crc) and _crc>.1) and D5:S+=.5
   S=_t10(S,_tac,3e11,d,.04,.08,1.05)
   if _lowgwr and D510:S*=1.1
   S=_t08(S,O,('net_margin',TT),'<',.0,d,.05,.1,.9)
   S=_t08(S,V,('fcf_yield',),'>',.08,d,.04,.08,1.1)
   _p=_g1(V,'payout_ratio')
   if _lowgwr and (_AN(_p) and _p<.4) and D510:S*=1.05
   if _lowgwr and _lt(_cpc,22) and D48:S*=1.05
   S=_t10(S,_om3mc,.35,d,.05,.1,1.05)
   S=_t10(S,_om3mc,.35,d,.04,.08,1.03)
   S=_t10(S,_om3mc,.35,d,.06,.1,1.03)
   S=_t10(S,_om3mc,.4,d,.04,.08,1.03)
   _s=_sc
   _v=_fy_c
   if _sc==308 and _gt(_fy_c,.08) and D48:S*=1.05
   if _lowgwr and _gt(_om3mc,.35) and D48:S*=1.03
   _v=_g1(O,'net_margin',TT)
   if _lowgwr and _gt(_v,.25) and D48:S*=1.05
   S=_t10(S,_om1,.4,d,.04,.08,1.05)
   _s=_sc
   _v=f_(V.ev_to_ebitda)
   if _s==310 and _nrg(_v,0,12) and D48:S*=1.05
   _s=_sc
   _v=_fy_c
   if _sc==206 and _gt(_fy_c,.05) and D510:S*=1.05
   S=_t10(S,_cfyc,.1,d,.04,.08,1.05)
   S=_t10(S,_cfyc,.15,d,.05,.1,1.05)
   S=_t08(S,V,('earning_yield',),'>',.06,d,.04,.08,1.05)
   S=_t10(S,_cfyc,.08,d,.02,.05,1.05)
   S=_t10(S,_rc3,.18,d,.005,.02,1.05)
   S=_t10(S,_rc3,.15,d,.005,.025,1.05)
   if _lowgwr and _nrg(_cpc,0,22) and D13:S*=1.03
   if _nrg(_r7,-.1,-.05):S*=1.08
   if _nrg(_pg,0,.8) and D13:S*=1.05
   _bars7=mtf[-7:] if len(mtf)>=7 else None
   _hi7=max(f_(b.high) for b in _bars7) if _bars7 else None
   _lo7=min(f_(b.low) for b in _bars7) if _bars7 else None
   if _hi7 is not None and _gt(_lo7,0) and (_hi7/_lo7)>1.12 and d>.03:S*=1.05
   if _gt((_g1(Er,'normalized_diluted_eps_growth',OY)),.05) and _gt(_ey_c,.06) and D510:S*=1.05
   S=_t08(S,Er,('basic_average_shares_growth',OY),'<',-.02,d,.04,.08,1.05)
   if (_AN(_cfyc) and _cfyc>.08) and _nrg(_r5,-.05,-.03):S*=1.05
   if (_AN(_vs) and _vs>50) and _nrg(_r5,-.05,-.03):S*=1.05
   if _nrg(_pg,0,1.0) and _nrg(_r7,-.05,-.02):S*=1.05
   if _nrg(_pg,0,.6) and _nrg(_r5,-.05,-.03):S*=1.05
   if (_AN(_rc3) and _rc3>.18) and _nrg(_r3,-.04,-.02):S*=1.08
   if (_AN(_rc3) and _rc3>.18) and _nrg(_r3,-.04,-.02):C*=1.5
   C=_t14(C,V,('cf_yield',),None,None,2.5,gt=(('>',.08),),rg=D5)
   C=_t14(C,V,('cf_yield',),None,None,2.0,gt=(('>',.08),),rg=D3)
   C=_t14(C,V,('peg_ratio',),None,None,2.0,gt=(('>',.0),('<',1.5)),rg=D3)
   C=_t14(C,V,('peg_ratio',),None,None,1.5,gt=(('>',.0),('<',1.5)),rg=Qd3)
   if _gt(_pt3,1e10) and _gt(_nd3,.1) and Z and D14:C*=.85
   if _nrg(_pg,0,1.5) and _D26b:S*=1.05
   if _nrg(_pg,0,1.5) and D3 and D24:S*=1.05
   _v=_pg
   if (_AN(_v) and 0<_v<1.5) and D3 and (_bc>f_(bar.open)) and D26:S*=1.05
   _v=_pg
   _bo=f_(bar.open); _bl=f_(bar.low)
   _body=abs(_bc-_bo) if _bc and _bo else 0
   _ls=(min(_bo,_bc)-_bl) if _bo and _bc and _bl else 0
   _hammer=_body>0 and _ls>2*_body
   if (_AN(_v) and 0<_v<1.5) and D3 and _hammer and D26:S*=1.05
   _v=_pg
   _both=_AN(_r3,_r5) and -.05<_r3<-.02 and -.05<_r5<-.02
   if _nrg(_pg,0,1.5) and D3 and _both and D48:S*=1.14
   _v=_pg
   _both=_AN(_r3,_r5) and -.05<_r3<-.02 and -.05<_r5<-.02
   if _nrg(_pg,0,1.5) and D3 and _both and D410:S*=1.1
   _v=_pg
   _b=mtf[-5:] if len(mtf)>=5 else None
   _sma=sum(f_(x.close) for x in _b)/5 if _b else None
   _above=_sma and _bc>_sma
   if (_AN(_v) and 0<_v<1.5) and Qd3 and _above and D26:S*=1.1
   _b=mtf[-5:] if len(mtf)>=5 else None
   _sma=sum(f_(x.close) for x in _b)/5 if _b else None
   _above=_sma and _bc>_sma
   if D3 and _above and D48:S*=1.08
   _b=mtf[-5:] if len(mtf)>=5 else None
   _sma=sum(f_(x.close) for x in _b)/5 if _b else None
   _above=_sma and _bc>_sma
   _bo=f_(bar.open); _bl=f_(bar.low)
   _body=abs(_bc-_bo) if _bc and _bo else 0
   _ls=(min(_bo,_bc)-_bl) if _bo and _bc and _bl else 0
   _hammer=_body>0 and _ls>2*_body
   if D3 and _above and _hammer and D26:S*=1.05
   _v=_sc
   _b=mtf[-5:] if len(mtf)>=5 else None
   _sma=sum(f_(x.close) for x in _b)/5 if _b else None
   _above=_sma and _bc>_sma
   if _v==206 and D3 and _above and D26:S*=1.08
   S=_t10(S,_vs,50.0,d,.05,.1,1.05)
   if _gt(_cfyc,.05) and _gt(_vs,50) and D510:S*=1.05
   if S309 and _lowgwr and D48:S*=1.1
   S=_t10(S,_rc3,.18,d,.03,None,1.14)
   S=_t10(S,_om3mc,.35,d,.03,None,1.1)
   S=_t08(S,O,('tax_rate',SM),'<',.18,d,.03,None,1.1)
   S=_t06(S,_cpc,'<',25.0,_om3mc,'>',.35,d,.03,None,1.3)
   S=_t10(S,_rc3,.15,d,None,None,1.2,Qd3)
   S=_t11(S,_pg,1.5,d,None,None,1.2,D5)
   S=_t10(S,_crc,.1,d,None,None,1.4,Qd5)
   S=_t10(S,_rc3,.15,d,None,None,1.2,D3)
   S=_t10(S,_rc3,.15,d,None,None,1.2,Qd7)
   S=_t11(S,_pg,1.5,d,None,None,1.2,Q3)
   S=_t10(S,_rc3,.15,d,None,None,1.4,H5)
   S=_t10(S,_rc3,.15,d,None,None,1.4,H3)
   S=_t06(S,_pg,'<',1.5,_fpec,'<',12.0,d,.05,None,1.3)
   S=_t10(S,_crc,.1,d,.03,None,1.15)
   S=_t06(S,_crc,'>',.1,_pg,'<',1.5,d,.03,None,1.25)
   S=_t06(S,_pg,'<',1.5,_pec,'<',12.0,d,.07,None,1.3)
   if _t16(_tr1y,'>',.35,_cfg1,'<',-.15,d,.03,None):continue
   if _t16(_tr1y,'>',.35,_cfg1,'<',-.15,d,None,None):continue
   if _t13(_cfg1,(('<',-.4),),d,None,None,True):continue
   if _t15(O,('fcf_growth',OY),(('<',-.7),),d,None,None,True):continue
   if _t15(O,('net_income_growth',TT),(('<',-.5),),d,None,None,True):continue
   S=_t08(S,O,('fcf_sales_ratio',OY),'>',.25,d,.03,None,1.1)
   if _nrg(_pg,0,1.5) and D3 and D1220:S*=1.8
   if _nrg(_pg,0,1.5) and _nrg(_bc,50,100) and D3 and D1220:S*=1.5
   if _nrg(_pg,5,20) and D3 and D1220:S*=.7
   _v=_sc; _p=_bc
   _b=mtf[-5:] if len(mtf)>=5 else None
   _sma=sum(f_(x.close) for x in _b)/5 if _b else None
   _above=_sma and _bc>_sma
   if _v==206 and (_AN(_p) and 100<_p<200) and D3 and _above and D26:S*=1.5
   if _nrg(_pg,0,1.5) and _nrg(_bc,100,200) and _D26b:S*=1.08
   _v=_pg
   _accel=_r3-_r7 if _r3 is not None and _r7 is not None else None
   if _nrg(_pg,0,1.5) and _nrg(_accel,-.1,-.02) and _D26b:S*=1.18
   _v=_sc
   _accel=_r3-_r7 if _r3 is not None and _r7 is not None else None
   if _sc==206 and _nrg(_accel,-.1,-.02) and _D26b:S*=1.1
   _v=_pg
   _accel=_r3-_r7 if _r3 is not None and _r7 is not None else None
   if _nrg(_pg,0,1.0) and _nrg(_accel,-.1,-.02) and _D26b:S*=1.18
   _v=_pg
   _accel=_r3-_r7 if _r3 is not None and _r7 is not None else None
   if _nrg(_pg,0,1.5) and _nrg(_accel,.05,.15) and _D26b:S*=.7
   S=_t01(S,_pg,.0,1.5,_qa,.01,.05,d,.02,.06,1.98,D3)
   S=_t01(S,_pg,.0,1.0,_qa,.01,.05,d,.02,.06,1.3,D3)
   S=_t04(S,_rc3,.1,_qa,.01,.05,d,.02,.06,2.16,D3)
   S=_t04(S,_ic1y,20.0,_qa,.01,.05,d,.02,.06,1.1,D3)
   S=_t04(S,_ic1y,50.0,_qa,.01,.05,d,.02,.06,1.05,D3)
   if (_AN(_ic1y) and _ic1y>20) and _nrg(HA,.01,.05) and _D26b:S*=1.14
   S=_t00(S,_sc,206,_pg,.0,1.5,_qa,.01,.05,d,.02,.06,1.95,D3)
   S=_t00(S,_sc,206,_pg,.0,1.5,_qa,-.05,-.01,d,.02,.06,.6,D3)
   if _sc==206 and Q and _D26b:S*=.95
   if _sc==206 and _nrg(_pg,0,1.5) and _nrg(HA,-.05,-.01) and _D26b:S*=.7
   S=_t04(S,_ic1y,20.0,_qa,-.05,-.01,d,.02,.06,.93,D3)
   S=_t00(S,_sc,102,_pg,.0,1.0,_qa,.01,.05,d,.02,.06,1.4,D3)
   S=_t00(S,_sc,102,_pg,.0,1.0,_qa,.01,.05,d,.02,.06,1.07)
   S=_t00(S,_sc,102,_pg,.0,1.0,_qa,-.05,-.01,d,.02,.06,.7)
   S=_t00(S,_sc,102,_cashc,5e9,1e15,_qa,.01,.05,d,.04,.08,1.5)
   S=_t00(S,_sc,308,_cashc,5e9,1e15,_qa,-.05,-.01,d,.04,.08,1.5)
   S=_t00(S,_sc,102,_cashc,5e9,1e15,_qa,-.05,-.01,d,.04,.08,.95)
   S=_t03(S,B,('dividends_payable',TM),(('>',5e8),),_qa,.01,.05,d,.04,.08,1.3)
   if N and D48:S*=1.5
   if S308 and N and D25:S*=1.3
   if S102 and N and D25:S*=1.5
   if S206 and _lt(_vol20,.02) and P and D48:S*=.85
   if _nrg((_g1(V,'normalized_pe_ratio')),0,12) and _q_dn and D48:S*=1.3
   if _lo_vol and _q_dn and D48:S*=.7
   if S311 and _nrg(_pec,0,12) and D3 and D412:S*=1.5
   if Qd7 and _nrg(_pec,0,12) and _q_dn and D412:S*=.85
   if S102 and _lt(_vol20,.015) and Qd3 and D412:S*=1.14
   if _icp:S*=.85
   if _fcp:S*=.85
   if _icp and _q_dn:S*=1.3
   if _icp and D3:S*=1.14
   if _icp and _nrg(_pg,0,1.5):S*=1.14
   if _fcp and D3:S*=1.3
   if _icp and P:S*=1.5
   if _gt((_g1(V,'forward_dividend_yield')),.04) and P and D48:S*=.85
   if _gt((_g1(I,'depreciation_and_amortization',TM)),1e9) and _q_dn and D48:S*=1.3
   if vol_climax and _lt(_r5,-.1) and D48:S*=1.2
   if S205 and P and D48:S*=1.4
   _v_fcfy=_fy_c
   if _gt(_v_fcfy,.06) and P and D3:S*=1.14
   if _gt(_v_fcfy,.06) and P and D14:S*=1.3
   if _gt(_ps12,0) and P and D3:S*=1.14
   if _gt(_nd3,.1) and P and D3:S*=1.14
   if _gt(_fy_c,.06) and N and D5:S*=.9
   _v_cor=_g1(I,'cost_of_revenue',TM)
   if _lt(_v_cor,1e10) and P and D3:S*=1.14
   if _lt(_v_cor,1e10) and N and D3:S*=1.14
   _v_psn=_ps12
   if _gt(_v_psn,0) and N and D3:S*=1.4
   if _gt(_v_psn,0) and N and D5:S*=.85
   if _gt((_g1(Er,'normalized_basic_eps_growth',OY)),.1) and P and D3:S*=.9
   if _lt(_ie12c,1e8) and P and D3:S*=1.2
   if _gt((_g1(O,'payment_turnover',TT)),5.0) and P and D3:S*=1.14
   _v_pegLT1=_pg
   if _nrg(_v_pegLT1,0,1.0) and P and D3:S*=.85
   if _nrg(_v_pegLT1,0,1.0) and N and D3:S*=1.2
   if _nrg(_v_pegLT1,0,1.0) and Z and D3:S*=.85
   if _nrg(_v_pegLT1,0,.8) and Z and D3:S*=1.14
   if _gt((_g1(Er,'dps_growth',TT)),.1) and Z and D3:S*=.8
   if _gt(_nd3,.1) and _gt(_fy_c,.06) and Z and D3:S*=1.5
   if _gt((_g1(I,'gross_profit',TM)),5e10) and Z and D3:S*=1.14
   _v_ndegB=_nd3
   _v_fcfyB=_fy_c
   if _gt(_v_ndegB,.1) and _gt(_v_fcfyB,.06) and P and D14:S*=.9
   if _gt(_v_ndegB,.1) and _gt(_v_fcfyB,.06) and N and D14:S*=.85
   _v_gpJ=_gp3
   _v_ndegJ=_nd3
   if _gt(_v_gpJ,1e10) and _gt(_v_ndegJ,.1) and Z and D14:S*=1.14
   if _gt(_v_gpJ,1e10) and _gt(_v_ndegJ,.1) and P and D3:S*=1.14
   if _gt((_g1(I,'ebitda',TT)),1e10) and _gt((_fy_c),.06) and Z and D14:S*=1.3
   if _gt(_pt3,1e10) and Z and D14:S*=1.5
   if _gt(_gp3,1e10) and _gt(_nd3,.1) and N and D14:S*=1.14
   if _lt(_ft3,-1e9) and Z and D14:S*=1.2
   if _gt((_g1(B,'preferred_stock',TT)),1e9) and Z and D14:S*=1.3
   if _gt(_pt3,1e10) and _gt(_nd3,.1) and Z and D14:S*=.7
   if _lt(_ft3,-1e9) and Z and D14:S*=1.1
   if _lt(_ft3,-1e9) and _gt(_nd3,.1) and N and D14:S*=1.3
   if _gt((_g1(I,'amortization',TT)),1e9) and Z and D14:S*=1.2
   _v_fyU=_fy_c
   _v_pgU=_pg
   if _gt(_v_fyU,.08) and _nrg(_v_pgU,0,1.0) and P and D3:S*=1.3
   if _gt(_v_fyU,.08) and _nrg(_v_pgU,0,1.0) and Z and D14:S*=1.14
   if _gt(_v_fyU,.08) and _nrg(_v_pgU,0,1.0) and N and D14:S*=1.14
   if _gt(_fy_c,.12) and N and D14:S*=1.3
   _v_eyV=_ey_c
   if _gt(_v_eyV,.08) and N and D14:S*=1.16
   if _gt(_v_eyV,.08) and _hi_cape and D14:S*=1.28
   if _gt(_v_eyV,.08) and _lo_cape and self.time.day<=5:S*=.85
   if S308 and _lo_cape and N:S*=1.14
   if self.time.day>=25 and _lo_vol and N and D14:S*=1.3
   if S308 and self.time.day>=25 and N:S*=1.14
   if S103 and _lo_cape and Z:S*=.7
   if P and S103 and H5:S*=1.2
   if P and _gt(_ey_c,.08) and _gt(_fy_c,.08) and H5:S*=1.14
   if _r60_dn and P and H5:S*=1.1
   if _r60_dn and Z and D14:S*=.88
   if _r60_dn and N and D14:S*=1.03
   if 1<=self.time.day<=5 and _r60_dn and P and H5:S*=1.2
   _v_pegpb=_pp_c
   if _lt(_v_pegpb,4.0) and Z and D3:S*=1.1
   if _lt(_v_pegpb,3.0) and Z and D3:S*=1.1
   if _lt(_ie12c,1e8) and Z and D3:S*=1.14
   if _gt(_fy_c,.1) and Z and D3:S*=.85
   if _lt((_g1(O,'tax_rate',TT)),.2) and P and D3:S*=1.05
   S=_t00(S,_sc,206,_pg,.0,1.5,_qa,-.05,-.01,d,.02,.06,.7)
   S=_t00(S,_sc,206,_pg,.0,1.5,_qa,.01,.05,d,.02,.06,1.08)
   S=_t01(S,_pg,.0,1.0,_qa,-.05,-.01,d,.02,.06,.8)
   if _nrg(_pg,0,1.0) and _nrg(HA,-.05,-.01) and D26:S*=.95
   if _sc==206 and _nrg(_pg,0,1.5) and _nrg(HA,-.05,-.01) and D26:S*=.9
   S=_t00(S,_sc,102,_pg,.0,1.0,_qa,-.05,-.01,d,.06,.12,.5)
   S=_t00(S,_sc,206,_pg,.0,1.5,_qa,-.05,-.01,d,.06,.12,.7)
   if _nrg(_pg,0,1.5) and Q and d>.12:S*=.55
   S=_t00(S,_sc,102,_pg,.0,1.0,_qa,.01,.05,d,.06,.12,2.2)
   if _nrg(_pg,0,1.5) and _gt(_ic1y,20) and Q and D612:S*=.8
   if _nrg(_pg,0,1.5) and _gt(_ic1y,50) and Q and D612:S*=.65
   if _nrg(_pg,0,1.5) and _gt(_ic1y,100) and Q and D612:S*=.55
   if _nrg(_pg,0,1.5) and _nrg(_pec,0,15) and Q and D612:S*=.65
   _vp=_pg; _ev=f_(V.ev_to_revenue)
   if _nrg(_vp,0,1.5) and _nrg(_ev,0,2) and Q and D612:S*=.85
   S=_t01(S,_pg,.0,1.5,_qa,-.05,-.01,d,.06,.12,.7,DP)
   S=_t01(S,_pg,.0,1.5,_qa,-.05,-.01,d,.06,.12,.93,D14)
   S=_t00(S,_sc,206,_pg,.0,1.5,_qa,-.05,-.01,d,.02,.06,.95,D14)
   S=_t00(S,_sc,206,_pg,.0,1.5,_qa,.01,.05,d,.02,.06,1.2,D14)
   S=_t04(S,_vs,50.0,_qa,.01,.05,d,.06,.12,1.3)
   S=_t04(S,_vs,70.0,_qa,.01,.05,d,.06,.12,1.4)
   _v=_vs
   if (_AN(_vs) and _vs>60) and P and D1220:continue
   _v=_vs
   if (_AN(_vs) and _vs>85) and P and D48:continue
   _v=_vs
   if (_AN(_vs) and _vs>85) and P and D24:continue
   _v=_vs
   if (_AN(_vs) and _vs>80) and Z and D26:continue
   _v=_vs
   if (_AN(_vs) and _vs>60) and Z and D612:continue
   if (_AN(_vs) and _vs>=15) and (_AN(_vs) and _vs<30) and Z and D612:S*=1.2
   if (_AN(_vs) and _vs>=50) and (_AN(_vs) and _vs<60) and Z and D612:S*=.5
   if (_AN(_vs) and _vs>=25) and (_AN(_vs) and _vs<30) and Z and D612:S*=1.2
   if (_AN(_vs) and _vs>=50) and (_AN(_vs) and _vs<60) and Z and D48:S*=.85
   if (_AN(_vs) and _vs>=25) and (_AN(_vs) and _vs<30) and Z and D612:S*=1.2
   if (_AN(_vs) and _vs>=15) and (_AN(_vs) and _vs<30) and Z and D48:S*=.95
   if _sc==206 and Z and D612:S*=.85
   if _sc==102 and Z and D612:S*=.95
   if _sc==308 and Z and D612:S*=1.05
   if _sc==308 and Z and D24:S*=1.05
   if _sc==311 and _nrg(_qa,-.05,-.01) and D612:S*=1.25
   if _sc==309 and Z and D48:S*=1.5
   if _sc==308 and Z and D48:S*=.95
   if (_AN(_vs) and _vs<5) and Z and D48:S*=.95
   if (_AN(_vs) and _vs<5) and Z and D24:S*=.55
   if (_AN(_vs) and _vs<5) and _nrg(_qa,-.05,-.01) and D48:S*=.85
   if (_AN(_vs) and _vs<10) and Z and D24:S*=1.05
   if (_AN(_vs) and _vs<10) and Z and D48:S*=1.05
   if (_AN(_vs) and _vs<10) and _nrg(_qa,-.05,-.01) and D48:S*=1.05
   if (_AN(_vs) and _vs<10) and P and D612:S*=1.5
   if (_AN(_vs) and _vs<5) and _nrg(_qa,-.05,-.01) and D612:S*=.55
   if _nrg(_vs,15,30) and _nrg(_r5,.05,.2) and D412:S*=1.5
   if _nrg(_vs,5,10) and _nrg(_r5,.05,.2) and D24:S*=1.5
   if _nrg(_vs,15,30) and _nrg(_r5,.05,.2) and D612:S*=1.14
   if _sc==308 and _nrg(_r5,.05,.2) and D412:S*=.55
   if _BC150 and Z and D612:S*=1.05
   if _BC150 and _QN and D612:S*=.95
   if _BC150 and _QN and D48:S*=.75
   _v=_g1(B,'cash_equivalents',TT)
   if (_AN(_v) and _v>1e8) and P and D612:S*=1.3
   if _nrg(_r7,-.3,-.1) and Z and D412:S*=.85
   if _lt(_qd5,-.05) and D412:
    S*=.95
    if -.05<_qa<-.01:
     S*=.85
     if _r5<0:S*=.75
   if _nrg(_r7,-.2,-.05) and Z and D24:S*=.55
   if _bc>150 and _sc is not None and _sc==308 and D412:S*=1.25
   if _nrg(_vs,5,10) and _nrg(_r5,-.2,-.05) and D412:S*=.95
   if (_AN(_vs) and _vs<5) and _nrg(_r3,-.15,-.03) and D412:S*=1.05
   if _nrg(_r7,-.2,-.05) and Z and D48:S*=.75
   if _nrg(_vs,5,10) and _nrg(_r3,-.15,-.02) and D412:S*=1.05
   if (_AN(_vs) and _vs<5) and _nrg(_r5,-.2,0) and D48:S*=1.5
   _o=f_(bar.open); _pc=f_(mtf[-2].close)
   if _o>0 and _pc>0 and _o/_pc<.95 and Z and D48:S*=.55
   if (_AN(_vs) and _vs<5) and _nrg(_r5,-.2,0) and D24:S*=.95
   if _lt(_bc,50) and _QN and D48:S*=.75
   if _nrg(_bc,50,100) and _QN and D48:S*=.95
   if _lt(_bc,50) and _QN and D612:S*=1.3
   if _lt(_bc,50) and Z and D48:S*=.95
   if _nrg(_bc,50,100) and _QN and D612:S*=1.05
   if _BC150 and _QN and D612:S*=1.14
   if _nrg(_bc,75,100) and _QN and D48:S*=.85
   if _nrg(_bc,30,50) and _QN and D48:S*=.95
   if _nrg(_bc,75,100) and _QN and D612:S*=.55
   if _nrg(_bc,25,50) and _QN and D612:S*=1.05
   _vola=_vol20
   if _vola is not None and _qa is not None:
    if _vola>.04 and D412:
     if Z:S*=.75
     elif -.05<_qa<-.01:S*=.85
    if _vola>.04 and Z and D24:S*=1.5
    if _vola>.05 and -.05<_qa<-.01 and D48:S*=.85
    if _vola>.04 and -.05<_qa<-.01 and D24:S*=.95
    if _vola>.04 and D412:
     if (_AN(_vs) and (_vs if _ac_z else None)<10):S*=.75
    if _vola>.04 and H3 and D412:S*=.85
    if _vola>.04 and H5 and D412:S*=.95
   if (_AN(_vs) and _vs<5) and H3 and D412:S*=1.14
   if _nrg(_vs,5,10) and D3 and D412:S*=.55
   if _nrg(_vs,55,60) and Z and D612:S*=1.5
   if _nrg(_vs,35,40) and Z and D612:S*=1.25
   S=_t05(S,_vs,15.0,_qa,.01,.05,d,.06,.12,1.2)
   S=_t01(S,_vs,30.0,50.0,_qa,.01,.05,d,.06,.12,.85)
   if _nrg(_vs,15,30) and Z and _RU and D412:S*=1.5
   if _nrg(_vs,10,15) and Z and _RU and D412:S*=.55
   if _nrg(_vs,15,30) and Z and _RU and D24:S*=.65
   if _sc==311 and Z and _RU and D412:S*=.85
   if _nrg(_vs,10,15) and Z and _RU and D24:S*=1.14
   if _gt(_vol20,.06) and Z and _RU and D412:S*=.5
   if (_AN(_vs) and _vs>50) and Z and _RU and D412:S*=1.05
   if _nrg(_r7,0,.2) and Z and _RU and D412:S*=1.14
   if (_AN(_vs) and _vs>50) and P and _RU and D412:S*=.85
   if _lt(_vs,10) and Q and _RU and D412:S*=.55
   if _sc is not None and _sc==311 and P and _RU and D412:S*=1.5
   if _sc is not None and _sc==206 and P and _RU and D412:S*=1.5
   _v=_cashc
   if _gt(_cashc,5e9) and P and D48:S*=.85
   if N and H3 and d>.08:continue
   if P and _hi_cape and H3 and d>.2:continue
   if N and _hi_vol and d>.12:continue
   if N and _lt(_r5,-.05) and D3 and d>.04:continue
   if P and .02<d<.05 and _gt(_g1(O,'operation_margin',SM),.2):S+=.04
   if P and .02<d<.05 and _gt(_g1(O,'net_income_cont_ops_growth',OY),.05):S+=.02
   if P and .015<d<.02 and _gt(_gcur,0):S+=.02
   if P and .015<d<.02 and _gt(_gpre,0):S+=.04
   if Q and .02<d<.05 and _gt(_x_ex,1e6):S+=.04
   if P and d>.06 and DP:S*=.85
   if Z and .015<d<.02 and _XIC6:S+=.02
   if Z and .005<d<.012 and _gt(_gsho1,1e6):S+=.02
   if Z and .012<d<.015 and _XRM6:S+=.04
   if Z and .02<d<.05 and _gt(_g1(B,'duefrom_related_parties_current',TM),1e6):S*=1.05
   if Z and .02<d<.05 and _gt(_gins,1e6):S*=1.1
   if N and .02<d<.05 and _gt(_gcha,1e6):S*=1.05
   if Z and .005<d<.012 and _gt(_g1(B,'total_deferred_credits_and_other_non_current_liabilities',TM),1e6):S*=1.1
   if Z and .005<d<.012 and _gt(_g1(B,'electric_utility_plant',TM),1e6):S*=1.05
   if Z and .015<d<.02 and _gt(_gnet2,1e6):S*=1.05
   if Z and .04<d<.06 and _gt(_ginv,1e6):S*=1.05
   if Z and .04<d<.06 and _gt(_gnet2,1e6):S*=1.08
   if Z and .075<d<.15 and _gt(_g1(I,'other_special_charges',TM),1e6):S*=1.05
   if P and .02<d<.05 and _gt(_g1(B,'dueto_related_parties_current',TM),1e6):S*=1.05
   if Z and .02<d<.05 and VF and _XEL6:S*=1.05
   if Z and .02<d<.05 and VF and _gt(_gsal,1e6):S*=1.05
   if P and .02<d<.05 and D3 and _XCL6:S*=1.05
   if P and .02<d<.05 and VR and _XCL6:S*=1.05
   if P and .02<d<.05 and H3 and _gt(_gear,1e6):S*=1.08
   if Z and .012<d<.015 and S310 and _XOE6:S*=1.08
   if P and D48 and _gt(_gnet,1e6):S*=1.05
   if P and D612 and _gt(_ggai,1e6):S*=1.05
   if P and _v is not None and (_AN(_v) and _v>=1000) and D24:S*=1.05
   if P and _bc is not None and _bc>=150 and D612:S*=1.05
   if P and S311 and _bc>=150 and .02<d<.05 and _XRM6:S*=1.05
   if P and S310 and _gt(_gcur,1e6):S*=1.05
   if Z and S311 and _XOE6:S+=.02
   if P and (_AN(_v) and _v>=1000) and _gt(_gamo,1e6):S+=.02
   if P and (_AN(_v) and _v>=1000) and _gt(_gpro,1e6):S+=.02
   if Z and (_AN(_v) and _v>=1000) and _XEX6:S+=.02
   if Z and (_AN(_v) and _v>=1000) and _gt(_g1(B,'other_non_current_liabilities',TM),1e6):S+=.02
   if P and (_AN(_v) and _v>=1000) and _gt(_ginv,1e6):S+=.02
   if Z and (_AN(_v) and _v>=1000) and _XEL6:S+=.02
   if Z and S311 and _gt(_g1(F,'change_in_other_current_assets',TM),1e6):S+=.02
   if Z and S310 and _gt(_gcha,1e6):S+=.02
   if P and S311 and _gt(_g1(B,'preferred_shares_number',TM),1e6):S+=.02
   if Z and (_AN(_v) and _v>=1000) and _XEL6:S+=.02
   if Z and S311 and _gt(_goth,1e6):S+=.02
   if Z and _HA0 and _XEX6:EG+=-.2
   if P and _HA0 and _XEX6:EG+=-.05
   if P and _gt(HA,.005) and _XRM6:EG+=-.1
   if P and _HA0 and _gt(_gins,1e6):EQ+=-.1
   if _PS3 and _gt(_g1(F,'cash_from_discontinued_investing_activities',TM),1e6):S*=1.14
   if P and S205 and DP and D14 and _gt(_g1(_er_z,'diluted_average_shares',TM),1e6):S*=.8
   if Z and S308 and DP and D5 and _gt(_g1(I,'depreciation',TM),1e6):S*=.9
   if P and S309 and DP and D3 and _gt(_g1(I,'fee_revenue_and_other_income',TM),1e6):S*=.95
   if P and S103 and VF and D5 and _gt(_g1(B,'stockholders_equity',TM),1e6):S*=.85
   if Z and S103 and VF and D14 and _gt(_gtot,1e6):S*=.95
   if P and S102 and DP and VF and _gt(_g1(F,'amortization',TM),1e6):S*=.95
   if Z and S309 and DP and Q3 and _gt(_g1(I,'general_and_administrative_expense',TM),1e6):S*=.85
   if Z and S309 and HA and D5 and _gt(_gtot1,1e6):S*=.95
   if Z and S206 and D3 and Q3 and _XIC6:S*=.8
   if Z and S308 and D3 and VF and _XOG6:S*=.91
   if _ZSh and D3 and _gt(_gnet1,1e6):S*=.94
   if Z and S206 and D14 and Q3 and _XOG6 and _NIM6:S*=.92
   if Z and S205 and D3 and Q3 and _FCF6 and _NIM6:S*=.91
   if Z and S102 and D3 and Q3 and _FCF6 and _lt(_gqui,.5):S*=.94
   if P and HA and d>.07:C*=1.12
   if P and HA and d>.06:C*=1.1
   if P and S102 and D14 and d>.05:C*=1.1
   if P and D14 and d>.02:C*=1.13
   if Z and S311 and D14 and d>.04:C*=1.13
   if P and VF and d>.05:C*=1.15
   if Z and D3 and d>.05:C*=1.25
   if P and D14 and D3 and d>.04:C*=1.15
   if P and HA and D5 and d>.04:C*=1.12
   if P and S206 and DP and HA and .02<d<.05 and _gt(_ocf12,1e7):S*=1.08
   if P and D14 and .03<d<.07 and _FCF7:C*=1.2
   if P and DP and .02<d<.05 and _NIM7:S+=.1
   if P and VF and .03<d<.04 and _NIM7:S*=1.06
   if P and D5 and .03<d<.04 and _gt(_ocf12,1e7):S+=.05
   if P and S310 and HA and .01<d<.02:S*=1.1
   if _PSh and .01<d<.02:S*=1.12
   if P and S102 and D14 and .04<d<.08:C*=1.07
   if Z and D5 and .01<d<.02 and _EVF20:C*=.8
   if Z and D14 and .01<d<.02 and _EVE15:C*=.75
   if Z and D5 and .007<d<.009 and _EY5:C*=.72
   if Z and D3 and .007<d<.009 and _EY5:C*=.63
   if Z and H5 and .01<d<.014 and _HAC4:C*=1.12
   if Z and H3 and .014<d<.02 and _AOI3K:C*=1.12
   if Z and H3 and .014<d<.02 and _AOI6K:C*=1.1
   if Z and H3 and .014<d<.02 and _AOI12K:C*=1.1
   if Z and H3 and .016<d<.017 and _AOI3K:C*=1.12
   score=S;wt_tilt=W;conv=C;entry_signal=ES;entry_score_mtf=EM;entry_score_regime=ER;entry_score_gate=EG;entry_score_quality=EQ;entry_score_conv=EC
   if P and H3 and .014<d<.02:wt_tilt*=1.22
   if P and H3 and .014<d<.02:conv*=1.07
   if P and H5 and .014<d<.02:wt_tilt*=1.05
   # --- ENTRY INJECT POINT ---
   S=score;W=wt_tilt;C=conv;ES=entry_signal;EM=entry_score_mtf;ER=entry_score_regime;EG=entry_score_gate;EQ=entry_score_quality;EC=entry_score_conv
   if O and d>.05:
    _rg=_rg1y
    if (_AN(_rg) and _rg>.15):S*=1.15
   if O:
    _rg8=_rg1y
    if _rg8 and (_AN(_rg8) and _rg8>.15) and D5:
     S*=1.2
   if O:
    _roe9=_rey
    if _lt(_roe9,-.05) and Qd3:
     continue
   if V:
    _peg11=_pg
    if _peg11 is not None and (_AN(_peg11) and 0<_peg11<1.2) and D5:
     S*=1.15
   if O and d>.18:
    _gm12=_gm1
    _rg12=_rg1y
    if _gm12 and (_AN(_gm12) and _gm12>.4) and _rg12 and (_AN(_rg12) and _rg12>.15):
     S*=1.25
   if O and d>.18:
    _gm13=_gm1
    _rg13=_rg1y
    if _gm13 and (_AN(_gm13) and _gm13>.4) and _rg13 and (_AN(_rg13) and _rg13>.15):
     S*=1.3
   if O:
    _rg14=_rg1y
    if _rg14 and (_AN(_rg14) and _rg14>.15):
     if window and len(window)>=20:
      _ma5=sum(f_(b.close) for b in window[-5:])/5
      _ma20=sum(f_(b.close) for b in window)/20
      if _ma5<_ma20*.92:
       S*=1.25
   if O:
    _roe16=_rey
    if _roe16 and (_AN(_roe16) and _roe16>.2) and _qs and len(_qs)>=10 and _hs and len(_hs)>=5:
     _qd16=_qd10
     _bd16=_bd5
     if _qd16<-.07 and _bd16<0:
      S*=1.25
     if _qd16<-.07 and _bd16<0:
      S*=1.21
   if Er and V:
    _depsg19=_g1(Er,'diluted_eps_growth',OY)
    _pe19=_pec
    if _depsg19 is not None and (_AN(_depsg19) and _depsg19>.35) and _pe19 is not None and (_AN(_pe19) and 0<_pe19<15):
     S*=1.2
   if O:
    _rg23=_rg1y
    if _rg23 is not None and (_AN(_rg23) and _rg23<-.2) and d>.1:
     continue
   if I and F and O:
    _ni22=f_(_nim12)
    _fc22=f_(_fcf12)
    _de22=_g1(O,'total_debt_equity_ratio',OY)
    if _AN(_ni22,_fc22,_de22) and _ni22<0 and _fc22<0 and (_AN(_de22) and _de22>2.0):
     continue
   if O:
    _rg22=_rg1y
    if _rg22 and (_AN(_rg22) and _rg22>.2) and _hs and len(_hs)>=10:
     _bd22=_bd10
     if _bd22>.02:
      S*=.9
   if O:
    _gm24=_gm1
    if _gm24 and (_AN(_gm24) and _gm24>.4) and _hs and len(_hs)>=5:
     _bd24=_bd5
     if _bd24>.015:
      S*=.87
   if O and V:
    _gm25=_gm1
    _pe25=_pec
    if _gm25 and (_AN(_gm25) and _gm25>.4) and _qs and len(_qs)>=10:
     _qd25=_qd10
     if _qd25>.05:
      S*=.85
    if _gm25 and (_AN(_gm25) and _gm25>.5) and _pe25 is not None and (_AN(_pe25) and 0<_pe25<10):
     if d>.15:
      S*=1.13
     if d>.3:
      S*=1.2
    if _gm25 and (_AN(_gm25) and _gm25>.4) and _pe25 is not None and (_AN(_pe25) and 0<_pe25<15):
     if d>.2:
      S*=1.13
     if d>.35:
      S*=1.2
   if O:
    _qr26=_g1(O,'quick_ratio',OY)
    _rg26=_rg1y
    if _qr26 is not None and (_AN(_qr26) and _qr26<.5) and _rg26 is not None and (_AN(_rg26) and _rg26<.05) and d>.05:
     continue
   if O:
    _rg26b=_rg1y
    if _rg26b and (_AN(_rg26b) and _rg26b>.3):
     if _hlc is not None and _hl_len>=120:
      _w120_first=_hlc[-120]
      if _w120_first>0:
       _r120=(_bc-_w120_first)/_w120_first
       if _r120<-.3:
        S*=1.2
   if _gt(_vol20,.06):C*=.5
   if O:
    _rg29=_rg1y
    if _rg29 and (_AN(_rg29) and _rg29>.15) and _qs and len(_qs)>=20:
     _qd20br=_qd20
     if _qd20br>.1 and d<.1:
      S*=.8
   if _hs and len(_hs)>=20:
    _bra=[f_(_hs[i].close)/f_(_hs[i-1].close)-1 for i in range(1,20) if f_(_hs[i-1].close)>0]
    if _bra:
     _bv=(sum(x*x for x in _bra)/len(_bra))**.5
     if _bv<.002 and d>.1:
      S*=1.1
   if F:
    if (_g1(F,'change_in_account_payable',TM))>1e9 and d>.05:S*=1.06
   if V:
    if (f_(V.first_year_estimated_eps_growth))>5 and d>.1:S*=1.1
   if _qs and len(_qs)>=5:
    if _qd5<-.03 and d>.03:S*=1.25
   if _hs and len(_hs)>=5:
    _bd5x=_bd5
    if _qd5<-.03 and _bd5x<0 and d>.05:S*=1.2
   if (_qs and len(_qs)>=5 and _hs and len(_hs)>=5 and
       len(window)>=10):
    _qd5c=_qd5
    _bd5c=_bd5
    _v_recent=sum(_wvol10[-3:])/3
    if _qd5c<-.04 and _bd5c<0 and d>.09 and _v_recent/max(.01,(sum(_wvol10)/10))>1.5:
     S*=2.2
   if Er is not None and d>.15:
    if (_g1(Er,'book_value_per_share_growth',OY))>.15:S*=1.13
   if (_AN(_vs) and _vs<60) and Z and D612:W*=.7
   if P and DP and _gt(_g1(F,'other_non_cash_items',TM),1e6):ER+=-.025
   if P and S311 and DP and _gt(_gnet,1e6):EQ+=-.1
   if Z and S311 and DP and _XOE6:EQ+=-.1
   if _PS3 and _XEX6:EM+=-.667
   if Z and S311 and DP and _gt(_gsho,1e6):EM+=-.25
   if Z and S310 and DP and _gt(_g1(B,'total_debt',TM),1e6):EM+=-.5
   if Z and S311 and D5 and _XIC6:EM+=-.333
   if Z and S310 and DP and _gt(_gpro,1e6):EG+=-.125
   if Z and S205 and HA and _gt(_gpre,1e6):EM+=-.5
   if Z and S308 and DP and _gt(_goth,1e6):EM+=-.15
   if P and S205 and DP and D14 and _gt(_gpro,1e6):EM+=-.5
   if Z and S205 and D5 and D14 and _gt(_gsho1,1e6):EM+=-.2
   if Z and S206 and DP and D14 and _XOE6:EM+=-.25
   if P and S205 and HA and D14 and D5 and _XRM6:EM+=-.2
   if Z and S103 and VF and D5 and _gt(O.capital_expenditure_annual_5_yr_growth.one_year,1e6):EM+=-.2
   if Z and S102 and DP and D5 and _XCL6:EM+=-.075
   if _ZSh and Q3 and _gt(_goth,1e6):EM+=-.1
   if _ZSh and D14 and _gt(_gnet1,1e6):EQ+=-.075
   if Z and S311 and VF and D3 and _gt(_g1(B,'cash_and_cash_equivalents',TM),1e6):EM+=-.25
   if Z and S308 and D14 and D3 and _gt(_ggai1,1e6):EG+=-.1
   if Z and S311 and D3 and Q3 and _XOG6 and _NIM6:EM+=-.2
   if Z and S310 and HA and Q3 and _FCF6 and _NIM6:EM+=-.075
   if Z and S311 and D3 and Q3 and _FCF6 and _gt(_pb_,3):EM+=-.15
   if _ZSh and D14 and _NIM6 and _PS5:EM+=-.2
   if Z and S311 and HA and D14 and _FCF6 and _lt(_g1(O,'net_margin',TT),.05):EM+=-.15
   if Z and S308 and HA and D14 and _NIM6 and _GROA20:EG+=-.05
   if _PSh and Q3 and _NIM6 and _GROA20:EG+=-.1
   if P and S102 and VF and Q3 and _OCF6 and _GROA20:EG+=-.1
   if _PSh and D14 and _OCF6 and _gt(_gtax,.35):EG+=-.05
   if _PSe and D14 and _FCF6 and _gt(_gtax,.35):EG+=-.125
   if _PS6 and D14 and _FCF6 and _gt(V.payout_ratio,.7):EG+=-.075
   if _PSe and D14 and _OCF6 and _gt(_g1(O,'days_in_payment',OY),60):EG+=-.075
   if P and S206 and D3 and Q3 and _OCF6 and _gt(_g1(I,'cost_of_revenue',TM),1e10):EG+=-.13
   if _PS6 and D14 and _OCF6 and _gt(_g1(I,'cost_of_revenue',TM),1e10):EG+=-.125
   if P and S206 and D3 and Q3 and _NIM6 and _gt(_g1(Er,'normalized_basic_eps_growth',OY),.1):EG+=-.125
   if _PSe and D14 and _OCF6 and _gt(_g1(O,'cash_ratio_growth',OY),.1):EG+=-.125
   if Z and D14 and .005<d<.01 and _FCF7:EM+=.2
   if Z and D14 and .005<d<.01 and _FCF7:S+=.005
   if P and D5 and .02<d<.05 and _gt(_g1(F,'change_in_tax_payable',TM),1e7):W*=.7
   if P and D14 and .03<d<.06 and _gt(_g1(I,'ebit',TM),1e7):W*=.65
   if P and VF and .02<d<.05 and _gt(_g1(F,'deferred_tax',TM),1e6):W*=.6
   if P and HA and .02<d<.05 and _gt(_g1(I,'other_costof_revenue',TM),1e6):W*=.6
   if P and S205 and D14 and .01<d<.02 and _gt(_ocf12,1e7):EQ+=-.1
   if Z and D5 and .01<d<.014 and _EVF20:ES+=-.1
   if Z and D5 and .007<d<.009 and _EVF20:ES+=-.1
   if Z and D5 and .014<d<.02 and _EVF20:ES+=-.07
   if Z and D5 and .04<d<.08 and _EVF20:ES+=-.08
   if Z and D5 and .002<d<.005 and _EVF20:ES+=-.08
   if Z and Q3 and .01<d<.03 and _EVF20:ES+=-.09
   if Z and Q3 and .01<d<.014 and _EVF20:ES+=-.1
   if Z and H5 and .01<d<.014 and _EVF20:ES+=-.09
   if Z and H3 and .001<d<.003 and _EVF20:ES+=-.09
   if Z and H3 and .014<d<.02 and _AOI3K:ER+=.03
   if Z and H5 and .01<d<.014 and _HAC4:EC+=.04
   if Z and H3 and .02<d<.022 and _AOI3K:ER+=.03
   if Z and Q3 and .01<d<.014 and _EY5:ER+=.05
   if Z and H3 and .014<d<.015 and _AOI3K:ER+=.06
   if Z and D3 and .014<d<.015 and _AOI3K:ER+=.055
   if Z and D3 and .02<d<.022 and _AOI3K:ER+=.07
   if Z and D3 and .02<d<.022 and _AOI6K:ER+=.06
   if Z and D3 and .02<d<.022 and _AOI12K:ER+=.06
   if Z and D14 and .02<d<.022 and _AOI3K:ER+=.06
   if P and D14 and .02<d<.022 and _AOI3K:ER+=.06
   if Z and D3 and .02<d<.022 and _gt(_g1(I,'depreciation',TM),1e6):ER+=.06
   if Z and D3 and .0145<d<.015 and _AOI3K:ER+=.06
   if Z and Q3 and .012<d<.014 and _EY5:ER+=.06
   if Z and H3 and .014<d<.015 and _EY5:ER+=.06
   if Z and H3 and .02<d<.022 and _EY5:ER+=.06
   if Z and H3 and .021<d<.022 and _EY5:ER+=.06
   if Z and H3 and .022<d<.024 and _EY5:ER+=.06
   if Z and H3 and .024<d<.026 and _EY5:ER+=.06
   if Z and H3 and .026<d<.028 and _EY5:ER+=.06
   if Z and H3 and .028<d<.03 and _EY5:ER+=.06
   if Z and H3 and .03<d<.032 and _EY5:ER+=.06
   if Z and H3 and .032<d<.034 and _EY5:ER+=.06
   if Z and H3 and .036<d<.038 and _EY5:ER+=.06
   if Z and H3 and .015<d<.017 and _EY5:ER+=.06
   if Z and VF and .014<d<.015 and _EY5:ER+=.06
   if N and H3 and .014<d<.015 and _EY5:ER+=.06
   if Z and VF and .02<d<.022 and _EY5:ER+=.08
   if N and VF and .014<d<.015 and _EY5:ER+=.06
   if Z and H3 and .023<d<.024 and _EY5:ER+=.06
   if Z and H3 and .044<d<.048 and _EY5:ER+=.07
   if Z and H3 and .048<d<.052 and _EY5:ER+=.07
   if Z and H3 and .052<d<.056 and _EY5:ER+=.07
   if Z and H3 and .056<d<.06 and _EY5:ER+=.07
   if Z and H3 and .038<d<.04:ER+=-.04
   if Z and H3 and .011<d<.013:ER+=-.04
   if Z and H3 and .029<d<.031:ER+=-.015
   if Z and H3 and .043<d<.045:ER+=-.05
   if Z and H3 and .047<d<.049:ER+=-.06
   if P and H3 and .047<d<.049:ER+=-.05
   if Z and _gt(HA,0) and H3 and .02<d<.022:ER+=-.04
   if Z and _gt(HA,0) and H3 and .016<d<.018:ER+=-.03
   if P and H5 and .04<d<.042:ER+=-.04
   if P and H3 and .02<d<.022:ER+=-.018
   if P and H5 and .044<d<.046:ER+=-.015
   if P and H5 and .042<d<.044:ER+=-.013
   if P and DP and .02<d<.022:ER+=-.015
   if P and Q3 and .014<d<.016:ER+=-.013
   if P and Q3 and .01<d<.012:ER+=-.014
   if P and Q3 and .018<d<.02:ER+=-.014
   if P and H3 and .027<d<.029:ER+=-.014
   if P and H3 and .041<d<.043:ER+=-.014
   if N and H3 and .02<d<.022:ER+=.02
   if Z and D3 and .02<d<.022:ER+=.02
   if Z and H3 and .024<d<.026 and _INV8:ER+=.05
   if Z and H3 and .02<d<.022:ER+=.02
   if Z and H3 and .02<d<.022 and _INV8:ER+=.07
   if Z and VF and .035<d<.037:ER+=.04
   if Z and _HA0 and H3 and .016<d<.018:ER+=-.03
   if Z and _HA0 and H3 and .02<d<.022:ER+=-.04
   if P and Q3 and .008<d<.02:C*=.93
   if P and H5 and .04<d<.046:W*=.86
   if P and DP and .04<d<.06:W*=.87
   if P and _gt(HA,0) and DP and .04<d<.06:W*=.87
   if P and _gt(HA,0) and DP and .04<d<.06:S*=.95
   if P and DP and .014<d<.03 and _INV8:W*=.85
   if P and DP and HA and .02<d<.04:W*=.88
   if P and H3 and HA and .01<d<.014:W*=.92
   if P and DP and HA and .025<d<.03:W*=.88
   if P and H3 and HA and .01<d<.012:W*=.94
   if P and DP and .014<d<.02:W*=.94
   if P and H3 and HA and .014<d<.02:W*=1.05
   if P and H3 and HA and .014<d<.017:W*=1.14
   if P and H5 and .014<d<.017:W*=.94
   if P and H5 and .017<d<.02:W*=.94
   if P and Q3 and .017<d<.02:W*=.97
   if P and H3 and .02<d<.025:W*=.94
   if P and H3 and .018<d<.02:W*=.92
   # --- ENTRY SIGNAL BAKE INSERT ---
   S+=ES+.3*EM+10*ER+EC+EQ
   S*=1+max(-.5,min(.5,EG))
   _uk=max(.55,min(1.0,1.0-UNAN_SLOPE*max(.0,getattr(self,'_xmove',.0)-UNAN_THR)))
   C=min(5.0,max(1.0,1.0+(C-1.0)*_uk))
   candidates.append((sym,S,C,W))
  if not candidates:return
  candidates_w=[]
  for sym,S,C,W in candidates:
   _tilt_clamped=max(.1,min(2.0,W))
   weight_score=min(WT_CAP,C*_tilt_clamped*WT_PER_CONV)
   candidates_w.append((sym,S,C,W,weight_score))
  ranked=sorted(candidates_w,key=lambda c:c[1],reverse=True)
  total_value=_g1(self,'portfolio','total_portfolio_value') or 1
  existing_pct=sum(abs(f_(h.holdings_value))/total_value for h in self.portfolio.values()
                     if h.invested and h.symbol not in self._hedge_syms)
  remaining_budget=max(0,gross_target-existing_pct)
  if remaining_budget<=0:return
  new_targets=[]
  used=.0
  for sym,S,C,W,weight_score in ranked:
   if used>=remaining_budget:break
   w=min(weight_score,remaining_budget-used)
   if w<MIN_WT:continue
   new_targets.append((sym,w))
   used+=w
  leftover=remaining_budget-used
  if 1e-4<leftover<MIN_WT and new_targets:
   for _i in range(len(new_targets)):
    if leftover<=1e-4:break
    _sym,_w=new_targets[_i];_add=min(leftover,WT_CAP-_w)
    if _add>0:new_targets[_i]=(_sym,_w+_add);leftover-=_add
  if not new_targets:return
  self.pending_entries=[PortfolioTarget(sym,min(WT_CAP,w)) for sym,w in new_targets]
 @staticmethod
 def _fv(obj,attr,timeframe):
  return _g1(obj,attr,timeframe) if timeframe else _g1(obj,attr)
 def execute_pending_orders(self):
  if self.is_warming_up:return
  for sym in list(self.pending_exits):
   self.liquidate(sym)
  if self.pending_entries:
   self.set_holdings(list(self.pending_entries))
  self.pending_exits=[]
  self.pending_entries=[]

 def on_end_of_algorithm(self):
  self.set_runtime_statistic('retired_fundamental_fields',str(len(_RETIRED_FUNDAMENTAL_FIELDS)))
  self.set_runtime_statistic('retired_fundamental_paths',','.join(sorted(_RETIRED_FUNDAMENTAL_FIELDS)))
