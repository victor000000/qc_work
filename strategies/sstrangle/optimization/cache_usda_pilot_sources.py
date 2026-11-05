"""Cache seven official dated forward calendars for descriptive research only."""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import argparse,hashlib,json,urllib.request

HERE=Path(__file__).resolve().parent
ROWS=[('2014-12-10',2014,'12_10_2014.pdf',10),('2015-06-10',2015,'06_10_2015.pdf',17),('2015-07-10',2015,'07_10_2015.pdf',19),('2016-06-10',2016,'06_10_2016.pdf',14),('2019-05-10',2019,'05-10-2019.pdf',18),('2019-06-11',2019,'06-11-2019.pdf',12),('2019-07-11',2019,'07-11-2019.pdf',23)]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--proxy');args=parser.parse_args()
    out=HERE/'usda_event_pilot_20261019';sources=out/'sources';sources.mkdir(parents=True,exist_ok=True)
    old_path=out/'source_manifest.json';old={r['url']:r for r in json.loads(old_path.read_text())} if old_path.exists() else {}
    def fetch(row):
        day,year,name,page=row;url=f'https://data.nass.usda.gov/Newsroom/Executive_Briefings/{year}/{name}';path=sources/(str(year)+'_'+name)
        identity=dict(document_date=day,url=url,file=str(path),upcoming_page_zero_based=page)
        now=datetime.now(timezone.utc).isoformat()
        try:
            if path.exists():
                data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
                if url in old:
                    if digest!=old[url]['sha256']:raise ValueError('Existing cached official source changed')
                    return dict(old[url],cached=True,observed_utc=now,success=True)
                retrieved=None;headers={};cached=True
            else:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({'https':args.proxy,'http':args.proxy})) if args.proxy else urllib.request.build_opener()
                req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (research document cache)'})
                with opener.open(req,timeout=30) as response:
                    data=response.read();headers={k:response.headers.get(k) for k in ('Content-Type','Last-Modified','ETag')}
                if not data.startswith(b'%PDF-'):raise ValueError('Official source returned a non-PDF payload')
                path.write_bytes(data);retrieved=now;cached=False
            return dict(identity,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),http_headers=headers,cached=cached,
                retrieved_utc=retrieved,observed_utc=now,success=True,
                provenance='Official dated briefing with forward Upcoming Reports table; original publication timestamp/archive revision history not independently pinned')
        except Exception as exc:return dict(identity,success=False,error=type(exc).__name__+': '+str(exc),observed_utc=now)
    with ThreadPoolExecutor(max_workers=4) as pool:records=list(pool.map(fetch,ROWS))
    attempt=dict(utc=datetime.now(timezone.utc).isoformat(),route='explicit local proxy' if args.proxy else 'direct',records=records)
    with (out/'cache_attempts.jsonl').open('a') as f:f.write(json.dumps(attempt)+'\n')
    successes=[r for r in records if r['success']]
    old_path.write_text(json.dumps(successes,indent=2)+'\n')
    print(json.dumps(dict(successes=len(successes),failed=[r for r in records if not r['success']]),indent=2))
    if len(successes)!=len(ROWS):raise SystemExit(1)


if __name__=='__main__':main()
