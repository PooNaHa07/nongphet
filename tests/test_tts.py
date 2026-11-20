# -*- coding: utf-8 -*-
"""
tests/test_tts.py — Unit Tests for Child Voice TTS and Stability Engine
"""
import unittest
import json
from app_new import app

class TestTTSSystem(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_tts_presets_api(self):
        """ทดสอบ API คืนค่า Presets เสียงทั้งหมด"""
        res = self.app.get('/api/tts/presets')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        presets = data.get('presets', [])
        self.assertTrue(len(presets) >= 3)
        preset_ids = [p['id'] for p in presets]
        self.assertIn('default', preset_ids)
        self.assertIn('cute_girl', preset_ids)
        self.assertNotIn('cute_boy', preset_ids)
        # ค่า default ต้องเป็นเสียงเดียวกับที่ระบบใช้จริง (config)
        from services.tts_service import voice_profile
        default_preset = next(p for p in presets if p['id'] == 'default')
        self.assertEqual((default_preset['voice'], default_preset['pitch'], default_preset['rate']), voice_profile('th'))

    def test_natural_speech_phrasing_and_cadence(self):
        """ทดสอบระบบจัดจังหวะการพูด วรรคตอน การหายใจ และแปลงลิสต์เป็นภาษาพูดธรรมชาติ"""
        from services.tts_service import clean_text_for_speech
        raw_text = (
            "สวัสดีครับ! ผมคือน้องเพชร ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีครับ\n"
            "สถานที่ท่องเที่ยวแนะนำ:\n"
            "1. พระนครคีรี เขาวัง\n"
            "2. หาดชะอำ\n"
            "3. ถ้ำเขาหลวง\n"
            "จังหวัดเพชรบุรีมี 8 อำเภอ ได้แก่ อำเภอเมือง อำเภอชะอำ ซึ่งเป็นแหล่งท่องเที่ยวยอดนิยม "
            "โดยเปิดให้เข้าชมทุกวัน สำหรับนักท่องเที่ยวทุกคน มีอะไรให้ผมช่วยแนะนำอีกไหมครับ\n"
            "---\n"
            "💡 ถามต่อยอดกับน้องเพชร:\n"
            "1. การเดินทาง"
        )
        cleaned = clean_text_for_speech(raw_text, lang='th')
        # ตรวจสอบการลบคำผู้ชาย 100%
        self.assertNotIn("ครับ", cleaned)
        self.assertNotIn("ผม", cleaned)
        # ตรวจสอบการแปลงรายการลิสต์เป็นภาษาพูด
        self.assertIn("ข้อแรกคือ", cleaned)
        self.assertIn("ข้อต่อมาคือ", cleaned)
        self.assertIn("ต่อมาคือ", cleaned)
        # ตรวจสอบการแทรกจังหวะหายใจและวรรคตอน
        self.assertIn(", ซึ่งเป็น", cleaned)
        self.assertIn(", โดย", cleaned)
        self.assertIn(", สำหรับ", cleaned)
        # ตรวจสอบการปรับเสียงคำถามลงท้าย
        self.assertTrue(cleaned.endswith("ไหมคะ?") or "ไหมคะ?" in cleaned)
        # ตรวจสอบการตัดกล่องคำถามต่อยอด
        self.assertNotIn("ถามต่อยอด", cleaned)

    def test_tts_preview_page(self):
        """ทดสอบการเข้าถึงหน้าสตูดิโอเสียง /tts-preview"""
        res = self.app.get('/tts-preview')
        self.assertEqual(res.status_code, 200)
        self.assertIn('สตูดิโอเสียงน้องเพชร'.encode('utf-8'), res.data)

    def test_tts_cache_hit_zero_latency(self):
        """ประโยคที่อัดเสียงเก็บไว้แล้ว ต้องตอบจากแคชทันที (ไม่ต้องใช้เน็ต) และใช้เสียงน้องเพชรเสมอ"""
        import os, shutil, tempfile
        from unittest import mock
        from services import tts_service
        tmp = tempfile.mkdtemp()
        fake_edge_mp3 = bytes([0xFF, 0xF3, 0x64, 0xC0]) + b'\x00' * 200   # MPEG2 24kHz 48kbps mono
        test_text = "สวัสดีค่ะ น้องเพชรยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ มีอะไรให้น้องเพชรช่วยแนะนำไหมคะ"
        try:
            with mock.patch.object(tts_service, 'AUDIO_CACHE_DIR', tmp):
                tts_service.TTS_CACHE.clear()
                v, p, r = tts_service.voice_profile('th')
                clean = tts_service.clean_text_for_speech(tts_service.prepare_speech_input(test_text), 2500, 'female', 'th')
                tts_service.save_cached_tts(tts_service.speech_cache_key(clean, v, p, r), fake_edge_mp3)
                tts_service.TTS_CACHE.clear()   # บังคับให้อ่านจากดิสก์
                # หน้าเว็บส่ง pitch/rate อื่นมา ก็ยังต้องได้เสียงน้องเพชรจากแคชเดิม
                res = self.app.post('/tts', json={'text': test_text, 'lang': 'th', 'pitch': '+0Hz', 'rate': '+2%'})
        finally:
            tts_service.TTS_CACHE.clear()
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('audio_base64', data)
        self.assertEqual(data.get('engine'), 'cache-disk-cache')
        self.assertEqual(data.get('pitch'), p)

if __name__ == '__main__':
    unittest.main()
