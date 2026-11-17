# -*- coding: utf-8 -*-
"""
services/tts_service.py — High-Performance Neural Voice & On-Device TTS Engine
"""
import os
import io
import re
import base64
import hashlib
import time
import asyncio
import threading
import logging
from collections import OrderedDict
import edge_tts

logger = logging.getLogger("nongphet.tts")

TTS_CACHE = OrderedDict()
MAX_TTS_CACHE_SIZE = 256
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, 'static', 'audio', 'cache')
try:
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
except Exception:
    pass

# ==============================================================================
# นโยบาย "เสียงเดียวทั้งระบบ" (One Voice Policy)
# - ทุกเส้นทางใช้ voice_profile() เดียวกัน (ค่ามาจาก config.Config)
# - ไม่มีเสียงสำรองที่เป็นคนอื่น (เลิกใช้ gTTS / PyThaiTTS / เสียงเบราว์เซอร์)
#   ถ้าสร้างเสียงน้องเพชรไม่ได้ หน้าเว็บจะแสดงข้อความอย่างเดียว
# - แคชรับเฉพาะไฟล์รูปแบบเดียวกับ Edge-TTS (MP3 24kHz 48kbps mono) กันไฟล์เสียงอื่นหลุดเข้ามาปน
# ==============================================================================
def voice_profile(lang='th'):
    """คืน (voice, pitch, rate) ของเสียงน้องเพชรสำหรับภาษานั้น"""
    from config import Config
    if lang == 'en':
        return 'en-US-AriaNeural', '+0Hz', '+3%'
    if lang == 'zh':
        return 'zh-CN-XiaoxiaoNeural', '+0Hz', '+3%'
    return Config.TTS_DEFAULT_VOICE, Config.TTS_DEFAULT_PITCH, Config.TTS_DEFAULT_RATE


_SUGGESTION_DELIMS = ['---', '💡 ถามต่อยอด', 'ถามต่อยอดกับน้องเพชร', '💡 แนะนำคำถาม', 'คำถามที่น่าสนใจ',
                      '💡 Follow-up', '💡 推荐问题', '❓ คำถาม']
_INPUT_EMOJI_RE = re.compile(r'[\U00010000-\U0010FFFF☀-➿︎️‍⌀-⏿⭐⭕]')


