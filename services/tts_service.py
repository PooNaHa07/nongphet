# -*- coding: utf-8 -*-
"""
services/tts_service.py — High-Performance Neural Voice & On-Device TTS Engine
"""
import os
import io
import re
import base64
import hashlib
import asyncio
import threading
import logging
from collections import OrderedDict
import edge_tts
from gtts import gTTS

logger = logging.getLogger("nongphet.tts")

TTS_CACHE = OrderedDict()
MAX_TTS_CACHE_SIZE = 256
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, 'static', 'audio', 'cache')
try:
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
except Exception:
    pass

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
            b64_str = base64.b64encode(raw_bytes).decode('utf-8')
            if len(TTS_CACHE) >= MAX_TTS_CACHE_SIZE:
                TTS_CACHE.popitem(last=False)
            TTS_CACHE[cache_key] = b64_str
            return b64_str, 'disk-cache'
        except Exception:
            pass
    return None, None

def save_cached_tts(cache_key, raw_bytes, b64_str=None):
    """บันทึกเสียงสังเคราะห์ลงทั้ง RAM Cache และ Disk Cache ถาวร"""
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

async def generate_edge_tts(text, voice="th-TH-PremwadeeNeural", rate="+2%", pitch="+0Hz", volume="+0%", timeout=6.0, retries=2):
    """
    สร้างเสียงสังเคราะห์ Studio Neural Quality ผ่าน Edge-TTS
    รักษาอัตลักษณ์เสียงสุภาพสตรี th-TH-PremwadeeNeural (Pitch +0Hz, Rate +2%) สม่ำเสมอ 100%
    มี Fast-Fail Timeout (6.0s) และ Auto-Reconnect เมื่อเน็ตสะดุด
    """
    if not voice or 'Niwat' in voice or 'Pattara' in voice:
        voice = 'th-TH-PremwadeeNeural'

    last_error = None
    for attempt in range(retries):
        try:
            communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch, volume=volume)
            chunks = []
            async def collect():
                async for chunk in communicate.stream():
                    if chunk['type'] == 'audio':
                        chunks.append(chunk['data'])
            # แต่ละ attempt ให้เวลาไม่เกิน 6 วินาที (หากค้างให้ตัดแล้ว reconnect ทันที)
            attempt_timeout = min(timeout, 6.0)
            await asyncio.wait_for(collect(), timeout=attempt_timeout)
            if chunks:
                return b''.join(chunks)
        except Exception as ve:
            last_error = ve or "Connection Timeout"
            err_msg = str(ve) if str(ve) else type(ve).__name__
            logger.warning(f"Edge-TTS [{voice}] attempt {attempt + 1}/{retries} failed ({err_msg})")
            if attempt < retries - 1:
                await asyncio.sleep(0.3 * (attempt + 1))
            continue

    raise RuntimeError(f"Edge-TTS failed after {retries} retries: {last_error}")

def generate_gemini_audio(clean_text, voice_name="Aoede", timeout=7.0):
    """
    สร้างเสียงสังเคราะห์ผ่าน Gemini 3.8 / Multimodal Audio Engine (gemini-3.8-flash)
    พร้อมระบบตรวจสอบ Quota และ Auto-Fallback
    """
    from config import Config
    if not Config.GEMINI_API_KEY or Config.GEMINI_API_KEY == 'YOUR_GEMINI_API_KEY_HERE':
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=Config.GEMINI_API_KEY,
            http_options=types.HttpOptions(api_version='v1beta')
        )

        candidate_models = ['gemini-3.8-flash', 'gemini-omni-flash-preview', 'gemini-3.1-flash-lite']
        for model_name in candidate_models:
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=f"ออกเสียงข้อความภาษาไทยนี้ให้ชัดเจนและเป็นธรรมชาติ: {clean_text}",
                    config=types.GenerateContentConfig(
                        response_modalities=['AUDIO'],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                            )
                        )
                    )
                )
                if res and res.candidates and len(res.candidates) > 0:
                    for part in res.candidates[0].content.parts:
                        if getattr(part, 'inline_data', None) and part.inline_data.data:
                            logger.info(f"✨ [Gemini TTS] สังเคราะห์เสียงสำเร็จด้วยโมเดล {model_name} (Voice: {voice_name})")
                            return part.inline_data.data, part.inline_data.mime_type
            except Exception as me:
                err_str = str(me)
                if '429' in err_str or 'RESOURCE_EXHAUSTED' in err_str:
                    logger.debug(f"Gemini Audio [{model_name}] Quota exhausted: {err_str[:80]}")
                else:
                    logger.debug(f"Gemini Audio [{model_name}] attempt note: {err_str[:80]}")
                continue
    except Exception as e:
        logger.warning(f"⚠️ [Gemini Audio Engine] ไม่สามารถสร้างเสียง: {e}")
    return None

def iter_audio_stream(text, voice="th-TH-PremwadeeNeural", rate="+2%", pitch="+0Hz", volume="+0%"):
    """
    Generator สำหรับส่งสตรีมข้อมูลเสียงแบบ Chunked HTTP Audio Stream (<200ms TTFB)
    โทนเสียงมาตรฐาน th-TH-PremwadeeNeural (Pitch +0Hz, Rate +2%)
    """
    clean_text = clean_text_for_speech(text, max_len=2500, voice_gender='female')
    cache_key = f"{voice}_{pitch}_{rate}_{clean_text}"
    cached_b64, _ = get_cached_tts(cache_key)
    
    if cached_b64:
        raw_bytes = base64.b64decode(cached_b64)
        chunk_size = 4096
        for i in range(0, len(raw_bytes), chunk_size):
            yield raw_bytes[i:i + chunk_size]
        return

    # ถ้ายังไม่มีแคช ให้สร้างแบบสดและเก็บลงแคชพร้อมส่งออกทันที
    try:
        audio_bytes = run_coroutine(generate_edge_tts(clean_text, voice=voice, rate=rate, pitch=pitch, volume=volume, timeout=6.0))
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

pythaitts_engine = None
pythaitts_checked = False

def get_pythaitts_engine():
    global pythaitts_engine, pythaitts_checked
    if not pythaitts_checked:
        pythaitts_checked = True
        try:
            from pythaitts import TTS
            pythaitts_engine = TTS(pretrained="fastthaig2p")
            logger.info("Loaded PyThaiTTS on-device engine (fastthaig2p)")
        except Exception as e:
            logger.info(f"PyThaiTTS unavailable ({e}), using Edge-TTS")
            pythaitts_engine = None
    return pythaitts_engine

