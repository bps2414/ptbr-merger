import urllib.request,urllib.parse,http.cookiejar,json,shlex
from pathlib import Path
class Qbit:
 def __init__(self):
  import sqlite3
  c=sqlite3.connect('file:/srv/appdata/radarr-ptbr/radarr.db?mode=ro',uri=True)
  settings=json.loads(c.execute('SELECT Settings FROM DownloadClients WHERE Implementation="QBittorrent" LIMIT 1').fetchone()[0]);c.close()
  self.url='http://127.0.0.1:8080'
  self.headers={'Referer':self.url,'Authorization':'Bearer '+settings['apiKey']}
  self.opener=urllib.request.build_opener()
 def call(self,ep,data=None,raw=False):
  req=urllib.request.Request(self.url+'/api/v2/'+ep,data=urllib.parse.urlencode(data).encode() if data is not None else None,headers=self.headers)
  with self.opener.open(req,timeout=30) as r:b=r.read().decode()
  return b if raw or not b else json.loads(b)
def seed_complete(t,p):
 if t.get('progress',0)<1:return False
 ratio=t.get('ratio_limit',-2);minutes=t.get('seeding_time_limit',-2)
 if ratio==-2:ratio=p.get('max_ratio',-1) if p.get('max_ratio_enabled') else -1
 if minutes==-2:minutes=p.get('max_seeding_time',-1) if p.get('max_seeding_time_enabled') else -1
 checks=[]
 if ratio>=0:checks.append(t.get('ratio',0)>=ratio)
 if minutes>=0:checks.append(t.get('seeding_time',0)>=minutes*60)
 # No configured limit means keep seeding; never interpret pause as completion.
 return bool(checks) and all(checks)
if __name__=='__main__':
 q=Qbit();p=q.call('app/preferences');print('limits',{k:v for k,v in p.items() if any(w in k.lower() for w in ['ratio','seed','action'])})
 for t in q.call('torrents/info'):print({k:t.get(k) for k in ['name','hash','category','state','progress','ratio','ratio_limit','seeding_time_limit','seeding_time','content_path']})
