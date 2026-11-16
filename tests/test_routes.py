# -*- coding: utf-8 -*-
"""
tests/test_routes.py — Integration Tests for Flask API Endpoints
"""
import unittest
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_new import app

class TestFlaskRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_health_check(self):
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'healthy')
        self.assertIn('uptime_seconds', data)

    def test_index_page(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'text/html', res.content_type.encode('utf-8'))

    def test_kiosk_page(self):
        res = self.client.get('/kiosk')
        self.assertEqual(res.status_code, 200)

    def test_iot_status(self):
        res = self.client.get('/api/iot/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('connected', data)
        self.assertIn('led_mode', data)

    def test_emotion_state_get_and_post(self):
        # GET
        res = self.client.get('/api/emotion/state')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('current_state', data)

        # POST
        res_post = self.client.post('/api/emotion/state', json={'state': 'happy'})
        self.assertEqual(res_post.status_code, 200)
        data_post = res_post.get_json()
        self.assertEqual(data_post.get('current_state'), 'happy')

    def test_analytics_api(self):
        res = self.client.get('/api/analytics')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('data', data)
        self.assertIn('telemetry', data)

    def test_chat_empty_message(self):
        res = self.client.post('/chat', json={'message': ''})
        self.assertEqual(res.status_code, 400)

    def test_chat_local_response(self):
        # Local rule / RAG should respond immediately without Cloud API error
        res = self.client.post('/chat', json={'message': 'สวัสดีครับน้องเพชร'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('reply', data)
        self.assertEqual(data.get('status'), 'success')

    def test_knowledge_admin_page(self):
        res = self.client.get('/admin/knowledge')
        self.assertEqual(res.status_code, 200)

    def test_kb_stats_and_entries_api(self):
        res_stats = self.client.get('/api/kb/stats')
        self.assertEqual(res_stats.status_code, 200)
        data_stats = res_stats.get_json()
        self.assertEqual(data_stats.get('status'), 'success')
        self.assertIn('total_entries', data_stats.get('stats', {}))

        res_entries = self.client.get('/api/kb/entries')
        self.assertEqual(res_entries.status_code, 200)
        data_entries = res_entries.get_json()
        self.assertGreater(data_entries.get('total', 0), 0)

    def test_kb_live_query_api(self):
        res = self.client.post('/api/kb/test_query', json={'query': 'เขาวังเปิดกี่โมง'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'matched')
        self.assertIn('เขาวัง', data.get('title', ''))

    def test_vision_status_standby(self):
        res = self.client.get('/api/vision/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('status', data)
        self.assertIn('data', data)

    def test_emotion_gaze(self):
        res = self.client.post('/api/emotion/gaze', json={'x': 0.35, 'y': -0.2})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn(data.get('status'), ['ok', 'success'])
        self.assertAlmostEqual(data.get('x'), 0.35)

    def test_iot_trigger_auto_greeting(self):
        res = self.client.post('/api/iot/trigger', json={
            'event': 'person_detected',
            'distance': 115,
            'source': 'vision_daemon'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn(data.get('status'), ['received', 'success'])
        self.assertIn('led_command', data)

    def test_iot_trigger_user_left(self):
        res = self.client.post('/api/iot/trigger', json={
            'event': 'user_left',
            'source': 'vision_daemon'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn(data.get('status'), ['received', 'success'])
        self.assertEqual(data.get('user_present'), False)

    def test_tts_empty(self):
        res = self.client.post('/tts', json={'text': ''})
        self.assertEqual(res.status_code, 400)

    def test_tts_filler_endpoint(self):
        res = self.client.get('/api/tts/filler')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertTrue('text' in data)
        self.assertTrue('audio_base64' in data)

if __name__ == '__main__':
    unittest.main()

