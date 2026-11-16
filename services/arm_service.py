# -*- coding: utf-8 -*-
"""
services/arm_service.py — Arm (shoulder servo) gesture control for น้องเพชร

หน้าที่:
- เป็นคลังท่าทางแขน (keyframe) — ต้องตรงกับ esp32_firmware/esp32_firmware.ino
  (tests/test_arm.py อ่านไฟล์ .ino แล้วเทียบ keyframe ให้ ถ้าไม่ตรงเทสต์จะล้ม)
- ตรวจสอบมุม/ท่าทางฝั่ง server ก่อนส่งต่อ (firmware ก็จำกัดมุมซ้ำอีกชั้น)
- แมปอารมณ์ / intent / ท่าภาษามือ / แท็ก [gesture:x] จาก LLM -> ท่าทางแขน
- ท่าประกอบการพูด (talk) ตามสัญญาณเริ่ม/จบการพูดของหน้าเว็บ
- เก็บสถานะฮาร์ดแวร์ที่บริดจ์รายงานกลับมา (เชื่อมต่อหรือไม่, เวอร์ชัน firmware, ack ล่าสุด)
- ส่งคำสั่งเป็น SSE event 'arm_gesture' / 'arm_pose' ผ่าน broadcast_iot_event
  จากนั้น esp32_listener.py จะรับแล้วแปลงเป็น JSON ลง Serial ไปยัง ESP32
"""
import os
import re
import time
import logging
import threading

logger = logging.getLogger("nongphet.arm")


def _env_flag(name, default='1'):
    return os.environ.get(name, default).lower() not in ('0', 'false', 'no', 'off')


# เปิด/ปิดระบบแขนทั้งหมด (ตั้ง ARM_ENABLED=0 ถ้ายังไม่ได้ติดตั้งแขน)
ARM_ENABLED = _env_flag('ARM_ENABLED')
# เปิด/ปิดท่าขยับแขนเบาๆ ระหว่างพูด (ตั้ง ARM_TALK=0 ถ้าไม่ต้องการ)
ARM_TALK_ENABLED = _env_flag('ARM_TALK')

# ช่วงมุมที่ปลอดภัยของเซอร์โวไหล่ (ตรงกับ firmware: ARM_MIN/ARM_MAX/ARM_REST)
ANGLE_MIN = 20
ANGLE_MAX = 120
ANGLE_REST = 20
SPEED_MIN = 5      # องศา/วินาที (ช้าที่สุด)
SPEED_MAX = 360    # องศา/วินาที (เร็วที่สุด)
VALID_SIDES = ('L', 'R', 'both')
SPEECH_REFRESH_SEC = 30   # สัญญาณ "กำลังพูด" ซ้ำภายในเวลานี้ไม่ต้องสั่งใหม่
HARDWARE_STALE_SEC = 30   # ไม่ได้ยินจากบอร์ดนานเกินนี้ ถือว่าไม่ได้เชื่อมต่อ

R, M = ANGLE_REST, ANGLE_MAX
# Keyframe: (มุมซ้าย, มุมขวา, ความเร็วองศา/วินาที, หน่วงค้างมิลลิวินาที) — -1 = ไม่เปลี่ยนแขนข้างนั้น
GESTURE_DEFS = {
    'rest': dict(
        description='กลับท่าพัก (ลดแขนทั้งสอง)', loop=False,
        keyframes=[(R, R, 120, 0)]),
    'wave': dict(
        description='โบกมือขวา ยก-ลงซ้ำ ๆ', loop=False,
        keyframes=[(-1, M, 240, 150), (-1, 70, 300, 0), (-1, M, 300, 0), (-1, 70, 300, 0), (-1, M, 300, 150), (-1, R, 120, 0)]),
    'wave_left': dict(
        description='โบกมือซ้าย', loop=False,
        keyframes=[(M, -1, 240, 150), (70, -1, 300, 0), (M, -1, 300, 0), (70, -1, 300, 0), (M, -1, 300, 150), (R, -1, 120, 0)]),
    'raise_left': dict(
        description='ยกแขนซ้ายค้าง', loop=False,
        keyframes=[(M, -1, 150, 1200), (R, -1, 120, 0)]),
    'raise_right': dict(
        description='ยกแขนขวาค้าง', loop=False,
        keyframes=[(-1, M, 150, 1200), (-1, R, 120, 0)]),
    'raise_both': dict(
        description='ยกสองแขนค้าง', loop=False,
        keyframes=[(M, M, 150, 1200), (R, R, 120, 0)]),
    'cheer': dict(
        description='ยกสองแขนขึ้น-ลงเร็ว (ดีใจ)', loop=False,
        keyframes=[(M, 60, 300, 0), (60, M, 300, 0), (M, 60, 300, 0), (60, M, 300, 0), (M, M, 300, 300), (R, R, 150, 0)]),
    'surprise': dict(
        description='สะดุ้ง ยกแขนเร็วแล้วลง', loop=False,
        keyframes=[(M, M, 360, 400), (R, R, 90, 0)]),
    'talk': dict(
        description='ขยับแขนเบา ๆ ประกอบการพูด (วนจนกว่าจะสั่ง rest)', loop=True,
        keyframes=[(-1, 45, 70, 250), (45, 30, 70, 250), (30, 45, 70, 250), (-1, 30, 70, 250)]),
}


