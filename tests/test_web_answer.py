# -*- coding: utf-8 -*-
"""
tests/test_web_answer.py — ชั้นค้นคำตอบจากเว็บ (Gemini + Google Search) เมื่อฐานความรู้ตอบไม่ได้
จำลองการเรียก API ทั้งหมด ไม่ใช้เน็ตและไม่ใช้คีย์จริง
"""
import os
import sys
import shutil
import tempfile
import unittest
from unittest import mock

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import web_answer_service as was
from services.knowledge_manager import kb_manager

GOOD_TEXT = ("คำตอบ: ตลาดน้ำอัมพวาเปิดวันศุกร์ถึงอาทิตย์ครับ ช่วงบ่ายถึงค่ำ [1]\n"
             "บทพูด: ตลาดน้ำอัมพวาเปิดศุกร์ถึงอาทิตย์นะคะ")


def fake_response(status=200, text=GOOD_TEXT):
    body = {'candidates': [{
        'content': {'parts': [{'text': text}]},
        'groundingMetadata': {
            'groundingChunks': [{'web': {'title': 'example.com', 'uri': 'https://x/1'}},
                                {'web': {'title': 'example.com', 'uri': 'https://x/2'}},
                                {'web': {'title': 'tat.or.th', 'uri': 'https://x/3'}}],
            'searchEntryPoint': {'renderedContent': '<div>chips</div>'},
        }}]}
    return httpx.Response(status, json=body if status == 200 else {'error': {}},
                          request=httpx.Request('POST', 'https://test'))


class WebCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key', 'WEB_ANSWER_ENABLED': '1',
                                     'GEMINI_MODELS': 'model-a,model-b'}).start()
        mock.patch.object(was, 'PENDING_FILE', os.path.join(self.tmp, 'pending.json')).start()
        was._cache.clear()
        was._state.update(cooldown_until=0.0, last_error=None)
        self.calls = []

    def tearDown(self):
        mock.patch.stopall()
        was._cache.clear()
        was._state.update(cooldown_until=0.0, last_error=None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def replies(self, *responses):
        responses = list(responses)

        def fake_call(model, question, lang):
            self.calls.append(model)
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        mock.patch.object(was, '_call', side_effect=fake_call).start()


class TestParsing(unittest.TestCase):
    def test_splits_answer_and_speech_and_fixes_persona(self):
        reply, speech = was.parse_answer(GOOD_TEXT)
        self.assertIn('ตลาดน้ำอัมพวา', reply)
        self.assertNotIn('ครับ', reply)
        self.assertNotIn('[1]', reply)
        self.assertEqual(speech, 'ตลาดน้ำอัมพวาเปิดศุกร์ถึงอาทิตย์นะคะ')

    def test_unformatted_text_still_usable(self):
        reply, speech = was.parse_answer('ประโยคแรกค่ะ ประโยคที่สองยาวมากนะคะ')
        self.assertTrue(reply)
        self.assertTrue(speech)
        self.assertLessEqual(len(speech), 160)


class TestGuards(WebCase):
    def test_college_topics_never_use_web(self):
        self.assertFalse(was.should_use_web('ค่าเทอมวิทยาลัยเท่าไหร่'))
        self.assertFalse(was.should_use_web('สาขาบัญชีเรียนอะไร'))
        self.assertFalse(was.should_use_web('อะไรก็ได้', intent='admission'))
        self.assertTrue(was.should_use_web('ตลาดน้ำอัมพวาเปิดวันไหน'))

    def test_disabled_without_key(self):
        with mock.patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            self.assertFalse(was.should_use_web('ตลาดน้ำอัมพวาเปิดวันไหน'))
            self.assertIsNone(was.answer('ตลาดน้ำอัมพวาเปิดวันไหน'))


class TestAnswer(WebCase):
    def test_answer_has_sources_notes_and_goes_to_pending(self):
        self.replies(fake_response())
        res = was.answer('ตลาดน้ำอัมพวาเปิดวันไหน')
        self.assertIn('ข้อมูลจากเว็บไซต์', res['reply'])
        self.assertTrue(res['speech'].startswith('น้องเพชรค้นจากเว็บมาให้แล้วค่ะ'))
        self.assertEqual([s['title'] for s in res['sources']], ['example.com', 'tat.or.th'])
        self.assertEqual(res['search_html'], '<div>chips</div>')
        pending = was.list_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['question'], 'ตลาดน้ำอัมพวาเปิดวันไหน')

    def test_ungrounded_refusal_not_labelled_or_queued(self):
        body = {'candidates': [{'content': {'parts': [{'text': 'คำตอบ: ขออภัยค่ะ ให้ข้อมูลนี้ไม่ได้นะคะ\nบทพูด: ขออภัยค่ะ ให้ข้อมูลนี้ไม่ได้นะคะ'}]}}]}
        self.replies(httpx.Response(200, json=body, request=httpx.Request('POST', 'https://test')))
        res = was.answer('คำขอไม่เหมาะสม')
        self.assertFalse(res['grounded'])
        self.assertNotIn('ข้อมูลจากเว็บไซต์', res['reply'])
        self.assertFalse(res['speech'].startswith('น้องเพชรค้นจากเว็บ'))
        self.assertEqual(was.list_pending(), [])

    def test_english_speech_has_no_thai(self):
        text = 'คำตอบ: Khao Wang opens at 8:30 AM. It closes at 4:30 PM.\nบทพูด: เขาวังเปิดแปดโมงครึ่งค่ะ'
        self.replies(fake_response(text=text))
        res = was.answer('What time does Khao Wang open?', 'en')
        self.assertNotRegex(res['speech'], '[฀-๿]')
        self.assertTrue(res['speech'].startswith("I looked this up online."))

    def test_punycode_source_made_readable(self):
        self.assertEqual(was._readable_domain('example.com'), 'example.com')
        self.assertNotIn('xn--', was._readable_domain('xn--22cap5dwcq3d9ac1l0f.com'))

    def test_repeat_question_uses_cache(self):
        self.replies(fake_response())
        was.answer('ตลาดน้ำอัมพวาเปิดวันไหน')
        was.answer('ตลาดน้ำอัมพวา เปิดวันไหน?')
        self.assertEqual(self.calls, ['model-a'])

    def test_quota_on_first_model_tries_next(self):
        self.replies(fake_response(429), fake_response())
        res = was.answer('ร้านกาแฟในเพชรบุรี')
        self.assertEqual(res['model'], 'model-b')
        self.assertEqual(self.calls, ['model-a', 'model-b'])

    def test_pause_follows_google_retry_delay(self):
        quota = httpx.Response(429, json={'error': {'details': [{'retryDelay': '7s'}]}},
                               request=httpx.Request('POST', 'https://test'))
        self.replies(quota, quota)
        before = __import__('time').time()
        self.assertIsNone(was.answer('ร้านกาแฟในเพชรบุรี'))
        self.assertAlmostEqual(was._state['cooldown_until'] - before, 7, delta=1)

    def test_blocked_question_does_not_pause_others(self):
        blocked = httpx.Response(200, json={'promptFeedback': {'blockReason': 'SAFETY'}},
                                 request=httpx.Request('POST', 'https://test'))
        self.replies(blocked)
        self.assertIsNone(was.answer('คำถามไม่เหมาะสม'))
        self.assertTrue(was.should_use_web('คำถามถัดไปปกติ'))
        self.assertEqual(self.calls, ['model-a'])

    def test_slow_search_does_not_pause_next_question(self):
        self.replies(httpx.ReadTimeout('slow'), fake_response())
        self.assertIsNone(was.answer('คำถามที่ค้นนาน'))
        self.assertTrue(was.should_use_web('คำถามถัดไป'))
        self.assertIsNotNone(was.answer('คำถามถัดไป'))

    def test_speech_is_capped(self):
        long_speech = 'คำตอบ: ยาวค่ะ\nบทพูด: ' + 'ประโยคยาวมากเลยนะคะ ' * 30
        self.replies(fake_response(text=long_speech))
        res = was.answer('คำถามบทพูดยาว')
        self.assertLessEqual(len(res['speech']), len(was.WEB_NOTE['th'][0]) + was.SPEECH_MAX_CHARS)

    def test_network_error_returns_none_and_pauses(self):
        self.replies(httpx.ConnectTimeout('no internet'))
        self.assertIsNone(was.answer('ร้านกาแฟในเพชรบุรี'))
        self.assertFalse(was.should_use_web('คำถามถัดไป'))       # พักชั่วคราว ไม่ยิงซ้ำตอนเน็ตหลุด
        self.assertEqual(self.calls, ['model-a'])               # เน็ตหลุดไม่ต้องลองรุ่นอื่น


