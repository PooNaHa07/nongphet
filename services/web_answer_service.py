# -*- coding: utf-8 -*-
"""
services/web_answer_service.py — ค้นคำตอบจากเว็บเมื่อฐานความรู้ในเครื่องตอบไม่ได้
(Gemini API + Grounding with Google Search)

ชั้นนี้เป็น "ชั้นสำรอง" ของระบบตอบคำถาม ไม่ใช่ตัวหลัก:
    1. ตัวจำแนกเจตนา + Semantic RAG ในเครื่อง (ข้อมูลที่ตรวจแล้ว) ตอบก่อนเสมอ
    2. ถ้า RAG ไม่เจอ หรือเจอแต่คะแนนต่ำกว่า WEB_PREFER_BELOW -> ค้นเว็บที่นี่
    3. ถ้าเน็ตหลุด/โควตาเต็ม/ช้าเกิน -> กลับไปใช้คำตอบในเครื่องทันที (ไม่ค้าง)

สิ่งที่ระบบทำเอง (ไม่ใช่แค่ส่งคำถามต่อให้แชตบอต):
    - ไม่ใช้เว็บกับเรื่องของวิทยาลัย (ต้องตอบจากข้อมูลทางการในฐานความรู้เท่านั้น)
    - คุมบุคลิกน้องเพชร แยกคำตอบบนจอ (reply) กับบทพูดสั้น (speech) แก้คำลงท้าย "ครับ"
    - บอกแหล่งที่มา + แจ้งผู้ฟังว่าเป็นข้อมูลจากเว็บ
    - เก็บคำตอบจากเว็บเข้า "คิวรออนุมัติ" ให้ครูกดเพิ่มเข้าฐานความรู้ (เรียนรู้ซ้ำ)
    - จำคำตอบซ้ำไว้ในหน่วยความจำ, พักการเรียกเมื่อโควตาเต็ม, สลับรุ่นโมเดลเมื่อรุ่นแรกใช้ไม่ได้

ส่งออกไปภายนอกเฉพาะ "ข้อความคำถาม" เท่านั้น (ไม่มีข้อมูลส่วนตัว/รหัสผู้ใช้)

ตั้งค่าใน .env:
    GEMINI_API_KEY=...                 (ไม่ตั้ง = ปิดชั้นนี้ ระบบทำงานออฟไลน์เหมือนเดิม)
    WEB_ANSWER_ENABLED=1               (0 = ปิด)
    GEMINI_MODELS=gemini-2.5-flash,gemini-2.5-flash-lite   (แต่ละรุ่นมีโควตาฟรีแยกกัน)
    WEB_ANSWER_TIMEOUT=12
    WEB_PREFER_BELOW=0.45              (คะแนน RAG ต่ำกว่านี้ถือว่า "ไม่แน่ใจ" ลองค้นเว็บก่อน)
    WEB_REPEAT_TTL_HOURS=24            (คำถามเดิมภายในเวลานี้ ตอบจากคำตอบที่บันทึกไว้ทันที ไม่ค้นเว็บซ้ำ; 0 = ปิด)
"""
import os
import re
import json
import time
import uuid
import logging
import datetime
import threading
from collections import OrderedDict

import httpx

import config  # noqa: F401  (โหลด .env)

logger = logging.getLogger("nongphet.web_answer")

API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING_FILE = os.path.join(ROOT, 'data', 'web_answers_pending.json')
MAX_PENDING = 300
CACHE_SIZE = 64
QUOTA_COOLDOWN_SEC = 60.0          # ใช้เมื่อ Google ไม่บอกเวลาที่ต้องรอ
MAX_QUOTA_COOLDOWN_SEC = 300.0
ERROR_COOLDOWN_SEC = 20.0
SPEECH_MAX_CHARS = 140

