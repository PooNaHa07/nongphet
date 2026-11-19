# -*- coding: utf-8 -*-
"""
services/voice_command_service.py — ระบบคำสั่งเสียงของน้องเพชร (ทำงานในเครื่อง ไม่ใช้เน็ต)

แยก "คำสั่ง" ออกจาก "คำถาม" ก่อนเข้าระบบแชต:
    "เปิดหน้าที่เที่ยว"  -> เปลี่ยนหน้าจอ      "หยุดพูด"      -> หยุดเสียง
    "ยิ้มหน่อย"          -> เปลี่ยนสีหน้า       "โบกมือ"        -> ขยับแขน
    "กี่โมงแล้ว"         -> บอกเวลา           "แนะนำที่เที่ยว" -> ไม่ใช่คำสั่ง (ส่งต่อให้แชตตอบ)

หลักการ:
    - ตัดคำปลุก ("น้องเพชร") และคำลงท้าย (หน่อย ได้ไหม ค่ะ ครับ ...) ออกก่อน
    - ต้องตรงทั้งประโยค (anchored) ไม่ใช่แค่มีคำอยู่ข้างใน กันคำถามยาวๆ ถูกตีความเป็นคำสั่ง
    - ประโยคตอบรับสั้นและคงที่ (อัดเสียงไว้ล่วงหน้าได้ ดู COMMAND_PHRASES ใน prebake_tts.py)

ผลลัพธ์ parse(): dict หรือ None
    {'name', 'category', 'reply', 'speech', 'ui': {...}, 'emotion', 'gesture'}
    ui  = สิ่งที่หน้าจอต้องทำ (navigate / speech / volume / language / modal / help)
    emotion / gesture = สิ่งที่เซิร์ฟเวอร์สั่ง (หน้าจอ emotion และแขนกล)
"""
import re
import datetime

# ---------------------------------------------------------------------------
# การตัดคำปลุกและคำสุภาพ
# ---------------------------------------------------------------------------
_WAKE = re.compile(r'^(?:เฮ้|เฮ้ย|hey|ok|hi)?\s*(?:น้องเพชร|น้องเพ็ด|น้องเพชรจ๋า|nong\s*phet|nongphet)\s*[,.!?~]*\s*', re.I)
_POLITE_TAIL = re.compile(
    r'(?:\s*(?:หน่อย(?:สิ|นะ)?|ได้ไหม|ได้มั้ย|ได้ป่าว|ให้หน่อย|ให้ดู|เลย|ที|ทีนะ|นะ|จ้า|จ๊ะ|ค่ะ|คะ|ครับ|คับ|please|pls)\s*)+[.!?~]*$',
    re.I)
_FILLER_HEAD = re.compile(r'^(?:ช่วย|ขอ|ลอง|please|can you|could you)\s*', re.I)

MAX_COMMAND_CHARS = 30      # คำสั่งพูดสั้นเสมอ ประโยคยาวกว่านี้ถือเป็นคำถาม


def normalize(text):
    t = (text or '').strip().lower()
    t = _WAKE.sub('', t)
    t = _FILLER_HEAD.sub('', t)
    t = _POLITE_TAIL.sub('', t)
    t = re.sub(r'[\s,.!?~"\'“”]+', '', t)       # ภาษาไทยไม่เว้นวรรค ตัดช่องว่างทิ้งเพื่อจับคำได้ง่าย
    return t


# ---------------------------------------------------------------------------
# ตารางคำสั่ง: (ชื่อ, หมวด, [regex ที่ต้องตรงทั้งประโยคหลัง normalize], ข้อมูลคำสั่ง)
# ---------------------------------------------------------------------------
_OPEN = r'(?:เปิด|ไป|ไปที่|ไปหน้า|ดู|เข้า|โชว์|แสดง|open|go to|show)?(?:หน้า|หน้าจอ|เมนู)?'

