# -*- coding: utf-8 -*-
"""
services/voice_server_client.py — ฝั่ง Raspberry Pi ที่เรียกเซิร์ฟเวอร์เสียงน้องเพชร (OmniVoice)
บนโน้ตบุ๊ก GPU ภายในบูธ (tools/voice_server.py) ผ่านวงแลน

ใช้เมื่อ TTS_ENGINE=omnivoice:
    VOICE_SERVER_URL=http://<IP โน้ตบุ๊ก>:8010
    VOICE_SERVER_TOKEN=<รหัสเดียวกับบนโน้ตบุ๊ก>
    VOICE_ID=nongphet-omni-v1      (เปลี่ยนเมื่อเปลี่ยนเสียงต้นแบบ เพื่อไม่ให้เล่นไฟล์เสียงเก่า)

ถ้าโน้ตบุ๊กดับหรือหลุดจากวงแลน จะพักการเรียกชั่วคราว แล้วให้ระบบใช้เสียงที่อัดไว้ / ประโยคกลางแทน
"""
import os
import time
import logging

import httpx

import config  # noqa: F401  (โหลดค่าจาก .env เข้า os.environ)

logger = logging.getLogger("nongphet.voice_server")

OFFLINE_COOLDOWN_SEC = 20.0      # ต่อไม่ได้: พักสั้นๆ แล้วลองใหม่ (โน้ตบุ๊กอาจกำลังรีสตาร์ท)
_state = {'offline_until': 0.0, 'last_error': None, 'last_ms': None}


class VoiceServerError(RuntimeError):
    """เซิร์ฟเวอร์เสียงใช้ไม่ได้ในครั้งนี้"""


def tts_engine():
    return os.environ.get('TTS_ENGINE', 'edge').strip().lower()


def omnivoice_enabled():
    return tts_engine() == 'omnivoice'


def voice_id():
    return os.environ.get('VOICE_ID', 'nongphet-omni-v1').strip() or 'nongphet-omni-v1'


def _url():
    return os.environ.get('VOICE_SERVER_URL', '').strip().rstrip('/')


def voice_server_status():
    remaining = max(0.0, _state['offline_until'] - time.time())
    return {
        'enabled': omnivoice_enabled(),
        'url': _url() or None,
        'voice_id': voice_id(),
        'available': bool(_url()) and remaining == 0.0,
        'cooling_down_sec': round(remaining, 1),
        'last_error': _state['last_error'],
        'last_synthesis_ms': _state['last_ms'],
    }


def voice_server_timeout_for(text):
    """
    เวลารอเซิร์ฟเวอร์เสียง: ตอบสด (8 รอบ) บน GTX 1650 ใช้เวลาใกล้เคียงความยาวเสียง
    ภาษาไทยพูดประมาณ 13 ตัวอักษร/วินาที จึงเผื่อ ~1 วินาทีต่อ 10 ตัวอักษร
    """
    return min(120.0, 10.0 + len(text or '') / 10.0)


def _mark_offline(reason):
    _state['offline_until'] = time.time() + OFFLINE_COOLDOWN_SEC
    _state['last_error'] = reason


async def synthesize_voice_server(text, timeout=None, purpose='live'):
    """ขอเสียงจากเซิร์ฟเวอร์เสียงในบูธ คืน MP3 bytes หรือ raise VoiceServerError"""
    url = _url()
    if not url:
        raise VoiceServerError('VOICE_SERVER_URL not set')
    if time.time() < _state['offline_until']:
        raise VoiceServerError(f"voice server cooling down ({_state['last_error']})")
    headers = {'X-Voice-Token': os.environ.get('VOICE_SERVER_TOKEN', '')}
    try:
        # อัดเก็บล่วงหน้าใช้รอบสร้างเสียงมากกว่าตอบสด (32 vs 8) จึงรอนานกว่า
        wait = timeout or voice_server_timeout_for(text) * (4 if purpose == 'bake' else 1)
        async with httpx.AsyncClient(timeout=wait) as client:
            res = await client.post(f'{url}/synthesize', json={'text': text, 'purpose': purpose}, headers=headers)
    except httpx.HTTPError as e:
        _mark_offline(f'network error: {type(e).__name__}')
        raise VoiceServerError(_state['last_error']) from e
    if res.status_code == 200 and res.content:
        _state['last_error'] = None
        try:
            _state['last_ms'] = int(res.headers.get('X-Synthesis-Ms', ''))
        except ValueError:
            pass
        return res.content
    if res.status_code == 403:
        _mark_offline('unauthorized: ตรวจ VOICE_SERVER_TOKEN ให้ตรงกับโน้ตบุ๊ก')
    else:
        _state['last_error'] = f'HTTP {res.status_code}'
    raise VoiceServerError(f"voice server HTTP {res.status_code}")
