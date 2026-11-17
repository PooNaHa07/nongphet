#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
สร้าง/อัปเดตหัวข้อ "ข้อมูลวิทยาลัย" ในฐานความรู้ (knowledge_base.json)
จากข้อมูลทางการที่ data/college_official.json (ได้จาก tools/fetch_college_data.py)

หลักการ:
  - ข้อเท็จจริง (หลักสูตร เกณฑ์รับ วิชา อาชีพ ที่อยู่ เบอร์โทร) มาจากเว็บไซต์วิทยาลัยเท่านั้น
  - ไม่ใส่ตัวเลขหรือคำโฆษณาที่ไม่มีแหล่งอ้างอิง (100%, เงินเดือน, คะแนนความเหมาะสม)
  - ข้อมูลที่ไม่มีบนเว็บแต่จำเป็น (ช่วงรับสมัคร/เอกสาร) คงไว้พร้อมระบุ "โปรดตรวจสอบกับวิทยาลัย"
  - หัวข้ออื่นในฐานความรู้ (ท่องเที่ยว อาหาร ฯลฯ) ไม่ถูกแตะ ยกเว้นแก้ชื่อย่อ PBVC -> PBPVC

วิธีใช้:
    python tools/fetch_college_data.py     # ดึงข้อมูลล่าสุดจากเว็บ (ถ้าต้องการ)
    python tools/build_college_kb.py       # เขียนหัวข้อวิทยาลัยลงฐานความรู้