COMMANDS = [
    # --- เปลี่ยนหน้าจอ ---
    ('go_home', 'navigate', [r'(?:กลับ)?(?:ไป)?หน้าแรก', r'กลับหน้าหลัก', r'หน้าหลัก', r'ย้อนกลับ', r'กลับ', r'home', r'gohome', r'goback', r'back'],
     {'reply': 'กลับหน้าแรกแล้วค่ะ', 'ui': {'navigate': 'screen-welcome'}}),
    ('open_places', 'navigate', [_OPEN + r'(?:สถานที่ท่องเที่ยว|แหล่งท่องเที่ยว|ที่เที่ยว)', r'(?:open|show)?places'],
     {'reply': 'เปิดหน้าสถานที่ท่องเที่ยวให้แล้วค่ะ', 'ui': {'navigate': 'screen-places'}}),
    ('open_courses', 'navigate', [_OPEN + r'(?:หลักสูตร|สาขาวิชา|สาขา|แผนก)(?:ทั้งหมด)?', r'(?:open|show)?courses'],
     {'reply': 'เปิดหน้าหลักสูตรให้แล้วค่ะ', 'ui': {'navigate': 'screen-courses'}}),
    ('open_sign', 'navigate', [_OPEN + r'(?:ตรวจจับ)?ภาษามือ', r'signlanguage'],
     {'reply': 'เปิดหน้าภาษามือแล้วค่ะ ทำท่าให้น้องเพชรดูได้เลยนะคะ', 'ui': {'navigate': 'screen-sign-language'}}),
    ('open_vision', 'navigate', [_OPEN + r'(?:กล้อง|วิเคราะห์ภาพ|ส่องภาพ)', r'(?:open)?camera'],
     {'reply': 'เปิดหน้ากล้องแล้วค่ะ', 'ui': {'navigate': 'screen-vision'}}),
    ('open_chat', 'navigate', [_OPEN + r'(?:ถามตอบ|ถาม-ตอบ|แชท|แชต)', r'(?:open)?chat'],
     {'reply': 'ถามน้องเพชรได้เลยค่ะ', 'ui': {'navigate': 'screen-chat'}}),
    ('close_modal', 'modal', [r'ปิด(?:หน้าต่าง|คิวอาร์(?:โค้ด)?|qr(?:code)?|ป๊อปอัพ|popup)?', r'close'],
     {'reply': 'ปิดให้แล้วค่ะ', 'ui': {'modal': 'close'}}),
    ('open_qr', 'modal', [r'(?:เปิด|แสดง)?(?:qr|คิวอาร์)(?:โค้ด|code)?(?:สมัครเรียน|แนะแนว)?', r'สแกน(?:qr|คิวอาร์)'],
     {'reply': 'สแกนคิวอาร์โค้ดนี้ดูข้อมูลการรับสมัครได้เลยค่ะ', 'ui': {'modal': 'qr'}}),

    # --- ควบคุมเสียง ---
    ('stop_speaking', 'speech', [r'หยุดพูด', r'เงียบ', r'หยุด', r'พอแล้ว', r'stop', r'stoptalking', r'bequiet'],
     {'reply': '', 'ui': {'speech': 'stop'}}),
    ('repeat', 'speech', [r'(?:พูด|บอก)(?:อีกครั้ง|อีกที|ซ้ำ)', r'ขอฟังอีก(?:ครั้ง|ที)', r'อะไรนะ', r'ไม่ได้ยิน', r'repeat', r'sayagain', r'pardon'],
     {'reply': '', 'ui': {'speech': 'repeat'}}),
    ('volume_up', 'speech', [r'(?:เสียง)?ดังขึ้น', r'เพิ่มเสียง', r'เปิดเสียงดัง(?:ขึ้น)?', r'louder', r'volumeup'],
     {'reply': 'เพิ่มเสียงให้แล้วค่ะ', 'ui': {'volume': 0.2}}),
    ('volume_down', 'speech', [r'(?:เสียง)?เบาลง', r'ลดเสียง', r'quieter', r'volumedown'],
     {'reply': 'ลดเสียงให้แล้วค่ะ', 'ui': {'volume': -0.2}}),
    ('lang_en', 'language', [r'(?:พูด|เปลี่ยน(?:เป็น)?|ใช้)ภาษาอังกฤษ', r'(?:speak)?english'],
     {'reply': "Sure! I'll speak English now.", 'ui': {'language': 'en'}, 'lang': 'en'}),
    ('lang_th', 'language', [r'(?:พูด|เปลี่ยน(?:เป็น)?|ใช้)ภาษาไทย', r'(?:speak)?thai'],
     {'reply': 'ได้เลยค่ะ น้องเพชรพูดภาษาไทยนะคะ', 'ui': {'language': 'th'}}),
    ('lang_zh', 'language', [r'(?:พูด|เปลี่ยน(?:เป็น)?|ใช้)ภาษาจีน', r'(?:speak)?chinese'],
     {'reply': '好的，我现在说中文。', 'ui': {'language': 'zh'}, 'lang': 'zh'}),

    # --- ใบหน้า (จอ emotion) ---
    ('face_smile', 'face', [r'ยิ้ม', r'ยิ้มให้ดู', r'smile'],
     {'reply': 'ยิ้มหวานให้เลยค่ะ', 'emotion': 'smile'}),
    ('face_wink', 'face', [r'ขยิบตา', r'wink'],
     {'reply': 'ขยิบตาให้แล้วนะคะ', 'emotion': 'wink'}),
    ('face_surprised', 'face', [r'(?:ทำหน้า)?ตกใจ', r'(?:ทำ)?หน้าตกใจ', r'surprised?'],
     {'reply': 'ว้าย ตกใจหมดเลยค่ะ', 'emotion': 'surprised'}),
    ('face_love', 'face', [r'(?:ทำหน้า)?เขิน', r'(?:ส่ง|ทำ)?หัวใจ', r'(?:send)?love'],
     {'reply': 'ส่งหัวใจให้เลยค่ะ', 'emotion': 'love'}),

    # --- แขน ---
    ('arm_wave', 'arm', [r'โบกมือ', r'(?:wave|wavehand)'],
     {'reply': 'สวัสดีค่ะ โบกมือให้เลยนะคะ', 'gesture': 'wave', 'emotion': 'happy'}),
    ('arm_raise', 'arm', [r'ยกมือ(?:ขวา)?', r'raise(?:your)?hand'],
     {'reply': 'ยกมือแล้วค่ะ', 'gesture': 'raise_right'}),
    ('arm_raise_both', 'arm', [r'(?:ยก|ชู)(?:สอง)?มือ(?:ทั้งสองข้าง|สองข้าง|ขึ้น)', r'ชูมือ', r'handsup'],
     {'reply': 'ชูมือสุดแขนเลยค่ะ', 'gesture': 'raise_both', 'emotion': 'excited'}),
    ('arm_cheer', 'arm', [r'เชียร์', r'ไชโย', r'ดีใจ', r'cheer'],
     {'reply': 'เย้ เชียร์สุดใจเลยค่ะ', 'gesture': 'cheer', 'emotion': 'excited'}),

    # --- ข้อมูลด่วน ---
    ('time_now', 'info', [r'(?:ตอนนี้)?(?:กี่โมง|เวลา)(?:แล้ว)?', r'ตอนนี้กี่โมง', r'เวลาเท่าไร(?:แล้ว)?', r'whattimeisit', r'time'],
     {'dynamic': 'time'}),
    ('date_today', 'info', [r'วันนี้วัน(?:อะไร|ที่เท่าไร|ที่เท่าไหร่|ที่)', r'วันที่เท่า(?:ไร|ไหร่)', r'whatday(?:isit)?(?:today)?', r'whatsthedate'],
     {'dynamic': 'date'}),
    # "ทำอะไรได้บ้าง" ไม่ใช่คำสั่ง: ให้ฐานความรู้ (greet_001) แนะนำตัวตามปกติ
    ('help', 'info', [r'(?:มี)?คำสั่ง(?:เสียง)?(?:อะไรบ้าง)?', r'สั่ง(?:อะไร|งานยังไง|ยังไง)(?:ได้)?(?:บ้าง)?', r'help', r'voicecommands?'],
     {'reply': 'ลองพูดคำสั่งตามบนหน้าจอได้เลยค่ะ', 'ui': {'help': True}}),
]

