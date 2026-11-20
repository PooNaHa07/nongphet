# -*- coding: utf-8 -*-
"""
tests/test_performance.py — การปรับให้ลื่นบน Raspberry Pi 5:
analytics แบบ atomic/debounce, Local SLM จำกัดเวลา/โมเดล, Edge-TTS circuit breaker, gunicorn 1 worker
"""
import os
import sys
import json
import time
import asyncio
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import local_slm
from services import analytics_service, tts_service


class TestAnalyticsWrites(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'analytics.json')
        self._orig_file = analytics_service.ANALYTICS_FILE
        self._orig_delay = analytics_service.SAVE_DEBOUNCE_SEC
        # เทสต์ก่อนหน้า (ที่เรียก /chat) อาจทิ้งการบันทึกที่รอเขียนไว้: ยกเลิกก่อน เทสต์นี้จะได้นับได้ถูก
        with analytics_service._save_lock:
            if analytics_service._save_timer is not None:
                analytics_service._save_timer.cancel()
                analytics_service._save_timer = None
        analytics_service.ANALYTICS_FILE = self.path

    def tearDown(self):
        analytics_service.flush_analytics()
        analytics_service.ANALYTICS_FILE = self._orig_file
        analytics_service.SAVE_DEBOUNCE_SEC = self._orig_delay

    def test_immediate_write_is_valid_json_without_tmp_leftover(self):
        analytics_service.save_analytics(immediate=True)
        with open(self.path, encoding='utf-8') as f:
            self.assertIn('total_interactions', json.load(f))
        self.assertFalse(os.path.exists(self.path + '.tmp'))

    def test_burst_of_saves_is_coalesced(self):
        analytics_service.SAVE_DEBOUNCE_SEC = 0.2
        with mock.patch.object(analytics_service, '_write_now', wraps=analytics_service._write_now) as w:
            for _ in range(20):
                analytics_service.save_analytics()
            self.assertEqual(w.call_count, 0)   # ยังไม่เขียนทันที
            time.sleep(0.5)
            self.assertEqual(w.call_count, 1)   # 20 ครั้งรวมเป็นการเขียนเดียว
        self.assertTrue(os.path.exists(self.path))

    def test_flush_writes_pending(self):
        analytics_service.SAVE_DEBOUNCE_SEC = 30
        analytics_service.save_analytics()
        self.assertFalse(os.path.exists(self.path))
        analytics_service.flush_analytics()
        self.assertTrue(os.path.exists(self.path))


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class TestLocalSLM(unittest.TestCase):
    def setUp(self):
        local_slm._status_cache.update(ts=0.0, running=False)
        local_slm._models_cache.update(ts=0.0, models=[])
        self._enabled = local_slm.LOCAL_SLM_ENABLED
        self._explicit = local_slm.EXPLICIT_MODEL
        local_slm.LOCAL_SLM_ENABLED = True   # ทดสอบตอนเปิดใช้ ไม่ขึ้นกับ LOCAL_SLM_ENABLED ใน .env ของเครื่อง

    def tearDown(self):
        local_slm.LOCAL_SLM_ENABLED = self._enabled
        local_slm.EXPLICIT_MODEL = self._explicit
        local_slm._status_cache.update(ts=0.0, running=False)
        local_slm._models_cache.update(ts=0.0, models=[])

    def tags(self, *names):
        return _Resp(200, {'models': [{'name': n} for n in names]})

    def test_disabled_skips_network(self):
        local_slm.LOCAL_SLM_ENABLED = False
        with mock.patch.object(local_slm.httpx, 'get') as g:
            self.assertFalse(local_slm.is_ollama_running())
            g.assert_not_called()

    def test_status_and_models_cached(self):
        with mock.patch.object(local_slm.httpx, 'get', return_value=self.tags('qwen2.5:1.5b')) as g:
            for _ in range(5):
                self.assertTrue(local_slm.is_ollama_running())
                local_slm.select_best_local_model()
            self.assertEqual(g.call_count, 1)

    def test_prefers_small_models_and_never_picks_big_ones(self):
        with mock.patch.object(local_slm.httpx, 'get', return_value=self.tags('gemma3:4b', 'qwen2.5:1.5b')):
            self.assertEqual(local_slm.select_best_local_model(), 'qwen2.5:1.5b')
        local_slm._models_cache.update(ts=0.0, models=[])
        with mock.patch.object(local_slm.httpx, 'get', return_value=self.tags('gemma3:4b', 'scb10x/typhoon2:latest')):
            self.assertEqual(local_slm.select_best_local_model(), local_slm.DEFAULT_MODEL)

    def test_explicit_model_wins(self):
        local_slm.EXPLICIT_MODEL = 'gemma3:4b'
        with mock.patch.object(local_slm.httpx, 'get', return_value=self.tags('qwen2.5:1.5b', 'gemma3:4b')):
            self.assertEqual(local_slm.select_best_local_model(), 'gemma3:4b')

    def test_request_uses_limits_and_keep_alive(self):
        local_slm._status_cache.update(ts=time.time(), running=True)
        local_slm._models_cache.update(ts=time.time(), models=['qwen2.5:1.5b'])
        ok = _Resp(200, {'message': {'content': 'สวัสดีค่ะ'}})
        with mock.patch.object(local_slm.httpx, 'post', return_value=ok) as p:
            res = local_slm.generate_local_response('สวัสดี')
        self.assertEqual(res['reply'], 'สวัสดีค่ะ')
        payload = p.call_args.kwargs['json']
        self.assertEqual(payload['options']['num_predict'], local_slm.MAX_TOKENS)
        self.assertEqual(payload['keep_alive'], local_slm.KEEP_ALIVE)
        self.assertEqual(p.call_args.kwargs['timeout'], local_slm.REQUEST_TIMEOUT)

    def test_timeout_backs_off(self):
        local_slm._status_cache.update(ts=time.time(), running=True)
        local_slm._models_cache.update(ts=time.time(), models=['qwen2.5:1.5b'])
        with mock.patch.object(local_slm.httpx, 'post', side_effect=httpx.ReadTimeout('slow')):
            self.assertIsNone(local_slm.generate_local_response('อธิบายยาวๆ'))
        # คำถามถัดไปต้องข้าม SLM ทันที โดยไม่ยิง HTTP เช็กสถานะ
        with mock.patch.object(local_slm.httpx, 'get') as g:
            self.assertFalse(local_slm.is_ollama_running())
            g.assert_not_called()


