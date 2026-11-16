#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
โครงการ: น้องเพชร AI Smart Guide (Nong Phet AI Assistant)
โมดูล: ระบบมองเห็นอัจฉริยะและการทักทายอัตโนมัติ (vision_daemon.py)
เป้าหมายฮาร์ดแวร์: Raspberry Pi 5 + USB Webcam / CSI Camera
==============================================================================
ความสามารถหลัก:
1. การตรวจจับบุคคล/ใบหน้าแบบ Real-time (YOLOv8n / MediaPipe / OpenCV Cascade)
2. ระบบทักทายอัตโนมัติ (Auto Greeting) เมื่อตรวจพบคนเดินเข้ามาในระยะ 1.5 - 2.5 เมตร
3. ระบบสบตาและหันมองตามคน (Gaze & Face Tracking) ส่งพิกัดไปยังจอแสดงอารมณ์
4. การตรวจจับภาษามือ/ท่าทาง (Gesture Recognition)
5. บริการ Live MJPEG Video Stream (พอร์ต 5002) สำหรับมอนิเตอร์บน Dashboard
6. โหมดจำลอง (--simulate) สำหรับทดสอบบนคอมพิวเตอร์ที่ไม่มีกล้อง
==============================================================================
"""

import sys
import os
import time
import json
import math
import queue
import argparse
import threading
import datetime
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# จัดการ UTF-8 บน Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# พยายามนำเข้า OpenCV
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# พยายามนำเข้า Ultralytics YOLOv8
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

# พยายามนำเข้า MediaPipe
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False


# กำหนดค่าคงที่ของระบบ
FLASK_IOT_TRIGGER_URL = "http://127.0.0.1:5000/api/iot/trigger"
FLASK_GAZE_URL = "http://127.0.0.1:5000/api/emotion/gaze"
GREETING_COOLDOWN_SEC = 12.0
CONSECUTIVE_FRAMES_TRIGGER = 2
CONSECUTIVE_ATTENTION_TRIGGER = 2
TARGET_WIDTH = 640
TARGET_HEIGHT = 480

# --- การจำกัดภาระ CPU (สำคัญบน Raspberry Pi 5 ที่ต้องแบ่ง CPU ให้ Chromium/Flask/TTS) ---
# ตรวจจับใบหน้า N ครั้ง/วินาที (กล้องยังอ่านเต็มความเร็วเพื่อให้ได้ภาพล่าสุดเสมอ แต่ถอดรหัส+ตรวจจับเฉพาะรอบที่ถึงเวลา)
DETECT_FPS = max(1.0, float(os.environ.get('VISION_DETECT_FPS', '10')))
# เข้ารหัส JPEG สำหรับสตรีมสูงสุด N ครั้ง/วินาที และเฉพาะตอนมีคนดูสตรีม/ขอ snapshot เท่านั้น
STREAM_FPS = max(1.0, float(os.environ.get('VISION_STREAM_FPS', '10')))
SNAPSHOT_KEEPALIVE_SEC = 5.0
# จำนวนเธรดที่ OpenCV ใช้ (ค่าเริ่มต้นของ OpenCV คือทุกคอร์ ซึ่งแย่ง CPU กับระบบอื่น)
CV_THREADS = int(os.environ.get('VISION_CV_THREADS', '2'))
if CV2_AVAILABLE:
    try:
        cv2.setNumThreads(CV_THREADS)
    except Exception:
        pass

# คลังภาพและสตรีมล่าสุดสำหรับ Web Streaming
LATEST_FRAME_JPEG = None
LATEST_FRAME_TS = 0.0
FRAME_LOCK = threading.Lock()
STREAM_CLIENTS = 0                 # จำนวนผู้ชม /video_feed ที่เปิดอยู่
LAST_SNAPSHOT_REQUEST = 0.0        # เวลาที่มีคนขอ /snapshot.jpg ล่าสุด
VISION_STATE = {
    "active": False,
    "backend": "none",
    "fps": 0.0,
    "person_detected": False,
    "distance_cm": None,
    "gaze_x": 0.0,
    "gaze_y": 0.0,
    "total_greetings": 0,
    "last_greeting_time": None,
    "gesture_detected": None,
    "auto_greeting_enabled": True,
    "is_looking_at_screen": False,
    "attention_score": 0.0,
    "head_yaw_deg": 0.0
}


# -----------------------------------------------------------------------------
# Non-blocking HTTP Event Dispatcher with Worker Queue
# -----------------------------------------------------------------------------
_HTTP_QUEUE = queue.Queue(maxsize=15)

def _http_dispatcher_worker():
    while True:
        try:
            url, payload, timeout = _HTTP_QUEUE.get()
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json', 'User-Agent': 'NongPhetVision/2026'}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read()
        except Exception:
            pass
        finally:
            _HTTP_QUEUE.task_done()

threading.Thread(target=_http_dispatcher_worker, daemon=True, name="VisionHttpDispatcher").start()

def send_http_json(url, payload, timeout=1.5):
    """ส่งข้อมูล JSON ไปยัง Flask Backend API แบบ Non-blocking ผ่านคิวงานเดี่ยว ป้องกันเธรดสะสม"""
    try:
        _HTTP_QUEUE.put_nowait((url, payload, timeout))
    except queue.Full:
        pass  # ละเว้นหากคิวเต็ม เพื่อรักษาความลื่นไหลของระบบกล้อง


class StreamingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class VideoStreamHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler สำหรับส่งต่อ Live MJPEG Video Stream ไปยังหน้าเว็บแดชบอร์ด"""
    def do_GET(self):
        global LATEST_FRAME_JPEG, STREAM_CLIENTS, LAST_SNAPSHOT_REQUEST
        if self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            with FRAME_LOCK:
                STREAM_CLIENTS += 1   # ลูปหลักจะเริ่มเข้ารหัส JPEG เมื่อมีผู้ชมอย่างน้อย 1 คน
            last_sent_ts = 0.0
            try:
                while True:
                    with FRAME_LOCK:
                        frame = LATEST_FRAME_JPEG
                        frame_ts = LATEST_FRAME_TS
                    # ส่งเฉพาะเฟรมใหม่ ไม่ส่งภาพซ้ำเปลืองแบนด์วิดท์
                    if frame and frame_ts > last_sent_ts:
                        last_sent_ts = frame_ts
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', str(len(frame)))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                    time.sleep(1.0 / STREAM_FPS / 2)
            except Exception:
                pass
            finally:
                with FRAME_LOCK:
                    STREAM_CLIENTS = max(0, STREAM_CLIENTS - 1)

        elif self.path == '/snapshot.jpg':
            # ปลุกการเข้ารหัส JPEG แล้วรอเฟรมใหม่สั้นๆ (ถ้าไม่มีใครดูสตรีม ลูปหลักจะไม่ได้เข้ารหัสไว้)
            requested_at = time.time()
            LAST_SNAPSHOT_REQUEST = requested_at
            deadline = requested_at + 0.8
            while time.time() < deadline:
                with FRAME_LOCK:
                    if LATEST_FRAME_TS >= requested_at:
                        break
                time.sleep(0.02)
            with FRAME_LOCK:
                frame = LATEST_FRAME_JPEG
            if frame:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
            else:
                self.send_error(404, "No frame available")

        elif self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(VISION_STATE).encode('utf-8'))

        elif self.path in ('/toggle_greeting', '/api/toggle_greeting'):
            VISION_STATE["auto_greeting_enabled"] = not VISION_STATE.get("auto_greeting_enabled", True)
            print(f"🔘 [Vision Daemon] สลับสถานะทักทายอัตโนมัติ: {VISION_STATE['auto_greeting_enabled']}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "auto_greeting_enabled": VISION_STATE["auto_greeting_enabled"]}).encode('utf-8'))

        elif self.path in ('/disable_greeting', '/api/disable_greeting'):
            VISION_STATE["auto_greeting_enabled"] = False
            print("🔕 [Vision Daemon] ปิดระบบทักทายอัตโนมัติแล้ว")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "auto_greeting_enabled": False}).encode('utf-8'))

        elif self.path in ('/enable_greeting', '/api/enable_greeting'):
            VISION_STATE["auto_greeting_enabled"] = True
            print("🔔 [Vision Daemon] เปิดระบบทักทายอัตโนมัติแล้ว")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "auto_greeting_enabled": True}).encode('utf-8'))

        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # ปิดการพิมพ์ log ของ HTTP server เพื่อลดข้อความใน console


