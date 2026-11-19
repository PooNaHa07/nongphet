# -*- coding: utf-8 -*-
"""
tests/test_voice_command.py — คำสั่งเสียงของน้องเพชร (เปิดหน้า หยุดพูด ยิ้ม โบกมือ กี่โมง ...)
คำสั่งต้องตรงทั้งประโยค คำถามทั่วไปต้องไม่ถูกตีความเป็นคำสั่ง
"""
import datetime
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import voice_command_service as vc


class TestParse(unittest.TestCase):
    CASES = [
        ('เปิดหน้าที่เที่ยว', 'open_places'),
        ('น้องเพชร เปิดหน้าที่เที่ยวหน่อยค่ะ', 'open_places'),
        ('ไปหน้าหลักสูตร', 'open_courses'),
        ('เปิดภาษามือ', 'open_sign'),
        ('กลับหน้าแรก', 'go_home'),
        ('หยุดพูด', 'stop_speaking'),
        ('พอแล้ว', 'stop_speaking'),
        ('พูดอีกครั้งได้ไหม', 'repeat'),
        ('เสียงดังขึ้นหน่อย', 'volume_up'),
        ('ลดเสียง', 'volume_down'),
        ('พูดภาษาอังกฤษ', 'lang_en'),
        ('ยิ้มหน่อย', 'face_smile'),
        ('โบกมือ', 'arm_wave'),
        ('ชูมือขึ้น', 'arm_raise_both'),
        ('กี่โมงแล้ว', 'time_now'),
        ('วันนี้วันอะไร', 'date_today'),
        ('ขอคิวอาร์โค้ดสมัครเรียน', 'open_qr'),
        ('ปิดหน้าต่าง', 'close_modal'),
        ('มีคำสั่งอะไรบ้าง', 'help'),
    ]
    NOT_COMMANDS = [
        'แนะนำที่เที่ยวหน่อย', 'เขาวังเปิดกี่โมง', 'เวลาเปิดเขาวัง', 'น้องเพชรทำอะไรได้บ้าง',
        'สาขาการบัญชีเรียนอะไร', 'ดีใจจังที่ได้มาเที่ยว', 'ปิดไฟ', 'ขนมหม้อแกงร้านไหนอร่อย', '',
        'ช่วยเล่าประวัติพระนครคีรีและวัดใหญ่สุวรรณารามให้ฟังหน่อย',
    ]

    def test_commands(self):
        wrong = [f'{t} -> {(vc.parse(t) or {}).get("name")}' for t, n in self.CASES
                 if (vc.parse(t) or {}).get('name') != n]
        self.assertEqual(wrong, [])

    def test_questions_are_not_commands(self):
        hits = [f'{t} -> {vc.parse(t)["name"]}' for t in self.NOT_COMMANDS if vc.parse(t)]
        self.assertEqual(hits, [])

    def test_time_and_date_replies(self):
        now = datetime.datetime(2026, 11, 19, 14, 5)
        self.assertEqual(vc.parse('กี่โมงแล้ว', now=now)['reply'], 'ตอนนี้เวลา 14 นาฬิกา 5 นาทีค่ะ')
        self.assertEqual(vc.parse('วันนี้วันอะไร', now=now)['reply'], 'วันนี้วันพฤหัสบดีที่ 19 พฤศจิกายน 2569 ค่ะ')

    def test_thai_replies_are_polite_and_short(self):
        for phrase in vc.COMMAND_PHRASES:
            self.assertTrue(phrase.endswith(('ค่ะ', 'นะคะ')), phrase)
            self.assertNotIn('ครับ', phrase)
            self.assertLessEqual(len(phrase), 80, phrase)

    def test_gestures_exist_on_arm(self):
        from services import arm_service
        names = {g['name'] if isinstance(g, dict) else g for g in arm_service.list_gestures()}
        for name, _, _, data in vc.COMMANDS:
            if data.get('gesture'):
                self.assertIn(data['gesture'], names, name)

    def test_command_replies_are_prebaked(self):
        import prebake_tts
        baked = {t for _, label, t in prebake_tts.collect_items() if label == 'command'}
        self.assertEqual(baked, set(vc.COMMAND_PHRASES))


class TestRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app_new import app
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def post(self, text):
        return self.client.post('/api/voice/command', json={'text': text}).get_json()

    def test_command_returns_ui_action(self):
        cmd = self.post('เปิดหน้าที่เที่ยว')['command']
        self.assertEqual(cmd['ui'], {'navigate': 'screen-places'})
        self.assertEqual(cmd['reply'], 'เปิดหน้าสถานที่ท่องเที่ยวให้แล้วค่ะ')

    def test_question_is_not_a_command(self):
        self.assertIsNone(self.post('แนะนำที่เที่ยวหน่อย')['command'])

    def test_gesture_command_moves_arm(self):
        with mock.patch('services.arm_service.trigger_gesture', return_value={'ok': True, 'status': 'sent'}) as tg:
            cmd = self.post('น้องเพชรโบกมือหน่อย')['command']
        tg.assert_called_once_with('wave', source='voice_command', force=True)
        self.assertEqual(cmd['arm'], 'sent')

    def test_help_includes_examples(self):
        cmd = self.post('มีคำสั่งอะไรบ้าง')['command']
        self.assertTrue(cmd['ui']['help'])
        self.assertGreater(len(cmd['help']), 0)
        groups = self.client.get('/api/voice/commands').get_json()['groups']
        self.assertEqual(groups, cmd['help'])


if __name__ == '__main__':
    unittest.main()
