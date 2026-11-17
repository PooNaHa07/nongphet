# -*- coding: utf-8 -*-
"""
tests/test_voice_server.py — โหมดเสียงน้องเพชร OmniVoice (เซิร์ฟเวอร์เสียงบนโน้ตบุ๊กในบูธ)
จำลองเซิร์ฟเวอร์และโมเดลทั้งหมด ไม่ต้องใช้ GPU หรือดาวน์โหลดโมเดล
"""
import os
import sys
import time
import asyncio
import hashlib
import shutil
import tempfile
import unittest
from unittest import mock

import httpx
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from services import tts_service, voice_server_client as vsc
import prebake_tts
import voice_server

CANONICAL_MP3 = bytes([0xFF, 0xF3, 0x64, 0xC0]) + b'V' * 200   # MP3 MPEG2 24kHz 48kbps mono
OMNI_ENV = {'TTS_ENGINE': 'omnivoice', 'VOICE_SERVER_URL': 'http://booth-laptop:8010',
            'VOICE_SERVER_TOKEN': 'booth-secret', 'VOICE_ID': 'nongphet-omni-test'}


class OmniCase(unittest.TestCase):
    def setUp(self):
        mock.patch.dict(os.environ, OMNI_ENV).start()
        vsc._state.update(offline_until=0.0, last_error=None, last_ms=None)
        tts_service._mark_edge_ok()
        self.requests = []
        self.edge = mock.patch.object(tts_service, 'generate_edge_tts').start()

    def tearDown(self):
        mock.patch.stopall()
        vsc._state.update(offline_until=0.0, last_error=None, last_ms=None)

    def server_replies(self, *responses):
        responses = list(responses)

        def handler(request):
            self.requests.append(request)
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        real = httpx.AsyncClient
        mock.patch.object(vsc.httpx, 'AsyncClient',
                          lambda **kw: real(transport=httpx.MockTransport(handler), **kw)).start()


class TestOmniVoiceMode(OmniCase):
    def test_one_voice_for_every_language(self):
        for lang in ('th', 'en', 'zh'):
            self.assertEqual(tts_service.voice_profile(lang), ('nongphet-omni-test', '+0Hz', '+0%'))

    def test_uses_booth_server_and_never_edge(self):
        self.server_replies(httpx.Response(200, content=CANONICAL_MP3, headers={'X-Synthesis-Ms': '850'}))
        audio = asyncio.run(tts_service.generate_speech('สวัสดีค่ะ'))
        self.assertEqual(audio, CANONICAL_MP3)
        self.edge.assert_not_called()
        req = self.requests[0]
        self.assertEqual(str(req.url), 'http://booth-laptop:8010/synthesize')
        self.assertEqual(req.headers['X-Voice-Token'], 'booth-secret')
        self.assertEqual(vsc.voice_server_status()['last_synthesis_ms'], 850)

    def test_server_down_does_not_fall_back_to_other_voice(self):
        self.server_replies(httpx.ConnectError('no route to host'))
        with self.assertRaises(tts_service.VoiceUnavailable):
            asyncio.run(tts_service.generate_speech('สวัสดีค่ะ'))
        self.edge.assert_not_called()
        # พักการเรียกชั่วคราว: คำขอถัดไปไม่ยิงซ้ำ
        with self.assertRaises(tts_service.VoiceUnavailable):
            asyncio.run(tts_service.generate_speech('อีกประโยค'))
        self.assertEqual(len(self.requests), 1)

    def test_wrong_format_rejected(self):
        self.server_replies(httpx.Response(200, content=b'RIFF' + bytes(100)))
        with self.assertRaises(tts_service.VoiceUnavailable):
            asyncio.run(tts_service.generate_speech('สวัสดีค่ะ'))

    def test_wrong_token_reported(self):
        self.server_replies(httpx.Response(403))
        with self.assertRaises(tts_service.VoiceUnavailable):
            asyncio.run(tts_service.generate_speech('สวัสดีค่ะ'))
        self.assertIn('VOICE_SERVER_TOKEN', vsc.voice_server_status()['last_error'])

    def test_status_endpoint(self):
        from app_new import app
        data = app.test_client().get('/api/tts/status').get_json()
        self.assertEqual(data['primary_engine'], 'omnivoice')
        self.assertEqual(data['voice_server']['voice_id'], 'nongphet-omni-test')
        self.assertNotIn('booth-secret', str(data))