def start_stream_server(port=5002):
    """เริ่มรัน MJPEG Streaming HTTP Server ใน Background Thread"""
    try:
        server = StreamingServer(('0.0.0.0', port), VideoStreamHandler)
        print(f"📡 [Vision Stream] Live MJPEG server running at http://0.0.0.0:{port}/video_feed")
        t = threading.Thread(target=server.serve_forever, daemon=True, name="MJPEG-Streamer")
        t.start()
    except Exception as e:
        print(f"⚠️ [Vision Stream Error] Could not start MJPEG server on port {port}: {e}")


def estimate_head_pose_and_attention(landmarks, bbox=None, frame_w=TARGET_WIDTH, frame_h=TARGET_HEIGHT):
    """
    ประเมินทิศทางการหันหน้า (Head Pose / Yaw & Pitch) และคะแนนความสนใจมองจอ (Attention Score)
    เพื่อตรวจสอบว่าผู้ใช้กำลังมองตรงมาที่จอคีออสจริงหรือไม่ (Attention-Gated Perception)
    คืนค่า:
      - is_attentive (bool): กำลังมองตรงมาที่จอคีออสหรือไม่
      - attention_score (float 0.0 - 1.0): ดัชนีความตั้งใจมองจอ
      - yaw_deg (float): องศาการหันหน้าซ้าย-ขวา (-50° ถึง +50°)
      - pitch_deg (float): องศาการก้ม-เงย
    """
    if landmarks:
        r_eye = None
        l_eye = None
        nose = None
        if isinstance(landmarks, dict):
            if 'right_eye' in landmarks and 'left_eye' in landmarks and 'nose' in landmarks:
                r_eye = landmarks['right_eye']
                l_eye = landmarks['left_eye']
                nose = landmarks['nose']
        elif isinstance(landmarks, (list, tuple)) and len(landmarks) >= 3:
            r_eye = landmarks[0]
            l_eye = landmarks[1]
            nose = landmarks[2]

        if r_eye and l_eye and nose:
            eye_dx = l_eye[0] - r_eye[0]
            eye_dy = l_eye[1] - r_eye[1]
            eye_dist = math.hypot(eye_dx, eye_dy)
            if eye_dist >= 8.0:
                dist_r_nose = abs(nose[0] - r_eye[0])
                dist_l_nose = abs(l_eye[0] - nose[0])
                total_eye_span = max(dist_r_nose + dist_l_nose, 1.0)

                # yaw_bias: ค่า 0.0 คือมองตรงเข้าหากล้องเป๊ะๆ สมมาตรสองข้าง
                yaw_bias = (dist_r_nose - dist_l_nose) / total_eye_span
                yaw_deg = round(yaw_bias * 50.0, 1)

                eye_mid_y = (r_eye[1] + l_eye[1]) / 2.0
                nose_dy = nose[1] - eye_mid_y
                pitch_ratio = nose_dy / max(eye_dist, 1.0)
                pitch_deg = round((pitch_ratio - 0.40) * 45.0, 1)

                yaw_penalty = min(1.0, abs(yaw_deg) / 30.0)
                pitch_penalty = min(1.0, abs(pitch_deg) / 28.0)
                attention_score = max(0.0, min(1.0, 1.0 - (0.75 * yaw_penalty + 0.25 * pitch_penalty)))
                attention_score = round(attention_score, 2)

                # สบตามองจอจริง: คะแนน >= 0.58 และองศาการหันหน้าไม่เกิน ±22 องศา
                is_attentive = (attention_score >= 0.58) and (abs(yaw_deg) <= 22.0)
                return is_attentive, attention_score, yaw_deg, pitch_deg

    # Fallback กรณีไม่มี Landmark ละเอียด (เช่น YOLO หรือ Cascade):
    # ประเมินจากตำแหน่งกึ่งกลางภาพ (Central Proximity Proxy)
    if bbox is not None:
        bx, by, bw, bh = bbox
        cx = bx + bw / 2.0
        center_norm = (cx - (frame_w / 2.0)) / (frame_w / 2.0)
        yaw_proxy = round(center_norm * 25.0, 1)
        att_proxy = round(max(0.0, min(1.0, 1.0 - abs(center_norm) * 0.7)), 2)
        is_attentive = att_proxy >= 0.60
        return is_attentive, att_proxy, yaw_proxy, 0.0

    return True, 0.75, 0.0, 0.0


