# -*- coding: utf-8 -*-
"""
routes/arm.py — Arm (shoulder servo) control API

การป้องกัน: คำสั่งที่เปลี่ยนสถานะ (POST) ต้องมาจากเครื่องเดียวกัน (localhost)
หรือแนบ header `X-Admin-Pin` ให้ตรงกับ ADMIN_PIN เท่านั้น
"""
import hmac
from flask import Blueprint, request, jsonify

from config import Config
from services import arm_service

arm_bp = Blueprint('arm', __name__)

_LOOPBACK = ('127.0.0.1', '::1', '::ffff:127.0.0.1')


def _authorized():
    if request.remote_addr in _LOOPBACK:
        return True
    supplied = request.headers.get('X-Admin-Pin', '')
    return bool(supplied) and hmac.compare_digest(supplied, str(Config.ADMIN_PIN))


@arm_bp.route('/api/arm/status', methods=['GET'])
def arm_status():
    return jsonify({'status': 'success', 'arm': arm_service.get_status()})


@arm_bp.route('/api/arm/hardware', methods=['GET', 'POST'])
def arm_hardware():
    """GET: สถานะบอร์ดล่าสุด / POST: บริดจ์ esp32_listener.py รายงานการเชื่อมต่อและคำตอบจาก ESP32"""
    if request.method == 'POST':
        if not _authorized():
            return jsonify({'status': 'error', 'message': 'ต้องใช้ X-Admin-Pin'}), 403
        hw = arm_service.update_hardware(request.get_json(silent=True) or {})
        return jsonify({'status': 'success', 'hardware': hw})
    return jsonify({'status': 'success', 'hardware': arm_service.get_hardware_status()})


@arm_bp.route('/api/arm/gestures', methods=['GET'])
def arm_gestures():
    return jsonify({'status': 'success', 'gestures': arm_service.list_gestures()})


@arm_bp.route('/api/arm/gesture', methods=['POST'])
def arm_gesture():
    if not _authorized():
        return jsonify({'status': 'error', 'message': 'ต้องใช้ X-Admin-Pin'}), 403
    data = request.get_json(silent=True) or {}
    result = arm_service.trigger_gesture(str(data.get('gesture', '')), source='admin_api', force=True)
    if result['ok']:
        return jsonify({'status': 'success', **result})
    code = 400 if result['status'] == 'invalid' else 409
    return jsonify({'status': 'error', **result}), code


@arm_bp.route('/api/arm/pose', methods=['POST'])
def arm_pose():
    if not _authorized():
        return jsonify({'status': 'error', 'message': 'ต้องใช้ X-Admin-Pin'}), 403
    data = request.get_json(silent=True) or {}
    result = arm_service.set_pose(
        data.get('side', 'both'),
        data.get('angle', arm_service.ANGLE_MIN),
        data.get('speed', 90),
        source='admin_api',
    )
    if result['ok']:
        return jsonify({'status': 'success', **result})
    code = 400 if result['status'] == 'invalid' else 409
    return jsonify({'status': 'error', **result}), code
