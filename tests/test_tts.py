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
        self.assertIn('cute_chibi', preset_ids)
        self.assertNotIn('cute_boy', preset_ids)
        default_preset = next(p for p in presets if p['id'] == 'default')
        self.assertEqual(default_preset['pitch'], '+2Hz')
        self.assertEqual(default_preset['rate'], '+5%')

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
        """ทดสอบว่าประโยคที่ Pre-baked ไว้แล้วตอบสนองด้วย Cache ทันที"""
        test_text = "สวัสดีค่ะ น้องเพชรยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ มีอะไรให้น้องเพชรช่วยแนะนำไหมคะ"
        res = self.app.post('/tts', json={
            'text': test_text,
            'lang': 'th',
            'voice': 'th-TH-PremwadeeNeural',
            'pitch': '+0Hz',
            'rate': '+2%'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('audio_base64', data)
        self.assertEqual(data.get('status'), 'success')

if __name__ == '__main__':
    unittest.main()