_COMPILED = [(name, cat, [re.compile(r'^(?:' + p + r')$', re.I) for p in pats], data)
             for name, cat, pats, data in COMMANDS]

# ประโยคตอบรับคงที่ทั้งหมด (ไว้อัดเสียงล่วงหน้า: prebake_tts.py)
COMMAND_PHRASES = sorted({d['reply'] for _, _, _, d in COMMANDS
                          if d.get('reply') and not d.get('lang')})

THAI_DAYS = ['วันจันทร์', 'วันอังคาร', 'วันพุธ', 'วันพฤหัสบดี', 'วันศุกร์', 'วันเสาร์', 'วันอาทิตย์']
THAI_MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
               'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']


def _dynamic_reply(kind, now):
    if kind == 'time':
        return f"ตอนนี้เวลา {now.hour} นาฬิกา {now.minute} นาทีค่ะ"
    return f"วันนี้{THAI_DAYS[now.weekday()]}ที่ {now.day} {THAI_MONTHS[now.month - 1]} {now.year + 543} ค่ะ"


def parse(text, now=None):
    """คืนคำสั่ง (dict) ถ้าประโยคนี้เป็นคำสั่ง ไม่ใช่ -> None (ให้ระบบแชตตอบตามปกติ)"""
    norm = normalize(text)
    if not norm or len(norm) > MAX_COMMAND_CHARS:
        return None
    for name, category, patterns, data in _COMPILED:
        if any(p.match(norm) for p in patterns):
            reply = _dynamic_reply(data['dynamic'], now or datetime.datetime.now()) if data.get('dynamic') else data['reply']
            return {
                'name': name,
                'category': category,
                'reply': reply,
                'speech': reply,
                'ui': dict(data.get('ui', {})),
                'emotion': data.get('emotion'),
                'gesture': data.get('gesture'),
                'lang': data.get('lang', 'th'),
            }
    return None


def help_list():
    """ตัวอย่างคำสั่งสำหรับการ์ด "ลองพูดว่า..." บนหน้าจอ"""
    return [
        {'group': 'เปลี่ยนหน้าจอ', 'examples': ['เปิดหน้าที่เที่ยว', 'ดูหลักสูตร', 'เปิดภาษามือ', 'กลับหน้าแรก']},
        {'group': 'ควบคุมเสียง', 'examples': ['หยุดพูด', 'พูดอีกครั้ง', 'เสียงดังขึ้น', 'พูดภาษาอังกฤษ']},
        {'group': 'ท่าทางน้องเพชร', 'examples': ['ยิ้มหน่อย', 'ขยิบตา', 'โบกมือ', 'เชียร์หน่อย']},
        {'group': 'ข้อมูลด่วน', 'examples': ['กี่โมงแล้ว', 'วันนี้วันอะไร', 'ขอคิวอาร์โค้ดสมัครเรียน', 'ปิดหน้าต่าง']},
    ]