def prepare_speech_input(text):
    """
    เตรียมข้อความขาเข้าให้เหมือนกันทุกเส้นทาง (เทียบเท่า stripEmojiAndIcons() ใน static/js/main.js)
    หน้าจอ kiosk / หน้าจอใบหน้า / สคริปต์อัดเสียง ส่งข้อความมาไม่เหมือนกัน (บางที่ตัดอีโมจิแล้ว บางที่ยัง)
    ถ้าไม่ทำให้เหมือนกันก่อน ประโยคเดียวกันจะได้เนื้อหาเสียงและคีย์แคชต่างกัน
    เรียกซ้ำได้ผลเท่าเดิม (idempotent)
    """
    t = text or ''
    for delim in _SUGGESTION_DELIMS:
        if delim in t:
            t = t.split(delim)[0].strip()
    t = _INPUT_EMOJI_RE.sub('', t)
    t = re.sub(r'[*#_~>•\-=|`]', ' ', t)
    t = re.sub(r'[^\w\s฀-๿一-龥.,!?\'"-]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


# ตัดช่องว่างและเครื่องหมายวรรคตอนออกจากคีย์แคช: หน้าจอต่างๆ เตรียมข้อความต่างกันเล็กน้อย
# (เช่น ขึ้นบรรทัดใหม่เป็น ", " หรือเป็นช่องว่าง) ให้ยังได้ไฟล์เสียงเดียวกัน
_KEY_STRIP_RE = re.compile(r"[\s.,!?'\"\-]+")


def speech_cache_key(clean_text, voice, pitch, rate):
    return f"{voice}_{pitch}_{rate}_{_KEY_STRIP_RE.sub('', clean_text or '')}"


# รูปแบบไฟล์ที่ Edge-TTS ส่งมา (audio-24khz-48kbitrate-mono-mp3)
_CANONICAL_AUDIO = (24000, 48, 'mono')
_MPEG2_BITRATES = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
_MPEG1_BITRATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def audio_format_of(raw_bytes):
    """อ่านรูปแบบจากเฟรม MP3 แรก คืน (sample_rate, kbps, 'mono'|'stereo') หรือ None ถ้าไม่ใช่ MP3"""
    if not raw_bytes or raw_bytes[:4] == b'RIFF':
        return None
    b = raw_bytes[:65536]
    i = 0
    if b[:3] == b'ID3' and len(b) > 10:
        i = ((b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]) + 10
    while i < len(b) - 4:
        if b[i] == 0xFF and (b[i + 1] & 0xE0) == 0xE0:
            version = (b[i + 1] >> 3) & 3
            layer = (b[i + 1] >> 1) & 3
            br_idx = b[i + 2] >> 4
            sr_idx = (b[i + 2] >> 2) & 3
            if version != 1 and layer == 1 and 0 < br_idx < 15 and sr_idx < 3:
                table = _MPEG1_BITRATES if version == 3 else _MPEG2_BITRATES
                mode = 'mono' if (b[i + 3] >> 6) == 3 else 'stereo'
                return _SAMPLE_RATES[version][sr_idx], table[br_idx], mode
        i += 1
    return None


def is_canonical_voice_audio(raw_bytes):
    return audio_format_of(raw_bytes) == _CANONICAL_AUDIO


def audit_audio_cache(delete=False):
    """
    ตรวจไฟล์ในแคชเสียงทั้งหมด คืนรายชื่อไฟล์ที่ไม่ใช่รูปแบบเสียงน้องเพชร (เช่น เสียง Google / WAV)
    delete=True จะลบไฟล์เหล่านั้นทิ้ง
    """
    bad = []
    for name in sorted(os.listdir(AUDIO_CACHE_DIR)):
        path = os.path.join(AUDIO_CACHE_DIR, name)
        if not os.path.isfile(path):
            continue
        with open(path, 'rb') as f:
            head = f.read(65536)
        if not is_canonical_voice_audio(head):
            bad.append((name, audio_format_of(head)))
            if delete:
                os.remove(path)
    return bad


def get_cached_tts(cache_key):
    """ดึงเสียงสังเคราะห์จาก RAM Cache หรือ Disk Cache ถาวร (0-5ms response)"""
    if cache_key in TTS_CACHE:
        return TTS_CACHE[cache_key], 'memory-cache'

    disk_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
    disk_file = os.path.join(AUDIO_CACHE_DIR, f"{disk_hash}.mp3")
    if os.path.exists(disk_file):
        try:
            with open(disk_file, 'rb') as f:
                raw_bytes = f.read()
            if not is_canonical_voice_audio(raw_bytes):
                # ไฟล์เสียงคนอื่นที่หลุดเข้ามาในแคช (เช่น เสียง Google) -> ไม่เล่น
                logger.warning(f"🔇 [Voice Cache] ข้ามไฟล์ที่ไม่ใช่เสียงน้องเพชร: {disk_hash}.mp3 {audio_format_of(raw_bytes)}")
                return None, None
            b64_str = base64.b64encode(raw_bytes).decode('utf-8')
            if len(TTS_CACHE) >= MAX_TTS_CACHE_SIZE:
                TTS_CACHE.popitem(last=False)
            TTS_CACHE[cache_key] = b64_str
            return b64_str, 'disk-cache'
        except Exception:
            pass
    return None, None

def save_cached_tts(cache_key, raw_bytes, b64_str=None):
    """บันทึกเสียงสังเคราะห์ลงทั้ง RAM Cache และ Disk Cache ถาวร (เฉพาะเสียงน้องเพชร)"""
    if not is_canonical_voice_audio(raw_bytes):
        logger.warning(f"🔇 [Voice Cache] ไม่บันทึกเสียงที่ไม่ใช่รูปแบบเสียงน้องเพชร {audio_format_of(raw_bytes)}")
        return
    if not b64_str:
        b64_str = base64.b64encode(raw_bytes).decode('utf-8')
    if len(TTS_CACHE) >= MAX_TTS_CACHE_SIZE:
        TTS_CACHE.popitem(last=False)
    TTS_CACHE[cache_key] = b64_str

    try:
        disk_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        disk_file = os.path.join(AUDIO_CACHE_DIR, f"{disk_hash}.mp3")
        if not os.path.exists(disk_file):
            with open(disk_file, 'wb') as f:
                f.write(raw_bytes)
    except Exception as e:
        logger.warning(f"Disk Cache Write Error: {e}")

def extract_first_sentence_for_speech(text, lang='th', max_len=500):
    """
    ตัดประโยคหรือย่อหน้าแรกที่สมบูรณ์ สำหรับโหมดที่ต้องการความกระชับเป็นพิเศษ
    """
    if not text:
        return ""
    
    # ตัดส่วน Interactive suggestion chip ท้ายข้อความ
    for delim in ['---', '💡 ถามต่อยอด', 'ถามต่อยอดกับน้องเพชร', '💡 แนะนำคำถาม', 'คำถามที่น่าสนใจ', '💡 Follow-up', '💡 推荐问题', '❓ คำถาม']:
        if delim in text:
            text = text.split(delim)[0].strip()

    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    first_para = paragraphs[0] if paragraphs else text

    if len(first_para) <= max_len:
        return first_para

    cutoff = max_len
    for sep in ['ค่ะ', 'ครับ', 'นะคะ', '.', '!', '?', ' ']:
        idx = first_para.rfind(sep, int(max_len * 0.6), max_len)
        if idx != -1:
            cutoff = idx + len(sep)
            break
    return first_para[:cutoff].strip()

def clean_text_for_speech(text, max_len=2500, voice_gender='female', lang='th'):
    """
    ขัดเกลาและจัดวรรคตอนข้อความให้อ่านได้ครบถ้วน ชัดเจน และเป็นธรรมชาติเสมือนคนพูดจริง
    - แปลงลิสต์หัวข้อเป็นภาษาพูดต่อเนื่อง (Natural Conversational Phrasing)
    - แทรกจังหวะวรรคตอนและการหายใจ (Prosodic Breath Pauses) ที่แม่นยำ
    - ปรับน้ำเสียงและหางเสียงเป็นสุภาพสตรี 'ค่ะ/นะคะ' สม่ำเสมอ 100%
    - ถอดรหัสคำย่อ คำทับศัพท์ภาษาอังกฤษให้เป็นคำอ่านภาษาไทย (Phonetic Expansion)
    """
    if not text:
        return ""
    t = text

    # ตัดเฉพาะส่วนเมนูคำถามต่อยอดท้ายคำตอบ
    for delim in ['---', '💡 ถามต่อยอด', 'ถามต่อยอดกับน้องเพชร', '💡 แนะนำคำถาม', 'คำถามที่น่าสนใจ', '💡 Follow-up', '💡 推荐问题', '❓ คำถามแนะนำ']:
        if delim in t:
            t = t.split(delim)[0].strip()

    # ลบ URLs และ Markdown Links
    t = re.sub(r'https?://\S+|www\.\S+', '', t)
    t = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', t)

    if lang == 'th':
        # แปลงรายการลิสต์หัวข้อ (Numbered/Bullet lists) ให้เป็นคำพูดบทสนทนาที่เป็นธรรมชาติ
        t = re.sub(r'(?:^|\n)\s*1\.\s*', r'ข้อแรกคือ ', t)
        t = re.sub(r'(?:^|\n)\s*2\.\s*', r', ข้อต่อมาคือ ', t)
        t = re.sub(r'(?:^|\n)\s*3\.\s*', r', ต่อมาคือ ', t)
        t = re.sub(r'(?:^|\n)\s*4\.\s*', r', และอีกข้อคือ ', t)
        t = re.sub(r'(?:^|\n)\s*[5-9]\.\s*', r', นอกจากนี้คือ ', t)
        t = re.sub(r'(?:^|\n)\s*[•\-]\s*', r', ', t)

        # บังคับใช้อัตลักษณ์เสียงผู้หญิงน้องเพชร 100% ปิดเสียงผู้ชาย
        t = re.sub(r'ครับ/ค่ะ', 'ค่ะ', t)
        t = re.sub(r'ค่ะ/นะคะ', 'ค่ะ', t)
        t = re.sub(r'สวัสดีครับ', 'สวัสดีค่ะ', t)
        t = re.sub(r'ผมคือน้องเพชร', 'น้องเพชร', t)
        t = re.sub(r'ผมน้องเพชร', 'น้องเพชร', t)
        t = re.sub(r'คุยกับผม', 'คุยกับน้องเพชร', t)
        t = re.sub(r'ให้ผม', 'ให้น้องเพชร', t)
        t = re.sub(r'เอ็นดูผม', 'เอ็นดูน้องเพชร', t)
        t = re.sub(r'ลูบหัวผม', 'ลูบหัวน้องเพชร', t)
        t = re.sub(r'จิ้มแก้มผม', 'จิ้มแก้มน้องเพชร', t)
        t = re.sub(r'เกาหู.*ผม', 'เกาหูน้องเพชร', t)
        t = re.sub(r'(?<=[\s,])ผม(?=[\s,])', 'น้องเพชร', t)
        t = re.sub(r'^ผม\s*', 'น้องเพชร ', t)
        t = re.sub(r'นะครับ', 'นะคะ', t)
        t = re.sub(r'ครับผม', 'ยินดีค่ะ', t)
        t = re.sub(r'ครับ', 'ค่ะ', t)
        t = re.sub(r'ค้าบ', 'ค่า', t)
        t = re.sub(r'ไหมค่ะ', 'ไหมคะ', t)
        t = re.sub(r'หรือยังค่ะ', 'หรือยังคะ', t)
        t = re.sub(r'หรือเปล่าค่ะ', 'หรือเปล่าคะ', t)
        t = re.sub(r'ใช่ไหมค่ะ', 'ใช่ไหมคะ', t)

        abbrev_map = [
            (r'\bร\.([๔-๙4-9])\b', r'รัชกาลที่ \1'),
            (r'ร\.4', 'รัชกาลที่สี่'),
            (r'ร\.5', 'รัชกาลที่ห้า'),
            (r'ร\.6', 'รัชกาลที่หก'),
            (r'\bกม\.', 'กิโลเมตร'),
            (r'\bซม\.', 'เซนติเมตร'),
            (r'\bม\.\s*(\d)', r'เมตร \1'),
            (r'\bปวช\.', 'ระดับ ปวช.'),
            (r'\bปวส\.', 'ระดับ ปวส.'),
            (r'\bAI\b', 'เอไอ'),
            (r'\bWi-?Fi\b', 'ไวไฟ'),
            (r'\bGPS\b', 'จีพีเอส'),
            (r'\bQR\s*Code\b', 'คิวอาร์โค้ด'),
            (r'\bPBPVC\b', 'พีบีพีวีซี วิทยาลัยอาชีวศึกษาเพชรบุรี'),
            (r'\bPBVC\b', 'พีบีวีซี วิทยาลัยอาชีวศึกษาเพชรบุรี'),
            (r'\bUNESCO\b', 'ยูเนสโก'),
            (r'\bGI\b', 'จีไอ สิ่งบ่งชี้ทางภูมิศาสตร์'),
        ]
        for pattern, repl in abbrev_map:
            t = re.sub(pattern, repl, t, flags=re.IGNORECASE)

    # แปลงการขึ้นบรรทัดใหม่เป็นจุลภาคแบ่งวรรค
    t = re.sub(r'\n+', ', ', t)

    # ลบสัญลักษณ์ Markdown และเครื่องหมายพิเศษ
    t = re.sub(r'[*#_~>•\-=|`]', ' ', t)
    t = re.sub(r'\((?:อังกฤษ|Tel|โทร|ค่าเข้า|ราคา)[^)]*\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'[()\[\]{}]', ' ', t)

    # ลบ Emojis
    emoji_clean_regex = re.compile(
        r'[\U00010000-\U0010FFFF]'
        r'|[\u2600-\u27BF]'
        r'|[\u2300-\u23FF]'
        r'|[\u2B50\u2B55\u200D\uFE0E\uFE0F]'
    )
    t = emoji_clean_regex.sub('', t)
    t = re.sub(r'[^a-zA-Z0-9\u0E00-\u0E7F\u4E00-\u9FA5\s.,!?\'"-]', ' ', t)

    if lang == 'th':
        # แทรกจังหวะวรรคตอนและการหายใจ (Prosodic Breath Pauses) ตามหลักการพูดภาษาไทย
        pause_phrases = [
            (r'(\bสวัสดีค่ะ)\s*', r'\1, '),
            (r'(\bยินดีต้อนรับค่ะ)\s*', r'\1, '),
            (r'(\bยินดีเลยค่ะ)\s*', r'\1, '),
            (r'(\bได้เลยค่ะ)\s*', r'\1, '),
            (r'(\bแน่นอนค่ะ)\s*', r'\1, '),
            (r'(\bอ๋อ)\s*', r'\1, '),
            (r'(\bขอบคุณค่ะ)\s*', r'\1, '),
            (r'(\bรับทราบค่ะ)\s*', r'\1, '),
            (r'(\bขอแนะนำว่า)\s*', r'\1, '),
            (r'\s*(ซึ่งเป็น|ซึ่งมี|ซึ่งจะ|ซึ่ง)\s*', r', \1 '),
            (r'\s*(โดยมี|โดยเป็น|โดยจะ|โดยเฉพาะ|โดย)\s*', r', \1 '),
            (r'\s*(เนื่องจาก|เพราะว่า|เพราะ)\s*', r', \1 '),
            (r'\s*(สำหรับ)\s*', r', สำหรับ '),
            (r'\s*(นอกจากนี้|ทั้งนี้|ตลอดจน|รวมถึง|รวมทั้ง)\s*', r', \1, '),
            (r'\s*(อย่างไรก็ตาม|แต่ว่า|แต่ทว่า)\s*', r', \1, '),
            (r'\s*(ดังนั้น|ฉะนั้น)\s*', r', \1, '),
            (r'\s*(บอกเลยว่า)\s*', r', บอกเลยว่า '),
            (r'\s*(ไฮไลท์คือ|จุดเด่นคือ|ที่สำคัญคือ|ที่สำคัญ)\s*', r', \1 '),
            (r'(\d+\s*(?:บาท|กิโลเมตร|เมตร|อำเภอ|ตำบล|สาขาวิชา|แห่ง|คน|ปี|วัน|ชั่วโมง|นาที))\s+(ได้แก่|คือ|ประกอบด้วย|โดย|ซึ่ง|เท่านั้น)', r'\1, \2'),
            (r'(ไหมคะ|หรือเปล่าคะ|หรือยังคะ|อย่างไรคะ|อะไรบ้างคะ|ที่ไหนคะ)(?!\?)', r'\1? '),
        ]
        for pattern, repl in pause_phrases:
            t = re.sub(pattern, repl, t)

    # จัดระเบียบจุลภาคและวรรคตอนให้เป็นระเบียบเรียบร้อย
    t = re.sub(r'[\s,]+,', ', ', t)
    t = re.sub(r',\s*,+', ', ', t)
    t = re.sub(r',\s*!', '!', t)
    t = re.sub(r',\s*\?', '?', t)
    t = re.sub(r'!\s*,', '!, ', t)
    t = re.sub(r'\?\s*,', '? ', t)
    t = re.sub(r',\s*(ค่ะ|นะคะ|ค่า)', r' \1', t)
    t = re.sub(r'(ค่ะ|นะคะ|ค่า)\s*,', r'\1, ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    # ตรวจสอบความยาวสูงสุด หากยาวเกิน 2,500 ตัวอักษร ให้ตัดที่ขอบเขตประโยคอย่างนุ่มนวล
    if len(t) > max_len:
        cutoff = max_len
        for sep in ['ค่ะ', 'ครับ', 'นะคะ', '.', '!', '?', ', ']:
            idx = t.rfind(sep, int(max_len * 0.8), max_len)
            if idx != -1:
                cutoff = idx + len(sep)
                break
        t = t[:cutoff].strip()

    return t

# ------------------------------------------------------------------------------
# Edge-TTS ต้องใช้อินเทอร์เน็ต: เมื่อเน็ตล่ม ให้พักไว้ชั่วคราว (circuit breaker)
# แทนที่จะรอ timeout ทุกประโยคจนเสียงเงียบนาน
# ------------------------------------------------------------------------------
EDGE_BACKOFF_SEC = float(os.environ.get('TTS_EDGE_BACKOFF_SEC', '60'))
_edge_state = {'offline_until': 0.0}
_NETWORK_ERROR_NAMES = (
    'ClientConnectorError', 'ClientConnectionError', 'ClientOSError', 'ServerDisconnectedError',
    'ServerTimeoutError', 'WSServerHandshakeError', 'ClientConnectorDNSError', 'gaierror',
)


class EdgeTTSOffline(RuntimeError):
    """Edge-TTS ใช้ไม่ได้เพราะเครือข่าย (ให้ผู้เรียกข้ามไปใช้เสียงในเครื่องทันที)"""


def _is_network_error(err):
    if isinstance(err, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        return True
    if type(err).__name__ in _NETWORK_ERROR_NAMES:
        return True
    msg = str(err)
    return 'Cannot connect' in msg or 'getaddrinfo' in msg


def _mark_edge_offline():
    _edge_state['offline_until'] = time.time() + EDGE_BACKOFF_SEC


def _mark_edge_ok():
    _edge_state['offline_until'] = 0.0


def edge_tts_available():
    return time.time() >= _edge_state['offline_until']


def edge_tts_backoff_remaining():
    return max(0.0, _edge_state['offline_until'] - time.time())


def edge_wait_budget(text, retries=3):
    """เวลารวมสูงสุดที่ผู้เรียกควรรอ generate_speech (Azure ถ้าตั้งค่าไว้ + Edge-TTS รวมการเปิดการเชื่อมต่อใหม่)"""
    from services.azure_speech import azure_enabled
    azure_part = azure_timeout_for(text) + 2.0 if azure_enabled() else 0.0
    return azure_part + retries * FIRST_AUDIO_TIMEOUT + edge_timeout_for(text) + 3.0


def azure_timeout_for(text):
    """Azure Speech ส่งไฟล์กลับทีเดียว: รอตามความยาวข้อความ (ข้อความยาวใช้เวลามากขึ้น)"""
    return min(30.0, 6.0 + len(text or '') / 60.0)


def edge_timeout_for(text, base=6.0):
    """
    เวลาที่ยอมรอ Edge-TTS ต่อครั้ง ยืดตามความยาวข้อความ
    (คำตอบยาวจากฐานความรู้ใช้เวลาสร้างเสียงเกิน 6 วินาทีได้ ถ้าตัดที่ 6 วินาทีจะไม่มีวันสร้างสำเร็จ)
    """
    return min(45.0, max(base, 4.0 + len(text or '') / 40.0))


# เสียงท่อนแรกจาก Edge-TTS ปกติมาภายในครึ่งวินาที ถ้าเกินค่านี้ถือว่าการเชื่อมต่อค้าง ให้ตัดแล้วเปิดใหม่ทันที
FIRST_AUDIO_TIMEOUT = float(os.environ.get('TTS_FIRST_AUDIO_TIMEOUT', '4'))


class _EdgeStalled(Exception):
    """การเชื่อมต่อ Edge-TTS ค้าง ไม่มีเสียงกลับมาในเวลาที่กำหนด"""
    def __init__(self, msg, got_audio=False):
        super().__init__(msg)
        self.got_audio = got_audio


async def _synthesize_once(text, voice, rate, pitch, volume, total_timeout):
    """
    สร้างเสียงหนึ่งครั้ง: ต้องได้เสียงท่อนแรกภายใน FIRST_AUDIO_TIMEOUT และได้ครบภายใน total_timeout
    ถ้าค้างจะยกเลิกการเชื่อมต่อนั้นทันที (ผู้เรียกจะเปิดการเชื่อมต่อใหม่)
    """
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch, volume=volume)
    stream = communicate.stream()
    chunks = []

    async def next_audio():
        async for chunk in stream:
            if chunk['type'] == 'audio':
                return chunk['data']
        return None

    async def rest():
        async for chunk in stream:
            if chunk['type'] == 'audio':
                chunks.append(chunk['data'])

    try:
        try:
            first = await asyncio.wait_for(next_audio(), timeout=FIRST_AUDIO_TIMEOUT)
        except asyncio.TimeoutError:
            raise _EdgeStalled(f"no audio within {FIRST_AUDIO_TIMEOUT:g}s")
        if first is None:
            return b''
        chunks.append(first)
        try:
            await asyncio.wait_for(rest(), timeout=total_timeout)
        except asyncio.TimeoutError:
            raise _EdgeStalled(f"audio stalled after {len(chunks)} chunks", got_audio=True)
        return b''.join(chunks)
    finally:
        try:
            await stream.aclose()
        except Exception:
            pass


async def generate_edge_tts(text, voice=None, rate=None, pitch=None, volume="+0%", timeout=None, retries=3):
    """
    สร้างเสียงสังเคราะห์ผ่าน Edge-TTS ด้วยเสียงประจำตัวน้องเพชร (voice_profile) เมื่อไม่ได้ระบุ voice/pitch/rate

    การรับมือเมื่อ Edge-TTS ค้างหรือล้ม:
      - การเชื่อมต่อค้าง (ไม่มีเสียงใน FIRST_AUDIO_TIMEOUT) หรือ "No audio was received"
        -> ตัดทิ้งแล้วเปิดการเชื่อมต่อใหม่ทันที (ส่วนใหญ่รอบใหม่ได้เสียงภายในไม่ถึง 1 วินาที)
      - ต่อเน็ตไม่ได้จริง (DNS / connection error) -> พัก Edge-TTS ชั่วคราว (circuit breaker)
      - ค้างทุกรอบ -> ถือว่าเน็ตมีปัญหา พักชั่วคราวเช่นกัน
    """
    default_voice, default_pitch, default_rate = voice_profile('th')
    if not voice or 'Niwat' in voice or 'Pattara' in voice:
        voice = default_voice
    pitch = pitch or default_pitch
    rate = rate or default_rate
    total_timeout = edge_timeout_for(text, base=timeout or 6.0)

    # เน็ตเพิ่งล่มไป -> ไม่ต้องรอซ้ำ ให้ผู้เรียกตอบกลับทันที (หน้าเว็บแสดงข้อความอย่างเดียว)
    if not edge_tts_available():
        raise EdgeTTSOffline(f"Edge-TTS skipped: network down, retry in {edge_tts_backoff_remaining():.0f}s")

    last_error = None
    stalls = 0
    for attempt in range(retries):
        try:
            audio = await _synthesize_once(text, voice, rate, pitch, volume, total_timeout)
            if audio:
                _mark_edge_ok()
                return audio
            last_error = 'empty audio'
        except _EdgeStalled as st:
            if not st.got_audio:
                stalls += 1   # นับเฉพาะรอบที่ไม่ได้เสียงเลย (ถ้าได้เสียงบางส่วน แปลว่าเน็ตยังใช้ได้)
            last_error = st
            logger.warning(f"Edge-TTS [{voice}] attempt {attempt + 1}/{retries} stalled ({st}) -> reconnect")
            continue
        except Exception as ve:
            last_error = ve
            err_msg = str(ve) if str(ve) else type(ve).__name__
            logger.warning(f"Edge-TTS [{voice}] attempt {attempt + 1}/{retries} failed ({err_msg})")
            if _is_network_error(ve) and not isinstance(ve, (asyncio.TimeoutError, TimeoutError)):
                # ต่อเครื่องปลายทางไม่ได้เลย: ลองซ้ำก็เสียเวลาเปล่า -> พัก Edge-TTS ชั่วคราว
                _mark_edge_offline()
                raise EdgeTTSOffline(f"Edge-TTS network error: {err_msg}") from ve
        if attempt < retries - 1:
            await asyncio.sleep(0.2)

    if stalls == retries:
        # ค้างทุกรอบ: เน็ตน่าจะมีปัญหา พักไว้ก่อนเพื่อไม่ให้ประโยคถัดไปต้องรอซ้ำ
        _mark_edge_offline()
        raise EdgeTTSOffline(f"Edge-TTS stalled on every attempt: {last_error}")
    raise RuntimeError(f"Edge-TTS failed after {retries} attempts: {last_error}")


async def generate_speech(text, voice=None, rate=None, pitch=None, volume="+0%", timeout=None, retries=3):
    """
    สร้างเสียงน้องเพชร: ใช้ Azure Speech (บริการทางการ) ก่อนถ้าตั้งค่าไว้ ถ้าใช้ไม่ได้ค่อยใช้ Edge-TTS
    ทั้งสองทางเป็นเสียงเดียวกัน (voice/pitch/rate เดียวกัน) และส่งไฟล์รูปแบบเดียวกัน
    """
    default_voice, default_pitch, default_rate = voice_profile('th')
    if not voice or 'Niwat' in voice or 'Pattara' in voice:
        voice = default_voice
    pitch = pitch or default_pitch
    rate = rate or default_rate

    from services.azure_speech import azure_enabled, synthesize_azure, AzureSpeechError
    if azure_enabled():
        try:
            audio = await synthesize_azure(text, voice, pitch, rate, volume, timeout=azure_timeout_for(text))
            if is_canonical_voice_audio(audio):
                return audio
            logger.warning(f"Azure Speech ส่งรูปแบบไฟล์ไม่ตรง {audio_format_of(audio)} -> ใช้ Edge-TTS แทน")
        except AzureSpeechError as e:
            logger.warning(f"Azure Speech ใช้ไม่ได้ ({e}) -> ใช้ Edge-TTS แทน")
    return await generate_edge_tts(text, voice=voice, rate=rate, pitch=pitch, volume=volume,
                                   timeout=timeout, retries=retries)


def iter_audio_stream(text, lang='th', volume="+0%", voice=None, pitch=None, rate=None, use_cache=True):
    """
    Generator สำหรับส่งสตรีมข้อมูลเสียงแบบ Chunked HTTP Audio Stream (<200ms TTFB)
    ใช้เสียงน้องเพชรจาก voice_profile() เสมอ ยกเว้นหน้าทดลองเสียง (use_cache=False) ที่ส่ง pitch/rate มาเอง
    """
    p_voice, p_pitch, p_rate = voice_profile(lang)
    voice, pitch, rate = voice or p_voice, pitch or p_pitch, rate or p_rate
    clean_text = clean_text_for_speech(prepare_speech_input(text), max_len=2500, voice_gender='female', lang=lang)
    cache_key = speech_cache_key(clean_text, voice, pitch, rate)
    cached_b64 = get_cached_tts(cache_key)[0] if use_cache else None

    if cached_b64:
        raw_bytes = base64.b64decode(cached_b64)
        chunk_size = 4096
        for i in range(0, len(raw_bytes), chunk_size):
            yield raw_bytes[i:i + chunk_size]
        return

    # ถ้ายังไม่มีแคช ให้สร้างแบบสดและเก็บลงแคชพร้อมส่งออกทันที
    try:
        audio_bytes = run_coroutine(generate_speech(clean_text, voice=voice, rate=rate, pitch=pitch, volume=volume),
                                    timeout=edge_wait_budget(clean_text))
        if use_cache:
            save_cached_tts(cache_key, audio_bytes)
        chunk_size = 4096
        for i in range(0, len(audio_bytes), chunk_size):
            yield audio_bytes[i:i + chunk_size]
    except Exception as e:
        logger.warning(f"Audio stream error ({e})")
        yield b""


class PersistentTTSWorker:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True, name="TTS-Worker-Thread")
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout=12.0):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            future.cancel()  # ตัดงานค้างใน worker thread ทันที ป้องกัน orphan retries
            raise e

tts_worker = PersistentTTSWorker()

def run_coroutine(coro, timeout=12.0):
    return tts_worker.run(coro, timeout=timeout)