# เรื่องของวิทยาลัยต้องตอบจากข้อมูลทางการเท่านั้น ห้ามใช้ข้อมูลจากเว็บทั่วไป
COLLEGE_INTENTS = {'admission'}
COLLEGE_KEYWORDS = (
    'วิทยาลัย', 'อาชีวศึกษาเพชรบุรี', 'pbpvc', 'สาขา', 'สมัครเรียน', 'รับสมัคร', 'ปวช', 'ปวส',
    'ปริญญาตรี', 'ทวิภาคี', 'หลักสูตร', 'ผู้อำนวยการ', 'ค่าเทอม', 'แผนก',
)

SYSTEM_PROMPT = (
    "คุณคือ \"น้องเพชร\" ไกด์หุ่นยนต์ผู้หญิงของวิทยาลัยอาชีวศึกษาเพชรบุรี ประจำบูธประชาสัมพันธ์ "
    "พูดสุภาพ น่ารัก เป็นกันเอง ใช้ภาษาพูดที่ฟังง่าย ลงท้ายประโยคด้วย ค่ะ หรือ นะคะ ห้ามใช้คำว่า ครับ "
    "ตอบเฉพาะข้อเท็จจริงที่ค้นเจอจากเว็บ ถ้าไม่แน่ใจให้บอกตรงๆ และแนะนำให้ตรวจสอบเพิ่มเติม "
    "ห้ามแต่งข้อมูลเอง ห้ามให้คำแนะนำทางการแพทย์ กฎหมาย หรือการเงินแบบเฉพาะบุคคล "
    "ถ้าคำถามเป็นภาษาอังกฤษหรือจีน ให้ตอบเป็นภาษานั้นทั้งหมด ห้ามใส่คำไทย (เช่น ค่ะ นะคะ) ปนในคำตอบ"
)

USER_TEMPLATE = {
    'th': ("คำถามจากผู้มาเยือน: {q}\n\nค้นข้อมูลจากเว็บ แล้วตอบเป็นภาษาไทยตามรูปแบบนี้เท่านั้น ห้ามมีข้อความอื่น:\n"
           "คำตอบ: <คำตอบ 2-4 ประโยค ไม่เกิน 400 ตัวอักษร>\n"
           "บทพูด: <สรุปสั้น 1-2 ประโยค ไม่เกิน 150 ตัวอักษร สำหรับอ่านออกเสียง ไม่มีลิงก์หรือตัวเลขยาวๆ>"),
    'en': ("Visitor question: {q}\n\nSearch the web, then answer in English using exactly this format and nothing else:\n"
           "คำตอบ: <2-4 sentence answer, max 400 characters>\n"
           "บทพูด: <1-2 sentence spoken summary, max 150 characters, no links>"),
    'zh': ("访客问题: {q}\n\n请上网搜索，然后只用以下格式以中文回答，不要有其他内容:\n"
           "คำตอบ: <2-4句回答，不超过200字>\n"
           "บทพูด: <1-2句口语摘要，不超过60字，不含链接>"),
}

WEB_NOTE = {
    'th': ('น้องเพชรค้นจากเว็บมาให้แล้วค่ะ ', '🌐 ข้อมูลจากเว็บไซต์ โปรดตรวจสอบอีกครั้งนะคะ'),
    'en': ("I looked this up online. ", '🌐 Information from the web. Please double-check.'),
    'zh': ('我在网上查到了。', '🌐 以上信息来自网络，请再次核实。'),
}

# คำถามที่คำตอบเปลี่ยนตามเวลา (อากาศ วันนี้/พรุ่งนี้ ข่าว) ต้องค้นใหม่ทุกครั้ง ไม่ใช้คำตอบที่บันทึกไว้
TIME_SENSITIVE = re.compile(
    r'วันนี้|พรุ่งนี้|เมื่อวาน|ตอนนี้|ขณะนี้|ล่าสุด|ฝน|อากาศ|พยากรณ์|ข่าว|\btoday\b|\btomorrow\b|\btonight\b|\bnow\b|latest|weather|\brain|\bnews\b|今天|明天|现在|天气',
    re.IGNORECASE)

