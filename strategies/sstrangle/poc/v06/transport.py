"""Authenticated QC JSON transport with per-worker persistent TLS connections.

No automatic replay of writes. Callers retry only explicitly read-only APIs.
Authentication remains in memory and is never logged or placed in argv.
"""
import hashlib,time,threading
import requests
_local=threading.local()

def request(user,token,path,body=None,method=None):
    stamp=str(int(time.time()))
    digest=hashlib.sha256(f'{token}:{stamp}'.encode()).hexdigest()
    if not hasattr(_local,'session'):_local.session=requests.Session()
    try:
        response=_local.session.request(method or ('POST' if body is not None else 'GET'),
            'https://www.quantconnect.com/api/v2'+path,json=body,
            auth=(str(user),digest),headers={'Timestamp':stamp},timeout=(15,180))
        response.raise_for_status()
        data=response.json()
    except (requests.RequestException,ValueError) as exc:
        _local.session.close();del _local.session
        raise RuntimeError('QC transport '+path+' failed: '+type(exc).__name__) from None
    if not data.get('success'):raise RuntimeError('QC '+path+' errors: '+str(data.get('errors')))
    return data
