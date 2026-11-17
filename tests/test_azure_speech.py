# -*- coding: utf-8 -*-
"""
tests/test_azure_speech.py — Azure Speech เป็นบริการหลัก (เสียงเปรมวดีเดียวกัน) และ Edge-TTS เป็นตัวสำรอง
ทุกเทสต์จำลองการตอบกลับของ Azure ไม่มีการยิงไปบริการจริง
"""
import os
import sys
import asyncio
import unittest
from unittest import mock

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import azure_speech, tts_service

EDGE_LIKE = bytes([0xFF, 0xF3, 0x64, 0xC0]) + bytes(200)   # MP3 MPEG2 24kHz 48kbps mono
AZURE_AUDIO = bytes([0xFF, 0xF3, 0x64, 0xC0]) + b'A' * 200
FAKE_KEY = 'test-key-1234567890'


class AzureCase(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {'AZURE_SPEECH_KEY': FAKE_KEY, 'AZURE_SPEECH_REGION': 'southeastasia'})
        self.env.start()
        os.environ.pop('AZURE_SPEECH_ENDPOINT', None)
        azure_speech._state.update(cooldown_until=0.0, last_error=None)
        tts_service._mark_edge_ok()
        self.requests = []
        self.responses = []

    def tearDown(self):
        mock.patch.stopall()
        self.env.stop()
        azure_speech._state.update(cooldown_until=0.0, last_error=None)
        tts_service._mark_edge_ok()

    def use_azure_responses(self, *responses):
        """จำลอง Azure: ตอบกลับตามลำดับที่กำหนด (Response หรือ Exception)"""
        self.responses = list(responses)

        def handler(request):
            self.requests.append(request)
            r = self.responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        real_client = httpx.AsyncClient
        mock.patch.object(azure_speech.httpx, 'AsyncClient',
                          lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)).start()

    def patch_edge(self, audio=EDGE_LIKE):
        async def fake_edge(*a, **k):
            return audio
        return mock.patch.object(tts_service, 'generate_edge_tts', side_effect=fake_edge).start()


class TestAzureSpeech(AzureCase):
    def test_ssml_uses_voice_tone_and_escapes_text(self):
        ssml = azure_speech.build_ssml('ขนม & <ของฝาก> "อร่อย"', 'th-TH-PremwadeeNeural', '+15Hz', '+5%')
        self.assertIn("xml:lang='th-TH'", ssml)
        self.assertIn("<voice name='th-TH-PremwadeeNeural'>", ssml)
        self.assertIn("pitch='+15Hz' rate='+5%'", ssml)
        self.assertIn('&amp;', ssml)
        self.assertIn('&lt;ของฝาก&gt;', ssml)
        self.assertNotIn('<ของฝาก>', ssml)

    def test_azure_is_primary_with_same_voice(self):
        self.use_azure_responses(httpx.Response(200, content=AZURE_AUDIO))
        edge = self.patch_edge()
        audio = asyncio.run(tts_service.generate_speech('สวัสดีค่ะ'))
        self.assertEqual(audio, AZURE_AUDIO)
        edge.assert_not_called()
        req = self.requests[0]
        self.assertEqual(str(req.url), 'https://southeastasia.tts.speech.microsoft.com/cognitiveservices/v1')
        self.assertEqual(req.headers['X-Microsoft-OutputFormat'], azure_speech.OUTPUT_FORMAT)
        voice, pitch, rate = tts_service.voice_profile('th')
        body = req.content.decode('utf-8')
        self.assertIn(voice, body)
        self.assertIn(f"pitch='{pitch}' rate='{rate}'", body)

    def test_not_configured_uses_edge_only(self):
        os.environ.pop('AZURE_SPEECH_KEY')
        self.use_azure_responses()
        self.patch_edge()
        self.assertEqual(asyncio.run(tts_service.generate_speech('สวัสดีค่ะ')), EDGE_LIKE)
        self.assertEqual(self.requests, [])

    def test_bad_key_falls_back_and_cools_down(self):
        self.use_azure_responses(httpx.Response(401))
        edge = self.patch_edge()
        self.assertEqual(asyncio.run(tts_service.generate_speech('สวัสดีค่ะ')), EDGE_LIKE)
        self.assertEqual(len(self.requests), 1)
        # ประโยคถัดไป: ไม่ยิง Azure ซ้ำระหว่างพัก (คีย์ผิดไม่ต้องลองทุกประโยค)
        asyncio.run(tts_service.generate_speech('ประโยคถัดไป'))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(edge.call_count, 2)
        self.assertIn('auth failed', azure_speech.azure_status()['last_error'])

    def test_rate_limit_waits_then_retries(self):
        self.use_azure_responses(httpx.Response(429, headers={'Retry-After': '0'}),
                                 httpx.Response(200, content=AZURE_AUDIO))
        edge = self.patch_edge()
        self.assertEqual(asyncio.run(tts_service.generate_speech('สวัสดีค่ะ')), AZURE_AUDIO)
        self.assertEqual(len(self.requests), 2)
        edge.assert_not_called()

    def test_network_error_falls_back_to_edge(self):
        self.use_azure_responses(httpx.ConnectError('dns failed'))
        self.patch_edge()
        self.assertEqual(asyncio.run(tts_service.generate_speech('สวัสดีค่ะ')), EDGE_LIKE)
        self.assertGreater(azure_speech.azure_status()['cooling_down_sec'], 0)

    def test_wrong_audio_format_is_not_used(self):
        self.use_azure_responses(httpx.Response(200, content=b'RIFF' + bytes(100)))   # WAV ไม่ใช่รูปแบบเสียงน้องเพชร
        self.patch_edge()
        self.assertEqual(asyncio.run(tts_service.generate_speech('สวัสดีค่ะ')), EDGE_LIKE)

    def test_both_down_reports_no_voice(self):
        self.use_azure_responses(httpx.Response(500))
        tts_service._mark_edge_offline()
        with self.assertRaises(tts_service.EdgeTTSOffline):
            asyncio.run(tts_service.generate_speech('สวัสดีค่ะ'))

    def test_status_endpoint_hides_key(self):
        from app_new import app
        res = app.test_client().get('/api/tts/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['primary_engine'], 'azure')
        self.assertTrue(data['azure']['configured'])
        self.assertEqual(data['azure']['region'], 'southeastasia')
        self.assertNotIn(FAKE_KEY, res.get_data(as_text=True))

    def test_wait_budget_covers_azure_and_edge(self):
        text = 'ก' * 600
        with_azure = tts_service.edge_wait_budget(text)
        os.environ.pop('AZURE_SPEECH_KEY')
        self.assertGreater(with_azure, tts_service.edge_wait_budget(text))


if __name__ == '__main__':
    unittest.main()
