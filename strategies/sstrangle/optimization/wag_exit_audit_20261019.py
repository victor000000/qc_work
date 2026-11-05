"""Read-only native-order diagnosis; no market-history exports or QC actions."""
import json,sys,hashlib
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'strategies/sstrangle'))
from qc_contracts import execution_rows,execution_signature
CAMP=ROOT/'strategies/sstrangle/results/strangle_basket-calmar_20261019_123602'
DATA=CAMP/'SSTRANGLE_20261019_123602_cap20_stop1'
orders=json.loads((DATA/'orders.json').read_text());rust=json.loads((DATA/'orders.rust.json').read_text())
rows=execution_rows(orders);assert execution_signature(rows)==execution_signature(execution_rows(rust))
assert len(orders)==762
key='WAG R735QTJ8XC9X';selected=[o for o in orders if o['id']>=759];rr=[r for r in rows if r['order_id']>=759]
assert len(rr)==4 and all(r['strategy_key']==key for r in rr)
q=defaultdict(float)
for r in rows:q[r['symbol_id']]+=r['quantity']
res={s:v for s,v in q.items() if v}
fees=sum(r['fee'] for r in rows)
info={'status':'Unexpected native exit failure; actual residual positions remain; no Calmar/performance success claim',
'backtest_id':'8a6d193829c51b26976d40707c081eb5','campaign':str(CAMP),'order_count':len(orders),'genuine_fill_count':len(rows),'rust_python_economic_signatures_match':True,'actual_fees_all_orders':fees,'actual_initial60000_plus_all_order_net_cash':60000+sum(-r['quantity']*r['qc_price']*r['multiplier']-r['fee'] for r in rows),'residual_holdings_native':res,'failure':'2019-12-02 00:00NY Mandatory exit lacked fresh quotes on its eligible session: WAG R735QTJ8XC9X','actual_last_cycle_fills':rr,'last_cycle_cashflow_net_fees':sum(-r['quantity']*r['qc_price']*r['multiplier']-r['fee'] for r in rr),'last_cycle_fees':sum(r['fee'] for r in rr),'last_cycle_realized_trade_cash_is_not_pnl':'Residual put57.5 and call65 are still short; $144netcash does not price their outstanding liability and is not completedcycleprofit.',
'identity':{'permanent_equity_sid':key,'contemporaneous_equity_ticker':'WBA','basis':'Official Nasdaq2014-44/SEC/MIAX namechange effective2014-12-31; original permanent WAG SID remains stable. Runtime ENTRY ticker should be verified from newly collected logs when available. Export underlying.value and option value are malformed duplicated aliases and do not determine economic identity.','same_expiry':'2019-12-20','put_open_and_residual_native_sid':rr[0]['symbol_id'],'initial_call_native_sid':rr[1]['symbol_id'],'rolled_call_residual_native_sid':rr[3]['symbol_id']},
'expected_exit':{'date':'2019-11-29','new_york_time':'12:00:00','utc':'2019-11-29T17:00:00Z','dte':21,'source':'Frozen atnoon mandatorydte<=21 logic; official2019exchangeholidaycalendar has openNov29earlyclose13:00 (eligibleoptions13:15), so noon remainsopen. No Thanksgivingholidaydeferral toMonday is warranted.'},
'proven_source_control_flow':[
'cap20_stop1.py361-371 cleanup constructs held native symbols from positions put/call, removes only subscribed_options-held when flat/noopenorders, retains held symbols in subscribed_options. This source does not imply accidental heldsymbol removal.',
'cap20_stop1.py453 adds replacementnativeoption before storingrollcandidate;729-753 submitsroll and filledcallbackupdates trade call to native65 option. Orders761/762 genuine FILLED, matching targetcontracts.',
'cap20_stop1.py470-475 process_exit_requests called on everyminute slice before intradayrisk and noon gates;556-571 existingmandatoryrequest waitsforboth good_quote thenbuys, errorsifdatepassesrequestday.',
'cap20_stop1.py457-461 good_quote requires cached QuoteBar, nonfillforward, endtimewithinfivemin and strictlypositivebid plusask>=bid. It does notrecordwhichpredicatefailed.',
'cap20_stop1.py485-504 first productopennoon21DTE setsTIMEexitrequest independentofquotes;process_exit_requests cannotexecuteuntilboth passgood_quote. Errorindicatesanexistingrequestoutliveditsday but doesnotidentifywhichleg/predicatefromsavedordersalone.'
],
'hypotheses_not_proven':[
'FreshzeroBid, positiveAsk OTM leg would failgood_quote despite buybackbeingexecutableatask. This is a concrete predicate mismatch forbuyclose requirements; neitherwhichlegnoractualzeroBidonNov29hasbeenshown.',
'Absent/stale/forward-only quote ononelegcouldalso blocksameexit; sourceand genuineorders do notdistinguishthese. Relaxingfreshnesswould conceal ratherthanrepair missingdata.',
'Underlying/optionsaliasmappingcouldinteractwithsubscriptionnativefeed, but malformedexportdisplayisnotproof and frozen nativeSIDmembership avoidsstringtickerpairing.'
],
'needed_native_evidence':[
'Exactposition control regression throughNov29 withfour realinitialfills matching original; frozen good_quote. Diagnostic aggregate counters perleg for cacheabsent,fillforward,ageinvalid,bidzero/negative,asknonpositive/crossed and heldsymbol/subscriptionmembership atmandatorysession. No rawquotehistory exports.',
'Repair samefixture ONLY if freshzeroBid positiveAsk is observed: buyback-specific freshQuoteBar nonFF bid>=0 ask>0 ask>=bid. Existing stricterentry/selling/rollreplacementpredicateunchanged. Native actualbuyfills atask/defaultmodel, fees/account/zeroresiduals audited.',
'If quoteabsent/stale, separatesubscription/dataavailabilitydiagnosis required; do notdeclarezeroBidrepairpassednorcarryNov29exittoMondayascompliant.'
],
'official_primary_sources':[
'https://www.nasdaqtrader.com/TraderNews.aspx?id=dtn2014-44',
'https://www.sec.gov/Archives/edgar/data/1618921/000119312514457671/d843789d8k12b.htm',
'https://www.miaxglobal.com/alert/2014/12/30/miax-corporate-action-alert-walgreen-co-wag-name-and-symbol-change?nav=all',
'https://ir.theice.com/press/news-details/2018/NYSE-Group-Announces-2019-2020-and-2021-Holiday-and-Early-Closings-Calendar/default.aspx'
],
'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [DATA/'orders.json',DATA/'orders.rust.json',CAMP/'cap20_stop1.py',CAMP/'extra_files.json']}}
assert len(res)==2 and all(x==-1 for x in res.values())
assert abs(info['last_cycle_cashflow_net_fees']-144)<1e-8
OUT=ROOT/'strategies/sstrangle/optimization/wag_exit_evidence_20261019.json';OUT.write_text(json.dumps(info,indent=2)+'\n')
print(json.dumps({k:info[k] for k in ['order_count','genuine_fill_count','actual_fees_all_orders','residual_holdings_native','last_cycle_cashflow_net_fees','last_cycle_fees']},indent=2))
