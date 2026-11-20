# -*- coding: utf-8 -*-
"""
routes/iot.py — ESP32 Embedded System & Sensor SSE Streaming Blueprint
"""
import time
import json
import queue
import datetime
import logging
from flask import Blueprint, request, jsonify, Response
from services.analytics_service import visitor_analytics

logger = logging.getLogger("nongphet.iot")

iot_bp = Blueprint('iot', __name__)

iot_state = {
    'connected': False,
    'last_seen': None,
    'distance_cm': None,
    'user_present': False,
    'last_trigger': None,
    'led_mode': 'idle',
    'total_triggers': 0,
    'source': 'standby'
}

iot_event_subscribers = []
IOT_TRIGGER_COOLDOWN_SEC = 12.0

def broadcast_iot_event(event_data):
    """ส่งต่อ Event จาก ESP32 / Vision ไปยังหน้าเว็บที่เปิดอยู่ทุกหน้าแบบ Realtime"""
    for sub_q in list(iot_event_subscribers):
        try:
            sub_q.put_nowait(event_data)
        except queue.Full:
            # หากคิวเต็ม (เช่น จังหวะสตรีม Gaze ความถี่สูง หรือแท็บเบื้องหลัง) ให้ทิ้งของเก่าแล้วใส่ของใหม่ล่าสุด
            try:
                sub_q.get_nowait()
                sub_q.put_nowait(event_data)
            except Exception:
                pass
        except Exception:
            pass

@iot_bp.route('/api/iot/trigger', methods=['POST'])
def iot_trigger():
    """รับสัญญาณ Trigger เมื่อเซนเซอร์ Ultrasonic (HC-SR04) หรือกล้อง AI ตรวจพบคนมาหยุดมอง หรือเดินออก"""
    data = request.json or {}
    event_type = data.get('event', 'user_detected')
    distance = data.get('distance')
    source = data.get('source', 'esp32_hardware')
    greeting_text = data.get('greeting_text')
    now_str = datetime.datetime.now().strftime("%H:%M:%S")

    # กรณีผู้ใช้ออกจากระยะตรวจจับ (user_left) ให้ส่งสัญญาณทันทีโดยไม่ติด Cooldown
    if event_type == 'user_left':
        iot_state['user_present'] = False
        iot_state['last_seen'] = now_str
        iot_state['led_mode'] = 'idle'
        event_payload = {
            'event': 'user_left',
            'timestamp': now_str,
            'source': source
        }
        broadcast_iot_event(event_payload)
        logger.info(f"IoT Event Broadcast (User Left): {event_payload}")
        return jsonify({
            'status': 'received',
            'event': event_payload,
            'led_command': 'idle',
            'user_present': False
        })

    # กรณีตรวจพบผู้ใช้ (user_detected)
    now_ts = time.time()
    last_ts = float(iot_state.get('_last_trigger_ts', 0.0) or 0.0)
    if source != 'manual_simulation' and (now_ts - last_ts) < IOT_TRIGGER_COOLDOWN_SEC:
        remaining = round(IOT_TRIGGER_COOLDOWN_SEC - (now_ts - last_ts), 1)
        return jsonify({
            'status': 'throttled',
            'cooldown_remaining': remaining,
            'source': source
        })

    iot_state['_last_trigger_ts'] = now_ts
    iot_state['connected'] = True
    iot_state['last_seen'] = now_str
    iot_state['distance_cm'] = distance
    iot_state['user_present'] = True
    iot_state['last_trigger'] = now_str
    iot_state['total_triggers'] += 1
    iot_state['source'] = source
    visitor_analytics['total_visitors'] += 1

    event_payload = {
        'event': event_type,
        'distance': distance,
        'timestamp': now_str,
        'total_triggers': iot_state['total_triggers'],
        'source': source,
        'greeting_text': greeting_text
    }
    
    broadcast_iot_event(event_payload)
    logger.info(f"IoT Event Broadcast: {event_payload}")

    # ทักทายด้วยการโบกมือเมื่อมีคนเข้าใกล้ (เฉพาะเหตุการณ์ที่ผ่าน Cooldown มาแล้ว)
    if event_type == 'user_detected':
        try:
            from services import arm_service
            arm_service.trigger_gesture('wave', source=source)
        except Exception as e:
            logger.debug(f"Arm greeting note: {e}")

    return jsonify({
        'status': 'received',
        'event': event_payload,
        'led_command': 'speaking'
    })

@iot_bp.route('/api/iot/status', methods=['GET'])
def get_iot_status():
    """ดึงสถานะล่าสุดของเซนเซอร์และบอร์ด ESP32"""
    return jsonify(iot_state)

@iot_bp.route('/api/iot/led', methods=['POST'])
def iot_set_led():
    """ส่งคำสั่งควบคุมไฟ LED ไปยังบอร์ด ESP32 ผ่าน GPIO"""
    data = request.json or {}
    state = data.get('state', 'idle')
    iot_state['led_mode'] = state
    broadcast_iot_event({'event': 'led_state_changed', 'state': state})

    # สัญญาณเริ่ม/จบการพูดจากหน้าเว็บ -> ขยับแขนเบาๆ ประกอบการพูด (ส่งเฉพาะตอนเปลี่ยนสถานะ)
    try:
        from services import arm_service
        arm_service.speech_changed(state == 'speaking')
    except Exception as e:
        logger.debug(f"Arm speech note: {e}")

    return jsonify({'status': 'ok', 'led_mode': state})

@iot_bp.route('/api/iot/events')
def iot_events():
    """Server-Sent Events (SSE) Stream ให้หน้าจอแสดงผลรับการแจ้งเตือนและทักทายอัตโนมัติ"""
    def event_stream():
        q = queue.Queue(maxsize=120)
        iot_event_subscribers.append(q)
        try:
            # แจ้ง Browser ให้นับถอยหลัง 3 วินาทีก่อน auto-reconnect หากการเชื่อมต่อสะดุด
            yield "retry: 3000\n\n"
            yield f"data: {json.dumps({'event': 'connected', 'status': iot_state})}\n\n"
            while True:
                try:
                    event = q.get(timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # ส่ง Heartbeat Ping ทุกๆ 15 วินาที กัน Browser / Proxy ตัดการเชื่อมต่อเมื่อไม่มีข้อมูล
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        except Exception as e:
            logger.debug(f"SSE client disconnected: {e}")
        finally:
            if q in iot_event_subscribers:
                try:
                    iot_event_subscribers.remove(q)
                except ValueError:
                    pass

    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers['Cache-Control'] = 'no-cache, no-transform'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Connection'] = 'keep-alive'
    return response

