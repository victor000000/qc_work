"""Read-only LVS actual order/corporate-action diagnostic; no QC or raw-history calls."""
import json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'strategies/sstrangle'))
from qc_contracts import execution_rows,execution_signature
CAMP=ROOT/'strategies/sstrangle/results/strangle_basket-calmar_20261019_123602';DATA=CAMP/'SSTRANGLE_20261019_123602_cap20_stop1'
orders=json.loads((DATA/'orders.json').read_text());rust=json.loads((DATA/'orders.rust.json').read_text())
assert execution_signature(execution_rows(orders))==execution_signature(execution_rows(rust))
chosen=[o for o in orders if o['tag'].startswith('LVS T4J5S7AT6WRP:')]
assert [o['id'] for o in chosen]==[257,258,263,264]
rs=execution_rows(chosen);net=sum(-r['quantity']*r['qc_price']*r['multiplier']-r['fee'] for r in rs)
assert abs(net+12180.9)<1e-8
native={}
for r in rs:native[r['symbol_id']]=native.get(r['symbol_id'],0)+r['quantity']
assert not any(native.values())
summary={'status':'Read-only native execution diagnosis; quote-source error NOT proved; no strategy edits/submissions',
'backtest':'8a6d193829c51b26976d40707c081eb5','native_underlying_sid':'LVS T4J5S7AT6WRP','point_in_time_alias':'LVS','genuine_fills':rs,'order_metadata':[{k:o[k] for k in ['id','symbol','time','quantity','price','status','priceAdjustmentMode','groupOrderManager','orderSubmissionData']} for o in chosen],
'actual_economics':{'initial_credit':246,'exit_cost':12422,'fees':sum(r['fee'] for r in rs),'net_pnl':net,'pnl_loss_multiple_original_credit':-net/246,'entry_equity':57718.42,'loss_fraction_entry_equity':-net/57718.42,'opening_margin_budget':2885.921,'estimated_initial_margin':2298.8,'residual_native_quantities':native,'exit_dte':30},
'put_submission_quote_arithmetic':{'bid':.61,'ask':62,'mid':31.305,'spread':61.39,'relative_spread':61.39/31.305,'ask_over_bid':62/.61,'ask_over_strike':62/47.5,'fill_minus_mid_cost_2lots':(62-31.305)*200,'warning':'Snapshot arithmetic, NOT independently validated market quotes or achievable midpoint fills. An ask above strike is not by itself an exploitable arbitrage or proof of bad data.'},
'deliverable_and_corporate_action_evidence':[
'NativeSIDdecoder gives P47.5 andC60,expiry2015-09-18,securitytypeequityoption; sameexactnativeSID onopen/close. NativeexportaliaseswellformedLVS,unlikeCBS/WBA historicaldisplayissues.',
'Frozen tags and default-security accounting multiplier100 forbothlegs, pricesUSD, priceAdjustmentMode0raw. Standard-lookingrootLVS and100multiplier do not independently certify historical OCC deliverable.',
'Issuerdividendhistory listsregularcashdividends$0.65 ex2015-06-18 and2015-09-18; nonewithintheinvestigated2015-07-28 through2015-08-19 interval. SECissuerJuly22releaseexplicitlycallsnextSep30paymentrecurringquarterly.',
'No contemporaneoussplit/merger/deliverable-adjustment evidence found in inspectedprimarysources. Searchabsence isnotproofthatnoneexists. Historicalcontract-specificOCCmemo/deliverablefile notobtained.',
'OCCstandardequityspecification says100sharesperstandardcontractandcorporateactionscancreatenonstandarddeliverables; this is generalcontext ratherthancontract-specificverification.'
],
'causal_evidence_and_limits':[
'cap20_stop1 intraday_risk_exits checks every15minbucket butthefirst2015Aug19openingslice09:31isnewbucket. ClosevaluationusesASKsum andnativecombo_market_order buysactualASK. Economicstop2legs occursat09:31,notnoonor21DTEtimeexit.',
'Putask62 withbid.61 isextremelyuncompetitive; sourcegood_quote onlycheckspositivebid/noncrossed/freshnonFFbar, withoutspread/economicaskceilingforvoluntaryexits. Bothquotescanpassthatpredicatewhiletheaskdrivesastopandbadmarketfill.',
'ExactsubmissionbidaskanddefaultfillequalityprovehowQCaccountlosesmoney, notwhether62wasvalidNBBO,historicaldatacorruption,orattainabledepth. Quotesideageandvendorfeedcrosschecksarenotavailablefromactualorderexports.',
'Forstandardnonnegativeequitydeliverable,putterminalpayoffperquotedsharecannotexceedstrike. This supportsa cautiousbuypricehypothesis,notreplacingthegenuine62fillnorprovingeverydisplayedaskmustobeyfairvaluebound. Arbitragewouldrequireexecutablebid/highsaleoradditionalconditions,notmerelyanuncompetitiveoffer.',
'Entry2lotswerewithincapped5%marginbudget;lossstill21.1%ofentryaccount. Cappedinitialmarginisnotamaxlossconstraint. Thisrequiresactualtail/executiontestingratherthanassuminglowercollateralalonefixesCalmar.'
],
'primary_sources':[
{'url':'https://www.sec.gov/Archives/edgar/data/1300514/000095014215001735/eh1501002_ex9901.htm','supports':'July22,2015issuerrelease identifiesNYSE:LVS,nextrecurringquarterlydividend.65 payableSep30,recordSep22.'},
{'url':'https://investor.sands.com/stock-info/dividend-history/default.aspx','supports':'2015cashdividendexdatesJun18/Sep18andamount.65.'},
{'url':'https://www.theocc.com/clearance-and-settlement/clearing/equity-options-product-specifications','supports':'Standard100-shareequityoptionunitandpossiblecorporateactionadjustments.'},
{'url':'https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/combo-market-orders','supports':'Defaultcombuyfillattheask; realorderfillevidenceconfirmsmodeledexecutionhere.'}],
'input_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [DATA/'orders.json',DATA/'orders.rust.json',CAMP/'cap20_stop1.py',CAMP/'extra_files.json']}}
summary['same_batch_other_cycle']={'key':'FUT_ZC','order_ids':[259,260,261,262],'net_pnl':-1772.38,'warning':'FocusedLVS-onlyfixturecashcannotreproducefullaccountmarginpathwithoutthisactualothercycle.'}
summary['fixed_trade_midpoint_sensitivity']={'all4_fills_touch_minus_mid_cost':6157,'net_after_addingback_all_midpoint_cost_arithmetic':-6023.9,'warning':'Notachievablefillmodelorportfolioforecast; noeconomicfillchanged.'}
# ActualexpirySep18-Aug19=30,not31: retaincalendardifferenceexactly.
(ROOT/'strategies/sstrangle/optimization/lvs_exit_evidence_20261019.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary['actual_economics'],indent=2))
