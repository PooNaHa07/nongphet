# -*- coding: utf-8 -*-
"""
services/analytics_service.py — Visitor Analytics & Interaction Logging Engine
"""
import os
import json
import datetime
import logging

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

def save_analytics():
    try:
        with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(visitor_analytics, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Could not save analytics file: {e}")

def record_interaction(user_message, intent, confidence, engine, language):
    """บันทึกสถิติการใช้งานสำหรับแดชบอร์ด"""
    visitor_analytics['total_interactions'] += 1
    
    # บันทึกภาษา
    lang_key = language if language in visitor_analytics['languages'] else 'th'
    visitor_analytics['languages'][lang_key] += 1
    
    # บันทึก Engine
    if engine == 'local_model':
        visitor_analytics['local_ai_count'] += 1
    else:
        visitor_analytics['cloud_ai_count'] += 1
        
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

