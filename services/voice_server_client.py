# -*- coding: utf-8 -*-
"""
services/voice_server_client.py — ฝั่ง Raspberry Pi ที่เรียกเซิร์ฟเวอร์เสียงน้องเพชร (OmniVoice)
บนโน้ตบุ๊ก GPU ภายในบูธ (tools/voice_server.py) ผ่านวงแลน

ใช้เมื่อ TTS_ENGINE=omnivoice:
    VOICE_SERVER_URL=http://<IP โน้ตบุ๊ก>:8010
    VOICE_SERVER_TOKEN=<รหัสเดียวกับบนโน้ตบุ๊ก>
    VOICE_ID=nongphet-omni-v2      (เปลี่ยนเมื่อเปลี่ยนเสียงต้นแบบ เพื่อไม่ให้เล่นไฟล์เสียงเก่า)

ถ้าโน้ตบุ๊กดับหรือหลุดจากวงแลน จะพักการเรียกชั่วคราว แล้วให้ระบบใช้เสียงที่อัดไว้ / ประโยคกลางแทน
"""
import os
import time
import logging

import httpx

import config  # noqa: F401  (โหลดค่าจาก .env เข้า os.environ)

logger = logging.getLogger("nongphet.voice_server")

OFFLINE_COOLDOWN_SEC = 20.0      # ต่อไม่ได้: พักสั้นๆ แล้วลองใหม่ (โน้ตบุ๊กอาจกำลังรีสตาร์ท)
BAKE_MIN_WAIT_SEC = 180.0        # อัดเก็บล่วงหน้า: รออย่างน้อย 3 นาทีต่อประโยค
_state = {'offline_until': 0.0, 'last_error': None, 'last_ms': None}


class VoiceServerError(RuntimeError):
    """เซิร์ฟเวอร์เสียงใช้ไม่ได้ในครั้งนี้"""


def tts_engine():
    return os.environ.get('TTS_ENGINE', 'edge').strip().lower()


def omnivoice_enabled():
    return tts_engine() == 'omnivoice'


def voice_id():
    return os.environ.get('VOICE_ID', 'nongphet-omni-v2').strip() or 'nongphet-omni-v2'


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
    เวลารอเซิร์ฟเวอร์เสียง: 32 รอบบน GTX 1650 (ต้นแบบ 5 วินาที) ใช้เวลาประมาณ 3 เท่าของความยาวเสียง
    ภาษาไทยพูดประมาณ 12 ตัวอักษร/วินาที จึงเผื่อ 0.3 วินาทีต่อตัวอักษร
    """
    return min(180.0, 15.0 + len(text or '') * 0.3)


def _mark_offline(reason):
    _state['offline_until'] = time.time() + OFFLINE_COOLDOWN_SEC
    _state['last_error'] = reason


async def synthesize_voice_server(text, timeout=None, purpose='live'):
    """ขอเสียงจากเซิร์ฟเวอร์เสียงในบูธ คืน MP3 bytes หรือ raise VoiceServerError"""
    url = _url()
    if not url:
        raise VoiceServerError('VOICE_SERVER_URL not set')
    # อัดเก็บล่วงหน้าไม่สนช่วงพัก: ลองต่อทุกประโยค (ตอบสดเท่านั้นที่ต้องรีบตัดไปใช้ประโยคสำรอง)
    if purpose != 'bake' and time.time() < _state['offline_until']:
        raise VoiceServerError(f"voice server cooling down ({_state['last_error']})")
    headers = {'X-Voice-Token': os.environ.get('VOICE_SERVER_TOKEN', '')}
    # อัดเก็บล่วงหน้าไม่มีคนรอฟัง จึงรอนานได้ (บางประโยคช้าเพราะ GPU ถูกแย่ง เช่น มีหน้าเว็บขอเสียงพร้อมกัน)
    wait = timeout or (max(BAKE_MIN_WAIT_SEC, voice_server_timeout_for(text) * 3) if purpose == 'bake'
                       else voice_server_timeout_for(text))
    try:
        async with httpx.AsyncClient(timeout=wait) as client:
            res = await client.post(f'{url}/synthesize', json={'text': text, 'purpose': purpose}, headers=headers)
    except httpx.TimeoutException as e:
        # เซิร์ฟเวอร์ยังทำงานอยู่ แค่ช้า: ไม่ต้องพัก ไม่งั้นประโยคถัดไปจะล้มตามทั้งที่เครื่องปกติ
        _state['last_error'] = f'timeout after {wait:.0f}s: {type(e).__name__}'
        raise VoiceServerError(_state['last_error']) from e
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


# ---------------------------------------------------------------------------
# ถอดเสียงพูดเป็นข้อความ (Whisper ภาษาไทยบนโน้ตบุ๊ก GPU) แทน Web Speech ของ Chromium บน Pi ที่ใช้ไม่ได้
# ---------------------------------------------------------------------------
_stt_state = {'available': None, 'checked_at': 0.0, 'last_error': None, 'last_ms': None}
STT_STATUS_TTL_SEC = 30.0


def stt_status(refresh=False):
    """มีตัวถอดเสียงบนเซิร์ฟเวอร์เสียงหรือไม่ (จำผลไว้ 30 วินาที ไม่ยิงถามทุกครั้ง)"""
    url = _url()
    now = time.time()
    if url and (refresh or _stt_state['available'] is None or now - _stt_state['checked_at'] > STT_STATUS_TTL_SEC):
        try:
            res = httpx.get(f'{url}/health', timeout=3.0)
            _stt_state['available'] = bool(res.status_code == 200 and res.json().get('stt'))
            _stt_state['last_error'] = None if _stt_state['available'] else 'stt not enabled on voice server'
        except (httpx.HTTPError, ValueError) as e:
            _stt_state['available'] = False
            _stt_state['last_error'] = f'network error: {type(e).__name__}'
        _stt_state['checked_at'] = now
    return {'available': bool(url) and bool(_stt_state['available']), 'url': url or None,
            'last_error': _stt_state['last_error'], 'last_ms': _stt_state['last_ms']}


def transcribe_voice_server(wav_bytes, lang='th', timeout=20.0):
    """ส่งเสียง WAV ไปถอดความที่เซิร์ฟเวอร์เสียง คืนข้อความ หรือ raise VoiceServerError"""
    url = _url()
    if not url:
        raise VoiceServerError('VOICE_SERVER_URL not set')
    try:
        res = httpx.post(f'{url}/transcribe', params={'lang': lang}, content=wav_bytes, timeout=timeout,
                         headers={'X-Voice-Token': os.environ.get('VOICE_SERVER_TOKEN', ''),
                                  'Content-Type': 'audio/wav'})
    except httpx.HTTPError as e:
        _stt_state.update(available=False, checked_at=time.time(), last_error=f'network error: {type(e).__name__}')
        raise VoiceServerError(_stt_state['last_error']) from e
    if res.status_code == 200:
        data = res.json()
        _stt_state.update(available=True, checked_at=time.time(), last_error=None, last_ms=data.get('ms'))
        return (data.get('text') or '').strip()
    _stt_state['last_error'] = 'unauthorized: ตรวจ VOICE_SERVER_TOKEN' if res.status_code == 403 else f'HTTP {res.status_code}'
    raise VoiceServerError(f"transcribe HTTP {res.status_code}")
