import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_runtime
from test_video_studio import _silence
from ali import creative_video as studio, studio_audio, outbox
from ali.config import config
from ali.plugins import video_studio
from fastapi.testclient import TestClient
from runtime import app

JOB='b'*32

class StudioAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch.object(config,'data_dir',self.root),patch.dict(studio._jobs,{},clear=True)]
        for p in self.patches:p.start()
        studio._jobs[JOB]={'id':JOB,'status':'ready','story':{'scenes':[{'voice':'Salom','speaker':'Hikoyachi'}]}}

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def test_wav_is_validated_persisted_and_required_before_render(self):
        with self.assertRaises(ValueError):studio.start_render(JOB,{'Hikoyachi':'aistudio'})
        with self.assertRaises(ValueError):studio_audio.save(JOB,1,b'not WAV')
        with self.assertRaises(ValueError):studio_audio.save(JOB,1,_silence()[:-20])
        with self.assertRaises(ValueError):studio_audio.save(JOB,2,_silence())
        job=studio_audio.save(JOB,1,_silence())
        self.assertEqual(job['voices']['Hikoyachi'],'aistudio')
        self.assertEqual(job['scene_audio']['1']['duration'],.5)
        studio._jobs.clear()
        self.assertTrue(studio_audio.path(JOB,1).is_file())
        with patch.object(studio.threading,'Thread'):
            studio.start_render(JOB,{'Hikoyachi':'aistudio'})
        with self.assertRaises(ValueError):studio_audio.save(JOB,1,_silence())

    def test_upload_routes_require_auth_and_same_origin(self):
        client=TestClient(app)
        url=f'/api/creative-video/{JOB}/audio/1'
        self.assertEqual(client.post(url,files={'file':('a.wav',_silence())}).status_code,401)
        with patch('runtime.is_authed',return_value=True),patch('runtime.foreign_origin',return_value=True):
            self.assertEqual(client.post(url,files={'file':('a.wav',_silence())}).status_code,403)
        with patch('runtime.is_authed',return_value=True),patch('runtime.foreign_origin',return_value=False):
            self.assertEqual(client.post(url,files={'file':('a.wav',_silence())}).status_code,200)
            self.assertEqual(client.get(url).content,_silence())
            r=client.post(f'/api/creative-video/{JOB}/preview',json={'speaker':'Hikoyachi','voice':'aistudio'})
            self.assertEqual(r.content,_silence())

    def test_imported_audio_renders_without_any_tts_and_preserves_original(self):
        source=self.root/'original.wav';source.write_bytes(_silence(21))
        with patch.object(outbox,'DIR',self.root/'outbox'),patch.object(video_studio,'FORMATS',{'9:16':(96,160)}),patch.object(video_studio,'FPS',2),patch.object(video_studio,'_tts',side_effect=AssertionError('API must not run')) as tts:
            result=video_studio.make_content_video(topic='Test',scenes=[{'title':'Salom','narration':'Salom','duration':2}],ai_images=False,_scene_audio=[source],_voice_cast={'Hikoyachi':'aistudio'})
        tts.assert_not_called()
        self.assertIn('ovozli',result)
        self.assertTrue(source.is_file())
        self.assertGreater(video_studio._audio_seconds(next((self.root/'outbox').glob('*.mp4'))),21)

if __name__=='__main__':unittest.main()
