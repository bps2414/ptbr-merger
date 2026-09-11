"""Real HEVC regression: remux must preserve the encoded video payload."""
import tempfile, unittest, subprocess
from pathlib import Path
import worker as w

class HevcRemuxTest(unittest.TestCase):
 def test_normalize_preserves_hevc_payload(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'source.mkv'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=128x72:rate=5','-f','lavfi','-i','sine=frequency=440','-t','1','-c:v','libx265','-x265-params','pools=1:log-level=error','-c:a','aac','-metadata:s:a:0','language=por',str(src)],check=True,capture_output=True)
   # Exercise production remux arguments and its exact payload comparison.
   # This tiny fixture is intentionally below 4K; all other checks remain real.
   from unittest.mock import patch
   with patch.object(w,'is4k',return_value=True):
    out=w.normalize_existing(src,w.audio(w.probe(src))[0])
   self.assertEqual(w.video_hash(src),w.video_hash(out))
   self.assertTrue(w.is_br(w.audio(w.probe(out))[0]))

if __name__=='__main__': unittest.main()