def _estimate_duration(keyframes, loop):
    """ประมาณเวลาที่ท่าทางใช้ (วินาที) จากระยะเดินทางของแขนและเวลาค้าง คืน 0 สำหรับท่าที่วนลูป"""
    if loop:
        return 0.0
    pos = {'L': float(ANGLE_REST), 'R': float(ANGLE_REST)}
    total = 0.0
    for l, r, speed, hold in keyframes:
        travel = 0.0
        for side, target in (('L', l), ('R', r)):
            if target >= 0:
                travel = max(travel, abs(target - pos[side]) / float(speed))
                pos[side] = float(target)
        total += travel + hold / 1000.0
    return round(total, 2)


# ท่าที่ firmware รู้จัก: ชื่อ -> (คำอธิบาย, ระยะเวลาโดยประมาณเป็นวินาที)
GESTURES = {
    name: (d['description'], _estimate_duration(d['keyframes'], d['loop']))
    for name, d in GESTURE_DEFS.items()
}

_lock = threading.Lock()
arm_state = {
    'enabled': ARM_ENABLED,
    'current_gesture': 'rest',
    'last_command': None,
    'last_source': None,
    'busy_until': 0.0,
    'pose': {'L': ANGLE_REST, 'R': ANGLE_REST},
    'total_commands': 0,
    'speaking': False,
    'speaking_since': 0.0,
}

# สถานะฮาร์ดแวร์ที่บริดจ์ (esp32_listener.py) รายงานกลับมา
hardware_state = {
    'connected': False,
    'port': None,
    'firmware': None,
    'device': None,
    'last_seen_ts': 0.0,
    'last_seen': None,
    'last_response': None,
    'last_error': None,
    'arm_l': None,
    'arm_r': None,
    'gesture': None,
}

# อารมณ์ (จาก resolve_living_emotion) -> ท่าทาง
EMOTION_GESTURE_MAP = {
    'love': 'raise_both',
    'excited': 'cheer',
    'surprised': 'surprise',
    'wink': 'wave',
}

# intent -> ท่าทาง (มาก่อนอารมณ์ ดู gesture_for_chat)
INTENT_GESTURE_MAP = {
    'greeting': 'wave',
}

# ท่าภาษามือไทยที่ผู้ใช้ทำ -> ท่าทางที่หุ่นตอบ
SIGN_GESTURE_MAP = {
    'open_palm': 'wave',
    'thumbs_up': 'raise_both',
    'love': 'raise_both',
    'peace': 'cheer',
    'shaka': 'surprise',
}

# แท็กท่าทางที่ LLM แนบมาในคำตอบ เช่น [gesture:wave] (ไม่อนุญาต talk/rest ให้ LLM สั่งเอง)
_GESTURE_TAG_RE = re.compile(r'\[\s*gesture\s*:\s*([A-Za-z_]+)\s*\]', re.IGNORECASE)
LLM_ALLOWED_GESTURES = tuple(n for n in GESTURES if n not in ('talk', 'rest'))


def _broadcast(event):
    # import ภายในฟังก์ชันเพื่อกัน circular import (routes.iot -> services.analytics)
    try:
        from routes.iot import broadcast_iot_event
        broadcast_iot_event(event)
    except Exception as e:
        logger.debug(f"Arm broadcast note: {e}")


def list_gestures():
    return {
        name: {
            'description': d['description'],
            'duration_s': GESTURES[name][1],
            'loop': d['loop'],
            'keyframes': [list(k) for k in d['keyframes']],
        }
        for name, d in GESTURE_DEFS.items()
    }


