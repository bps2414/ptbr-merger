import unittest
from worker import stalled_reason
class PeerTests(unittest.TestCase):
 def torrent(self,**kw):
  t=dict(hash='abc',category='movies-ptbr',progress=0,downloaded=0,added_on=100,state='metaDL',num_seeds=0,num_leechs=0,dlspeed=0);t.update(kw);return t
 def test_metadata(self):
  self.assertIsNone(stalled_reason(self.torrent(),{},1899))
  self.assertIsNotNone(stalled_reason(self.torrent(),{},1900))
 def test_progress_resets(self):
  j=dict(progress_hash='abc',progress_bytes=0,progress_since=0)
  self.assertIsNone(stalled_reason(self.torrent(state='stalledDL',downloaded=10),j,8000))
 def test_stalled(self):
  j=dict(progress_hash='abc',progress_bytes=0,progress_since=100)
  self.assertIsNotNone(stalled_reason(self.torrent(state='stalledDL'),j,7300))
 def test_protect_active_complete_paused_main(self):
  for changes in [dict(dlspeed=1),dict(progress=1),dict(state='stoppedDL'),dict(category='movies')]:
   self.assertIsNone(stalled_reason(self.torrent(**changes),{},99999))
 def test_connected_grace(self):
  self.assertIsNone(stalled_reason(self.torrent(num_leechs=1),{},2000))
if __name__=='__main__':unittest.main()
