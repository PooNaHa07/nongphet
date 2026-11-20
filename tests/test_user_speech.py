# -*- coding: utf-8 -*-
"""
tests/test_user_speech.py — สถานะเสียงพูดของผู้ใช้ ส่งต่อให้จอใบหน้า (/emotion) ผ่าน SSE
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestUserSpeechEvent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app_new import app
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def post(self, body):
        with mock.patch('routes.display.broadcast_iot_event') as bc:
            res = self.client.post('/api/user-speech', json=body)
        return res, bc

    def test_final_text_is_broadcast(self):
        res, bc = self.post({'state': 'final', 'text': 'เขาวังเปิดกี่โมง'})
        self.assertEqual(res.status_code, 200)
        bc.assert_called_once_with({'event': 'user_speech', 'state': 'final', 'text': 'เขาวังเปิดกี่โมง'})

    def test_pending_states_carry_no_text(self):
        for state in ('listening', 'transcribing', 'clear'):
            res, bc = self.post({'state': state, 'text': 'ไม่ควรส่ง'})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(bc.call_args[0][0], {'event': 'user_speech', 'state': state, 'text': ''})

    def test_long_text_is_trimmed(self):
        _, bc = self.post({'state': 'final', 'text': 'ก' * 500})
        self.assertEqual(len(bc.call_args[0][0]['text']), 200)

    def test_invalid_state_rejected(self):
        res, bc = self.post({'state': 'hack'})
        self.assertEqual(res.status_code, 400)
        bc.assert_not_called()


if __name__ == '__main__':
    unittest.main()