def is_hardware_connected(now=None):
    now = now or time.time()
    return bool(hardware_state['connected']) and (now - hardware_state['last_seen_ts']) < HARDWARE_STALE_SEC


def trigger_gesture(name, source='api', force=False):
    """
    สั่งเล่นท่าทางตามชื่อ
    คืน dict: {'ok': bool, 'status': 'sent'|'busy'|'disabled'|'invalid', ...}
    force=True ข้ามการเช็คว่าท่าก่อนหน้ายังเล่นอยู่ (ใช้กับคำสั่งจากผู้ดูแล)
    'sent' หมายถึงส่งเป็นอีเวนต์แล้ว ดู hardware_connected ว่ามีบอร์ดรับอยู่จริงหรือไม่
    """
    if name not in GESTURES:
        return {'ok': False, 'status': 'invalid', 'message': f'ไม่รู้จักท่าทาง "{name}"'}
    if not ARM_ENABLED:
        return {'ok': False, 'status': 'disabled', 'message': 'ระบบแขนถูกปิดอยู่ (ARM_ENABLED=0)'}

    now = time.time()
    with _lock:
        interrupts = name in ('rest', 'talk')
        if not force and not interrupts and now < arm_state['busy_until']:
            return {'ok': False, 'status': 'busy', 'current': arm_state['current_gesture']}
        _, duration = GESTURES[name]
        arm_state['current_gesture'] = name
        arm_state['last_command'] = time.strftime('%H:%M:%S')
        arm_state['last_source'] = source
        if name == 'rest':
            arm_state['busy_until'] = now + 1.0
        elif name != 'talk':
            # ท่าพูดวนลูปไม่ควรตัดช่วงที่ท่าอื่นกำลังเล่นอยู่ (firmware จะรอให้ท่านั้นจบก่อนแล้วค่อยกลับมาขยับเบาๆ)
            arm_state['busy_until'] = now + duration
        arm_state['total_commands'] += 1
        stamp = arm_state['last_command']

    _broadcast({
        'event': 'arm_gesture',
        'gesture': name,
        'source': source,
        'timestamp': stamp,
    })
    logger.info(f"🦾 [Arm] gesture={name} source={source}")
    return {'ok': True, 'status': 'sent', 'gesture': name, 'hardware_connected': is_hardware_connected()}


def set_pose(side, angle, speed=90, source='api'):
    """สั่งมุมโดยตรง side: 'L' | 'R' | 'both', angle: 20-120, speed: องศา/วินาที"""
    if side not in VALID_SIDES:
        return {'ok': False, 'status': 'invalid', 'message': 'side ต้องเป็น L, R หรือ both'}
    try:
        angle = float(angle)
        speed = float(speed)
    except (TypeError, ValueError):
        return {'ok': False, 'status': 'invalid', 'message': 'angle/speed ต้องเป็นตัวเลข'}
    if not ARM_ENABLED:
        return {'ok': False, 'status': 'disabled', 'message': 'ระบบแขนถูกปิดอยู่ (ARM_ENABLED=0)'}

    angle = int(max(ANGLE_MIN, min(ANGLE_MAX, angle)))
    speed = int(max(SPEED_MIN, min(SPEED_MAX, speed)))
    with _lock:
        for s in (('L', 'R') if side == 'both' else (side,)):
            arm_state['pose'][s] = angle
        arm_state['current_gesture'] = 'pose'
        arm_state['last_command'] = time.strftime('%H:%M:%S')
        arm_state['last_source'] = source
        arm_state['total_commands'] += 1
        stamp = arm_state['last_command']

    _broadcast({
        'event': 'arm_pose',
        'side': side,
        'angle': angle,
        'speed': speed,
        'source': source,
        'timestamp': stamp,
    })
    return {'ok': True, 'status': 'sent', 'side': side, 'angle': angle, 'speed': speed,
            'hardware_connected': is_hardware_connected()}


# ------------------------------------------------------------------------------
# การแมปเหตุการณ์ -> ท่าทาง
# ------------------------------------------------------------------------------
def gesture_for_chat(intent, emotion):
    """
    เลือกท่าทางจากผลการสนทนา คืน None ถ้าไม่ต้องขยับ
    intent ทักทายมาก่อนอารมณ์ เพราะคำตอบทักทายมักมีคำเกี่ยวกับการท่องเที่ยว
    ทำให้อารมณ์ถูกตีเป็น excited ทั้งที่ควรโบกมือ
    """
    return INTENT_GESTURE_MAP.get(intent) or EMOTION_GESTURE_MAP.get(emotion)