แล้วรัน python prebake_tts.py เพื่ออัดเสียงคำตอบที่เปลี่ยน
"""
import os
import re
import sys
import json
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_FILE = os.path.join(ROOT, 'knowledge_base.json')
OFFICIAL_FILE = os.path.join(ROOT, 'data', 'college_official.json')

ABBR = 'PBPVC'
SOURCE_NOTE = '📌 ข้อมูลจากเว็บไซต์วิทยาลัย (พ.ย. 2569)'
VERIFY_NOTE = '⚠️ โปรดตรวจสอบกับวิทยาลัยอีกครั้ง'

# หัวข้อเดิมที่ถูกรวม/แยกไปเป็นหัวข้อใหม่ (คำถามเดิมจะถูกย้ายไปด้วย)
MERGED_INTO = {
    'admission_bc_001': 'admission_dbt_001',
    'admission_hotel_tourism_001': 'admission_hotel_001',
}

# แผนก (ชื่อตามเว็บไซต์) -> หัวข้อในฐานความรู้
DEPARTMENTS = [
    {
        'id': 'admission_acct_001', 'dept': 'การบัญชี', 'name': 'การบัญชี', 'emoji': '📊',
        'keywords': ['การบัญชี', 'สาขาการบัญชี', 'บัญชี', 'เรียนบัญชี', 'นักบัญชี'],
        'questions': ['สาขาการบัญชีเรียนอะไร', 'จบบัญชีทำงานอะไร', 'เรียนบัญชีอาชีวะเพชรบุรี'],
    },
    {
        'id': 'admission_office_001', 'dept': 'การจัดการสำนักงาน', 'name': 'การจัดการสำนักงาน', 'emoji': '🗂️',
        'aka': 'บางสื่อของวิทยาลัยใช้ชื่อ "การจัดการสำนักงานดิจิทัล"',
        'keywords': ['การจัดการสำนักงาน', 'สำนักงาน', 'การจัดการสำนักงานดิจิทัล', 'เลขานุการ', 'งานเอกสาร'],
        'questions': ['สาขาการจัดการสำนักงานเรียนอะไร', 'จบการจัดการสำนักงานทำงานอะไร',
                      'อยากเป็นเลขานุการเรียนสาขาไหน', 'การจัดการสำนักงานดิจิทัลคืออะไร'],
    },
    {
        'id': 'admission_mkt_001', 'dept': 'การตลาด', 'name': 'การตลาด', 'emoji': '📈',
        'keywords': ['การตลาด', 'สาขาการตลาด', 'ขายของออนไลน์', 'ค้าขาย', 'โฆษณา'],
        'questions': ['สาขาการตลาดเรียนอะไร', 'จบการตลาดทำงานอะไร', 'อยากขายของออนไลน์เรียนสาขาไหน'],
    },
    {
        'id': 'admission_dbt_001', 'dept': 'เทคโนโลยีธุรกิจดิจิทัลและคอมพิวเตอร์ธุรกิจ',
        'name': 'เทคโนโลยีธุรกิจดิจิทัลและคอมพิวเตอร์ธุรกิจ', 'emoji': '💻',
        'extra': ('• ระดับ ปวช. ใช้ชื่อสาขาวิชาคอมพิวเตอร์ธุรกิจ ส่วน ปวส. และปริญญาตรี ใช้ชื่อสาขาวิชาเทคโนโลยีธุรกิจดิจิทัล\n'
                  '• ✨ เป็นแผนกของทีมผู้สร้างหุ่นยนต์น้องเพชรตัวนี้ด้วยค่ะ'),
        'keywords': ['เทคโนโลยีธุรกิจดิจิทัล', 'คอมพิวเตอร์ธุรกิจ', 'dbt', 'bc', 'เรียนคอม', 'เขียนโปรแกรม'],
        'questions': ['สาขาเทคโนโลยีธุรกิจดิจิทัลเรียนอะไร', 'คอมพิวเตอร์ธุรกิจกับเทคโนโลยีธุรกิจดิจิทัลต่างกันอย่างไร',
                      'อยากเป็นโปรแกรมเมอร์เรียนสาขาไหน'],
    },
    {
        'id': 'admission_digital_graphic_001', 'dept': 'คอมพิวเตอร์กราฟิก', 'name': 'ดิจิทัลกราฟิก', 'emoji': '🖌️',
        'aka': 'ชื่อแผนกบนเว็บไซต์คือ "คอมพิวเตอร์กราฟิกและดิจิทัลกราฟิก"',
        'manual': ('• มีนักเรียนทั้งระดับ ปวช. และ ปวส. (ตามข่าวผลงานของวิทยาลัย)\n'
                   '• ผลงานเด่น: นักเรียน ปวช.3 สาขานี้ได้รับคัดเลือกเป็น "นักเรียนรางวัลพระราชทาน" ปีการศึกษา 2568 '
                   'และนักเรียนสาขานี้คว้าเหรียญทองการประกวดวิดีทัศน์ส่งเสริมการท่องเที่ยว\n'
                   '• รายละเอียดหลักสูตรและเกณฑ์รับยังไม่มีบนเว็บไซต์ ' + VERIFY_NOTE),
        'keywords': ['ดิจิทัลกราฟิก', 'คอมพิวเตอร์กราฟิก', 'กราฟิก', 'ออกแบบกราฟิก', 'ตัดต่อวิดีโอ'],
        'questions': ['สาขาดิจิทัลกราฟิกเรียนอะไร', 'อยากเรียนกราฟิกเรียนสาขาไหน', 'สาขาคอมพิวเตอร์กราฟิกมีไหม',
                      'ชอบวาดรูปในคอมเรียนอะไรดี'],
    },
    {
        'id': 'admission_fine_arts_001', 'dept': 'วิจิตรศิลป์', 'name': 'วิจิตรศิลป์', 'emoji': '🎨',
        'keywords': ['วิจิตรศิลป์', 'ศิลปะ', 'วาดรูป', 'จิตรกรรม', 'ประติมากรรม'],
        'questions': ['สาขาวิจิตรศิลป์เรียนอะไร', 'ชอบวาดรูปเรียนสาขาไหน', 'จบวิจิตรศิลป์ทำงานอะไร'],
    },
    {
        'id': 'admission_fashion_001', 'dept': 'แฟชั่นและสิ่งทอ', 'name': 'แฟชั่นและสิ่งทอ', 'emoji': '👗',
        'aka': 'บางสื่อของวิทยาลัยใช้ชื่อ "เทคโนโลยีแฟชั่นและสิ่งทอ"',
        'keywords': ['แฟชั่น', 'สิ่งทอ', 'ตัดเย็บ', 'ออกแบบเสื้อผ้า', 'เครื่องแต่งกาย'],
        'questions': ['สาขาแฟชั่นและสิ่งทอเรียนอะไร', 'อยากออกแบบเสื้อผ้าเรียนสาขาไหน'],
    },
    {
        'id': 'admission_culinary_001', 'dept': 'อาหารและโภชนาการ', 'name': 'อาหารและโภชนาการ', 'emoji': '🍳',
        'keywords': ['อาหารและโภชนาการ', 'ทำอาหาร', 'เชฟ', 'เบเกอรี่', 'ขนมไทย'],
        'questions': ['สาขาอาหารและโภชนาการเรียนอะไร', 'อยากเป็นเชฟเรียนสาขาไหน'],
    },
    {
        'id': 'admission_home_econ_001', 'dept': 'คหกรรม', 'name': 'คหกรรม', 'emoji': '🌸',
        'keywords': ['คหกรรม', 'คหกรรมศาสตร์', 'จัดดอกไม้', 'แกะสลัก', 'งานใบตอง'],
        'questions': ['สาขาคหกรรมเรียนอะไร', 'อยากเรียนจัดดอกไม้เรียนสาขาไหน', 'จบคหกรรมทำงานอะไร'],
    },
    {
        'id': 'admission_hotel_001', 'dept': 'การโรงแรม', 'name': 'การโรงแรม', 'emoji': '🏨',
        'keywords': ['การโรงแรม', 'สาขาการโรงแรม', 'โรงแรม', 'พนักงานโรงแรม', 'บาร์เทนเดอร์'],
        'questions': ['สาขาการโรงแรมเรียนอะไร', 'จบการโรงแรมทำงานอะไร'],
    },
    {
        'id': 'admission_tourism_001', 'dept': 'การท่องเที่ยว', 'name': 'การท่องเที่ยว', 'emoji': '🧭',
        'extra': ('• วิทยาลัยลงนามความร่วมมือ (MOU) ส่งนักเรียนฝึกประสบการณ์กับการท่องเที่ยวแห่งประเทศไทย สำนักงานเพชรบุรี\n'
                  '• ข่าววิทยาลัยมีกล่าวถึงสาขาวิชาการท่องเที่ยวไมซ์และอีเวนต์ด้วย ' + VERIFY_NOTE),
        'keywords': ['การท่องเที่ยว', 'สาขาการท่องเที่ยว', 'ไกด์', 'มัคคุเทศก์', 'ไมซ์', 'อีเวนต์'],
        'questions': ['สาขาการท่องเที่ยวเรียนอะไร', 'อยากเป็นไกด์เรียนสาขาไหน', 'จบการท่องเที่ยวทำงานอะไร'],
    },
]

# ข้อมูลวิทยาลัยเดิมที่ผิด ซึ่งอยู่ในหัวข้ออื่น (เช่น คำทักทาย เบอร์ฉุกเฉิน) -> ข้อมูลทางการ
STALE_FACTS = {
    '032-425-467': '032-425-557',
    '032-425-470': '032-425-557',
    'www.pbvc.ac.th': 'www.pbpvc.ac.th',
    '9 สาขาวิชาชีพแห่งอนาคตสุดล้ำของ PBPVC': '11 สาขาวิชาของ PBPVC',
    '9 สาขาวิชาชีพแห่งอนาคต': '11 สาขาวิชา',
    '9 สาขา': '11 สาขา',
}

COMMON_SUGGESTIONS = ['วิทยาลัยเปิดสอนกี่สาขา', 'สมัครเรียนต้องใช้เอกสารอะไร', 'ติดต่อวิทยาลัยได้ที่ไหน']


def short_admission(text):
    t = text.replace('รับผู้สำเร็จการศึกษาระดับชั้น', 'รับผู้จบ ')
    t = t.replace('มัธยมศึกษาปีที่ 3', ' ม.3').replace('มัธยมศึกษาปีที่ 6', ' ม.6')
    t = re.sub(r'\[ทั้งสายตรงหรือจบจากสาขาอื่น ๆ\]', '(สายตรงหรือสาขาอื่น)', t)
    return re.sub(r'\s+', ' ', t).replace('รับผู้จบ  ', 'รับผู้จบ ').strip()


def program_line(p):
    if 'raw' in p:
        return p['raw']
    major = re.sub(r'^ประเภทวิชา\S+\s*', '', p['name']).replace('สาขาวิชาการเทคโนโลยี', 'สาขาวิชาเทคโนโลยี')
    level = p['level'].replace('ปริญญาตรีสายเทคโนโลยี', 'ปริญญาตรีสายเทคโนโลยี')
    track = '' if p['track'] in ('ปกติ', 'หลักสูตรปกติ') else f" ({p['track'].replace('หลักสูตร', '')})"
    return f"{level}{track} {major} — {short_admission(p['admission'])}"


def clean_list(items, limit):
    return [i for i in items if not i.startswith('อื่น ๆ')][:limit]


def dept_answer(spec, dept, contact_phone):
    lines = [f"{spec['emoji']} **สาขาวิชา{spec['name']} วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})**", '']
    if spec.get('aka'):
        lines.append(f"• {spec['aka']}")
    if dept and dept.get('programs'):
        lines.append('• **หลักสูตรที่เปิดสอน**:')
        lines += [f'  - {program_line(p)}' for p in dept['programs']]
        subjects = clean_list(dept.get('sample_subjects', []), 6)
        if subjects:
            lines.append('• **ตัวอย่างวิชาที่เรียน**: ' + ', '.join(subjects))
        careers = clean_list(dept.get('careers', []), 6)
        if careers:
            lines.append('• **อาชีพหลังเรียนจบ**: ' + ', '.join(careers))
    if spec.get('manual'):
        lines.append(spec['manual'])
    if spec.get('extra'):
        lines.append(spec['extra'])
    lines += ['', f'{SOURCE_NOTE} สอบถามเพิ่มเติม โทร {contact_phone}']
    return '\n'.join(lines)


def fmt_phone(p):
    digits = re.sub(r'\D', '', p or '')
    return f'{digits[:3]}-{digits[3:6]}-{digits[6:]}' if len(digits) == 9 else (p or '')


def build(official, existing):
    c = official['college']
    contact = c['contact']
    phone = fmt_phone(contact['phone'])
    fax = fmt_phone(contact['fax'])
    depts = {d['department']: d for d in official['departments']}
    majors = official['facebook_intro']['majors_11']

    def merged(entry_id, keywords, questions, suggestions):
        """รวมคำถาม/คีย์เวิร์ดเดิมของหัวข้อนั้น (และหัวข้อที่ถูกรวมเข้ามา) เพื่อไม่ให้คำถามเดิมตอบไม่ได้"""
        old_q, old_k = [], []
        for src_id, dst_id in list(MERGED_INTO.items()) + [(entry_id, entry_id)]:
            if dst_id == entry_id and src_id in existing:
                old_q += existing[src_id].get('questions', [])
                old_k += existing[src_id].get('keywords', [])
        fix = lambda s: s.replace('PBVC', ABBR)
        uniq = lambda xs: list(dict.fromkeys(fix(x) for x in xs if x))
        return {'keywords': uniq(keywords + old_k), 'questions': uniq(questions + old_q),
                'suggestions': suggestions}

    entries = []
    for spec in DEPARTMENTS:
        dept = depts.get(spec['dept'])
        q = merged(spec['id'], spec['keywords'], spec['questions'], COMMON_SUGGESTIONS)
        if spec['id'] == 'admission_hotel_001':
            # คำถามเรื่องไกด์/มัคคุเทศก์ของหัวข้อเดิมให้ไปอยู่ที่การท่องเที่ยว
            q['questions'] = [x for x in q['questions'] if 'ท่องเที่ยว' not in x]
            q['keywords'] = [x for x in q['keywords'] if x not in ('การท่องเที่ยว', 'ไกด์', 'มัคคุเทศก์')]
        entries.append({'id': spec['id'], 'intent': 'admission',
                        'title': f"สาขาวิชา{spec['name']} ({ABBR})",
                        'answer': dept_answer(spec, dept if dept and dept.get('has_content') else None, phone), **q})

    # ภาพรวม 11 สาขา พร้อมระดับที่เปิดสอน
    levels = {}
    for spec in DEPARTMENTS:
        d = depts.get(spec['dept'])
        lv = sorted({p['level'].replace('ปริญญาตรีสายเทคโนโลยี', 'ป.ตรี') for p in (d or {}).get('programs', []) if 'level' in p},
                    key=lambda x: ['ปวช.', 'ปวส.', 'ป.ตรี'].index(x) if x in ['ปวช.', 'ปวส.', 'ป.ตรี'] else 9)
        levels[spec['name']] = '/'.join(lv) if lv else 'โปรดตรวจสอบกับวิทยาลัย'
    overview = [f"🎓 **วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR}) เปิดสอน {len(majors)} สาขาวิชา**", '']
    for i, spec in enumerate(DEPARTMENTS, 1):
        overview.append(f"{i}. {spec['emoji']} **{spec['name']}** ({levels[spec['name']]})")
    overview += ['', 'ถามรายละเอียดของสาขาที่สนใจกับน้องเพชรได้เลยนะคะ', f'{SOURCE_NOTE}']
    entries.append({'id': 'admission_branches_001', 'intent': 'admission',
                    'title': f'สาขาวิชาที่เปิดสอน วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})',
                    'answer': '\n'.join(overview),
                    **merged('admission_branches_001', ['สาขา', 'สาขาวิชา', 'เปิดสอน', 'มีสาขาอะไรบ้าง', 'แผนก'],
                             ['วิทยาลัยมีสาขาอะไรบ้าง', 'เปิดสอนกี่สาขา', 'มีแผนกอะไรบ้าง', 'อาชีวะเพชรบุรีเรียนอะไรได้บ้าง'],
                             ['สาขาไหนเรียน ป.ตรี ต่อได้', 'สมัครเรียนต้องใช้เอกสารอะไร', 'ระบบทวิภาคีคืออะไร'])})

    # ทวิภาคี และปริญญาตรี จากข้อมูลหลักสูตร
    dve_vocational, bachelor = [], []
    for spec in DEPARTMENTS:
        for p in (depts.get(spec['dept']) or {}).get('programs', []):
            if 'ทวิภาคี' in p.get('track', ''):
                (bachelor if p['level'].startswith('ปริญญาตรี') else dve_vocational).append(spec['name'])
    entries.append({'id': 'admission_dve_001', 'intent': 'admission',
                    'title': f'ระบบทวิภาคี ({ABBR})',
                    'answer': '\n'.join([
                        f'💼 **ระบบทวิภาคี วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})**', '',
                        '• เรียนทฤษฎีที่วิทยาลัย และฝึกปฏิบัติงานจริงในสถานประกอบการตามหลักสูตร',
                        '• **ปวส. ระบบทวิภาคี**: สาขา' + ', '.join(dict.fromkeys(dve_vocational)),
                        '• **ปริญญาตรีสายเทคโนโลยี (ทวิภาคี)**: สาขา' + ', '.join(dict.fromkeys(bachelor)),
                        '• วิทยาลัยลงนามความร่วมมือ (MOU) กับหน่วยงานในจังหวัด เช่น การท่องเที่ยวแห่งประเทศไทย สำนักงานเพชรบุรี '
                        'เพื่อรับนักเรียนนักศึกษาฝึกอาชีพ',
                        '• ค่าตอบแทนและสวัสดิการระหว่างฝึก ขึ้นกับสถานประกอบการ ' + VERIFY_NOTE, '',
                        f'{SOURCE_NOTE} สอบถามเพิ่มเติม โทร {phone}']),
                    **merged('admission_dve_001', ['ทวิภาคี', 'ระบบทวิภาคี', 'ฝึกงาน', 'ทำงานระหว่างเรียน'],
                             ['ระบบทวิภาคีคืออะไร', 'สาขาไหนเรียนทวิภาคีได้'],
                             ['สาขาไหนเรียน ป.ตรี ต่อได้', 'สมัครเรียนต้องใช้เอกสารอะไร', 'ติดต่อวิทยาลัยได้ที่ไหน'])})
    entries.append({'id': 'admission_bachelor_001', 'intent': 'admission',
                    'title': f'ปริญญาตรีสายเทคโนโลยี ({ABBR})',
                    'answer': '\n'.join([
                        f'🎓 **ปริญญาตรีสายเทคโนโลยี (หลักสูตรทวิภาคี) วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})**', '',
                        '• เปิดสอนในสาขา: ' + ', '.join(dict.fromkeys(bachelor)),
                        '• รับผู้จบ ปวส. ในสาขาเดียวกันหรือสาขาที่เกี่ยวข้องเท่านั้น',
                        '• เรียนแบบทวิภาคี คือเรียนที่วิทยาลัยควบคู่กับฝึกงานในสถานประกอบการ', '',
                        f'{SOURCE_NOTE} สอบถามเพิ่มเติม โทร {phone}']),
                    **merged('admission_bachelor_001', ['ปริญญาตรี', 'ป.ตรี', 'ปริญญาตรีสายเทคโนโลยี', 'เรียนต่อ ป.ตรี', 'ทล.บ.'],
                             ['วิทยาลัยมีปริญญาตรีไหม', 'จบ ปวส. เรียนต่อ ป.ตรี ที่นี่ได้ไหม', 'ปริญญาตรีสายเทคโนโลยีคืออะไร',
                              'สาขาไหนเรียน ป.ตรี ต่อได้'],
                             ['ระบบทวิภาคีคืออะไร', 'สมัครเรียนต้องใช้เอกสารอะไร', 'ติดต่อวิทยาลัยได้ที่ไหน'])})

    # การรับสมัคร (ช่วงเวลา/เอกสารไม่มีบนเว็บ: คงไว้พร้อมให้ตรวจสอบ)
    entries.append({'id': 'admission_apply_001', 'intent': 'admission',
                    'title': f'การรับสมัครนักเรียน นักศึกษาใหม่ ({ABBR})',
                    'answer': '\n'.join([
                        f'📝 **การรับสมัครนักเรียน นักศึกษาใหม่ วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})**', '',
                        '• **ระดับที่เปิดรับ**:',
                        '  - ปวช. รับผู้จบ ม.3 หรือเทียบเท่า',
                        '  - ปวส. รับผู้จบ ปวช. หรือ ม.6 หรือเทียบเท่า (บางสาขารับเฉพาะ ปวช. สายตรง)',
                        '  - ปริญญาตรีสายเทคโนโลยี รับผู้จบ ปวส. สาขาที่เกี่ยวข้อง',
                        f'• **ช่วงเวลาเปิดรับสมัคร** ({VERIFY_NOTE}): รอบโควตา (พ.ย. - ม.ค.) และรอบทั่วไป (ก.พ. - พ.ค.)',
                        f'• **เอกสารที่ต้องเตรียม** ({VERIFY_NOTE}):',
                        '  1. ใบระเบียนแสดงผลการเรียน (ปพ.1) หรือใบรับรองผลการเรียน',
                        '  2. สำเนาทะเบียนบ้าน และสำเนาบัตรประชาชนของผู้สมัคร บิดา และมารดา',
                        '  3. รูปถ่ายหน้าตรงขนาด 1.5 นิ้ว จำนวน 2 รูป',
                        f'• 📞 **สอบถาม**: โทร {phone} (จันทร์ - ศุกร์ 08:00 - 16:00 น.)', '',
                        SOURCE_NOTE]),
                    **merged('admission_apply_001', ['รับสมัคร', 'สมัครเรียน', 'เอกสารสมัคร'],
                             ['สมัครเรียนต้องใช้เอกสารอะไร', 'เปิดรับสมัครเมื่อไหร่'],
                             ['วิทยาลัยเปิดสอนกี่สาขา', 'ระบบทวิภาคีคืออะไร', 'ติดต่อวิทยาลัยได้ที่ไหน'])})

    entries.append({'id': 'college_contact_001', 'intent': 'admission',
                    'title': f'ข้อมูลติดต่อ วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})',
                    'answer': '\n'.join([
                        f'📍 **ติดต่อวิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})**', '',
                        f"• **ที่อยู่**: {contact['address']}",
                        f'• **โทรศัพท์**: {phone}',
                        f'• **โทรสาร**: {fax}',
                        f"• **อีเมล**: {contact['email']}",
                        f"• **เวลาทำการ**: {contact['office_hours']} น.",
                        '• **เว็บไซต์**: www.pbpvc.ac.th',
                        '• **Facebook**: วิทยาลัยอาชีวศึกษาเพชรบุรี (facebook.com/PBPVC)', '',
                        SOURCE_NOTE]),
                    **merged('college_contact_001',
                             ['ติดต่อ', 'เบอร์โทร', 'โทรศัพท์', 'ที่อยู่', 'อีเมล', 'เวลาทำการ', 'เว็บไซต์วิทยาลัย', 'วิทยาลัยอยู่ที่ไหน'],
                             ['ติดต่อวิทยาลัยได้ที่ไหน', 'เบอร์โทรวิทยาลัย', 'วิทยาลัยอยู่ที่ไหน', 'ที่อยู่วิทยาลัยอาชีวศึกษาเพชรบุรี',
                              'วิทยาลัยเปิดกี่โมง', 'อีเมลวิทยาลัย'],
                             ['สมัครเรียนต้องใช้เอกสารอะไร', 'วิทยาลัยเปิดสอนกี่สาขา', 'ประวัติวิทยาลัย'])})

    entries.append({'id': 'college_about_001', 'intent': 'admission',
                    'title': f'ประวัติและวิสัยทัศน์ วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})',
                    'answer': '\n'.join([
                        f'🏫 **วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})**', '',
                        f"• สังกัด{c['affiliation']}",
                        '• **ประวัติโดยย่อ**: ก่อตั้งเมื่อ พ.ศ. 2477 ในชื่อโรงเรียนการเรือนและฝึกหัดครูประกาศนียบัตรเพชรบุรี '
                        'ตั้งอยู่ที่พระรามราชนิเวศน์ (วังบ้านปืน) ต่อมา พ.ศ. 2482 ย้ายมาอยู่ที่ถนนราชวิถี',
                        f"• **วิสัยทัศน์**: {c['vision']}",
                        f"• **ปรัชญา**: {c['philosophy']}",
                        f"• **อัตลักษณ์**: {c['identity']}",
                        f"• **เอกลักษณ์**: {c['uniqueness']}", '',
                        SOURCE_NOTE]),
                    **merged('college_about_001',
                             ['ประวัติ', 'ประวัติวิทยาลัย', 'วิสัยทัศน์', 'ปรัชญา', 'อัตลักษณ์', 'เอกลักษณ์', 'ก่อตั้ง'],
                             ['ประวัติวิทยาลัย', 'วิทยาลัยก่อตั้งเมื่อไหร่', 'วิสัยทัศน์ของวิทยาลัยคืออะไร', 'ปรัชญาวิทยาลัย',
                              'อัตลักษณ์ของวิทยาลัย'],
                             ['ใครเป็นผู้อำนวยการวิทยาลัย', 'วิทยาลัยเปิดสอนกี่สาขา', 'ติดต่อวิทยาลัยได้ที่ไหน'])})

    entries.append({'id': 'college_director_001', 'intent': 'admission',
                    'title': f'ผู้อำนวยการ วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})',
                    'answer': '\n'.join([
                        f'👩‍💼 **ผู้อำนวยการวิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR})**', '',
                        f"• {c['director']}", '',
                        SOURCE_NOTE]),
                    **merged('college_director_001', ['ผู้อำนวยการ', 'ผอ', 'ผอ.', 'ผู้บริหาร'],
                             ['ใครเป็นผู้อำนวยการวิทยาลัย', 'ผอ. วิทยาลัยชื่ออะไร', 'ผู้บริหารวิทยาลัย'],
                             ['ประวัติวิทยาลัย', 'วิทยาลัยเปิดสอนกี่สาขา', 'ติดต่อวิทยาลัยได้ที่ไหน'])})

    # สาขาที่ไม่มี: ตอบตรงๆ แทนการแต่งข้อมูล
    entries.append({'id': 'admission_logistics_001', 'intent': 'admission',
                    'title': f'สาขาโลจิสติกส์ ({ABBR})',
                    'answer': '\n'.join([
                        f'📦 วิทยาลัยอาชีวศึกษาเพชรบุรี ({ABBR}) **ไม่มีสาขาโลจิสติกส์** ค่ะ', '',
                        'ถ้าสนใจงานด้านธุรกิจ การขาย หรือการจัดการ ลองดูสาขาเหล่านี้นะคะ:',
                        '• **การตลาด**: การขายออนไลน์ การจัดจำหน่ายสินค้าและบริการ',
                        '• **การจัดการสำนักงาน**: งานเอกสาร ระบบสารสนเทศในสำนักงาน',
                        '• **เทคโนโลยีธุรกิจดิจิทัล**: คอมพิวเตอร์และระบบงานธุรกิจ', '',
                        SOURCE_NOTE]),
                    **merged('admission_logistics_001', ['โลจิสติกส์'], [],
                             ['วิทยาลัยเปิดสอนกี่สาขา', 'สาขาการตลาดเรียนอะไร', 'ติดต่อวิทยาลัยได้ที่ไหน'])})
    return entries


def main():
    official = json.load(open(OFFICIAL_FILE, encoding='utf-8'))
    kb = json.load(open(KB_FILE, encoding='utf-8'))
    existing = {e['id']: e for e in kb['entries']}

    new_entries = build(official, existing)
    new_ids = {e['id'] for e in new_entries}
    removed = set(MERGED_INTO)

    result, placed = [], set()
    for e in kb['entries']:
        if e['id'] in removed:
            continue
        if e['id'] in new_ids:
            result.append(next(n for n in new_entries if n['id'] == e['id']))
            placed.add(e['id'])
        else:
            # หัวข้ออื่น: แก้เฉพาะข้อมูลวิทยาลัยที่ผิด (ชื่อย่อ, เบอร์โทรเดิม, จำนวนสาขาเดิม)
            text = json.dumps(e, ensure_ascii=False).replace('PBVC', ABBR)
            for old, new in STALE_FACTS.items():
                text = text.replace(old, new)
            result.append(json.loads(text))
    result += [n for n in new_entries if n['id'] not in placed]

    kb['entries'] = result
    if kb.get('description'):
        kb['description'] = kb['description'].replace('PBVC', ABBR)
    shutil.copyfile(KB_FILE, KB_FILE + '.bak')
    tmp = KB_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, KB_FILE)

    print(f'อัปเดตแล้ว {len(placed)} หัวข้อ, เพิ่มใหม่ {len(new_ids - placed)} หัวข้อ, รวมเข้าหัวข้ออื่น {len(removed)} หัวข้อ')
    print(f'ฐานความรู้มีทั้งหมด {len(result)} หัวข้อ (สำรองไฟล์เดิมไว้ที่ knowledge_base.json.bak)')


if __name__ == '__main__':
    main()
