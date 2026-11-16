# -*- coding: utf-8 -*-
"""
routes/display.py — Dual-Screen Emotion Display & Mobile QR Share Blueprint
"""
import uuid
import datetime
from flask import Blueprint, request, jsonify, render_template

from state import emotion_state, shared_cards
from routes.iot import broadcast_iot_event

display_bp = Blueprint('display', __name__)

@display_bp.route('/emotion')
def emotion_page():
    return render_template('emotion.html')

@display_bp.route('/api/emotion/state', methods=['GET', 'POST'])
def api_emotion_state():
    if request.method == 'POST':
        data = request.json or {}
        new_state = data.get('state', 'idle')
        emotion_state['current'] = new_state
        emotion_state['timestamp'] = datetime.datetime.now().strftime("%H:%M:%S")
        broadcast_iot_event({
            'event': 'emotion_changed',
            'state': new_state,
            'timestamp': emotion_state['timestamp']
        })
        return jsonify({'status': 'ok', 'current_state': new_state})
    
    return jsonify({
        'status': 'success',
        'current_state': emotion_state['current'],
        'timestamp': emotion_state['timestamp']
    })

@display_bp.route('/api/emotion/gaze', methods=['POST'])
def api_emotion_gaze():
    data = request.json or {}
    try:
        x = max(-1.0, min(1.0, float(data.get('x', 0.0))))
        y = max(-1.0, min(1.0, float(data.get('y', 0.0))))
    except (ValueError, TypeError):
        x, y = 0.0, 0.0
    broadcast_iot_event({
        'event': 'gaze_changed',
        'x': x,
        'y': y
    })
    return jsonify({'status': 'ok', 'x': x, 'y': y})

@display_bp.route('/api/share', methods=['POST'])
def api_create_share():
    data = request.json or {}
    title = data.get('title', 'ข้อมูลแนะนำจากน้องเพชร AI')
    content = data.get('content', '')
    intent = data.get('intent', 'travel')
    maps_query = data.get('maps_query', 'จังหวัดเพชรบุรี')
    
    if len(shared_cards) > 200:
        for k in list(shared_cards.keys())[:50]:
            shared_cards.pop(k, None)

    share_id = uuid.uuid4().hex[:8]
    created_at = datetime.datetime.now().strftime("%d/%m/%Y %H:%M น.")
    
    shared_cards[share_id] = {
        'id': share_id,
        'title': title,
        'content': content,
        'intent': intent,
        'maps_query': maps_query,
        'created_at': created_at
    }
    
    host_url = request.host_url.rstrip('/')
    share_url = f"{host_url}/share/{share_id}"
    
    return jsonify({
        'status': 'success',
        'share_id': share_id,
        'share_url': share_url
    })

@display_bp.route('/share/<share_id>')
def view_shared_card(share_id):
    card = shared_cards.get(share_id)
    if not card:
        card = {
            'id': share_id,
            'title': 'ข้อมูลแนะนำจากน้องเพชร AI',
            'content': 'วิทยาลัยอาชีวศึกษาเพชรบุรี และการท่องเที่ยวเมืองเพชรบุรี ยินดีต้อนรับค่ะ!',
            'intent': 'travel',
            'maps_query': 'วิทยาลัยอาชีวศึกษาเพชรบุรี',
            'created_at': datetime.datetime.now().strftime("%d/%m/%Y %H:%M น.")
        }
    return render_template('share.html', card=card)