_lock = threading.Lock()
_cache = OrderedDict()
_state = {'cooldown_until': 0.0, 'last_error': None, 'last_ms': None, 'last_model': None,
          'requests': 0, 'answers': 0}


def _env(name, default=''):
    return os.environ.get(name, default).strip()


def api_key():
    return _env('GEMINI_API_KEY')


def is_enabled():
    return bool(api_key()) and _env('WEB_ANSWER_ENABLED', '1') != '0'


def models():
    raw = _env('GEMINI_MODELS', 'gemini-2.5-flash,gemini-2.5-flash-lite')
    return [m.strip() for m in raw.split(',') if m.strip()]


def prefer_web_below():
    try:
        return float(_env('WEB_PREFER_BELOW', '0.45'))
    except ValueError:
        return 0.45


def repeat_ttl_sec():
    try:
        return max(0.0, float(_env('WEB_REPEAT_TTL_HOURS', '24'))) * 3600
    except ValueError:
        return 24 * 3600.0


def _answered_at(item):
    raw = item.get('answered_at') or item.get('created_at') or ''
    try:
        return datetime.datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return 0.0


def saved_answer(question, lang='th'):
    """
    คำตอบจากเว็บที่บันทึกไว้ในคิวรออนุมัติ ของคำถามเดิม (ถามซ้ำ) ที่ยังไม่หมดอายุ
    ข้อความเดิมทุกตัวอักษร = หน้าจอขอเสียงท่อนเดิม จึงได้เสียงจากแคชทันที ไม่ต้องสร้างใหม่
    คืน None ถ้าไม่มี, หมดอายุ, เป็นคำถามที่คำตอบเปลี่ยนตามเวลา หรือรายการเก่าที่ไม่มีคำค้นแนะนำของ Google
    """
    ttl = repeat_ttl_sec()
    if not ttl or TIME_SENSITIVE.search(question or ''):
        return None
    norm = _normalize(question)
    with _lock:
        items = _load_pending()
    for it in items:
        if it.get('lang', 'th') != lang or _normalize(it.get('question', '')) != norm:
            continue
        # Google กำหนดให้แสดงคำค้นแนะนำคู่กับคำตอบที่ใช้ Google Search ทุกครั้ง: ไม่มีเก็บไว้ = ค้นใหม่
        if not it.get('search_html') or time.time() - _answered_at(it) > ttl:
            return None
        return {
            'reply': it['reply'], 'speech': it['speech'], 'sources': it.get('sources', []),
            'grounded': True, 'search_html': it['search_html'], 'model': it.get('model', ''),
            'repeat': True,
        }
    return None


def _timeout():
    try:
        return float(_env('WEB_ANSWER_TIMEOUT', '12'))
    except ValueError:
        return 12.0


def is_college_topic(question, intent=None):
    q = (question or '').lower()
    return intent in COLLEGE_INTENTS or any(k in q for k in COLLEGE_KEYWORDS)


def should_use_web(question, intent=None):
    """ใช้เว็บได้เมื่อเปิดใช้งาน ไม่อยู่ในช่วงพัก และไม่ใช่เรื่องของวิทยาลัย"""
    if not is_enabled() or not (question or '').strip():
        return False
    if is_college_topic(question, intent):
        return False
    return time.time() >= _state['cooldown_until']


def status():
    remaining = max(0.0, _state['cooldown_until'] - time.time())
    return {
        'enabled': is_enabled(),
        'models': models(),
        'prefer_web_below': prefer_web_below(),
        'cooling_down_sec': round(remaining, 1),
        'last_error': _state['last_error'],
        'last_ms': _state['last_ms'],
        'last_model': _state['last_model'],
        'requests': _state['requests'],
        'answers': _state['answers'],
        'pending': len(list_pending()),
    }


