import json, urllib.request, urllib.error, xml.etree.ElementTree as ET
from pathlib import Path
PORTS={'radarr':7878,'radarr-ptbr':7879,'prowlarr':9696}
def api(name,ep,method='GET',data=None,timeout=60):
 key=ET.parse(f'/srv/appdata/{name}/config.xml').findtext('ApiKey')
 ver='v1' if name=='prowlarr' else 'v3'
 req=urllib.request.Request(f'http://127.0.0.1:{PORTS[name]}/api/{ver}/{ep}',data=json.dumps(data).encode() if data is not None else None,headers={'X-Api-Key':key,'Content-Type':'application/json'},method=method)
 try:
  with urllib.request.urlopen(req,timeout=timeout) as r:
   b=r.read();return json.loads(b) if b else None
 except urllib.error.HTTPError as e:
  raise RuntimeError(f'{name} {method} {ep}: {e.code} {e.read().decode()[:1200]}') from None
def fields(obj):return {f['name']:f.get('value') for f in obj.get('fields',[])}
def setfield(obj,name,value):
 for f in obj['fields']:
  if f['name']==name:f['value']=value;return
 obj['fields'].append({'name':name,'value':value})
