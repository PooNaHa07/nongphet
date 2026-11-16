# -*- coding: utf-8 -*-
"""
services/analytics_service.py — Visitor Analytics & Interaction Logging Engine
"""
import os
import json
import atexit
import datetime
import logging
import threading

logger = logging.getLogger("nongphet.analytics")

# Path to persistent analytics file in project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYTICS_FILE = os.path.join(BASE_DIR, 'analytics_data.json')

visitor_analytics = {
    'total_visitors': 0,
    'total_interactions': 0,
    'local_ai_count': 0,
    'cloud_ai_count': 0,
    'sign_language_count': 0,
    'languages': {'th': 0, 'en': 0, 'zh': 0, 'tsl': 0},
    'intents': {
        'travel': 0,
        'food': 0,
        'admission': 0,
        'history': 0,
        'greeting': 0,
        'sign_language': 0,
        'general': 0
    },
    'hourly_traffic': [0] * 24,
    'recent_logs': []
}

def load_analytics():
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                visitor_analytics.update(saved)
                logger.info(f"Loaded persistent stats from {ANALYTICS_FILE}")
        except Exception as e:
            logger.warning(f"Could not load analytics file: {e}")

# รวมการบันทึกไฟล์เป็นช่วงๆ แทนการเขียนทุกครั้งที่มีการโต้ตอบ (ลดการเขียน SD card บน Raspberry Pi)
SAVE_DEBOUNCE_SEC = float(os.environ.get('ANALYTICS_SAVE_DELAY', '5'))
_save_lock = threading.Lock()
_save_timer = None


def _write_now():
    """เขียนไฟล์แบบ atomic: เขียนไฟล์ชั่วคราวแล้ว rename ทับ ไฟล์เดิมจึงไม่พังถ้าไฟดับระหว่างเขียน"""
    global _save_timer
    with _save_lock:
        _save_timer = None
        tmp_path = ANALYTICS_FILE + '.tmp'
        try:
            data = json.dumps(visitor_analytics, ensure_ascii=False, indent=2)
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, ANALYTICS_FILE)
        except Exception as e:
            logger.warning(f"Could not save analytics file: {e}")


def save_analytics(immediate=False):
    """
    บันทึกสถิติลงไฟล์
    immediate=False (ค่าเริ่มต้น): รวมการบันทึกที่เกิดถี่ๆ ภายใน SAVE_DEBOUNCE_SEC เป็นการเขียนครั้งเดียว
    immediate=True: เขียนทันที (ใช้ตอนรีเซ็ตสถิติหรือปิดโปรแกรม)
    """
    global _save_timer
    if immediate or SAVE_DEBOUNCE_SEC <= 0:
        with _save_lock:
            if _save_timer is not None:
                _save_timer.cancel()
                _save_timer = None
        _write_now()
        return
    with _save_lock:
        if _save_timer is not None:
            return  # มีการบันทึกที่รอเขียนอยู่แล้ว ข้อมูลล่าสุดจะถูกเขียนรวมไปในครั้งนั้น
        _save_timer = threading.Timer(SAVE_DEBOUNCE_SEC, _write_now)
        _save_timer.daemon = True
        _save_timer.start()


def flush_analytics():
    """เขียนข้อมูลที่ค้างอยู่ทันที (เรียกอัตโนมัติตอนปิดโปรแกรม)"""
    with _save_lock:
        pending = _save_timer is not None
    if pending:
        save_analytics(immediate=True)


atexit.register(flush_analytics)

def record_interaction(user_message, intent, confidence, engine, language):
    """บันทึกสถิติการใช้งานสำหรับแดชบอร์ด"""
    visitor_analytics['total_interactions'] += 1
    
    # บันทึกภาษา
    lang_key = language if language in visitor_analytics['languages'] else 'th'
    visitor_analytics['languages'][lang_key] += 1
    
    # บันทึก Engine (ระบบทำงานในเครื่องทั้งหมดแล้ว ไม่มี Cloud AI; คงคีย์ cloud_ai_count ไว้เพื่อให้ไฟล์สถิติเดิมยังอ่านได้)
    visitor_analytics['local_ai_count'] += 1
        
    # บันทึก Intent
    clean_intent = intent if intent in visitor_analytics['intents'] else 'general'
    visitor_analytics['intents'][clean_intent] = visitor_analytics['intents'].get(clean_intent, 0) + 1
    
    # บันทึกช่วงเวลาชั่วโมงปัจจุบัน
    current_hour = datetime.datetime.now().hour
    visitor_analytics['hourly_traffic'][current_hour] += 1
    
    # บันทึกลงรายการล่าสุด (เก็บ 25 รายการ)
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    log_entry = {
        'time': now_str,
        'message': user_message[:55] + ('...' if len(user_message) > 55 else ''),
        'intent': clean_intent,
        'confidence': round(confidence * 100, 1),
        'engine': engine,
        'language': lang_key
    }
    visitor_analytics['recent_logs'].insert(0, log_entry)
    visitor_analytics['recent_logs'] = visitor_analytics['recent_logs'][:25]
    save_analytics()

# Load analytics on module import
load_analytics()