def _normalize(q):
    return re.sub(r'[\s?？!！.。,，]+', '', (q or '').lower())


def _clean(text):
    t = re.sub(r'\*\*|__|`|#+\s*', '', text or '')
    t = re.sub(r'\[(\d+(,\s*\d+)*)\]', '', t)           # ตัดเลขอ้างอิง [1] [2, 3]
    t = re.sub(r'ครับ', 'ค่ะ', t)
    return re.sub(r'[ \t]+', ' ', t).strip()


def _first_sentences(text, limit=160):
    parts = [p.strip() for p in re.findall(r'.+?(?:นะคะ|ค่ะ|[.!?。！？])(?=\s|$)|.+$', text or '', re.S)]
    out = ''
    for p in parts:
        if len(out) + len(p) > limit and out:
            break
        out = (out + ' ' + p).strip()
    return out[:limit]


def parse_answer(text):
    """แยก 'คำตอบ:' กับ 'บทพูด:' ถ้าโมเดลไม่ทำตามรูปแบบ ใช้ทั้งก้อนเป็นคำตอบ และตัดประโยคแรกเป็นบทพูด"""
    text = (text or '').strip()
    m = re.search(r'คำตอบ\s*[:：]\s*(.*?)\s*บทพูด\s*[:：]\s*(.*)', text, re.S)
    if m:
        reply, speech = _clean(m.group(1)), _clean(m.group(2))
    else:
        reply = _clean(re.sub(r'^\s*คำตอบ\s*[:：]\s*', '', text))
        speech = _first_sentences(reply)
    # บทพูดต้องสั้น (~10 วินาที) แม้โมเดลจะเขียนยาวเกินที่สั่ง
    return reply, _first_sentences(speech or reply, SPEECH_MAX_CHARS)


THAI_CHARS = re.compile(r'[\u0e00-\u0e7f]+')


def _readable_domain(title):
    """ชื่อโดเมนภาษาไทยมาเป็น punycode (xn--...) แปลงกลับให้อ่านได้"""
    if 'xn--' not in title:
        return title
    try:
        return '.'.join(part.encode('ascii').decode('idna') if part.startswith('xn--') else part
                        for part in title.split('.'))
    except (UnicodeError, ValueError):
        return title


def _extract_sources(candidate, limit=3):
    sources, seen = [], set()
    for ch in candidate.get('groundingMetadata', {}).get('groundingChunks', []) or []:
        web = ch.get('web') or {}
        title = _readable_domain((web.get('title') or '').strip())
        if title and title not in seen:
            seen.add(title)
            sources.append({'title': title, 'uri': web.get('uri', '')})
        if len(sources) >= limit:
            break
    return sources


def _retry_delay(res):
    """อ่านเวลาที่ต้องรอจาก 429 (RetryInfo.retryDelay เช่น "23s") ถ้าไม่มีใช้ค่าเริ่มต้น"""
    try:
        for d in res.json().get('error', {}).get('details', []) or []:
            m = re.match(r'([\d.]+)s', str(d.get('retryDelay', '')))
            if m:
                return min(MAX_QUOTA_COOLDOWN_SEC, max(1.0, float(m.group(1))))
    except ValueError:
        pass
    return QUOTA_COOLDOWN_SEC


def _call(model, question, lang):
    body = {
        'systemInstruction': {'parts': [{'text': SYSTEM_PROMPT}]},
        'contents': [{'role': 'user', 'parts': [{'text': USER_TEMPLATE.get(lang, USER_TEMPLATE['th']).format(q=question)}]}],
        'tools': [{'google_search': {}}],
        # ปิด "thinking" ของ Gemini 2.5: ไม่งั้นกินโทเคนจนคำตอบขาดกลางประโยค และช้าลง
        'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 2048,
                             'thinkingConfig': {'thinkingBudget': 0}},
    }
    return httpx.post(API_URL.format(model=model), headers={'x-goog-api-key': api_key()},
                      json=body, timeout=_timeout())