class VisionDetector:
    """ตัวจัดการการตรวจจับใบหน้า วัตถุ และบุคคล (Multi-Backend: YuNet ONNX / YOLOv8 / MediaPipe / OpenCV Cascade / Skin Centroid)"""
    def __init__(self, preferred_backend="auto"):
        self.backend = "none"
        self.yunet_detector = None
        self.yunet_input_size = None
        self.yolo_model = None
        self.face_cascade = None
        self.mp_face = None
        self.mp_hands = None

        # 1. ลำดับที่ 1: OpenCV YuNet (Deep Learning Face Detector ONNX) — แม่นยำสูง รวดเร็ว และคำนวณ Landmark ได้
        yunet_path = os.path.join(os.path.dirname(__file__), "models", "face_detection_yunet_2023mar.onnx")
        if preferred_backend in ("yunet", "auto") and CV2_AVAILABLE and hasattr(cv2, 'FaceDetectorYN') and os.path.exists(yunet_path):
            try:
                print(f"🚀 [Vision Engine] กำลังโหลดโมเดล OpenCV YuNet ONNX ({yunet_path})...")
                self.yunet_input_size = (TARGET_WIDTH, TARGET_HEIGHT)
                self.yunet_detector = cv2.FaceDetectorYN.create(
                    model=yunet_path,
                    config="",
                    input_size=self.yunet_input_size,
                    score_threshold=0.6,
                    nms_threshold=0.3,
                    top_k=5000
                )
                self.backend = "yunet"
                print("✅ [Vision Engine] โหลด OpenCV YuNet ONNX สำเร็จ (High-Precision Deep Learning Mode)")
                return
            except Exception as e:
                print(f"ℹ️ [Vision Engine] ไม่สามารถโหลด YuNet: {e}")

        # 2. ลำดับที่ 2: Ultralytics YOLOv8 (Person Detection)
        if preferred_backend in ("yolo", "auto") and YOLO_AVAILABLE:
            try:
                print("🚀 [Vision Engine] กำลังโหลดโมเดล Ultralytics YOLOv8n...")
                self.yolo_model = YOLO("yolov8n.pt")
                self.backend = "yolov8"
                print("✅ [Vision Engine] โหลด YOLOv8n สำเร็จพร้อมใช้งาน")
                return
            except Exception as e:
                print(f"ℹ️ [Vision Engine] ไม่สามารถโหลด YOLOv8: {e}")

        # 3. ลำดับที่ 3: MediaPipe Face Detection
        if preferred_backend in ("mediapipe", "auto") and MEDIAPIPE_AVAILABLE:
            try:
                print("🚀 [Vision Engine] กำลังโหลดโมเดล MediaPipe Face & Hands...")
                self.mp_face = mp.solutions.face_detection.FaceDetection(
                    model_selection=0, min_detection_confidence=0.5
                )
                self.backend = "mediapipe"
                print("✅ [Vision Engine] โหลด MediaPipe สำเร็จ")
                return
            except Exception as e:
                print(f"ℹ️ [Vision Engine] ไม่สามารถโหลด MediaPipe: {e}")

        # 4. ลำดับที่ 4: OpenCV Haar Cascade
        if CV2_AVAILABLE:
            try:
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                if os.path.exists(cascade_path):
                    self.face_cascade = cv2.CascadeClassifier(cascade_path)
                    self.backend = "opencv_cascade"
                    print("✅ [Vision Engine] โหลด OpenCV Haar Cascade สำเร็จ (High-Speed CPU Mode)")
                    return
            except Exception:
                pass

            # 5. Fallback: ระบบตรวจจับใบหน้าคนด้วย Skin-Tone YCrCb & Head Contour
            self.backend = "skin_centroid"
            print("✅ [Vision Engine] เปิดใช้งานระบบตรวจจับใบหน้าคน (Adaptive Skin Centroid & Face Tracking)")
            return

        print("⚠️ [Vision Engine] ไม่มีโมเดล AI ตรวจจับภายนอก ระบบจะทำงานในโหมด Synthetic Simulation")
        self.backend = "simulation"

    def detect(self, frame):
        """
        วิเคราะห์เฟรมภาพ คืนค่า:
        - detections: รายการ [{ 'bbox': (x, y, w, h), 'label': 'person/face', 'conf': float, 'landmarks': ... }]
        - gaze_target: (norm_x, norm_y) หรือ None
        - estimated_distance: ระยะห่างประมาณการ (cm)
        - is_attentive: ผู้ใช้กำลังหันหน้าสบตามองจอจริงหรือไม่ (Attention Gating)
        - attention_score: ดัชนีความสนใจมองจอ (0.0 - 1.0)
        - yaw_deg: องศาการหันหน้าซ้าย-ขวา (-50° ถึง +50°)
        """
        detections = []
        gaze_target = None
        estimated_distance = None
        is_attentive = False
        attention_score = 0.0
        yaw_deg = 0.0

        if frame is None:
            return detections, gaze_target, estimated_distance, is_attentive, attention_score, yaw_deg

        h_img, w_img = frame.shape[:2]

        # --- A. YuNet ONNX Deep Learning Face Detection ---
        if self.backend == "yunet" and self.yunet_detector:
            # ปรับ input_size ของ detector ให้ตรงกับขนาดเฟรมภาพจริง
            if self.yunet_input_size != (w_img, h_img):
                self.yunet_input_size = (w_img, h_img)
                self.yunet_detector.setInputSize((w_img, h_img))

            _, faces = self.yunet_detector.detect(frame)
            if faces is not None and len(faces) > 0:
                # เรียงลำดับจากขนาดใบหน้าที่ใหญ่ที่สุด (เด่นสุดหน้าระบบ)
                sorted_faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                for f in sorted_faces:
                    x = max(0, int(f[0]))
                    y = max(0, int(f[1]))
                    w = int(f[2])
                    h = int(f[3])
                    conf = float(f[14])
                    
                    # 5 Landmarks: ขวาตา (4,5), ซ้ายตา (6,7), จมูก (8,9), มุมปากขวา (10,11), มุมปากซ้าย (12,13)
                    r_eye = (float(f[4]), float(f[5]))
                    l_eye = (float(f[6]), float(f[7]))
                    nose = (float(f[8]), float(f[9]))
                    r_mouth = (float(f[10]), float(f[11]))
                    l_mouth = (float(f[12]), float(f[13]))

                    # จุดสนใจในการสบตา (เน้นตำแหน่งจมูก/ระหว่างตาสองข้าง)
                    cx = nose[0] if nose[0] > 0 else (x + w / 2.0)
                    cy = nose[1] if nose[1] > 0 else (y + h / 2.0)
                    norm_x = (cx - (w_img / 2.0)) / (w_img / 2.0)
                    norm_y = (cy - (h_img / 2.0)) / (h_img / 2.0)
                    gaze_target = (norm_x, norm_y)

                    # คำนวณระยะห่าง (Distance) จากระยะระหว่างตาสองข้าง (Inter-Pupillary Distance: ปกติคนเราห่างกัน ~6.3 cm)
                    eye_dist_px = math.hypot(l_eye[0] - r_eye[0], l_eye[1] - r_eye[1])
                    if eye_dist_px > 5:
                        calc_dist = int((500.0 * 6.3) / eye_dist_px)
                    else:
                        calc_dist = int((h_img / max(h, 1)) * 32.0)
                    estimated_distance = max(40, min(300, calc_dist))

                    lm_dict = {
                        'right_eye': r_eye,
                        'left_eye': l_eye,
                        'nose': nose,
                        'right_mouth': r_mouth,
                        'left_mouth': l_mouth
                    }
                    is_attentive, attention_score, yaw_deg, pitch_deg = estimate_head_pose_and_attention(
                        lm_dict, bbox=(x, y, w, h), frame_w=w_img, frame_h=h_img
                    )

                    detections.append({
                        'bbox': (x, y, w, h),
                        'label': 'face',
                        'conf': conf,
                        'landmarks': lm_dict,
                        'is_attentive': is_attentive,
                        'attention_score': attention_score,
                        'yaw_deg': yaw_deg,
                        'pitch_deg': pitch_deg
                    })
                    break  # โฟกัสคนที่อยู่ใกล้ที่สุดหน้าระบบ

        elif self.backend == "yolov8" and self.yolo_model:
            results = self.yolo_model(frame, verbose=False, classes=[0])  # class 0 = person
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    w = x2 - x1
                    h = y2 - y1
                    cx = x1 + w / 2.0
                    cy = y1 + h / 2.0
                    norm_x = (cx - (w_img / 2.0)) / (w_img / 2.0)
                    norm_y = (cy - (h_img / 2.0)) / (h_img / 2.0)
                    gaze_target = (norm_x, norm_y)
                    estimated_distance = max(40, min(350, int((h_img / max(h, 1)) * 90.0)))
                    is_attentive, attention_score, yaw_deg, pitch_deg = estimate_head_pose_and_attention(
                        None, bbox=(x1, y1, w, h), frame_w=w_img, frame_h=h_img
                    )
                    detections.append({
                        'bbox': (x1, y1, w, h),
                        'label': 'person',
                        'conf': conf,
                        'is_attentive': is_attentive,
                        'attention_score': attention_score,
                        'yaw_deg': yaw_deg,
                        'pitch_deg': pitch_deg
                    })
                    break

        elif self.backend == "mediapipe" and self.mp_face:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.mp_face.process(rgb)
            if results.detections:
                for det in results.detections:
                    box = det.location_data.relative_bounding_box
                    x = int(box.xmin * w_img)
                    y = int(box.ymin * h_img)
                    w = int(box.width * w_img)
                    h = int(box.height * h_img)
                    conf = det.score[0] if det.score else 0.85
                    cx = x + w / 2.0
                    cy = y + h / 2.0
                    norm_x = (cx - (w_img / 2.0)) / (w_img / 2.0)
                    norm_y = (cy - (h_img / 2.0)) / (h_img / 2.0)
                    gaze_target = (norm_x, norm_y)
                    estimated_distance = max(40, min(250, int((h_img / max(h, 1)) * 32.0)))
                    
                    lm_dict = {}
                    if hasattr(det, 'location_data') and hasattr(det.location_data, 'relative_keypoints'):
                        kps = det.location_data.relative_keypoints
                        if len(kps) >= 3:
                            lm_dict['right_eye'] = (kps[0].x * w_img, kps[0].y * h_img)
                            lm_dict['left_eye'] = (kps[1].x * w_img, kps[1].y * h_img)
                            lm_dict['nose'] = (kps[2].x * w_img, kps[2].y * h_img)
                    is_attentive, attention_score, yaw_deg, pitch_deg = estimate_head_pose_and_attention(
                        lm_dict, bbox=(x, y, w, h), frame_w=w_img, frame_h=h_img
                    )
                    detections.append({
                        'bbox': (x, y, w, h),
                        'label': 'face',
                        'conf': conf,
                        'landmarks': lm_dict,
                        'is_attentive': is_attentive,
                        'attention_score': attention_score,
                        'yaw_deg': yaw_deg,
                        'pitch_deg': pitch_deg
                    })
                    break

        elif self.backend == "opencv_cascade" and self.face_cascade:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(45, 45))
            for (x, y, w, h) in faces:
                cx = x + w / 2.0
                cy = y + h / 2.0
                norm_x = (cx - (w_img / 2.0)) / (w_img / 2.0)
                norm_y = (cy - (h_img / 2.0)) / (h_img / 2.0)
                gaze_target = (norm_x, norm_y)
                estimated_distance = max(40, min(250, int((h_img / max(h, 1)) * 32.0)))
                is_attentive, attention_score, yaw_deg, pitch_deg = estimate_head_pose_and_attention(
                    None, bbox=(x, y, w, h), frame_w=w_img, frame_h=h_img
                )
                detections.append({
                    'bbox': (x, y, w, h),
                    'label': 'face',
                    'conf': 0.90,
                    'is_attentive': is_attentive,
                    'attention_score': attention_score,
                    'yaw_deg': yaw_deg,
                    'pitch_deg': pitch_deg
                })
                break

        elif self.backend == "skin_centroid":
            ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
            skin_mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel)
            skin_mask = cv2.dilate(skin_mask, kernel, iterations=2)

            contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            best_face = None
            max_area = 0

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 1200:
                    x, y, w, h = cv2.boundingRect(cnt)
                    aspect_ratio = float(h) / max(w, 1)
                    if 0.8 <= aspect_ratio <= 2.2:
                        if area > max_area:
                            max_area = area
                            best_face = (x, y, w, h)

            if best_face:
                x, y, w, h = best_face
                cx = x + w / 2.0
                cy = y + h / 2.0
                norm_x = (cx - (w_img / 2.0)) / (w_img / 2.0)
                norm_y = (cy - (h_img / 2.0)) / (h_img / 2.0)
                gaze_target = (norm_x, norm_y)
                estimated_distance = max(40, min(250, int((h_img / max(h, 1)) * 35.0)))
                is_attentive, attention_score, yaw_deg, pitch_deg = estimate_head_pose_and_attention(
                    None, bbox=(x, y, w, h), frame_w=w_img, frame_h=h_img
                )
                detections.append({
                    'bbox': (x, y, w, h),
                    'label': 'face',
                    'conf': 0.88,
                    'is_attentive': is_attentive,
                    'attention_score': attention_score,
                    'yaw_deg': yaw_deg,
                    'pitch_deg': pitch_deg
                })

        return detections, gaze_target, estimated_distance, is_attentive, attention_score, yaw_deg


