# -*- coding: utf-8 -*-
"""
==============================================================================
น้องเพชร AI Smart Guide — Main Flask Application (Modular 2026 Edition)
วิทยาลัยอาชีวศึกษาเพชรบุรี (PBPVC) — นวัตกรรมสิ่งประดิษฐ์คนรุ่นใหม่ สอศ.
==============================================================================
สถาปัตยกรรม Modularized:
- routes/:
    * chat.py      — Conversational AI, Semantic RAG & Itinerary Planning
    * vision.py    — Vision Analysis & Thai Sign Language (TSL)
    * media.py     — Neural Voice TTS & Weather
    * iot.py       — ESP32 Hardware Integration & Sensor SSE Stream
    * admin.py     — Telemetry Dashboard & Mission Control
    * display.py   — Dual-Screen Emotion Display & QR Mobile Handoff
    * knowledge.py — Dynamic RAG Knowledge Base CRUD & Retrain APIs
- services/:
    * text_utils.py        — Suggestion / Language / Trap-query Helpers
    * arm_service.py       — Shoulder Servo Arm Gestures
    * knowledge_service.py — Local Knowledge & Fast Offline Fallback
    * analytics_service.py — Visitor Analytics Engine
    * tts_service.py       — Edge-TTS & PyThaiTTS Neural Engine
- state.py         — Centralized Shared Mutable State
==============================================================================
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import os
import uuid
import datetime
import logging
import logging.handlers
from flask import Flask, render_template, session, jsonify, send_from_directory

from config import Config
from state import APP_START_TIME

# Setup Rotating File Logger
def setup_logging():
    log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base_dir, 'nongphet.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # กรอง Log /api/emotion/gaze ความถี่สูงไม่ให้รกไฟล์ log
    class GazeNoiseFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            return '/api/emotion/gaze' not in msg

    logging.getLogger('werkzeug').addFilter(GazeNoiseFilter())
    return logging.getLogger("nongphet")

logger = setup_logging()

# ชนิดไฟล์ของไลบรารีที่เก็บในเครื่อง (static/vendor): Windows / Pi บางเครื่องไม่รู้จัก
# ถ้าส่งผิดชนิด เบราว์เซอร์อาจไม่ยอมโหลดฟอนต์ หรือโหลด WebAssembly ของ MediaPipe ไม่ได้
import mimetypes
mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('font/ttf', '.ttf')
mimetypes.add_type('application/wasm', '.wasm')

# Initialize Flask App
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = os.environ.get('SECRET_KEY', app.config.get('SECRET_KEY', 'nongphet_smart_guide_secure_key_2026_pbvc'))

# Import & Register Modular Blueprints
from routes.chat import chat_bp
from routes.vision import vision_bp
from routes.media import media_bp
from routes.iot import iot_bp
from routes.admin import admin_bp
from routes.display import display_bp
from routes.knowledge import knowledge_bp
from routes.arm import arm_bp

app.register_blueprint(arm_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(vision_bp)
app.register_blueprint(media_bp)
app.register_blueprint(iot_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(display_bp)
app.register_blueprint(knowledge_bp)

# Core Entrypoint Routes
@app.route('/health', methods=['GET'])
def health_check():
    uptime_sec = int((datetime.datetime.now() - APP_START_TIME).total_seconds())
    return jsonify({
        'status': 'healthy',
        'service': 'nongphet-ai-kiosk-modular',
        'uptime_seconds': uptime_sec,
        'timestamp': datetime.datetime.now().isoformat()
    }), 200

@app.route('/')
def index():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return render_template('index.html')

@app.route('/kiosk')
def kiosk():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return render_template('kiosk.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'img'), 'robot.svg', mimetype='image/svg+xml')

def main():
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1')
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cert_path = os.path.join(base_dir, 'cert.pem')
    key_path = os.path.join(base_dir, 'key.pem')
    
    ssl_context = None
    if os.path.exists(cert_path) and os.path.exists(key_path):
        ssl_context = (cert_path, key_path)
        logger.info(f"🔒 HTTPS Enabled: running with SSL certificate on https://0.0.0.0:{port}")
    else:
        logger.info(f"⚠️ SSL certificate not found, running HTTP on http://0.0.0.0:{port}")

    app.run(debug=debug_mode, host='0.0.0.0', port=port, ssl_context=ssl_context, threaded=True)

if __name__ == '__main__':
    main()