def answer(question, language='th'):
    """
    คืน dict {reply, speech, sources, search_html, model} หรือ None (ให้ระบบใช้คำตอบในเครื่องต่อ)
    """
    question = (question or '').strip()[:500]
    lang = language if language in USER_TEMPLATE else 'th'
    key = (lang, _normalize(question))
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return dict(_cache[key])
    saved = saved_answer(question, lang)
    if saved:
        with _lock:
            _cache[key] = dict(saved)
            if len(_cache) > CACHE_SIZE:
                _cache.popitem(last=False)
        add_pending(question, lang, saved)          # นับว่าถามซ้ำอีกครั้ง (ครูเห็นว่าควรเพิ่มเข้าฐานความรู้)
        logger.info("🌐 [Web] ตอบจากคำตอบที่บันทึกไว้ (ถามซ้ำ ไม่ค้นเว็บใหม่)")
        return dict(saved)
    if not is_enabled() or time.time() < _state['cooldown_until']:
        return None

    started = time.time()
    all_quota = True
    quota_waits = []
    for model in models():
        _state['requests'] += 1
        try:
            res = _call(model, question, lang)
        except (httpx.ReadTimeout, httpx.WriteTimeout) as e:
            # ต่อได้แล้วแต่คำถามนี้ค้นนาน: ข้ามไปใช้คำตอบในเครื่อง ไม่พักระบบ (คำถามถัดไปยังค้นเว็บได้)
            _state['last_error'] = f'{model}: {type(e).__name__}'
            logger.warning(f"🌐 [Web] {_state['last_error']}")
            return None
        except httpx.HTTPError as e:
            all_quota = False
            _state['last_error'] = f'{model}: {type(e).__name__}'
            logger.warning(f"🌐 [Web] {_state['last_error']}")
            break                                   # ต่อเน็ตไม่ได้: ไม่ต้องลองรุ่นอื่น
        if res.status_code == 429:
            wait = _retry_delay(res)
            quota_waits.append(wait)
            _state['last_error'] = f'{model}: quota exceeded (429, retry in {wait:.0f}s)'
            continue                                # ลองรุ่นถัดไป (โควตาแยกกันแต่ละรุ่น)
        all_quota = False
        if res.status_code != 200:
            _state['last_error'] = f'{model}: HTTP {res.status_code}'
            logger.warning(f"🌐 [Web] {_state['last_error']} {res.text[:200]}")
            continue
        try:
            data = res.json()
        except ValueError:
            _state['last_error'] = f'{model}: unexpected response'
            continue
        cand = (data.get('candidates') or [{}])[0]
        text = ''.join(p.get('text', '') for p in (cand.get('content') or {}).get('parts', []) or [])
        blocked = (data.get('promptFeedback', {}).get('blockReason')
                   or cand.get('finishReason') in ('SAFETY', 'PROHIBITED_CONTENT', 'BLOCKLIST', 'SPII'))
        if blocked or not text.strip():
            # คำถามไม่เหมาะสม/ไม่มีคำตอบ: เฉพาะคำถามนี้ใช้คำตอบในเครื่อง ไม่ต้องพักระบบ ไม่ต้องลองรุ่นอื่น
            _state['last_error'] = f'{model}: no answer ({blocked or "empty"})'
            return None
        reply, speech = parse_answer(text)
        if not reply:
            _state['last_error'] = f'{model}: empty answer'
            return None
        sources = _extract_sources(cand)
        # คำถามภาษาอังกฤษ/จีน: บทพูดต้องไม่มีภาษาไทยปน (ถ้ามี ใช้ประโยคแรกของคำตอบแทน)
        if lang != 'th' and THAI_CHARS.search(speech):
            speech = _first_sentences(THAI_CHARS.sub('', reply), SPEECH_MAX_CHARS)
        # ค้นเว็บจริง (มีแหล่งที่มา) = บอกผู้ฟังว่ามาจากเว็บ + เข้าคิวรออนุมัติ
        # ไม่มีแหล่งที่มา (เช่น ปฏิเสธคำขอไม่เหมาะสม) = ตอบตามปกติ ไม่ติดป้ายเว็บ ไม่เข้าคิว
        grounded = bool(sources)
        lead, note = WEB_NOTE[lang] if grounded else ('', '')
        result = {
            'reply': f'{reply}\n\n{note}' if note else reply,
            'speech': lead + speech,
            'sources': sources,
            'grounded': grounded,
            # Google กำหนดให้แสดง "คำค้นแนะนำ" ทุกครั้งที่ใช้ Grounding with Google Search
            'search_html': cand.get('groundingMetadata', {}).get('searchEntryPoint', {}).get('renderedContent', ''),
            'model': model,
        }
        _state.update(last_error=None, last_ms=int((time.time() - started) * 1000), last_model=model)
        _state['answers'] += 1
        with _lock:
            _cache[key] = dict(result)
            if len(_cache) > CACHE_SIZE:
                _cache.popitem(last=False)
        if grounded:
            add_pending(question, lang, result)
        logger.info(f"🌐 [Web] {model} ตอบใน {_state['last_ms']} ms (แหล่ง {len(result['sources'])} แห่ง)")
        return result

    # โควตาเต็มทุกรุ่น: พักเท่าที่ Google บอก (รุ่นที่ว่างเร็วสุด) ไม่ใช่พักนานเกินจำเป็น
    pause = min(quota_waits) if (all_quota and quota_waits) else ERROR_COOLDOWN_SEC
    _state['cooldown_until'] = time.time() + pause
    return None