class TestEdgeTTSBreaker(unittest.TestCase):
    def setUp(self):
        tts_service._mark_edge_ok()

    def tearDown(self):
        tts_service._mark_edge_ok()

    def test_network_error_classification(self):
        self.assertTrue(tts_service._is_network_error(asyncio.TimeoutError()))
        self.assertTrue(tts_service._is_network_error(OSError('getaddrinfo failed')))
        self.assertTrue(tts_service._is_network_error(Exception('Cannot connect to host speech.platform.bing.com')))
        self.assertFalse(tts_service._is_network_error(Exception('No audio was received')))

    def test_network_failure_trips_breaker_without_retry(self):
        calls = []

        class FailingCommunicate:
            def __init__(self, *a, **k):
                calls.append(1)

            async def stream(self):
                raise OSError('getaddrinfo failed')
                yield  # pragma: no cover

        with mock.patch.object(tts_service.edge_tts, 'Communicate', FailingCommunicate):
            with self.assertRaises(tts_service.EdgeTTSOffline):
                asyncio.run(tts_service.generate_edge_tts('ทดสอบ', retries=3))
        self.assertEqual(len(calls), 1)          # ไม่ลองซ้ำเมื่อเน็ตล่ม
        self.assertFalse(tts_service.edge_tts_available())

        # ระหว่างพัก: ไม่แตะเครือข่ายเลย
        with mock.patch.object(tts_service.edge_tts, 'Communicate') as comm:
            with self.assertRaises(tts_service.EdgeTTSOffline):
                asyncio.run(tts_service.generate_edge_tts('ทดสอบ'))
            comm.assert_not_called()

    def test_timeout_scales_with_text_length(self):
        self.assertEqual(tts_service.edge_timeout_for('สั้น'), 6.0)
        self.assertGreater(tts_service.edge_timeout_for('ก' * 1200), 20.0)
        self.assertLessEqual(tts_service.edge_timeout_for('ก' * 100000), 45.0)

    def test_slow_but_working_stream_does_not_trip_breaker(self):
        class SlowCommunicate:
            def __init__(self, *a, **k):
                pass

            async def stream(self):
                yield {'type': 'audio', 'data': b'partial'}
                await asyncio.sleep(5)   # ส่งเสียงมาบางส่วนแล้วช้า (ข้อความยาว) ไม่ใช่เน็ตล่ม

        with mock.patch.object(tts_service.edge_tts, 'Communicate', SlowCommunicate), \
             mock.patch.object(tts_service, 'edge_timeout_for', return_value=0.2):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(tts_service.generate_edge_tts('ข้อความยาว', retries=1))
        self.assertNotIsInstance(ctx.exception, tts_service.EdgeTTSOffline)
        self.assertTrue(tts_service.edge_tts_available())

    def test_stalled_connection_is_reopened(self):
        """การเชื่อมต่อแรกค้าง (ไม่มีเสียง) -> เปิดใหม่ทันทีและได้เสียง โดยไม่พักระบบ"""
        calls = []

        class FlakyCommunicate:
            def __init__(self, *a, **k):
                calls.append(1)
                self.n = len(calls)

            async def stream(self):
                if self.n == 1:
                    await asyncio.sleep(5)        # ค้าง
                yield {'type': 'audio', 'data': b'ok-audio'}

        with mock.patch.object(tts_service.edge_tts, 'Communicate', FlakyCommunicate), \
             mock.patch.object(tts_service, 'FIRST_AUDIO_TIMEOUT', 0.2):
            start = time.time()
            audio = asyncio.run(tts_service.generate_edge_tts('สวัสดีค่ะ'))
        self.assertEqual(audio, b'ok-audio')
        self.assertEqual(len(calls), 2)
        self.assertLess(time.time() - start, 2.0)
        self.assertTrue(tts_service.edge_tts_available())

    def test_stalls_on_every_attempt_trip_breaker(self):
        class HangingCommunicate:
            def __init__(self, *a, **k):
                pass

            async def stream(self):
                await asyncio.sleep(5)
                yield {'type': 'audio', 'data': b'never'}

        with mock.patch.object(tts_service.edge_tts, 'Communicate', HangingCommunicate), \
             mock.patch.object(tts_service, 'FIRST_AUDIO_TIMEOUT', 0.1):
            with self.assertRaises(tts_service.EdgeTTSOffline):
                asyncio.run(tts_service.generate_edge_tts('สวัสดีค่ะ', retries=3))
        self.assertFalse(tts_service.edge_tts_available())

    def test_tts_route_answers_fast_when_offline(self):
        from app_new import app
        tts_service._mark_edge_offline()
        client = app.test_client()
        start = time.time()
        res = client.post('/tts', json={'text': 'ข้อความที่ไม่มีในแคชแน่นอน %f' % time.time()})
        elapsed = time.time() - start
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.get_json()['status'], 'no_voice')
        self.assertLess(elapsed, 1.0)


class TestServerConfig(unittest.TestCase):
    def test_gunicorn_single_worker_enough_threads(self):
        cfg = {}
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gunicorn.conf.py')
        with open(path, encoding='utf-8') as f:
            exec(compile(f.read(), path, 'exec'), cfg)
        self.assertEqual(cfg['workers'], 1)
        self.assertGreaterEqual(cfg['threads'], 16)


if __name__ == '__main__':
    unittest.main()
