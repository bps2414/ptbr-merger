from common import *
import copy
BR=r'(?i)(?<![a-z0-9])(?:pt[ ._-]?br|por[ ._-]?br|portugu[eê]s[ ._-]?(?:br|brasil|brasileiro)|brazilian(?:[ ._-]?portuguese)?|portuguese[ ._-]?(?:br|brazil)|dublado)(?![a-z0-9])'
PT=r'(?i)(?<![a-z0-9])(?:pt[ ._-]?pt|portugal|portugu[eê]s[ ._-]?(?:europeu|portugal)|european[ ._-]?portuguese)(?![a-z0-9])'
DUAL=r'(?i)(?<![a-z0-9])(?:dual(?:[ ._-]?audio)?|multi(?:[ ._-]?(?:audio|lang))?)(?![a-z0-9])'
def spec(name,regex,negate=False):return {'name':name,'implementation':'ReleaseTitleSpecification','negate':negate,'required':True,'fields':[{'name':'value','value':regex}]}
def upcf(n,name,specs,existing=None):
 rows=api(n,'customformat');x=next((r for r in rows if r['name']==name),None)
 if x is None and existing:x=next((r for r in rows if r['id']==existing),None)
 payload={'name':name,'includeCustomFormatWhenRenaming':False,'specifications':specs}
 if x:payload['id']=x['id'];return api(n,f'customformat/{x["id"]}','PUT',payload)['id']
 return api(n,'customformat','POST',payload)['id']
def flatten(items):
 for x in items:
  if x.get('items'):yield from flatten(x['items'])
  else:yield copy.deepcopy(x)
def configure(n,donor=False):
 br=upcf(n,'PT-BR',[spec('Brazilian',BR),spec('Not European',PT,True)],1)
 dual=upcf(n,'Dual Audio',[spec('Dual or multi (not language proof)',DUAL)],2 if not donor else None)
 bad=upcf(n,'PT-PT',[spec('European Portuguese',PT)],3 if not donor else None)
 web=upcf(n,'WEB-DL preference',[spec('WEB-DL',r'(?i)web[ ._-]?dl')])
 target_name='720p-1080p PT-BR Donor' if donor else '4K PT-BR'
 p=next((x for x in api(n,'qualityprofile') if x['name']==target_name),None) or api(n,'qualityprofile/7')
 p.update(name=target_name,language={'id':-1,'name':'Any'},upgradeAllowed=not donor,minFormatScore=10000 if donor else 0,cutoffFormatScore=10000,minUpgradeFormatScore=1,cutoff=1000)
 leaves=list(flatten(p['items']));allow={5,14,6,3,15,7} if donor else {18,17,19}
 selected=[];disabled=[]
 for x in leaves:
  x['allowed']=x['quality']['id'] in allow
  (selected if x['allowed'] else disabled).append(x)
 p['items']=disabled+[{'id':1000,'name':'Donor 720p-1080p' if donor else '4K WEB + Blu-ray','items':selected,'allowed':True}]
 scores={br:10000,dual:100,bad:-20000,web:50}
 p['formatItems']=[{'format':c['id'],'name':c['name'],'score':scores.get(c['id'],0)} for c in api(n,'customformat')]
 api(n,'qualityprofile/7','PUT',p)
 if not donor:
  locked=next((x for x in api(n,'qualityprofile') if x['name']=='4K PT-BR Concluído'),None)
  q=copy.deepcopy(p);q.update(name='4K PT-BR Concluído',upgradeAllowed=False)
  if locked:q['id']=locked['id'];api(n,f'qualityprofile/{q["id"]}','PUT',q)
  else:q.pop('id',None);api(n,'qualityprofile','POST',q)
 # MB/min: deliberately broad enough to retain small legacy releases; cap outliers.
 for q in api(n,'qualitydefinition'):
  if q['quality']['id'] in allow:
   q.update(minSize=2 if donor else 15,maxSize=100 if donor else 350,preferredSize=30 if donor else 180)
   api(n,f'qualitydefinition/{q["id"]}','PUT',q)
 mm=api(n,'config/mediamanagement');mm.update(downloadPropersAndRepacks='doNotUpgrade',minimumFreeSpaceWhenImporting=2048,copyUsingHardlinks=True,enableMediaInfo=True,importExtraFiles=True,extraFileExtensions='srt,ass,ssa')
 api(n,'config/mediamanagement','PUT',mm)
 naming=api(n,'config/naming');naming.update(renameMovies=True,standardMovieFormat='{Movie Title} ({Release Year}) {[Quality Full]}{[MediaInfo VideoDynamicRangeType]}{[MediaInfo AudioLanguages]}{-Release Group}')
 api(n,'config/naming','PUT',naming)
 if donor:
  for lst in api(n,'importlist'):
   if lst['implementation']=='RadarrImport':
    lst['enableAuto']=False;lst['searchOnAdd']=False;api(n,f'importlist/{lst["id"]}','PUT',lst)
  for dc in api(n,'downloadclient'):
   dc['removeCompletedDownloads']=False;api(n,f'downloadclient/{dc["id"]}','PUT',dc)
  # Stop RSS grabs until the worker has checked the actual 4K file.
  for m in api(n,'movie'):
   if m['monitored']:m['monitored']=False;api(n,f'movie/{m["id"]}','PUT',m)
 print(n,'configured')
if __name__=='__main__':
 configure('radarr');configure('radarr-ptbr',True)
