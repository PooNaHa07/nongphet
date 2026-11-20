# -*- coding: utf-8 -*-
"""
services/azure_speech.py — Azure AI Speech (Text-to-Speech) แบบทางการของ Microsoft

ใช้เสียงเดียวกับ Edge-TTS (th-TH-PremwadeeNeural) แต่เป็นบริการทางการที่มีคีย์ จึงเสถียรกว่า
ช่องทางฟรีของ Edge ที่ค้าง/ถูกจำกัดความถี่บ่อย ระบบจะใช้ Azure ก่อน ถ้าใช้ไม่ได้ค่อยใช้ Edge-TTS
(เป็นเสียงเดียวกันทั้งสองทาง น้ำเสียงจึงไม่เปลี่ยน)

ตั้งค่าในไฟล์ .env (ไม่ต้องแก้โค้ด):
    AZURE_SPEECH_KEY=<คีย์จาก Azure Portal: Speech service > Keys and Endpoint>
    AZURE_SPEECH_REGION=<ภูมิภาคของ resource เช่น southeastasia>
    # หรือระบุ endpoint เต็มแทน region:
    # AZURE_SPEECH_ENDPOINT=https://<region>.tts.speech.microsoft.com/cognitiveservices/v1
ถ้าไม่ได้ตั้งค่า ระบบจะใช้ Edge-TTS อย่างเดียวเหมือนเดิม
"""
import os
import time
import html
import asyncio
import logging

import httpx

import config  # noqa: F401  (โหลดค่าจาก .env เข้า os.environ)

logger = logging.getLogger("nongphet.azure_speech")

# รูปแบบเดียวกับที่ Edge-TTS ส่งมา ไฟล์จากสองทางจึงใช้แคชร่วมกันได้และผ่านตัวตรวจ "เสียงน้องเพชร"
OUTPUT_FORMAT = 'audio-24khz-48kbitrate-mono-mp3'
AUTH_FAIL_COOLDOWN_SEC = 300.0     # คีย์ผิด/หมดอายุ: ไม่ต้องลองซ้ำทุกประโยค
NETWORK_FAIL_COOLDOWN_SEC = 30.0   # ต่อไม่ได้: พักสั้นๆ แล้วค่อยลองใหม่
MAX_RETRY_AFTER_SEC = 10.0

_state = {'cooldown_until': 0.0, 'last_error': None}


class AzureSpeechError(RuntimeError):
    """Azure Speech ใช้ไม่ได้ในครั้งนี้ (ผู้เรียกควรไปใช้ Edge-TTS ต่อ)"""


def _settings():
    key = os.environ.get('AZURE_SPEECH_KEY', '').strip()
    region = os.environ.get('AZURE_SPEECH_REGION', '').strip()
    endpoint = os.environ.get('AZURE_SPEECH_ENDPOINT', '').strip()
    if not endpoint and region:
        endpoint = f'https://{region}.tts.speech.microsoft.com/cognitiveservices/v1'
    return key, region, endpoint


def azure_enabled():
    key, _, endpoint = _settings()
    return bool(key and endpoint)


def azure_status():
    """สถานะสำหรับแสดงผล (ไม่เปิดเผยคีย์)"""
    key, region, endpoint = _settings()
    remaining = max(0.0, _state['cooldown_until'] - time.time())
    return {
        'configured': bool(key and endpoint),
        'region': region or None,
        'cooling_down_sec': round(remaining, 1),
        'last_error': _state['last_error'],
    }


def _cooldown(seconds, reason):
    _state['cooldown_until'] = time.time() + seconds
    _state['last_error'] = reason


def build_ssml(text, voice, pitch, rate, volume='+0%'):
    lang = '-'.join(voice.split('-')[:2]) or 'th-TH'
    body = html.escape(text or '', quote=True)
    return (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{lang}'>"
        f"<voice name='{voice}'><prosody pitch='{pitch}' rate='{rate}' volume='{volume}'>{body}</prosody></voice>"
        f"</speak>"
    )


async def synthesize_azure(text, voice, pitch, rate, volume='+0%', timeout=10.0):
    """
    สร้างเสียงผ่าน Azure Speech REST API คืน MP3 bytes
    raise AzureSpeechError เมื่อใช้ไม่ได้ (ไม่ได้ตั้งค่า / คีย์ผิด / โควตาเต็ม / ต่อไม่ได้)
    """
    key, _, endpoint = _settings()
    if not (key and endpoint):
        raise AzureSpeechError('Azure Speech not configured')
    if time.time() < _state['cooldown_until']:
        raise AzureSpeechError(f"Azure Speech cooling down ({_state['last_error']})")

    headers = {
        'Ocp-Apim-Subscription-Key': key,
        'Content-Type': 'application/ssml+xml',
        'X-Microsoft-OutputFormat': OUTPUT_FORMAT,
        'User-Agent': 'nongphet-kiosk',
    }
    ssml = build_ssml(text, voice, pitch, rate, volume).encode('utf-8')

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(2):
                res = await client.post(endpoint, content=ssml, headers=headers)
                if res.status_code == 200 and res.content:
                    _state['last_error'] = None
                    return res.content
                if res.status_code == 429 and attempt == 0:
                    # ใช้เกินโควตาต่อนาที: รอตามที่ Azure บอก แล้วลองอีกครั้ง
                    try:
                        wait = float(res.headers.get('Retry-After', '2'))
                    except ValueError:
                        wait = 2.0
                    await asyncio.sleep(min(max(wait, 0.5), MAX_RETRY_AFTER_SEC))
                    continue
                if res.status_code in (401, 403):
                    _cooldown(AUTH_FAIL_COOLDOWN_SEC, f'auth failed (HTTP {res.status_code}): ตรวจ AZURE_SPEECH_KEY / REGION')
                    raise AzureSpeechError(_state['last_error'])
                if res.status_code == 429:
                    _cooldown(MAX_RETRY_AFTER_SEC, 'rate limited (HTTP 429)')
                    raise AzureSpeechError(_state['last_error'])
                _state['last_error'] = f'HTTP {res.status_code}'
                raise AzureSpeechError(f'Azure Speech HTTP {res.status_code}')
    except httpx.HTTPError as e:
        _cooldown(NETWORK_FAIL_COOLDOWN_SEC, f'network error: {type(e).__name__}')
        raise AzureSpeechError(_state['last_error']) from e
    raise AzureSpeechError('Azure Speech returned no audio')
