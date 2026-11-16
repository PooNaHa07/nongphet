"""
Unit tests for Vision Daemon Attention Gating and Head Pose Estimation
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vision_daemon import estimate_head_pose_and_attention


class TestAttentionGating(unittest.TestCase):
    def test_direct_eye_contact_landmarks(self):
        # 5 Landmarks: [r_eye, l_eye, nose, r_mouth, l_mouth]
        # Direct eye contact: Right eye at (120, 100), Left eye at (200, 100), Nose exactly at (160, 130)
        landmarks = [
            (120, 100),  # Right eye
            (200, 100),  # Left eye
            (160, 130),  # Nose (centered: dist_r = 40, dist_l = 40)
            (130, 170),  # Right mouth
            (190, 170)   # Left mouth
        ]
        is_attentive, score, yaw, pitch = estimate_head_pose_and_attention(
            landmarks, bbox=(100, 80, 120, 120), frame_w=640, frame_h=480
        )
        self.assertTrue(is_attentive)
        self.assertGreaterEqual(score, 0.70)
        self.assertAlmostEqual(yaw, 0.0, delta=5.0)

    def test_looking_away_landmarks(self):
        # Visitor looking far to the side (e.g. walking down the hallway)
        # Nose shifted heavily to the left: right eye at (120, 100), left eye at (200, 100), nose at (130, 130)
        landmarks = [
            (120, 100),
            (200, 100),
            (130, 130),  # Nose very close to right eye -> large yaw bias
            (125, 170),
            (175, 170)
        ]
        is_attentive, score, yaw, pitch = estimate_head_pose_and_attention(
            landmarks, bbox=(100, 80, 120, 120), frame_w=640, frame_h=480
        )
        self.assertFalse(is_attentive, "Person looking away should not trigger attention gate")
        self.assertGreater(abs(yaw), 22.0)

    def test_bbox_center_fallback(self):
        # Person in dead center of the frame
        is_attentive, score, yaw, pitch = estimate_head_pose_and_attention(
            landmarks=None, bbox=(270, 190, 100, 100), frame_w=640, frame_h=480
        )
        self.assertTrue(is_attentive)
        self.assertGreaterEqual(score, 0.60)

    def test_bbox_edge_fallback(self):
        # Person at the far edge of the frame (passing by)
        is_attentive, score, yaw, pitch = estimate_head_pose_and_attention(
            landmarks=None, bbox=(20, 190, 100, 100), frame_w=640, frame_h=480
        )
        self.assertFalse(is_attentive)
        self.assertLess(score, 0.60)


if __name__ == '__main__':
    unittest.main()
