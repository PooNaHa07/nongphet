# -*- coding: utf-8 -*-
"""
services/text_utils.py — ตัวช่วยประมวลผลข้อความที่ใช้ร่วมกันหลายส่วน
(ดึงคำถามต่อยอด, ตรวจจับคำถามลองภูมิ, ตรวจจับภาษา) ทำงานออฟไลน์ทั้งหมด
"""
import re


def extract_suggestions(text):
    """ดึงคำถามต่อยอดอัตโนมัติจากข้อความที่ AI แนะนำ"""
    suggestions = []
    lines = (text or '').split('\n')
    is_suggest_block = False
    for line in lines:
        stripped = line.strip()
        if any(k in stripped for k in ['ถามต่อยอด', 'แนะนำคำถาม', 'คำถามที่น่าสนใจ', 'สอบถามเพิ่มเติม']):
            is_suggest_block = True
            continue
        if is_suggest_block:
            cleaned = re.sub(r'^[•\-\*\d\.\s\[\]]+', '', stripped).strip(' []"\'')
            if cleaned and 2 < len(cleaned) < 50:
                suggestions.append(cleaned)
            if len(suggestions) >= 3:
                break
    return suggestions


def is_complex_or_trap_query(msg: str) -> bool:
    """
    ตรวจจับคำถามลองภูมิ, คำถามตรวจสอบข้อเท็จจริง (Doubt/Fact-check),
    คำถามกวนประสาท, เปรียบเทียบ, หรือคำถามที่ต้องการ Semantic Reasoning
    """
    if not msg:
        return False

    trap_markers = [
        'ใช่ไหม', 'ใช่ปะ', 'ใช่ป่ะ', 'หรือเปล่า', 'รึเปล่า', 'จริงหรอ', 'จริงไหม',
        'จริงปะ', 'มีไหม', 'มีปะ', 'มีมั้ย', 'ไม่ใช่', 'ไม่ใช่หรอ', 'หรอ', 'มั้ย',
        'ที่ไหนแน่', 'ทำไมถึงไม่', 'หรือว่า', 'หรือ', 'เชียงใหม่', 'ภูเก็ต', 'กรุงเทพ',
        'หอไอเฟล', 'ต่างประเทศ', 'เมืองนอก', 'เครื่องบิน', 'สนามบิน'
    ]
    if any(k in msg for k in trap_markers):
        return True

    troll_markers = [
        'ยืมเงิน', 'ยืมตัง', 'ยืมตังค์', 'ขอตัง', 'ขอเงิน', 'แฟน', 'จีบ', 'รักไหม',
        'รักผมไหม', 'รักหนูไหม', 'โง่', 'บ้า', 'กวน', 'ด่า', 'หน้าตา', 'หล่อไหม',
        'สวยไหม', 'สู้ได้ไหม', 'สู้ใคร', 'แย่ที่สุด', 'ไม่อร่อย', 'ห่วย', 'กระจอก',
        'ระเบิด', 'ปืน', 'ยาเสพติด', 'แฮก', 'hack', 'ignore', 'jailbreak', 'ฆ่า'
    ]
    if any(k in msg for k in troll_markers):
        return True

    if len(msg.strip()) < 4:
        return True

    return False


def detect_message_language(text, fallback_lang='th'):
    """ตรวจจับภาษาของข้อความอัตโนมัติ (th, en, zh)"""
    if not text:
        return fallback_lang
    if re.search(r'[一-龥]', text):
        return 'zh'
    has_thai = bool(re.search(r'[฀-๿]', text))
    has_english = bool(re.search(r'[a-zA-Z]', text))

    if has_thai:
        return 'th'
    elif has_english:
        return 'en'
    return fallback_lang
