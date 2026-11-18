# -*- coding: utf-8 -*-
"""
tests package for น้องเพชร AI Smart Guide
"""

import os

# เทสต์ต้องไม่ขึ้นกับ .env ของเครื่อง (เช่น TTS_ENGINE=omnivoice บนเครื่องที่อัดเสียง)
# ตั้งค่าเสียงกลางไว้ก่อน config.py โหลด .env (config ไม่ทับค่าที่มีอยู่แล้ว)
# เทสต์ที่ต้องการโหมดอื่นจะ patch os.environ เอง
TEST_VOICE_ENV = {
    'TTS_ENGINE': 'edge',
    'VOICE_ID': 'nongphet-omni-v1',
    'VOICE_SERVER_URL': '',
    'VOICE_SERVER_TOKEN': '',
    'AZURE_SPEECH_KEY': '',
    'AZURE_SPEECH_REGION': '',
    # ไม่ให้เทสต์เรียก Gemini จริงด้วยคีย์ใน .env (เทสต์ชั้นค้นเว็บจะ patch เอง)
    'GEMINI_API_KEY': '',
}


def isolate_voice_env():
    os.environ.update(TEST_VOICE_ENV)


isolate_voice_env()