class TestFallbackPhrase(OmniCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        mock.patch.object(tts_service, 'AUDIO_CACHE_DIR', self.tmp).start()
        tts_service.TTS_CACHE.clear()
        self.server_replies(*[httpx.ConnectError('down')] * 3)
        from app_new import app
        app.config['TESTING'] = True
        self.client = app.test_client()

    def tearDown(self):
        tts_service.TTS_CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def bake_fallback(self):
        lang, label, text = next(i for i in prebake_tts.collect_items() if i[1] == 'no-voice' and i[0] == 'th')
        _, key, *_ = prebake_tts.plan_item(lang, text)
        tts_service.save_cached_tts(key, CANONICAL_MP3)
        tts_service.TTS_CACHE.clear()

    def test_unbaked_answer_speaks_fallback_phrase(self):
        self.bake_fallback()
        res = self.client.post('/tts', json={'text': 'คำถามที่ไม่มีเสียงอัดไว้แน่นอน %f' % time.time()})
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(data['engine'], 'fallback-phrase')
        self.assertTrue(data['fallback'])
        self.assertEqual(data['spoken_text'], tts_service.NO_VOICE_PHRASES['th'])

    def test_no_fallback_baked_returns_503(self):
        res = self.client.post('/tts', json={'text': 'ไม่มีเสียงเลย %f' % time.time()})
        self.assertEqual(res.status_code, 503)

    def test_prebake_always_includes_fallback_phrases(self):
        labels = [(lang, label) for lang, label, _ in prebake_tts.collect_items() if label == 'no-voice']
        self.assertEqual(sorted(lang for lang, _ in labels), ['en', 'th', 'zh'])

    def test_bake_in_background_stores_voice(self):
        async def fake_speech(*a, **k):
            return CANONICAL_MP3
        with mock.patch.object(tts_service, 'generate_speech', side_effect=fake_speech):
            t = tts_service.bake_text_in_background('คำตอบใหม่จากการเรียนรู้ซ้ำค่ะ')
            t.join(5)
        self.assertEqual(len(os.listdir(self.tmp)), 1)


class FakeBackend:
    model_id = 'fake/omnivoice'
    device = 'cpu'
    steps = 16
    model = object()

    def __init__(self):
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        return np.zeros(2400, dtype=np.float32)


class TestVoiceServerApp(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        mock.patch.object(voice_server, 'encode_mp3', return_value=CANONICAL_MP3).start()
        self.client = voice_server.create_app(self.backend, token='booth-secret').test_client()

    def tearDown(self):
        mock.patch.stopall()

    def test_health(self):
        data = self.client.get('/health').get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['model'], 'fake/omnivoice')

    def test_requires_token(self):
        self.assertEqual(self.client.post('/synthesize', json={'text': 'สวัสดี'}).status_code, 403)
        res = self.client.post('/synthesize', json={'text': 'สวัสดี'}, headers={'X-Voice-Token': 'wrong'})
        self.assertEqual(res.status_code, 403)

    def test_synthesize_returns_mp3(self):
        res = self.client.post('/synthesize', json={'text': 'สวัสดีค่ะ'}, headers={'X-Voice-Token': 'booth-secret'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, 'audio/mpeg')
        self.assertEqual(res.data, CANONICAL_MP3)
        self.assertEqual(self.backend.texts, ['สวัสดีค่ะ'])
        self.assertIn('X-Synthesis-Ms', res.headers)

    def test_rejects_empty_and_too_long(self):
        h = {'X-Voice-Token': 'booth-secret'}
        self.assertEqual(self.client.post('/synthesize', json={'text': ' '}, headers=h).status_code, 400)
        long_text = 'ก' * (voice_server.MAX_TEXT_CHARS + 1)
        self.assertEqual(self.client.post('/synthesize', json={'text': long_text}, headers=h).status_code, 413)

    @unittest.skipUnless(__import__('importlib').util.find_spec('lameenc'), 'lameenc not installed')
    def test_encoder_produces_cache_format(self):
        mock.patch.stopall()
        mp3 = voice_server.encode_mp3(np.zeros(24000, dtype=np.float32))
        self.assertTrue(tts_service.is_canonical_voice_audio(mp3))


if __name__ == '__main__':
    unittest.main()