# ---------------------------------------------------------------------------
# คิวรออนุมัติ: คำตอบจากเว็บที่ครูตรวจแล้วเพิ่มเข้าฐานความรู้ได้ (เรียนรู้ซ้ำ)
# ---------------------------------------------------------------------------
def _load_pending():
    try:
        with open(PENDING_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_pending(items):
    os.makedirs(os.path.dirname(PENDING_FILE), exist_ok=True)
    tmp = PENDING_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items[-MAX_PENDING:], f, ensure_ascii=False, indent=2)
    os.replace(tmp, PENDING_FILE)


def list_pending():
    with _lock:
        return _load_pending()


def add_pending(question, lang, result):
    with _lock:
        items = _load_pending()
        norm = _normalize(question)
        now = datetime.datetime.now().isoformat(timespec='seconds')
        for it in items:
            if _normalize(it['question']) == norm:
                it['count'] = it.get('count', 1) + 1       # ถามซ้ำบ่อย = ควรเพิ่มเข้าฐานความรู้
                it['last_asked'] = now
                if not result.get('repeat') and it.get('lang', 'th') == lang:
                    # ค้นเว็บใหม่ (คำตอบเดิมหมดอายุ): เก็บคำตอบล่าสุดไว้ตอบครั้งถัดไป
                    it.update(reply=result['reply'], speech=result['speech'], sources=result['sources'],
                              model=result['model'], search_html=result.get('search_html', ''),
                              answered_at=now)
                _save_pending(items)
                return it['id']
        item = {
            'id': uuid.uuid4().hex[:12],
            'question': question,
            'lang': lang,
            'reply': result['reply'],
            'speech': result['speech'],
            'sources': result['sources'],
            'model': result['model'],
            'search_html': result.get('search_html', ''),
            'count': 1,
            'created_at': now,
            'answered_at': now,
        }
        items.append(item)
        _save_pending(items)
        return item['id']


def pop_pending(item_id):
    with _lock:
        items = _load_pending()
        found = next((it for it in items if it['id'] == item_id), None)
        if found:
            _save_pending([it for it in items if it['id'] != item_id])
        return found
