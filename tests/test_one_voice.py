# -*- coding: utf-8 -*-
"""
tests/test_one_voice.py — นโยบาย "เสียงเดียวทั้งระบบ"
ทุกเส้นทางพูดด้วยเสียงน้องเพชรตาม config, ไม่มีเสียงสำรองที่เป็นคนอื่น, แคชไม่รับเสียงอื่น
"""
import os
import sys
import base64
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import Config
from services import tts_service
import prebake_tts


def mp3_frame(version_bits, bitrate_idx, sr_idx=1, mono=True):
    """สร้างหัวเฟรม MP3 ปลอมสำหรับทดสอบตัวตรวจรูปแบบไฟล์"""
    b1 = 0xE0 | (version_bits << 3) | (1 << 1) | 1           # sync + version + layer III + no CRC
    b2 = (bitrate_idx << 4) | (sr_idx << 2)
    b3 = 0xC0 if mono else 0x00
    return bytes([0xFF, b1, b2, b3]) + b'\x00' * 200


EDGE_LIKE = mp3_frame(2, 6)    # MPEG2, 24kHz, 48kbps, mono  (รูปแบบ Edge-TTS)
GTTS_LIKE = mp3_frame(2, 8)    # MPEG2, 24kHz, 64kbps, mono  (รูปแบบ gTTS)
WAV_LIKE = b'RIFF' + b'\x00' * 100


class TestVoiceProfile(unittest.TestCase):
    def test_thai_uses_configured_voice(self):
        self.assertEqual(tts_service.voice_profile('th'),
                         (Config.TTS_DEFAULT_VOICE, Config.TTS_DEFAULT_PITCH, Config.TTS_DEFAULT_RATE))

    def test_default_tone_is_the_chosen_one(self):
        # เสียงที่เลือก: voice_samples/2_premwadee_sweet_+15Hz.mp3
        if not os.environ.get('TTS_PITCH') and not os.environ.get('TTS_RATE'):
            self.assertEqual((Config.TTS_DEFAULT_PITCH, Config.TTS_DEFAULT_RATE), ('+15Hz', '+5%'))

    def test_edge_defaults_follow_profile(self):
        captured = {}

        class FakeCommunicate:
            def __init__(self, text, voice, rate, pitch, volume):
                captured.update(voice=voice, rate=rate, pitch=pitch)

            async def stream(self):
                yield {'type': 'audio', 'data': EDGE_LIKE}

        import asyncio
        tts_service._mark_edge_ok()
        with mock.patch.object(tts_service.edge_tts, 'Communicate', FakeCommunicate):
            asyncio.run(tts_service.generate_edge_tts('ทดสอบ'))
        self.assertEqual((captured['voice'], captured['pitch'], captured['rate']), tts_service.voice_profile('th'))


class TestAudioFormatGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._dir = tts_service.AUDIO_CACHE_DIR
        tts_service.AUDIO_CACHE_DIR = self.tmp
        tts_service.TTS_CACHE.clear()

    def tearDown(self):
        tts_service.AUDIO_CACHE_DIR = self._dir
        tts_service.TTS_CACHE.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_format_detection(self):
        self.assertEqual(tts_service.audio_format_of(EDGE_LIKE), (24000, 48, 'mono'))
        self.assertTrue(tts_service.is_canonical_voice_audio(EDGE_LIKE))
        self.assertFalse(tts_service.is_canonical_voice_audio(GTTS_LIKE))
        self.assertFalse(tts_service.is_canonical_voice_audio(WAV_LIKE))
        self.assertFalse(tts_service.is_canonical_voice_audio(b''))

    def test_save_rejects_other_voices(self):
        tts_service.save_cached_tts('k_gtts', GTTS_LIKE)
        tts_service.save_cached_tts('k_wav', WAV_LIKE)
        self.assertEqual(os.listdir(self.tmp), [])
        self.assertEqual(len(tts_service.TTS_CACHE), 0)
        tts_service.save_cached_tts('k_edge', EDGE_LIKE)
        self.assertEqual(len(os.listdir(self.tmp)), 1)

    def test_get_ignores_foreign_file_already_on_disk(self):
        import hashlib
        name = hashlib.md5('k_bad'.encode('utf-8')).hexdigest() + '.mp3'
        with open(os.path.join(self.tmp, name), 'wb') as f:
            f.write(GTTS_LIKE)
        self.assertEqual(tts_service.get_cached_tts('k_bad'), (None, None))

    def test_audit_and_clean(self):
        for name, data in (('a.mp3', EDGE_LIKE), ('b.mp3', GTTS_LIKE), ('c.mp3', WAV_LIKE)):
            with open(os.path.join(self.tmp, name), 'wb') as f:
                f.write(data)
        bad = [n for n, _ in tts_service.audit_audio_cache(delete=False)]
        self.assertEqual(bad, ['b.mp3', 'c.mp3'])
        tts_service.audit_audio_cache(delete=True)
        self.assertEqual(os.listdir(self.tmp), ['a.mp3'])


