"""Deterministic synthetic delivery for engineering tests, never market evidence."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json
from .axis import stamp


def make_bundle(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    calendar=[];minutes=[];decisions=[];options=[]
    day=datetime(2024,1,2,14,30,tzinfo=timezone.utc)
    for session_index in range(23):
        while day.weekday()>=5:day+=timedelta(days=1)
        session=day.date().isoformat();calendar.append(dict(session=session,open=stamp(day),close=stamp(day+timedelta(minutes=60))))
        for i in range(60):
            for symbol in ['SPX','SPY']:
                price=100+session_index*.1+i*.02
                minutes.append(dict(session=session,symbol=symbol,start=stamp(day+timedelta(minutes=i)),
                    end=stamp(day+timedelta(minutes=i+1)),available_at=stamp(day+timedelta(minutes=i+1,seconds=1)),
                    frequency_seconds=60,open=price-.01,high=price+.01,low=price-.02,close=price,
                    volume=10,trade_notional=price*10,source_row_id=f'{session}:{symbol}:{i}'))
        decisions.append(dict(decision_at=stamp(day+timedelta(minutes=35)),strategy='C0',frozen_order=['fixture',1]))
        options.append(dict(contract_id=f'SPXW:{session}:P:100',root='SPXW',expiry=session,listed_asof=True,
            observed_at=stamp(day+timedelta(minutes=34)),quote_ts=stamp(day+timedelta(minutes=34)),
            available_at=stamp(day+timedelta(minutes=34,seconds=1)),greek_asof=stamp(day+timedelta(minutes=34)),
            greek_available_at=stamp(day+timedelta(minutes=34,seconds=1)),greek_input_at=stamp(day+timedelta(minutes=34)),
            frequency_seconds=60,greek_frequency_seconds=60,greek_model_accepted=True,bid=1.,ask=1.2,delta=-.2,spot=110.,source_row_id=f'{session}:quote'))
        day+=timedelta(days=1)
    files={}
    for key,rows in dict(calendar=calendar,minutes=minutes,decisions=decisions,options=options).items():
        f=folder/(key+'.json');f.write_text(json.dumps(rows));files[key]=dict(path=f.name,sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    receipt=folder/'verification.json';receipt.write_text(json.dumps({'synthetic':True,'scope':'engineering fixture, not provider data'}))
    manifest=dict(version='0.8.9',status='verified',input_kind='synthetic_fixture',frequency_seconds=60,upsampled=False,
                  release='synthetic-23-session-v089',files=files,
                  verification_receipt=dict(path=receipt.name,sha256=hashlib.sha256(receipt.read_bytes()).hexdigest()))
    f=folder/'manifest.json';f.write_text(json.dumps(manifest,indent=2));seal_fixture(f);return f


def seal_fixture(path):
    """Test-only attestation builder. Never used to promote provider deliveries."""
    path=Path(path);m=json.loads(path.read_text())
    if m['input_kind']!='synthetic_fixture':raise ValueError('fixture only')
    receipt=path.parent/m['verification_receipt']['path']
    receipt.write_text(json.dumps(dict(status='verified',release=m['release'],synthetic=True,
        frequency_seconds=60,artifacts={k:v['sha256'] for k,v in m['files'].items()})))
    m['verification_receipt']['sha256']=hashlib.sha256(receipt.read_bytes()).hexdigest()
    path.write_text(json.dumps(m,indent=2))
