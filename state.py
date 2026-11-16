# -*- coding: utf-8 -*-
"""
state.py — Shared mutable state ที่ใช้ร่วมกันหลาย routes
(chat_histories, SESSION_LAST_TOPIC, circuit-breaker flags, shared_cards, emotion_state, APP_START_TIME)
"""
import datetime
from collections import OrderedDict

APP_START_TIME = datetime.datetime.now()

# Multi-turn chat histories per session
chat_histories = {}

# เก็บหัวข้อล่าสุดของแต่ละ Session เพื่อรองรับคำถามสั้นต่อเนื่องในโหมด RAG Offline
SESSION_LAST_TOPIC = OrderedDict()
MAX_SESSION_TOPICS = 200

# Circuit Breaker สำหรับ Cloud AI
LAST_GEMINI_FAIL_TIME = 0
GEMINI_CIRCUIT_COOLDOWN = 120  # วินาที

# QR Share cards (in-memory)
shared_cards = {}

# อารมณ์น้องเพชร (Emotion Engine)
emotion_state = {
    'current': 'idle',
    'timestamp': datetime.datetime.now().strftime("%H:%M:%S")
}