class TestChatPipeline(WebCase):
    def setUp(self):
        super().setUp()
        mock.patch('local_slm.is_ollama_running', return_value=False).start()
        from app_new import app
        app.config['TESTING'] = True
        self.client = app.test_client()

    def ask(self, q):
        return self.client.post('/chat', json={'message': q, 'language': 'th'}).get_json()

    def test_unknown_place_answered_from_web(self):
        self.replies(fake_response())
        data = self.ask('ตลาดน้ำอัมพวาเปิดวันไหนบ้าง')
        self.assertEqual(data['engine'], 'web_search')
        self.assertTrue(data['speech'])
        self.assertEqual(len(data['sources']), 2)

    def test_known_topic_stays_local(self):
        self.replies()
        data = self.ask('เขาวังเปิดกี่โมง')
        self.assertEqual(data['engine'], 'semantic_rag')
        self.assertEqual(self.calls, [])

    def test_college_question_stays_local(self):
        self.replies()
        data = self.ask('ค่าเทอมวิทยาลัยเท่าไหร่')
        self.assertNotEqual(data['engine'], 'web_search')
        self.assertEqual(self.calls, [])

    def test_web_down_falls_back_to_local_answer(self):
        self.replies(httpx.ConnectTimeout('no internet'))
        data = self.ask('ตลาดน้ำอัมพวาเปิดวันไหนบ้าง')
        self.assertNotEqual(data['engine'], 'web_search')
        self.assertTrue(data['reply'])


class TestApproveFlow(WebCase):
    def setUp(self):
        super().setUp()
        from app_new import app
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.created = []

    def tearDown(self):
        for eid in self.created:
            if kb_manager.get_entry(eid):
                kb_manager.delete_entry(eid, auto_reindex=True)
        super().tearDown()

    def test_approve_moves_answer_into_knowledge_base(self):
        self.replies(fake_response())
        was.answer('ตลาดน้ำทดสอบควอนตัมเปิดวันไหน')
        item = was.list_pending()[0]
        res = self.client.post(f"/api/kb/web-pending/{item['id']}/approve", json={})
        self.assertEqual(res.status_code, 201)
        entry = res.get_json()['entry']
        self.created.append(entry['id'])
        self.assertNotIn('ข้อมูลจากเว็บไซต์', entry['answer'])
        self.assertIn('แหล่งข้อมูล: example.com, tat.or.th', entry['answer'])
        self.assertFalse(entry['speech'].startswith('น้องเพชรค้นจากเว็บ'))
        self.assertEqual(entry['questions'], ['ตลาดน้ำทดสอบควอนตัมเปิดวันไหน'])
        self.assertEqual(was.list_pending(), [])

    def test_reject_removes_item(self):
        self.replies(fake_response())
        was.answer('ตลาดน้ำทดสอบเปิดวันไหน')
        item = was.list_pending()[0]
        self.assertEqual(self.client.delete(f"/api/kb/web-pending/{item['id']}").status_code, 200)
        self.assertEqual(was.list_pending(), [])


if __name__ == '__main__':
    unittest.main()
