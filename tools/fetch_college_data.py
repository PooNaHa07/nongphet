#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ดึงข้อมูลทางการของวิทยาลัยอาชีวศึกษาเพชรบุรีจากเว็บไซต์ http://www.pbpvc.ac.th
แล้วบันทึกเป็นข้อมูลมีโครงสร้างที่ data/college_official.json

ใช้เป็น "แหล่งข้อมูลอ้างอิง" สำหรับตรวจและเขียนคำตอบในฐานความรู้ของน้องเพชร
(สคริปต์นี้ไม่แก้ knowledge_base.json เอง)

วิธีใช้:
    python tools/fetch_college_data.py
"""
import os
import re
import sys
import json
import datetime
import urllib.parse
from html.parser import HTMLParser

import httpx

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE = 'http://www.pbpvc.ac.th/page/'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(ROOT, 'data', 'college_official.json')

# ชื่อแผนกตามเมนู "แผนกวิชา" บนเว็บไซต์ (ใช้เป็นพารามิเตอร์ s_group)
DEPARTMENTS = [
    'การบัญชี', 'การจัดการสำนักงาน', 'การตลาด', 'เทคโนโลยีธุรกิจดิจิทัลและคอมพิวเตอร์ธุรกิจ',
    'วิจิตรศิลป์', 'คอมพิวเตอร์กราฟิก', 'แฟชั่นและสิ่งทอ', 'อาหารและโภชนาการ', 'คหกรรม',
    'การโรงแรม', 'การท่องเที่ยว',
]

# ข้อมูลจากเพจ Facebook ทางการ (https://www.facebook.com/PBPVC/) ซึ่งต้องเปิดผ่านเบราว์เซอร์
# คัดลอกด้วยมือเมื่อ 2026-11-17: ใช้เทียบกับเว็บไซต์
FACEBOOK_INTRO = {
    'url': 'https://www.facebook.com/PBPVC/',
    'checked_at': '2026-11-17',
    'majors_11': ['การบัญชี', 'การตลาด', 'การจัดการสำนักงานดิจิทัล', 'เทคโนโลยีธุรกิจดิจิทัล', 'การโรงแรม',
                  'การท่องเที่ยว', 'อาหารและโภชนาการ', 'คหกรรม', 'เทคโนโลยีแฟชั่นและสิ่งทอ', 'วิจิตรศิลป์',
                  'ดิจิทัลกราฟิก'],
    'phone': '032 425 557',
    'email': 'sarabun@pbpvc.ac.th',
    'youtube': 'https://www.youtube.com/@pbpvc_vec',
}


class TextExtractor(HTMLParser):
    """ดึงข้อความจาก HTML โดยข้าม script/style และขึ้นบรรทัดใหม่ตามแท็กบล็อก"""
    BLOCK = {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'td'}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        t = ''.join(self.parts).replace('\xa0', ' ')
        lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in t.split('\n')]
        return '\n'.join(ln for ln in lines if ln)


def page_text(client, url):
    res = client.get(url)
    res.raise_for_status()
    parser = TextExtractor()
    parser.feed(res.text)
    return parser.text()


def section(text, start, ends):
    i = text.find(start)
    if i < 0:
        return ''
    i += len(start)
    j = min([k for k in (text.find(e, i) for e in ends) if k > 0] or [len(text)])
    return text[i:j].strip()


def bullets(block):
    return [ln.lstrip('-•* ').strip() for ln in block.split('\n') if ln.strip().startswith(('-', '•', '*'))]


def parse_department(name, text, url):
    title_match = re.search(r'สาขาวิชา[^\n]+', text)
    programs = []
    for line in bullets(section(text, 'หลักสูตรที่เปิดสอน', ['รายละเอียดสาขาวิชา'])):
        m = re.match(r'หลักสูตร\s*(ปวช\.|ปวส\.|ปริญญาตรี[^\s]*)\s*(\([^)]*\))?\s*(.*?)\s*\((รับ.*)\)\s*$', line)
        if m:
            programs.append({
                'level': m.group(1),
                'track': (m.group(2) or '').strip('() ') or 'ปกติ',
                'name': re.sub(r'\s+', ' ', m.group(3)).strip(),
                'admission': m.group(4).strip(),
            })
        else:
            programs.append({'raw': line})
    head = re.search(r'\n([^\n]{3,40})\nหัวหน้าแผนกวิชา([^\n]*)', text)
    return {
        'department': name,
        'title': title_match.group(0).strip() if title_match else None,
        'source_url': url,
        'has_content': bool(programs),
        'programs': programs,
        'description': section(text, 'รายละเอียดสาขาวิชา', ['ตัวอย่างบางส่วนรายวิชาที่ศึกษา']),
        'sample_subjects': bullets(section(text, 'ตัวอย่างบางส่วนรายวิชาที่ศึกษา', ['อาชีพที่รองรับหลังจบการศึกษา'])),
        'careers': bullets(section(text, 'อาชีพที่รองรับหลังจบการศึกษา', ['Social Share', 'สื่อออนไลน์', 'คณะครูผู้สอน'])),
        'head_of_department': {'name': re.sub(r'\s+', ' ', head.group(1)).strip(),
                               'position': 'หัวหน้าแผนกวิชา' + head.group(2).strip()} if head else None,
    }


def parse_home(text):
    def after(label):
        # ต้องมี ":" ตามหลังหัวข้อ กันไปจับคำเดียวกันที่อยู่ในข้อความข่าว (เช่น "จากอัตลักษณ์จิตรกรรม...")
        m = re.search(re.escape(label) + r'\s*:\s*([^\n]+)', text)
        return m.group(1).strip() if m else None
    director = re.search(r'([^\n]+)\nผู้อำนวยการวิทยาลัยอาชีวศึกษาเพชรบุรี', text)
    contact_line = after('โทรศัพท์')
    phone = fax = None
    if contact_line:
        parts = contact_line.split('|')
        phone = parts[0].strip()
        fax_m = re.search(r'โทรสาร\s*:\s*(\S+)', contact_line)
        fax = fax_m.group(1) if fax_m else None
    history = section(text, 'มีประวัติโดยสังเขป ดังนี้', ['More About Us'])
    categories = re.findall(r'(ประเภทวิชา[^\n]+)\n([A-Z][^\n]+)', text)
    return {
        'name_th': 'วิทยาลัยอาชีวศึกษาเพชรบุรี',
        'name_en': 'Phetchaburi Vocational College',
        'affiliation': 'สำนักงานคณะกรรมการการอาชีวศึกษา (สอศ.) กระทรวงศึกษาธิการ',
        'director': director.group(1).strip() if director else None,
        'vision': after('วิสัยทัศน์'),
        'philosophy': after('ปรัชญาวิทยาลัย'),
        'identity': after('อัตลักษณ์'),
        'uniqueness': after('เอกลักษณ์'),
        'program_categories': [{'th': th.strip(), 'en': en.strip()} for th, en in categories],
        'history_summary': history or None,
        'contact': {
            'address': after('ที่อยู่'),
            'phone': phone,
            'fax': fax,
            'email': after('E-Mail'),
            'office_hours': re.sub(r'\s+', ' ', section(text, 'วันเวลาทำการ', ['ติดต่อวิทยาลัยฯ'])) or None,
            'website': 'http://www.pbpvc.ac.th',
        },
    }


def main():
    with httpx.Client(timeout=20, headers={'User-Agent': 'nongphet-kiosk-data-sync'}) as client:
        home = parse_home(page_text(client, BASE + 'index.php'))
        departments = []
        for name in DEPARTMENTS:
            url = BASE + 'Department.php?s_group=' + urllib.parse.quote(name)
            try:
                dept = parse_department(name, page_text(client, url), url)
            except Exception as e:
                dept = {'department': name, 'source_url': url, 'error': str(e)}
            departments.append(dept)
            status = 'ok' if dept.get('has_content') else 'ไม่มีข้อมูลบนเว็บ'
            print(f"  {name}: {status}, หลักสูตร {len(dept.get('programs', []))}")

    data = {
        'fetched_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'sources': [BASE + 'index.php', FACEBOOK_INTRO['url']],
        'note': 'ข้อมูลดึงจากเว็บไซต์ทางการของวิทยาลัยโดยอัตโนมัติ ควรให้งานประชาสัมพันธ์/งานทะเบียนตรวจก่อนใช้ตอบจริง',
        'college': home,
        'facebook_intro': FACEBOOK_INTRO,
        'departments': departments,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"บันทึกแล้ว: {OUT_FILE}")


if __name__ == '__main__':
    main()