def react_to_chat(intent, emotion, source='chat'):
    gesture = gesture_for_chat(intent, emotion)
    if gesture:
        return trigger_gesture(gesture, source=source)
    return None


def react_to_sign(sign_gesture, source='sign_language'):
    gesture = SIGN_GESTURE_MAP.get(sign_gesture)
    if gesture:
        return trigger_gesture(gesture, source=source)
    return None


def extract_gesture_tag(text):
    """
    ดึงแท็ก [gesture:xxx] ออกจากคำตอบของ LLM
    คืน (ข้อความที่ตัดแท็กออกแล้ว, ชื่อท่าที่ใช้ได้ หรือ None)
    ตัดแท็กทุกรูปแบบออกเสมอ (แม้ชื่อท่าไม่ถูกต้อง) เพื่อไม่ให้ถูกอ่านออกเสียง/แสดงบนจอ
    """
    if not text:
        return text, None
    found = _GESTURE_TAG_RE.findall(text)
    if not found:
        return text, None
    clean = _GESTURE_TAG_RE.sub('', text)
    clean = re.sub(r'[ \t]{2,}', ' ', clean).strip()
    for name in found:
        name = name.lower()
        if name in LLM_ALLOWED_GESTURES:
            return clean, name
    return clean, None


def speech_changed(speaking, source='speech'):
    """
    ท่าขยับแขนเบาๆ ประกอบการพูด: เรียกเมื่อหน้าเว็บแจ้งเริ่ม/จบการพูด (ผ่าน /api/iot/led)
    ส่งเฉพาะตอนเปลี่ยนสถานะ เพราะหน้าเว็บส่งสัญญาณ "speaking" ซ้ำหลายครั้งต่อหนึ่งประโยค
    """
    if not ARM_ENABLED or not ARM_TALK_ENABLED:
        return None
    now = time.time()
    with _lock:
        if speaking:
            if arm_state['speaking'] and (now - arm_state['speaking_since']) < SPEECH_REFRESH_SEC:
                return None
            arm_state['speaking'] = True
            arm_state['speaking_since'] = now
        else:
            if not arm_state['speaking']:
                return None
            arm_state['speaking'] = False
    return trigger_gesture('talk' if speaking else 'rest', source=source, force=True)


# ------------------------------------------------------------------------------
# สถานะฮาร์ดแวร์ (รายงานจากบริดจ์)
# ------------------------------------------------------------------------------
def update_hardware(report):
    """
    รับรายงานจากบริดจ์ รูปแบบ (ฟิลด์ใดก็ได้):
      {'connected': bool, 'port': str, 'response': {...คำตอบ JSON ของ ESP32...}}
    """
    if not isinstance(report, dict):
        return get_hardware_status()
    now = time.time()
    with _lock:
        hw = hardware_state
        if 'connected' in report:
            hw['connected'] = bool(report['connected'])
            if not hw['connected']:
                hw['arm_l'] = hw['arm_r'] = hw['gesture'] = None
        if report.get('port'):
            hw['port'] = str(report['port'])[:64]
        resp = report.get('response')
        if isinstance(resp, dict):
            hw['connected'] = True
            hw['last_response'] = {k: resp[k] for k in list(resp)[:10]}
            if resp.get('device'):
                hw['device'] = str(resp['device'])[:64]
            if resp.get('version'):
                hw['firmware'] = str(resp['version'])[:32]
            if resp.get('response') == 'error':
                hw['last_error'] = str(resp.get('reason', 'unknown'))[:64]
            if resp.get('response') == 'status':
                hw['arm_l'] = resp.get('arm_l')
                hw['arm_r'] = resp.get('arm_r')
                hw['gesture'] = resp.get('gesture')
        if report.get('connected') or isinstance(resp, dict):
            hw['last_seen_ts'] = now
            hw['last_seen'] = time.strftime('%H:%M:%S')
    return get_hardware_status()


def get_hardware_status():
    with _lock:
        snap = dict(hardware_state)
    snap['connected'] = is_hardware_connected()
    snap.pop('last_seen_ts', None)
    return snap


def get_status():
    with _lock:
        snap = dict(arm_state)
        snap['pose'] = dict(arm_state['pose'])
    snap['gestures'] = list(GESTURES.keys())
    snap['limits'] = {'angle_min': ANGLE_MIN, 'angle_max': ANGLE_MAX}
    snap['talk_enabled'] = ARM_TALK_ENABLED
    snap['hardware'] = get_hardware_status()
    return snap
