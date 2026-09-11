from pathlib import Path
from worker import *
p=BASE/'test-artifacts';ref=p/'reference.wav';shift=p/'shift.wav'
print('Creating synthetic UHD + dual-audio donor',flush=True)
command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:s=3840x2160:r=1:d=180','-i',ref,'-map','0:v','-map','1:a','-c:v','libx264','-threads','2','-preset','ultrafast','-crf','40','-c:a','flac','-metadata:s:a:0','language=eng',p/'main.mkv'])
command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=1280x720:r=1:d=181.25','-i',shift,'-map','0:v','-map','1:a','-map','1:a','-c:v','libx264','-threads','2','-preset','ultrafast','-crf','40','-c:a','flac','-metadata:s:a:0','language=eng','-metadata:s:a:1','language=por','-metadata:s:a:1','title=Português Brasileiro',p/'donor.mkv'])
print('Testing complete reference alignment, sibling timeline and remux',flush=True)
out=sync_files(p/'main.mkv',p/'donor.mkv','PT-BR',p/'mux-work')
print('VALIDATED',out,'video hash preserved, Brazilian audio default',flush=True)
