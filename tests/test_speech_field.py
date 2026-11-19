# -*- coding: utf-8 -*-
"""
tests/test_speech_field.py — บทพูดสั้น (speech) แยกจากคำตอบเต็มบนหน้าจอ (answer)
หน้าจอแสดง answer เต็ม แต่น้องเพชรพูด/อัดเสียงเฉพาะ speech (ถ้าไม่มี speech ใช้ answer)
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.knowledge_manager import kb_manager
from services.text_utils import spoken_text_of
from semantic_retriever import get_semantic_retriever
import prebake_tts

ENTRY_ID = 'test_speech_field_8888'
ANSWER = ('หลักสูตรหุ่นยนต์ควอนตัมทดสอบเรียนสามปีนะคะ มีวิชาพื้นฐาน วิชาชีพ และฝึกงานในสถานประกอบการ '
          'ผู้เรียนจะได้ลงมือสร้างหุ่นยนต์จริงตั้งแต่ปีแรกเลยค่ะ')
SPEECH = 'หลักสูตรหุ่นยนต์ควอนตัมทดสอบเรียนสามปี ได้ลงมือสร้างหุ่นยนต์จริงตั้งแต่ปีแรกเลยค่ะ'
QUESTION = 'หลักสูตรหุ่นยนต์ควอนตัมทดสอบเรียนกี่ปี'


class TestSpokenTextOf(unittest.TestCase):
    def test_prefers_speech(self):
        self.assertEqual(spoken_text_of({'answer': 'ยาว', 'speech': ' สั้น '}), 'สั้น')

    def test_falls_back_to_answer(self):
        self.assertEqual(spoken_text_of({'answer': 'ยาว', 'speech': '  '}), 'ยาว')
        self.assertEqual(spoken_text_of({'answer': 'ยาว'}), 'ยาว')
        self.assertEqual(spoken_text_of(None), '')


class TestSpeechScripts(unittest.TestCase):
    def test_every_kb_entry_has_short_polite_speech(self):
        for entry in kb_manager.list_entries():
            if entry['id'].startswith('test_'):
                continue
            speech = entry.get('speech', '')
            self.assertTrue(speech, entry['id'])
            self.assertLessEqual(len(speech), 200, entry['id'])
            self.assertTrue(speech.endswith(('ค่ะ', 'นะคะ')), entry['id'])
            self.assertNotIn('ครับ', speech, entry['id'])

    def test_every_answer_variant_has_short_polite_speech(self):
        for entry in kb_manager.list_entries():
            for n, variant in enumerate(entry.get('answer_variants') or []):
                label = f"{entry['id']}#{n + 1}"
                self.assertTrue((variant.get('answer') or '').strip(), label)
                speech = variant.get('speech', '')
                self.assertTrue(speech, label)
                self.assertLessEqual(len(speech), 200, label)
                self.assertTrue(speech.endswith(('ค่ะ', 'นะคะ')), label)
                self.assertNotIn('ครับ', speech, label)

    def test_pronunciation_fix_het(self):
        from services.tts_service import clean_text_for_speech, prepare_speech_input
        clean = lambda s: clean_text_for_speech(prepare_speech_input(s), max_len=2500, voice_gender='female', lang='th')
        self.assertIn('เหดด่วนเหดร้าย', clean('เหตุด่วนเหตุร้ายโทรหนึ่งเก้าหนึ่งค่ะ'))
        self.assertIn('เหตุการณ์', clean('เหตุการณ์นี้ค่ะ'))

    def test_pronunciation_fix_quota_and_palm(self):
        from services.tts_service import clean_text_for_speech, prepare_speech_input
        clean = lambda s: clean_text_for_speech(prepare_speech_input(s), max_len=2500, voice_gender='female', lang='th')
        self.assertIn('โคว ต้า', clean('มีรอบโควตาค่ะ'))
        self.assertIn('โคว ต้า', clean('มีรอบโควต้าค่ะ'))
        self.assertIn('ตะโหนด', clean('น้ำตาลโตนดหอมมากค่ะ'))
        self.assertNotIn('โตนด', clean('ดงตาลโตนดค่ะ'))

    def test_no_doubled_level_word(self):
        from services.tts_service import clean_text_for_speech, prepare_speech_input
        out = clean_text_for_speech(prepare_speech_input('เปิดสอนระดับ ปวช. ค่ะ'), max_len=2500,
                                    voice_gender='female', lang='th')
        self.assertNotIn('ระดับ ระดับ', out)
        self.assertNotIn('ระดับระดับ', out)


class TestSpeechThroughSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if kb_manager.get_entry(ENTRY_ID):
            kb_manager.delete_entry(ENTRY_ID, auto_reindex=True)
        kb_manager.add_entry({
            'id': ENTRY_ID, 'intent': 'admission', 'title': 'หลักสูตรหุ่นยนต์ควอนตัมทดสอบ',
            'keywords': ['หุ่นยนต์ควอนตัมทดสอบ'], 'questions': [QUESTION],
            'answer': ANSWER, 'speech': SPEECH, 'suggestions': [],
        }, auto_reindex=True)

    @classmethod
    def tearDownClass(cls):
        if kb_manager.get_entry(ENTRY_ID):
            kb_manager.delete_entry(ENTRY_ID, auto_reindex=True)

    def test_manager_stores_and_updates_speech(self):
        self.assertEqual(kb_manager.get_entry(ENTRY_ID)['speech'], SPEECH)
        kb_manager.update_entry(ENTRY_ID, {'speech': SPEECH + ' '}, auto_reindex=False)
        self.assertEqual(kb_manager.get_entry(ENTRY_ID)['speech'], SPEECH)

    def test_retriever_returns_speech(self):
        match = get_semantic_retriever().retrieve(QUESTION)
        self.assertEqual(match['id'], ENTRY_ID)
        self.assertEqual(match['reply'], ANSWER)
        self.assertEqual(match['speech'], SPEECH)

    def test_chat_api_sends_full_reply_and_short_speech(self):
        from app_new import app
        with mock.patch('local_slm.is_ollama_running', return_value=False):
            data = app.test_client().post('/chat', json={'message': QUESTION, 'language': 'th'}).get_json()
        self.assertEqual(data['reply'], ANSWER)
        self.assertEqual(data['speech'], SPEECH)

    def test_prebake_lang_filter_bakes_thai_only(self):
        import asyncio
        baked = []

        async def fake_bake(clean, key, *a):
            baked.append(clean)
            return 1024
        with mock.patch.object(prebake_tts, 'bake_one', side_effect=fake_bake), \
             mock.patch.object(prebake_tts, 'has_canonical_file', return_value=False), \
             mock.patch.object(prebake_tts, 'omnivoice_enabled', return_value=True), \
             mock.patch('builtins.print'):
            asyncio.run(prebake_tts.prebake_all(langs={'th'}))
        expected = [i for i in prebake_tts.collect_items() if i[0] == 'th']
        self.assertEqual(len(baked), len(expected))
        others = {prebake_tts.plan_item(l, t)[0] for l, _, t in prebake_tts.collect_items() if l != 'th'}
        self.assertFalse(others & set(baked))   # ไม่มีประโยคอังกฤษ/จีนหลุดเข้ามา

    def test_prebake_bakes_every_answer_variant(self):
        texts = {label: text for lang, label, text in prebake_tts.collect_items()}
        for entry in kb_manager.list_entries():
            for n, variant in enumerate(entry.get('answer_variants') or []):
                self.assertEqual(texts.get(f"KB:{entry['id']}#{n + 1}"), variant['speech'])

    def test_prebake_bakes_speech_not_full_answer(self):
        texts = {label: text for lang, label, text in prebake_tts.collect_items()}
        self.assertEqual(texts.get(f'KB:{ENTRY_ID}'), SPEECH)


if __name__ == '__main__':
    unittest.main()
