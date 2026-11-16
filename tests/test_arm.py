# -*- coding: utf-8 -*-
"""
tests/test_arm.py — Arm gesture service, API and ESP32 bridge protocol tests
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_new import app
from services import arm_service
import esp32_listener
import routes.iot as iot_routes


class TestArmService(unittest.TestCase):
    def setUp(self):
        arm_service.arm_state['busy_until'] = 0.0
        arm_service.ARM_ENABLED = True
        self.events = []
        self._orig = iot_routes.broadcast_iot_event
        iot_routes.broadcast_iot_event = self.events.append

    def tearDown(self):
        iot_routes.broadcast_iot_event = self._orig
        arm_service.ARM_ENABLED = True

    def test_unknown_gesture_rejected(self):
        res = arm_service.trigger_gesture('dance')
        self.assertFalse(res['ok'])
        self.assertEqual(res['status'], 'invalid')
        self.assertEqual(self.events, [])

    def test_gesture_broadcasts_event(self):
        res = arm_service.trigger_gesture('wave', source='test')
        self.assertTrue(res['ok'])
        self.assertEqual(self.events[0]['event'], 'arm_gesture')
        self.assertEqual(self.events[0]['gesture'], 'wave')

    def test_busy_blocks_automatic_but_not_forced_or_rest(self):
        arm_service.trigger_gesture('wave')
        self.assertEqual(arm_service.trigger_gesture('cheer')['status'], 'busy')
        self.assertTrue(arm_service.trigger_gesture('cheer', force=True)['ok'])
        self.assertTrue(arm_service.trigger_gesture('rest')['ok'])

    def test_disabled_blocks_commands(self):
        arm_service.ARM_ENABLED = False
        self.assertEqual(arm_service.trigger_gesture('wave')['status'], 'disabled')
        self.assertEqual(arm_service.set_pose('L', 90)['status'], 'disabled')

    def test_pose_clamps_angle_and_speed(self):
        res = arm_service.set_pose('both', 300, 9999)
        self.assertEqual(res['angle'], arm_service.ANGLE_MAX)
        self.assertEqual(res['speed'], arm_service.SPEED_MAX)
        res = arm_service.set_pose('L', -50, 0)
        self.assertEqual(res['angle'], arm_service.ANGLE_MIN)
        self.assertEqual(res['speed'], arm_service.SPEED_MIN)

    def test_pose_rejects_bad_input(self):
        self.assertEqual(arm_service.set_pose('middle', 90)['status'], 'invalid')
        self.assertEqual(arm_service.set_pose('L', 'abc')['status'], 'invalid')

    def test_chat_mapping(self):
        self.assertEqual(arm_service.gesture_for_chat('greeting', 'smile'), 'wave')
        self.assertEqual(arm_service.gesture_for_chat('greeting', 'excited'), 'wave')
        self.assertEqual(arm_service.gesture_for_chat('travel', 'excited'), 'cheer')
        self.assertEqual(arm_service.gesture_for_chat('love', 'love'), 'raise_both')
        self.assertIsNone(arm_service.gesture_for_chat('general_faq', 'smile'))

    def test_all_mapped_gestures_exist(self):
        mapped = (set(arm_service.EMOTION_GESTURE_MAP.values())
                  | set(arm_service.INTENT_GESTURE_MAP.values())
                  | set(arm_service.SIGN_GESTURE_MAP.values()))
        self.assertTrue(mapped.issubset(arm_service.GESTURES.keys()))


class TestArmRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def setUp(self):
        arm_service.arm_state['busy_until'] = 0.0
        arm_service.ARM_ENABLED = True

    def test_status_and_gesture_list(self):
        res = self.client.get('/api/arm/status')
        self.assertEqual(res.status_code, 200)
        self.assertIn('wave', res.get_json()['arm']['gestures'])
        self.assertIn('cheer', self.client.get('/api/arm/gestures').get_json()['gestures'])

    def test_gesture_from_localhost(self):
        res = self.client.post('/api/arm/gesture', json={'gesture': 'wave'})
        self.assertEqual(res.status_code, 200)

    def test_gesture_invalid_name(self):
        res = self.client.post('/api/arm/gesture', json={'gesture': 'nope'})
        self.assertEqual(res.status_code, 400)

    def test_remote_requires_pin(self):
        remote = {'REMOTE_ADDR': '192.168.1.50'}
        res = self.client.post('/api/arm/gesture', json={'gesture': 'wave'}, environ_overrides=remote)
        self.assertEqual(res.status_code, 403)
        res = self.client.post('/api/arm/gesture', json={'gesture': 'wave'},
                               headers={'X-Admin-Pin': 'wrong'}, environ_overrides=remote)
        self.assertEqual(res.status_code, 403)
        from config import Config
        res = self.client.post('/api/arm/gesture', json={'gesture': 'wave'},
                               headers={'X-Admin-Pin': str(Config.ADMIN_PIN)}, environ_overrides=remote)
        self.assertEqual(res.status_code, 200)

    def test_pose_route(self):
        res = self.client.post('/api/arm/pose', json={'side': 'L', 'angle': 90, 'speed': 60})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['angle'], 90)
        res = self.client.post('/api/arm/pose', json={'side': 'X', 'angle': 90})
        self.assertEqual(res.status_code, 400)


INO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'esp32_firmware', 'esp32_firmware.ino')


class TestFirmwareSync(unittest.TestCase):
    """Python gesture library และ firmware ต้องตรงกัน ไม่งั้นท่าบนหน้าจอกับท่าจริงจะต่างกัน"""

    @classmethod
    def setUpClass(cls):
        with open(INO_PATH, encoding='utf-8') as f:
            cls.ino = f.read()

    def _const(self, name):
        m = re.search(r'const int %s\s*=\s*(\d+)\s*;' % name, self.ino)
        self.assertIsNotNone(m, f'ไม่พบค่าคงที่ {name} ใน .ino')
        return int(m.group(1))

    def test_angle_limits_match(self):
        self.assertEqual(self._const('ARM_MIN'), arm_service.ANGLE_MIN)
        self.assertEqual(self._const('ARM_MAX'), arm_service.ANGLE_MAX)
        self.assertEqual(self._const('ARM_REST'), arm_service.ANGLE_REST)

    def test_keyframes_match(self):
        rest = self._const('ARM_REST')
        ino_frames = {}
        for m in re.finditer(r'const ArmStep (G_\w+)\[\]\s*=\s*\{(.*?)\};', self.ino, re.DOTALL):
            name = m.group(1)[2:].lower()
            steps = []
            for tup in re.findall(r'\{([^{}]*)\}', m.group(2)):
                vals = [int(t.strip().replace('ARM_REST', str(rest))) for t in tup.split(',')]
                steps.append(tuple(vals))
            ino_frames[name] = steps
        self.assertEqual(set(ino_frames), set(arm_service.GESTURE_DEFS))
        for name, d in arm_service.GESTURE_DEFS.items():
            self.assertEqual(ino_frames[name], [tuple(k) for k in d['keyframes']], f'keyframe ของ {name} ไม่ตรงกับ .ino')

    def test_loop_flags_match(self):
        table = re.search(r'const Gesture GESTURES\[\]\s*=\s*\{(.*?)\n\};', self.ino, re.DOTALL).group(1)
        found = dict(re.findall(r'\{"(\w+)",\s*G_\w+,[^}]*,\s*(true|false)\}', table))
        self.assertEqual(set(found), set(arm_service.GESTURE_DEFS))
        for name, d in arm_service.GESTURE_DEFS.items():
            self.assertEqual(found[name] == 'true', d['loop'], f'loop ของ {name} ไม่ตรงกับ .ino')

    def test_angles_within_limits(self):
        for name, d in arm_service.GESTURE_DEFS.items():
            for l, r, speed, hold in d['keyframes']:
                for a in (l, r):
                    self.assertTrue(a == -1 or arm_service.ANGLE_MIN <= a <= arm_service.ANGLE_MAX, f'{name}: มุม {a} เกินช่วง')
                self.assertTrue(arm_service.SPEED_MIN <= speed <= arm_service.SPEED_MAX)

    def test_durations(self):
        self.assertEqual(arm_service.GESTURES['talk'][1], 0.0)
        self.assertGreater(arm_service.GESTURES['wave'][1], 1.0)


class TestSpeechAndTags(unittest.TestCase):
    def setUp(self):
        arm_service.arm_state['busy_until'] = 0.0
        arm_service.arm_state['speaking'] = False
        arm_service.arm_state['speaking_since'] = 0.0
        arm_service.ARM_ENABLED = True
        arm_service.ARM_TALK_ENABLED = True
        self.events = []
        self._orig = iot_routes.broadcast_iot_event
        iot_routes.broadcast_iot_event = self.events.append

    def tearDown(self):
        iot_routes.broadcast_iot_event = self._orig
        arm_service.arm_state['speaking'] = False
        arm_service.ARM_ENABLED = True
        arm_service.ARM_TALK_ENABLED = True

    def gestures(self):
        return [e['gesture'] for e in self.events if e['event'] == 'arm_gesture']

    def test_speech_sends_only_on_transition(self):
        arm_service.speech_changed(True)
        arm_service.speech_changed(True)   # หน้าเว็บส่งซ้ำ ต้องไม่สั่งซ้ำ
        arm_service.speech_changed(False)
        arm_service.speech_changed(False)  # จบซ้ำ ต้องไม่สั่งซ้ำ
        self.assertEqual(self.gestures(), ['talk', 'rest'])

    def test_speech_end_without_start_is_noop(self):
        self.assertIsNone(arm_service.speech_changed(False))
        self.assertEqual(self.events, [])

    def test_talk_does_not_cancel_busy_window(self):
        arm_service.trigger_gesture('cheer')
        busy_until = arm_service.arm_state['busy_until']
        arm_service.speech_changed(True)
        self.assertEqual(arm_service.arm_state['busy_until'], busy_until)

    def test_talk_can_be_disabled(self):
        arm_service.ARM_TALK_ENABLED = False
        self.assertIsNone(arm_service.speech_changed(True))
        self.assertEqual(self.events, [])

    def test_led_route_drives_talk(self):
        client = app.test_client()
        client.post('/api/iot/led', json={'state': 'speaking'})
        client.post('/api/iot/led', json={'state': 'speaking'})
        client.post('/api/iot/led', json={'state': 'idle'})
        self.assertEqual(self.gestures(), ['talk', 'rest'])

    def test_extract_tag(self):
        self.assertEqual(arm_service.extract_gesture_tag('[gesture:wave] สวัสดีค่ะ'), ('สวัสดีค่ะ', 'wave'))
        self.assertEqual(arm_service.extract_gesture_tag('ยินดีค่ะ [Gesture: CHEER]'), ('ยินดีค่ะ', 'cheer'))
        self.assertEqual(arm_service.extract_gesture_tag('ไม่มีแท็ก'), ('ไม่มีแท็ก', None))
        self.assertEqual(arm_service.extract_gesture_tag(''), ('', None))

    def test_tag_unknown_or_forbidden_is_stripped_but_ignored(self):
        self.assertEqual(arm_service.extract_gesture_tag('[gesture:dance] ได้ค่ะ'), ('ได้ค่ะ', None))
        # LLM ห้ามสั่ง talk/rest เอง
        self.assertEqual(arm_service.extract_gesture_tag('[gesture:talk] ได้ค่ะ'), ('ได้ค่ะ', None))
        self.assertEqual(arm_service.extract_gesture_tag('[gesture:rest] ได้ค่ะ'), ('ได้ค่ะ', None))

    def test_tag_first_valid_wins(self):
        self.assertEqual(arm_service.extract_gesture_tag('[gesture:nope][gesture:surprise] อุ๊ย'), ('อุ๊ย', 'surprise'))

    def test_chat_response_prefers_llm_gesture(self):
        import routes.chat as chat_routes
        with app.test_request_context():
            chat_routes.send_chat_response('ทดสอบ', 'ตอบ', [], 'local_slm', 'general', 'ทั่วไป',
                                           0.9, 'test', 'th', 'smile', gesture='surprise')
        arm_events = [e for e in self.events if e['event'] == 'arm_gesture']
        self.assertEqual(arm_events[0]['gesture'], 'surprise')
        self.assertEqual(arm_events[0]['source'], 'llm_tag')


class TestHardwareStatus(unittest.TestCase):
    def setUp(self):
        arm_service.ARM_ENABLED = True
        for k in ('port', 'firmware', 'device', 'last_response', 'last_error', 'arm_l', 'arm_r', 'gesture', 'last_seen'):
            arm_service.hardware_state[k] = None
        arm_service.hardware_state['connected'] = False
        arm_service.hardware_state['last_seen_ts'] = 0.0
        self.client = app.test_client()

    def test_initially_disconnected(self):
        self.assertFalse(arm_service.get_hardware_status()['connected'])
        self.assertFalse(arm_service.trigger_gesture('rest')['hardware_connected'])

    def test_connect_report_and_response(self):
        arm_service.update_hardware({'connected': True, 'port': 'COM3'})
        self.assertTrue(arm_service.get_hardware_status()['connected'])
        arm_service.update_hardware({'response': {'device': 'ESP32_NONGPHET_IOT', 'version': '1.1.0', 'status': 'ready'}})
        hw = arm_service.get_hardware_status()
        self.assertEqual(hw['firmware'], '1.1.0')
        self.assertEqual(hw['port'], 'COM3')
        arm_service.update_hardware({'response': {'response': 'status', 'arm_l': 20, 'arm_r': 90, 'gesture': 'wave'}})
        hw = arm_service.get_hardware_status()
        self.assertEqual((hw['arm_l'], hw['arm_r'], hw['gesture']), (20, 90, 'wave'))
        self.assertTrue(arm_service.trigger_gesture('rest')['hardware_connected'])

    def test_error_response_recorded(self):
        arm_service.update_hardware({'response': {'response': 'error', 'reason': 'unknown_gesture'}})
        self.assertEqual(arm_service.get_hardware_status()['last_error'], 'unknown_gesture')

    def test_disconnect_clears_arm_values(self):
        arm_service.update_hardware({'connected': True})
        arm_service.update_hardware({'response': {'response': 'status', 'arm_l': 50, 'arm_r': 50}})
        arm_service.update_hardware({'connected': False})
        hw = arm_service.get_hardware_status()
        self.assertFalse(hw['connected'])
        self.assertIsNone(hw['arm_l'])

    def test_goes_stale_without_heartbeat(self):
        arm_service.update_hardware({'connected': True})
        arm_service.hardware_state['last_seen_ts'] -= arm_service.HARDWARE_STALE_SEC + 5
        self.assertFalse(arm_service.get_hardware_status()['connected'])

    def test_hardware_route(self):
        res = self.client.post('/api/arm/hardware', json={'connected': True, 'port': '/dev/ttyUSB0'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(self.client.get('/api/arm/hardware').get_json()['hardware']['connected'])
        self.assertTrue(self.client.get('/api/arm/status').get_json()['arm']['hardware']['connected'])

    def test_hardware_route_requires_pin_remotely(self):
        res = self.client.post('/api/arm/hardware', json={'connected': True},
                               environ_overrides={'REMOTE_ADDR': '10.0.0.9'})
        self.assertEqual(res.status_code, 403)
        self.assertFalse(arm_service.get_hardware_status()['connected'])

    def test_dashboard_has_arm_panel(self):
        res = self.client.get('/admin')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'armPanel', res.data)


class TestBridgeProtocol(unittest.TestCase):
    def test_led_state_mapping(self):
        f = esp32_listener.event_to_serial_command
        self.assertEqual(f({'event': 'led_state_changed', 'state': 'listening'}), {'cmd': 'set_led', 'state': 'idle'})
        self.assertIsNone(f({'event': 'led_state_changed', 'state': 'weird'}))
        for s in ('idle', 'speaking', 'thinking', 'off'):
            self.assertEqual(f({'event': 'led_state_changed', 'state': s}), {'cmd': 'set_led', 'state': s})

    def test_event_translation(self):
        f = esp32_listener.event_to_serial_command
        self.assertEqual(f({'event': 'arm_gesture', 'gesture': 'wave'}), {'cmd': 'arm', 'gesture': 'wave'})
        self.assertEqual(
            f({'event': 'arm_pose', 'side': 'L', 'angle': 90, 'speed': 60}),
            {'cmd': 'arm', 'side': 'L', 'angle': 90, 'speed': 60})
        self.assertEqual(f({'event': 'led_state_changed', 'state': 'speaking'}),
                         {'cmd': 'set_led', 'state': 'speaking'})
        self.assertIsNone(f({'event': 'emotion_changed', 'state': 'smile'}))

    def test_serial_json_is_compact(self):
        class FakeSerial:
            is_open = True
            written = b''
            def write(self, data): self.written += data
            def flush(self): pass
        ser = FakeSerial()
        esp32_listener.send_command_to_esp32(ser, {'cmd': 'arm', 'gesture': 'wave'})
        self.assertEqual(ser.written, b'{"cmd":"arm","gesture":"wave"}\n')


if __name__ == '__main__':
    unittest.main()
