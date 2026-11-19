# -*- coding: utf-8 -*-
"""
tests/test_stt.py — ถอดเสียงพูดด้วย Whisper บนเซิร์ฟเวอร์เสียงในบูธ (แทน Web Speech ที่ใช้ไม่ได้บน Pi)
จำลองโมเดลและเครือข่ายทั้งหมด ไม่ต้องใช้ GPU
"""
import io
import os
import sys
import wave
import unittest
from unittest import mock

import httpx
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import voice_server
from services import voice_server_client as vsc


def make_wav(seconds=1.0, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.sin(np.linspace(0, 200, int(rate * seconds))) * 8000).astype('<i2').tobytes())
    return buf.getvalue()


class FakeStt:
    model_id = 'fake/whisper-th'
    model = object()

    def __init__(self):
        self.calls = []

    def transcribe(self, samples, lang='th'):
        self.calls.append((len(samples), lang))
        return 'เขาวังเปิดกี่โมง'


class FakeTts:
    model_id, device, steps, seed = 'fake/omnivoice', 'cpu', 32, 7
    model = object()


class TestVoiceServerTranscribe(unittest.TestCase):
    def setUp(self):
        self.stt = FakeStt()
        self.client = voice_server.create_app(FakeTts(), token='secret', stt=self.stt).test_client()
        self.h = {'X-Voice-Token': 'secret', 'Content-Type': 'audio/wav'}

    def test_transcribes_wav(self):
        res = self.client.post('/transcribe?lang=th', data=make_wav(1.0), headers=self.h)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['text'], 'เขาวังเปิดกี่โมง')
        self.assertEqual(self.stt.calls, [(16000, 'th')])

    def test_resamples_other_rates_to_16k(self):
        self.client.post('/transcribe', data=make_wav(1.0, rate=48000), headers=self.h)
        self.assertEqual(self.stt.calls[0][0], 16000)

    def test_requires_token_and_audio(self):
        self.assertEqual(self.client.post('/transcribe', data=make_wav()).status_code, 403)
        self.assertEqual(self.client.post('/transcribe', data=b'', headers=self.h).status_code, 400)
        self.assertEqual(self.client.post('/transcribe', data=b'not a wav', headers=self.h).status_code, 400)

    def test_rejects_too_long(self):
        res = self.client.post('/transcribe', data=make_wav(voice_server.MAX_STT_SECONDS + 1), headers=self.h)
        self.assertEqual(res.status_code, 413)

    def test_health_reports_stt(self):
        data = self.client.get('/health').get_json()
        self.assertTrue(data['stt'])
        self.assertEqual(data['stt_model'], 'fake/whisper-th')

    def test_disabled_stt_returns_503(self):
        client = voice_server.create_app(FakeTts(), token='secret', stt=None).test_client()
        self.assertEqual(client.post('/transcribe', data=make_wav(), headers=self.h).status_code, 503)
        self.assertFalse(client.get('/health').get_json()['stt'])


class TestAppSttRoute(unittest.TestCase):
    def setUp(self):
        mock.patch.dict(os.environ, {'VOICE_SERVER_URL': 'http://booth:8010', 'VOICE_SERVER_TOKEN': 'secret'}).start()
        vsc._stt_state.update(available=None, checked_at=0.0, last_error=None)
        from app_new import app
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.requests = []

    def tearDown(self):
        mock.patch.stopall()
        vsc._stt_state.update(available=None, checked_at=0.0, last_error=None)

    def fake_http(self, response):
        def handler(request):
            self.requests.append(request)
            if isinstance(response, Exception):
                raise response
            return response
        transport = httpx.MockTransport(handler)
        real_post, real_get = httpx.post, httpx.get
        mock.patch.object(vsc.httpx, 'post', lambda *a, **k: httpx.Client(transport=transport).post(*a, **k)).start()
        mock.patch.object(vsc.httpx, 'get', lambda *a, **k: httpx.Client(transport=transport).get(*a, **k)).start()

    def test_forwards_audio_with_token(self):
        self.fake_http(httpx.Response(200, json={'text': 'สวัสดีค่ะ', 'ms': 900}))
        res = self.client.post('/api/stt?lang=th', data=make_wav(), headers={'Content-Type': 'audio/wav'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['text'], 'สวัสดีค่ะ')
        req = self.requests[0]
        self.assertEqual(str(req.url), 'http://booth:8010/transcribe?lang=th')
        self.assertEqual(req.headers['X-Voice-Token'], 'secret')

    def test_voice_server_down_returns_503(self):
        self.fake_http(httpx.ConnectError('down'))
        res = self.client.post('/api/stt', data=make_wav(), headers={'Content-Type': 'audio/wav'})
        self.assertEqual(res.status_code, 503)
        self.assertFalse(self.client.get('/api/stt/status').get_json()['available'])

    def test_status_reads_health(self):
        self.fake_http(httpx.Response(200, json={'ok': True, 'stt': True}))
        self.assertTrue(self.client.get('/api/stt/status?refresh=1').get_json()['available'])

    def test_empty_audio_rejected(self):
        self.assertEqual(self.client.post('/api/stt', data=b'').status_code, 400)


if __name__ == '__main__':
    unittest.main()
