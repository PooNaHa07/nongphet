# -*- coding: utf-8 -*-
"""
tests/test_cant_answer.py — ตอบไม่ได้ต้องบอกตรงๆ (ไม่ตอบข้อความต้อนรับทั่วไป ไม่เดา)
และประโยค "กำลังคิด" / "รอนาน" ต้องอัดไว้ล่วงหน้า
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import knowledge_service as ks
from services import tts_service


class TestCantAnswer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app_new import app
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def ask(self, q, lang='th'):
        with mock.patch('local_slm.is_ollama_running', return_value=False):
            return self.client.post('/chat', json={'message': q, 'language': lang}).get_json()

    def test_unknown_question_says_cant_answer(self):
        data = self.ask('วิธีเปลี่ยนยางรถยนต์')
        self.assertEqual(data['engine'], 'cant_answer')
        self.assertIn(data['speech'], [v['speech'] for v in ks.CANT_ANSWER['th']])
        self.assertNotIn('ยินดีต้อนรับ', data['reply'])
        self.assertTrue(data['suggestions'])

    def test_unknown_college_question_points_to_college(self):
        data = self.ask('วิทยาลัยมีชมรมดนตรีสากลไหม')
        if data['engine'] == 'cant_answer':
            self.assertIn('โปรดตรวจสอบกับวิทยาลัย', data['reply'])
            self.assertIn('032-425-557', data['reply'])

    def test_variants_are_polite_and_short(self):
        for key, variants in ks.CANT_ANSWER.items():
            for v in variants:
                self.assertLessEqual(len(v['speech']), 200)
                if key.endswith('th'):
                    self.assertTrue(v['speech'].endswith(('ค่ะ', 'นะคะ')), v['speech'])
                    self.assertNotIn('ครับ', v['reply'] + v['speech'])

    def test_cant_answer_reply_picks_right_set(self):
        self.assertIn('032-425-557', ks.cant_answer_reply('th', college=True)['reply'])
        self.assertIn(ks.cant_answer_reply('en')['speech'], [v['speech'] for v in ks.CANT_ANSWER['en']])

    def test_generic_welcome_kept_when_allowed(self):
        self.assertIsNone(ks.get_local_knowledge_reply('ควอนตัมคอมพิวติ้งทำงานยังไง', 'th', allow_generic=False))
        self.assertTrue(ks.get_local_knowledge_reply('ควอนตัมคอมพิวติ้งทำงานยังไง', 'th'))


class TestThinkingPhrases(unittest.TestCase):
    def test_all_spoken_phrases_are_prebaked(self):
        import prebake_tts
        items = prebake_tts.collect_items()
        labels = {label: [t for _, l, t in items if l == label] for label in ('filler', 'long-wait', 'cant-answer')}
        self.assertEqual(labels['filler'], tts_service.FILLER_PHRASES)
        self.assertEqual(labels['long-wait'], tts_service.LONG_WAIT_PHRASES)
        self.assertEqual(len(labels['cant-answer']), sum(len(v) for v in ks.CANT_ANSWER.values()))

    def test_thinking_phrases_are_polite(self):
        for t in tts_service.FILLER_PHRASES + tts_service.LONG_WAIT_PHRASES:
            self.assertTrue(t.endswith(('ค่ะ', 'นะคะ')), t)

    def test_filler_route_serves_long_wait_kind(self):
        from app_new import app
        with mock.patch('routes.media.get_cached_tts', return_value=('QUJD', 'mp3')):
            data = app.test_client().get('/api/tts/filler?index=1&kind=long').get_json()
        self.assertEqual(data['text'], tts_service.LONG_WAIT_PHRASES[1])


if __name__ == '__main__':
    unittest.main()