class TestSameTextSameKey(unittest.TestCase):
    """หน้าจอ kiosk / หน้าจอใบหน้า / สคริปต์อัดเสียง ต้องได้คีย์แคชเดียวกันสำหรับคำตอบเดียวกัน"""

    def key_from(self, text):
        v, p, r = tts_service.voice_profile('th')
        clean = tts_service.clean_text_for_speech(tts_service.prepare_speech_input(text), 2500, 'female', 'th')
        return tts_service.speech_cache_key(clean, v, p, r)

    def test_prepare_is_idempotent(self):
        raw = "🎓 **สาขาการโรงแรม** (อังกฤษ/จีน)\n• ทักษะ 2 ภาษา ✨\n---\n💡 ถามต่อยอด"
        once = tts_service.prepare_speech_input(raw)
        self.assertEqual(tts_service.prepare_speech_input(once), once)

    def test_kiosk_and_emotion_variants_share_key(self):
        raw = "🎓 **สาขาการโรงแรม** (อังกฤษ/จีน)\nเรียนสนุกค่ะ 🏛️\n• ฝึกงานโรงแรม 5 ดาว"
        kiosk = tts_service.prepare_speech_input(raw)                      # แบบ stripEmojiAndIcons()
        emotion = raw.replace('**', ' ').replace('•', ' ').replace('\n', ', ')  # แบบ emotion.js
        self.assertEqual(self.key_from(raw), self.key_from(kiosk))
        self.assertEqual(self.key_from(raw), self.key_from(emotion))
        self.assertEqual(self.key_from(raw), prebake_tts.plan_item('th', raw)[1])

    def test_key_changes_with_tone(self):
        clean = 'สวัสดีค่ะ'
        self.assertNotEqual(tts_service.speech_cache_key(clean, 'v', '+0Hz', '+2%'),
                            tts_service.speech_cache_key(clean, 'v', '+15Hz', '+5%'))


class TestRoutesUseOneVoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app_new import app
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def setUp(self):
        tts_service._mark_edge_ok()
        self.calls = []

        def fake_run(coro, timeout=12.0):
            coro.close()
            return EDGE_LIKE

        async def fake_edge(text, voice=None, rate=None, pitch=None, **kw):
            self.calls.append((voice, pitch, rate))
            return EDGE_LIKE

        self.p1 = mock.patch('routes.media.generate_speech', side_effect=fake_edge)
        self.p2 = mock.patch('routes.media.save_cached_tts')
        self.p3 = mock.patch('routes.media.get_cached_tts', return_value=(None, None))
        self.edge = self.p1.start()
        self.save = self.p2.start()
        self.p3.start()

    def tearDown(self):
        mock.patch.stopall()

    def test_client_pitch_is_ignored(self):
        res = self.client.post('/tts', json={'text': 'สวัสดีค่ะ', 'pitch': '+45Hz', 'rate': '+30%'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.calls[-1], tts_service.voice_profile('th'))
        self.save.assert_called_once()

    def test_preview_may_change_tone_but_is_not_cached(self):
        res = self.client.post('/tts', json={'text': 'สวัสดีค่ะ', 'pitch': '+35Hz', 'rate': '+10%', 'preview': True})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.calls[-1][1:], ('+35Hz', '+10%'))
        self.save.assert_not_called()

    def test_filler_uses_profile(self):
        res = self.client.get('/api/tts/filler?index=0')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.calls[-1], tts_service.voice_profile('th'))

    def test_no_foreign_voice_fallback_when_edge_fails(self):
        async def failing(*a, **k):
            raise RuntimeError('No audio was received')
        self.edge.side_effect = failing
        res = self.client.post('/tts', json={'text': 'สวัสดีค่ะ'})
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.get_json()['status'], 'no_voice')
        self.assertNotIn('audio_base64', res.get_json())

    def test_presets_report_active_voice(self):
        data = self.client.get('/api/tts/presets').get_json()
        default = [p for p in data['presets'] if p['id'] == data['active']][0]
        self.assertEqual((default['voice'], default['pitch'], default['rate']), tts_service.voice_profile('th'))


class TestNoOtherVoiceEnginesLeft(unittest.TestCase):
    def test_no_gtts_or_browser_speech_in_runtime_code(self):
        checks = {
            'routes/media.py': ('gTTS', 'pythaitts'),
            'services/tts_service.py': ('from gtts', 'pythaitts.'),
            'static/js/main.js': ('speechSynthesis.speak',),
            'static/js/emotion.js': ('speechSynthesis.speak',),
        }
        for rel, needles in checks.items():
            with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
                src = f.read()
            for n in needles:
                self.assertNotIn(n, src, f'{rel} ยังมี {n}')


if __name__ == '__main__':
    unittest.main()
