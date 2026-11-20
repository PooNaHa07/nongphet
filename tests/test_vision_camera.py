# -*- coding: utf-8 -*-
"""
tests/test_vision_camera.py — หากล้องเองเมื่อเสียบทีหลัง / กล้องหลุด (ไม่ต้องรันระบบใหม่)
ไม่ใช้กล้องจริง: จำลอง cv2.VideoCapture
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vision_daemon as vd


class FakeCap:
    def __init__(self, opened=True, frame_ok=True):
        self.opened, self.frame_ok, self.released, self.props = opened, frame_ok, False, {}

    def isOpened(self):
        return self.opened and not self.released

    def read(self):
        return (True, vd.np.zeros((2, 2, 3), dtype=vd.np.uint8)) if self.frame_ok else (False, None)

    def set(self, k, v):
        self.props[k] = v

    def release(self):
        self.released = True


@unittest.skipUnless(vd.CV2_AVAILABLE, 'OpenCV not installed')
class TestOpenCamera(unittest.TestCase):
    def test_no_camera_returns_none_and_releases(self):
        caps = []

        def fake(*a):
            caps.append(FakeCap(opened=False))
            return caps[-1]
        with mock.patch.object(vd.cv2, 'VideoCapture', side_effect=fake):
            self.assertIsNone(vd.open_camera(0, quiet=True))
        self.assertEqual(len(caps), len(vd._camera_candidates(0)))
        self.assertTrue(all(c.released for c in caps))

    def test_camera_that_cannot_read_is_skipped(self):
        seq = [FakeCap(frame_ok=False), FakeCap()]
        with mock.patch.object(vd.cv2, 'VideoCapture', side_effect=lambda *a: seq.pop(0)):
            cap = vd.open_camera(0)
        self.assertIsNotNone(cap)
        self.assertEqual(cap.props.get(vd.cv2.CAP_PROP_FRAME_WIDTH), vd.TARGET_WIDTH)

    def test_quiet_restores_opencv_log_level(self):
        before = vd.cv2.utils.logging.getLogLevel()
        with mock.patch.object(vd.cv2, 'VideoCapture', side_effect=lambda *a: FakeCap(opened=False)):
            vd.open_camera(0, quiet=True)
        self.assertEqual(vd.cv2.utils.logging.getLogLevel(), before)

    def test_no_camera_frame_size(self):
        self.assertEqual(vd.no_camera_frame(1.0).shape, (vd.TARGET_HEIGHT, vd.TARGET_WIDTH, 3))

    def test_missing_camera_is_not_simulated_visitor(self):
        # ไม่พบกล้องต้องไม่สลับเป็นโหมดจำลอง (ผู้มาเยือนจำลองทำให้หุ่นทักทายคนที่ไม่มีอยู่จริง)
        src = open(vd.__file__, encoding='utf-8').read()
        self.assertNotIn('simulate = True', src)


if __name__ == '__main__':
    unittest.main()
