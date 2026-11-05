from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse,unquote
import json,hashlib
root=Path('/mnt/c/Users/victo/.codex/sites/ss45dte-manual-guide/dist')
class Page(HTMLParser):
 def __init__(self,text):
  super().__init__();self.ids=set();self.links=[];self.feed(text)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.add(a['id'])
  for k in ['href','src']:
   if k in a:self.links.append(a[k])
pages={p:Page(p.read_text()) for p in root.glob('*.html')};bad=[]
for p,doc in pages.items():
 for link in doc.links:
  u=urlparse(link)
  if u.scheme or u.netloc:continue
  target=(p.parent/unquote(u.path)).resolve() if u.path else p
  if not target.exists():bad.append((p.name,link,'missing file'))
  elif u.fragment and target in pages and unquote(u.fragment) not in pages[target].ids:bad.append((p.name,link,'missing fragment'))
assert not bad,bad
proof=json.loads((root/'review_evidence_20261026.json').read_text())
for short,filename in [('FIVE_DAILYIV_V1','current_control.py.txt'),('FIXED_PILOT_V2','current_pilot.py.txt')]:
 assert hashlib.sha256((root/filename).read_bytes()).hexdigest()==proof['runs'][short]['source_sha256']
assert all(r['reconciliation']['reconciled'] for r in proof['runs'].values())
print(f'{len(pages)} HTML pages: local files/fragments valid; published source hashes match QC; all {len(proof["runs"])} fill ledgers reconcile.')
