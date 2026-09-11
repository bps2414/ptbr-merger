import unittest,tempfile,json,os
from pathlib import Path
from unittest.mock import patch
import worker as w
from qbit import seed_complete
class WorkerTests(unittest.TestCase):
 def stream(self,language,title=''):return {'codec_type':'audio','tags':{'language':language,'title':title}}
 def test_brazilian_evidence(self):
  for title in ['Film.PT-BR.1080p','Film_ptbr_2025','Film.Dublado']:
   self.assertTrue(w.is_br(self.stream('por'),title),title)
  for title in ['Film.Dual.Audio','Film.Multi','Film.Portuguese','Film.PT-PT.Dublado']:
   self.assertFalse(w.is_br(self.stream('por'),title),title)
  self.assertFalse(w.is_br(self.stream('pt-PT'),'Film.Dublado'))
  self.assertFalse(w.is_br(self.stream('por','Português Europeu'),'Film.PT-BR'))
  self.assertTrue(w.is_br(self.stream('por','Português Brasileiro')))
 def test_common_language_not_only_english(self):
  self.assertIsNotNone(w.choose_common([self.stream('fre')],[self.stream('fra')]))
  self.assertIsNone(w.choose_common([self.stream('und')],[self.stream('und')]))
 def test_candidate_gate(self):
  r={'title':'Film.PT-BR.1080p','quality':{'quality':{'id':3}},'approved':True,'guid':'abc'}
  self.assertTrue(w.eligible(r,[]));self.assertFalse(w.eligible(r,['abc']))
  self.assertFalse(w.eligible(dict(r,title='Film.Dual.Audio'),[]))
  self.assertFalse(w.eligible(dict(r,rejected=True),[]))
 def test_seed_limits(self):
  t={'progress':1,'ratio_limit':-2,'seeding_time_limit':-2}
  self.assertFalse(seed_complete(t,{}))
  self.assertTrue(seed_complete(dict(t,ratio_limit=1,ratio=1),{}))
  self.assertFalse(seed_complete(dict(t,progress=.9,ratio_limit=1,ratio=2),{}))
  self.assertTrue(seed_complete(dict(t,seeding_time_limit=4320,seeding_time=4320*60),{}))
 def test_recover_before_and_after_replace(self):
  for replaced in [False,True]:
   with tempfile.TemporaryDirectory() as d:
    p=Path(d);src=p/'movie.mkv';bak=p/'backup';out=p/'out';bak.write_text('original');out.write_text('candidate')
    if replaced:os.replace(out,src)
    job={'transaction':{'original':str(src),'backup':str(bak),'final':str(src),'output':str(out),'committed':False}}
    w.recover(job);self.assertEqual(src.read_text(),'original');self.assertFalse(bak.exists())
 def test_recover_committed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);src=p/'movie.mkv';bak=p/'backup';src.write_text('validated');bak.write_text('old')
   job={'transaction':{'original':str(src),'backup':str(bak),'final':str(src),'output':str(p/'out'),'committed':True}}
   w.recover(job);self.assertEqual(src.read_text(),'validated');self.assertFalse(bak.exists())
 def test_commit_rollback(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);src=p/'movie.mkv';out=p/'out';src.write_text('original');out.write_text('new');job={};state={'movies':{'1':job}}
   original=os.replace
   def fail(a,b):
    if Path(a)==out:raise OSError('disk failure')
    return original(a,b)
   with patch.object(w,'STATE',p/'state.json'),patch.object(w.os,'replace',side_effect=fail):
    with self.assertRaises(OSError):w.commit(src,out,job,state)
   self.assertEqual(src.read_text(),'original')
 def test_state_corruption_is_not_reset(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state';p.write_text('{broken')
   with patch.object(w,'STATE',p):
    with self.assertRaises(json.JSONDecodeError):w.read_state()
 def test_main_hardlink_not_modified(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);src=p/'movie.mkv';download=p/'torrent.mkv';out=p/'out';src.write_text('original');os.link(src,download);out.write_text('new');job={};state={'movies':{'1':job}}
   with patch.object(w,'STATE',p/'state.json'):w.commit(src,out,job,state)
   self.assertEqual(src.read_text(),'new');self.assertEqual(download.read_text(),'original')
 def test_exit_zero_failed_verification_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   with patch.object(w,'command',return_value='[{"verification":{"passed":false}}]'):
    with self.assertRaises(w.CandidateError):w.redsync([],Path(d)/'report.json')
 def test_cleanup_preserves_unassociated_torrent(self):
  state={'cleanup':[{'key':'1','hash':None}]}
  with patch.object(w,'Qbit') as cls,patch.object(w,'api') as api:
   cls.return_value.call.side_effect=[{},[]]
   w.cleanup(state);api.assert_not_called();self.assertEqual(len(state['cleanup']),1)
 def test_cleanup_waits_for_seeding(self):
  state={'cleanup':[{'key':'1','hash':'abc'}]}
  with patch.object(w,'Qbit') as cls,patch.object(w,'api') as api:
   cls.return_value.call.side_effect=[{},[{'hash':'abc','category':'movies-ptbr','progress':1,'ratio_limit':1,'ratio':0.1}]]
   w.cleanup(state);api.assert_not_called();self.assertEqual(len(state['cleanup']),1)
 def test_cleanup_after_goal(self):
  state={'cleanup':[{'key':'1','hash':'abc','path':'/srv/data/donor/movies/Test/Test.mkv','movieId':12,'fileId':34}]}
  with tempfile.TemporaryDirectory() as d:
   with patch.object(w,'STATE',Path(d)/'state.json'),patch.object(w,'Qbit') as cls,patch.object(w,'api') as api:
    cls.return_value.call.side_effect=[{},[{'hash':'abc','category':'movies-ptbr','progress':1,'ratio_limit':1,'ratio':1,'content_path':'/data/downloads/torrents/Test.mkv'}],None]
    api.return_value={'movieFile':{'id':34}};w.cleanup(state)
    api.assert_any_call(w.DONOR,'moviefile/34','DELETE');self.assertFalse(state['cleanup'])
 def test_flexible_br_untagged_audio(self):
  stream_untagged={'codec_type':'audio','tags':{}}
  self.assertTrue(w.is_br(stream_untagged,'Toy.Story.5.2026.1080p.WEBRip.Dublado.mkv'))
  self.assertTrue(w.is_br(stream_untagged,'Film.2026.1080p [Brazilian]'))
  self.assertFalse(w.is_br(stream_untagged,'Film.2026.1080p.Dual.Audio'))
  self.assertFalse(w.is_br(stream_untagged,'Film.2026.1080p.English'))
 def test_choose_common_prefers_lightweight(self):
  s_truehd={'codec_name':'truehd','channels':8,'tags':{'language':'eng'}}
  s_ac3={'codec_name':'ac3','channels':6,'tags':{'language':'eng'}}
  donor_ac3={'codec_name':'ac3','channels':6,'tags':{'language':'eng'}}
  pair=w.choose_common([s_truehd,s_ac3],[donor_ac3])
  self.assertIsNotNone(pair)
  self.assertEqual(pair[0]['codec_name'],'ac3')
 def test_video_hash_duration_flag(self):
  with patch.object(w,'command',return_value='test_hash') as mock_cmd:
   h=w.video_hash('/path/to/vid.mkv',duration=30)
   self.assertEqual(h,'test_hash')
   self.assertIn('-t',mock_cmd.call_args[0][0])
 def test_cleanup_immediate(self):
  state={'cleanup':[{'key':'1','hash':'abc','path':'/srv/data/donor/movies/Test/Test.mkv','movieId':1,'fileId':2,'immediate':True}]}
  with tempfile.TemporaryDirectory() as d:
   with patch.object(w,'STATE',Path(d)/'state.json'),patch.object(w,'Qbit') as cls,patch.object(w,'api') as api:
    cls.return_value.call.side_effect=[{},[{'hash':'abc','category':'movies-ptbr','progress':1,'ratio_limit':1,'ratio':0.1,'content_path':'/data/downloads/torrents/Test.mkv'}],None]
    api.return_value={'movieFile':{'id':2}}
    w.cleanup(state)
    cls.return_value.call.assert_any_call('torrents/delete',{'hashes':'abc','deleteFiles':'true'},raw=True)
    self.assertFalse(state['cleanup'])
 def test_non_pt_title_filtering(self):
  self.assertTrue(w.is_non_pt_title('Moana.2026.1080p.AMZN.WEB-DL.MULTi.LATINO.DDP5.1.H264.MP4-BTM'))
  self.assertTrue(w.is_non_pt_title('Film.2026.1080p.French.Multi'))
  self.assertFalse(w.is_non_pt_title('Film.2026.1080p.Dual.Audio'))
  self.assertFalse(w.is_non_pt_title('Film.2026.1080p.Multi.PT-BR'))
  r_latino = {'title': 'Moana.2026.1080p.AMZN.WEB-DL.MULTi.LATINO.DDP5.1.H264.MP4-BTM', 'quality': {'quality': {'id': 3}}, 'seeders': 10}
  self.assertFalse(w.eligible_tier2(r_latino, []))
 def test_pivot_4k_native_dual(self):
  m = {'id': 1, 'title': 'Test Movie', 'tmdbId': 100}
  job = {}
  state = {'movies': {'100': job}}
  rel_native = {'title': 'Test Movie 2026 2160p WEB-DL Dual Audio', 'quality': {'quality': {'id': 18}}, 'seeders': 10, 'customFormatScore': 10000, 'size': 10*1024**3, 'guid': 'g1'}
  rel_other = {'title': 'Test Movie 2026 2160p DSNP WEB-DL', 'quality': {'quality': {'id': 18}}, 'seeders': 50, 'customFormatScore': 0, 'size': 12*1024**3, 'guid': 'g2'}
  with patch.object(w, 'api') as mock_api:
   mock_api.side_effect = [{'records': []}, [rel_other, rel_native], None]
   res = w.attempt_4k_pivot(m, job, state, dry=False)
   self.assertTrue(res)
   self.assertEqual(job.get('status'), 'downloading_pivoted_4k')
   self.assertEqual(job.get('pivoted_4k_candidate', {}).get('title'), rel_native['title'])
 def test_pivot_4k_matches_donor_source(self):
  m = {'id': 1, 'title': 'Test Movie', 'tmdbId': 100}
  job = {}
  state = {'movies': {'100': job}}
  rel_amzn = {'title': 'Test Movie 2026 2160p AMZN WEB-DL', 'quality': {'quality': {'id': 18}}, 'seeders': 20, 'customFormatScore': 0, 'size': 10*1024**3, 'guid': 'g1'}
  rel_other = {'title': 'Test Movie 2026 2160p DSNP WEB-DL', 'quality': {'quality': {'id': 18}}, 'seeders': 50, 'customFormatScore': 0, 'size': 12*1024**3, 'guid': 'g2'}
  with patch.object(w, 'api') as mock_api:
   mock_api.side_effect = [{'records': []}, [rel_other, rel_amzn], None]
   res = w.attempt_4k_pivot(m, job, state, dry=False, last_donor_title='Test Movie 2026 1080p AMZN Dublado')
   self.assertTrue(res)
   self.assertEqual(job.get('pivoted_4k_candidate', {}).get('title'), rel_amzn['title'])
 def test_pivot_4k_no_candidates_returns_false(self):
  m = {'id': 1, 'title': 'Test Movie', 'tmdbId': 100}
  job = {}
  state = {'movies': {'100': job}}
  with patch.object(w, 'api') as mock_api:
   mock_api.side_effect = [{'records': []}, []]
   res = w.attempt_4k_pivot(m, job, state, dry=False)
   self.assertFalse(res)
if __name__=='__main__':unittest.main()