def run_vision_loop(camera_idx=0, backend_choice="auto", simulate=False, stream_port=5002, headless=True):
    """ลูปการทำงานหลักของระบบประมวลผลภาพบน Raspberry Pi 5"""
    global LATEST_FRAME_JPEG, LATEST_FRAME_TS, VISION_STATE

    start_stream_server(port=stream_port)
    detector = VisionDetector(preferred_backend=backend_choice)
    VISION_STATE["backend"] = detector.backend
    VISION_STATE["active"] = True

    cap = None
    if not simulate and CV2_AVAILABLE:
        try:
            print(f"📷 [Camera] กำลังเชื่อมต่อกล้อง Webcam (Index: {camera_idx})...")
            # รายการ Candidate Configurations สำหรับเชื่อมต่อกล้องบน Windows (DSHOW / Native)
            # รองรับทั้งโหมด 2 อาร์กิวเมนต์ และโหมด DSHOW Domain ของ OpenCV 5.x
            candidates = []
            if os.name == 'nt' and hasattr(cv2, 'CAP_DSHOW'):
                candidates.extend([
                    (camera_idx, cv2.CAP_DSHOW),
                    (cv2.CAP_DSHOW + camera_idx, None),
                    (1, cv2.CAP_DSHOW),
                    (cv2.CAP_DSHOW + 1, None),
                    (camera_idx, None)
                ])
            else:
                candidates.extend([
                    (camera_idx, None),
                    (1, None)
                ])

            for test_idx, test_backend in candidates:
                try:
                    if test_backend is not None:
                        temp_cap = cv2.VideoCapture(test_idx, test_backend)
                    else:
                        temp_cap = cv2.VideoCapture(test_idx)

                    if temp_cap.isOpened():
                        ret, test_frame = temp_cap.read()
                        if ret and test_frame is not None:
                            cap = temp_cap
                            break
                        temp_cap.release()
                except Exception:
                    pass

            if cap and cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_HEIGHT)
                cap.set(cv2.CAP_PROP_FPS, 30)
                if hasattr(cv2, 'CAP_PROP_BUFFERSIZE'):
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                print("✅ [Camera] เปิดกล้องเว็บแคมจริงสำเร็จพร้อมทำงาน")
            else:
                print(f"⚠️ [Camera Warning] ไม่สามารถเปิดกล้อง index {camera_idx} ได้ -> สลับเข้าโหมด Simulate อัตโนมัติ")
                simulate = True
        except Exception as e:
            print(f"⚠️ [Camera Error] {e} -> สลับเข้าโหมด Simulate")
            simulate = True

    consecutive_person_count = 0
    consecutive_attention_count = 0
    is_person_engaged = False
    last_person_seen_time = 0.0
    last_trigger_time = 0.0
    last_gaze_time = 0.0
    last_sent_gx = 0.0
    last_sent_gy = 0.0
    smoothed_gx = 0.0
    smoothed_gy = 0.0
    fps_counter = 0
    fps_timer = time.time()
    sim_t = 0.0
    detect_interval = 1.0 / DETECT_FPS
    encode_interval = 1.0 / STREAM_FPS
    last_detect_time = 0.0
    last_encode_time = 0.0

    print("=" * 65)
    print("👁️ [Nong Phet Vision Daemon] ระบบมองเห็นและทักทายพร้อมทำงานเต็มรูปแบบ!")
    print(f"   - Backend Model : {detector.backend.upper()}")
    print(f"   - Live Stream   : http://localhost:{stream_port}/video_feed")
    print(f"   - Auto Greeting : Cooldown {GREETING_COOLDOWN_SEC}s, Attention Threshold {CONSECUTIVE_ATTENTION_TRIGGER} frames")
    print(f"   - CPU Budget    : detect {DETECT_FPS:g} fps, stream {STREAM_FPS:g} fps (on demand), OpenCV threads {CV_THREADS}")
    print("=" * 65)

    try:
        while True:
            t0 = time.time()

            if simulate or not cap or not cap.isOpened():
                # สร้างเฟรมภาพจำลองแบบ Cyberpunk สำหรับโหมด Test/Simulate
                if CV2_AVAILABLE:
                    frame = np.zeros((TARGET_HEIGHT, TARGET_WIDTH, 3), dtype=np.uint8)
                    # พื้นหลังตาราง Grid
                    for x in range(0, TARGET_WIDTH, 40):
                        cv2.line(frame, (x, 0), (x, TARGET_HEIGHT), (15, 23, 42), 1)
                    for y in range(0, TARGET_HEIGHT, 40):
                        cv2.line(frame, (0, y), (TARGET_WIDTH, y), (15, 23, 42), 1)

                    # วาดเป้าหมายบุคคลจำลองที่เดินไปมา (ความเร็วตามเวลาจริง ไม่ขึ้นกับ fps)
                    sim_t += 1.5 * detect_interval
                    person_x = int(TARGET_WIDTH / 2.0 + math.sin(sim_t * 0.8) * 160)
                    person_y = int(TARGET_HEIGHT / 2.0 + math.cos(sim_t * 0.4) * 40)
                    pw, ph = 100, 130

                    cv2.rectangle(frame, (person_x - pw//2, person_y - ph//2), (person_x + pw//2, person_y + ph//2), (56, 189, 248), 2)
                    cv2.circle(frame, (person_x, person_y - 25), 22, (244, 63, 94), -1)
                    cv2.putText(frame, "SIMULATED VISITOR", (person_x - 55, person_y - ph//2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (56, 189, 248), 1)

                    is_attentive = True
                    attention_score = 0.95
                    yaw_deg = 0.0
                    detections = [{
                        'bbox': (person_x - pw//2, person_y - ph//2, pw, ph),
                        'label': 'sim_person',
                        'conf': 0.95,
                        'is_attentive': is_attentive,
                        'attention_score': attention_score,
                        'yaw_deg': yaw_deg
                    }]
                    norm_x = (person_x - (TARGET_WIDTH / 2.0)) / (TARGET_WIDTH / 2.0)
                    norm_y = (person_y - (TARGET_HEIGHT / 2.0)) / (TARGET_HEIGHT / 2.0)
                    gaze_target = (norm_x, norm_y)
                    estimated_distance = 120
                else:
                    detections, gaze_target, estimated_distance = [], None, None
                    is_attentive, attention_score, yaw_deg = False, 0.0, 0.0
                    frame = None
                time.sleep(detect_interval)
            else:
                # grab() ดึงเฟรมออกจากบัฟเฟอร์กล้องโดยยังไม่ถอดรหัส (ถูกมาก) เพื่อให้ภาพล่าสุดไม่ค้างในบัฟเฟอร์
                # ถอดรหัส + ตรวจจับเฉพาะรอบที่ถึงเวลาตาม DETECT_FPS เท่านั้น
                if not cap.grab():
                    time.sleep(0.01)
                    continue
                if (t0 - last_detect_time) < detect_interval:
                    time.sleep(0.001)
                    continue
                ret, frame = cap.retrieve()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue
                detections, gaze_target, estimated_distance, is_attentive, attention_score, yaw_deg = detector.detect(frame)

            frame_dt = (t0 - last_detect_time) if last_detect_time else detect_interval
            last_detect_time = t0

            has_person = len(detections) > 0
            VISION_STATE["person_detected"] = has_person
            VISION_STATE["distance_cm"] = estimated_distance
            VISION_STATE["is_looking_at_screen"] = is_attentive if has_person else False
            VISION_STATE["attention_score"] = attention_score if has_person else 0.0
            VISION_STATE["head_yaw_deg"] = yaw_deg if has_person else 0.0

            # -----------------------------------------------------------------
            # 1. ระบบหันมองตามคน (Gaze Tracking แบบ Smoothed Smart Motion)
            # -----------------------------------------------------------------
            if gaze_target:
                gx, gy = gaze_target
                # กรองความสั่นไหวด้วย Exponential Moving Average (EMA) เพื่อให้ดวงตาเคลื่อนไหวอย่างนุ่มนวล
                # ปรับน้ำหนักตามเวลาจริง: ให้ความหน่วงเท่าเดิม (0.65 ต่อเฟรมที่ 30 fps) ไม่ว่า DETECT_FPS จะเท่าไร
                keep = 0.65 ** min(frame_dt * 30.0, 30.0)
                smoothed_gx = round(keep * smoothed_gx + (1.0 - keep) * gx, 3)
                smoothed_gy = round(keep * smoothed_gy + (1.0 - keep) * gy, 3)
                VISION_STATE["gaze_x"] = smoothed_gx
                VISION_STATE["gaze_y"] = smoothed_gy
                # ส่งเฉพาะเมื่อตำแหน่งเคลื่อนไหวเกินเกณฑ์ (threshold 0.08) และเว้นระยะอย่างน้อย 350ms
                if (t0 - last_gaze_time) > 0.35:
                    if abs(smoothed_gx - last_sent_gx) > 0.08 or abs(smoothed_gy - last_sent_gy) > 0.08:
                        last_gaze_time = t0
                        last_sent_gx = smoothed_gx
                        last_sent_gy = smoothed_gy
                        send_http_json(FLASK_GAZE_URL, {"x": round(smoothed_gx, 2), "y": round(smoothed_gy, 2)})

            # -----------------------------------------------------------------
            # 2. ระบบทักทายอัตโนมัติ (Attention-Gated Auto Greeting)
            # -----------------------------------------------------------------
            if has_person:
                last_person_seen_time = t0
                if VISION_STATE["auto_greeting_enabled"] and not is_person_engaged:
                    # Attention Gating: นับสะสมเฉพาะเมื่อผู้ใช้หันหน้าสบตามองจอจริง
                    if is_attentive:
                        consecutive_attention_count += 1
                    else:
                        consecutive_attention_count = max(0, consecutive_attention_count - 1)

                    consecutive_person_count += 1

                    # เงื่อนไขทักทาย: สบตามองจอจริงต่อเนื่องอย่างน้อย 2 เฟรม (~0.5 - 0.8 วินาที) และผ่านคูลดาวน์
                    if consecutive_attention_count >= CONSECUTIVE_ATTENTION_TRIGGER and (t0 - last_trigger_time) > GREETING_COOLDOWN_SEC:
                        is_person_engaged = True  # ล็อกสถานะว่าทักทายคนนี้แล้ว จะไม่พูดซ้ำขณะที่เขายังอยู่หน้าตู้!
                        last_trigger_time = t0
                        consecutive_person_count = 0
                        consecutive_attention_count = 0
                        VISION_STATE["total_greetings"] += 1
                        now_str = datetime.datetime.now().strftime("%H:%M:%S")
                        VISION_STATE["last_greeting_time"] = now_str
                        dist_val = estimated_distance or 110

                        print(f"👁️ [Attention Gating] สบตามองจอจริง! (Attention: {int(attention_score*100)}%, Yaw: {yaw_deg:+.1f}°, ระยะ ~{dist_val} ซม.) -> ส่งเสียงทักทาย")
                        trigger_payload = {
                            "event": "user_detected",
                            "distance": dist_val,
                            "attention_score": attention_score,
                            "yaw_deg": yaw_deg,
                            "source": "opencv_camera",
                            "greeting_text": "สวัสดีค่ะ ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ ต้องการคุยหรือพิมพ์แชทกับน้องเพชรดีคะ"
                        }
                        send_http_json(FLASK_IOT_TRIGGER_URL, trigger_payload)
            else:
                consecutive_person_count = max(0, consecutive_person_count - 1)
                consecutive_attention_count = max(0, consecutive_attention_count - 1)

            # รีเซ็ตสถานะล็อกเซสชันเฉพาะเมื่อคนเดินออกไปเกิน 4 วินาที (หากยังอยู่หน้าตู้จะไม่ทักซ้ำเด็ดขาด)
            if is_person_engaged and not has_person:
                if (t0 - last_person_seen_time) > 4.0:
                    is_person_engaged = False
                    consecutive_person_count = 0
                    consecutive_attention_count = 0
                    print("👋 [Auto Greeting] ผู้ใช้ออกจากระยะตรวจจับแล้ว -> รีเซ็ตเซสชันพร้อมต้อนรับคนใหม่")
                    send_http_json(FLASK_IOT_TRIGGER_URL, {
                        "event": "user_left",
                        "source": "opencv_camera"
                    })

            # -----------------------------------------------------------------
            # 3. วาด Bounding Box & HUD Telemetry บนเฟรมภาพสตรีมมิ่ง
            #    ทำเฉพาะตอนมีคนดูสตรีม/ขอ snapshot (หรือเปิดหน้าต่าง --gui) และไม่เกิน STREAM_FPS
            #    ตอนไม่มีใครดู จะไม่เสีย CPU กับการวาดและเข้ารหัส JPEG เลย
            # -----------------------------------------------------------------
            stream_wanted = (STREAM_CLIENTS > 0
                             or (t0 - LAST_SNAPSHOT_REQUEST) < SNAPSHOT_KEEPALIVE_SEC
                             or not headless)
            if (frame is not None and CV2_AVAILABLE and stream_wanted
                    and (t0 - last_encode_time) >= encode_interval):
                last_encode_time = t0
                for d in detections:
                    bx, by, bw, bh = d['bbox']
                    att = d.get('is_attentive', False)
                    att_score = d.get('attention_score', 0.0)
                    yaw_val = d.get('yaw_deg', 0.0)

                    # สีเขียวมรกตเมื่อสบตามองจอ (Eye Contact) / สีฟ้าเมื่อมองทางอื่น (Looking Away)
                    box_color = (16, 185, 129) if att else (56, 189, 248)
                    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), box_color, 2)

                    # ป้ายกำกับบน
                    label = f"{d['label']} {int(d['conf']*100)}%"
                    if estimated_distance:
                        label += f" (~{estimated_distance}cm)"
                    cv2.putText(frame, label, (bx, max(18, by - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, box_color, 1)

                    # ป้ายกำกับล่าง (Attention Status)
                    if att:
                        att_label = f"EYE CONTACT {int(att_score*100)}% (Yaw {yaw_val:+.0f}deg)"
                        att_color = (16, 185, 129)
                    else:
                        att_label = f"LOOKING AWAY (Yaw {yaw_val:+.0f}deg)"
                        att_color = (0, 165, 255)
                    cv2.putText(frame, att_label, (bx, min(TARGET_HEIGHT - 8, by + bh + 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.40, att_color, 1)

                    # วาดจุด Landmark บนใบหน้า (ถ้าตรวจพบด้วย YuNet)
                    if 'landmarks' in d and d['landmarks']:
                        for lm_name, lm_pt in d['landmarks'].items():
                            if lm_pt[0] > 0 and lm_pt[1] > 0:
                                cv2.circle(frame, (int(lm_pt[0]), int(lm_pt[1])), 3, (0, 255, 255), -1)

                # วาด HUD Overlay
                fps_text = f"FPS: {VISION_STATE['fps']:.1f} | Backend: {detector.backend.upper()}"
                cv2.putText(frame, fps_text, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (6, 182, 212), 1)

                status_color = (16, 185, 129) if VISION_STATE["is_looking_at_screen"] else (148, 163, 184)
                att_hud = f"Attention: {int(VISION_STATE['attention_score']*100)}% | Gaze: {'LOCKED' if VISION_STATE['is_looking_at_screen'] else 'OFF'}"
                cv2.putText(frame, att_hud, (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.42, status_color, 1)

                if gaze_target:
                    g_text = f"Gaze: ({VISION_STATE['gaze_x']:.2f}, {VISION_STATE['gaze_y']:.2f})"
                    cv2.putText(frame, g_text, (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (244, 63, 94), 1)

                # เข้ารหัส JPEG สำหรับ MJPEG Streaming
                ret_jpg, jpeg_buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if ret_jpg:
                    with FRAME_LOCK:
                        LATEST_FRAME_JPEG = jpeg_buf.tobytes()
                        LATEST_FRAME_TS = time.time()

                if not headless:
                    cv2.imshow("Nong Phet Vision - Debug Preview", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

            # คำนวณ FPS
            fps_counter += 1
            if (time.time() - fps_timer) >= 1.0:
                VISION_STATE["fps"] = round(fps_counter / (time.time() - fps_timer), 1)
                fps_counter = 0
                fps_timer = time.time()

    except KeyboardInterrupt:
        print("\n🛑 [Vision Daemon] กำลังหยุดการทำงานของระบบตรวจจับภาพ...")
    finally:
        if cap and cap.isOpened():
            cap.release()
        if CV2_AVAILABLE:
            cv2.destroyAllWindows()
        VISION_STATE["active"] = False
        print("✅ [Vision Daemon] หยุดการทำงานเรียบร้อย")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Nong Phet AI Smart Guide - Computer Vision & Auto Greeting Daemon")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--backend", type=str, default="auto", choices=["auto", "yunet", "yolo", "mediapipe", "opencv", "skin"], help="Model backend")
    parser.add_argument("--simulate", action="store_true", help="Run in simulation mode without physical webcam")
    parser.add_argument("--port", type=int, default=5002, help="MJPEG stream HTTP port (default: 5002)")
    parser.add_argument("--gui", action="store_true", help="Show local desktop OpenCV preview window")
    args = parser.parse_args()

    run_vision_loop(
        camera_idx=args.camera,
        backend_choice=args.backend,
        simulate=args.simulate,
        stream_port=args.port,
        headless=not args.gui
    )

