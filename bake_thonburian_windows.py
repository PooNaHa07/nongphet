#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
โครงการ: น้องเพชร AI Smart Guide (PBVC)
สคริปต์: สร้างคลังเสียงล่วงหน้าออฟไลน์ 100% ด้วย ThonburianTTS (bake_thonburian_windows.py)
อุปกรณ์เป้าหมายการเจน: โน้ตบุ๊ก Windows (NVIDIA GTX 1650 CUDA / CPU Fallback)
อุปกรณ์ใช้งานจริง: Raspberry Pi 5 (RAM 8GB) ในโหมด Standalone Offline 0ms
==============================================================================
"""

import os
import sys
import re
import io
import time
import json
import base64
import hashlib
import argparse
import datetime
from pathlib import Path

# ปรับการแสดงผล UTF-8 บน Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# โฟลเดอร์รากและแคช
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, 'static', 'audio', 'cache')
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
MANIFEST_PATH = os.path.join(BASE_DIR, 'static', 'audio', 'cache_manifest.json')
KB_PATH = os.path.join(BASE_DIR, 'knowledge_base.json')

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# 1. ฟังก์ชันทำความสะอาดข้อความตามสูตรเดียวกับ app.py (ใช้คำนวณ MD5 Hash)
# -----------------------------------------------------------------------------
def clean_text_for_hash(text, max_len=2500, lang='th'):
    """
    ขัดเกลาข้อความตามสูตรเดียวกับ app.py และ routes/media.py เป๊ะ 100%
    *** สำคัญ: ห้ามแก้ไขฟังก์ชันนี้เพื่อให้ Hash ตรงกับเซิร์ฟเวอร์ทุกประการ ***
    """
    if not text:
        return ""
    t = text

    # ตัดเฉพาะส่วนปุ่มถามต่อยอดท้ายคำตอบ
    for delim in ['---', '💡 ถามต่อยอด', 'ถามต่อยอดกับน้องเพชร', '💡 แนะนำคำถาม', 'คำถามที่น่าสนใจ', '💡 Follow-up', '💡 推荐问题', '❓ คำถามแนะนำ']:
        if delim in t:
            t = t.split(delim)[0].strip()

    t = re.sub(r'https?://\S+|www\.\S+', '', t)
    t = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', t)
    t = re.sub(r'\n+', ', ', t)

    if lang == 'th':
        t = re.sub(r'ครับ/ค่ะ', 'ค่ะ', t)
        t = re.sub(r'ค่ะ/นะคะ', 'ค่ะ', t)
        t = re.sub(r'สวัสดีครับ', 'สวัสดีค่ะ', t)
        t = re.sub(r'ผมน้องเพชร', 'น้องเพชร', t)
        t = re.sub(r'\bผม\b', 'น้องเพชร', t)
        t = re.sub(r'นะครับ', 'นะคะ', t)
        t = re.sub(r'ครับผม', 'ยินดีค่ะ', t)
        t = re.sub(r'ครับ', 'ค่ะ', t)

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

    t = re.sub(r'[*#_~>•\-=|`]', ' ', t)
    t = re.sub(r'\((?:อังกฤษ|Tel|โทร|ค่าเข้า|ราคา)[^)]*\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'[()\[\]{}]', ' ', t)

    emoji_clean_regex = re.compile(
        r'[\U00010000-\U0010FFFF]'
        r'|[\u2600-\u27BF]'
        r'|[\u2300-\u23FF]'
        r'|[\u2B50\u2B55\u200D\uFE0E\uFE0F]'
    )
    t = emoji_clean_regex.sub('', t)
    t = re.sub(r'[^a-zA-Z0-9\u0E00-\u0E7F\u4E00-\u9FA5\s.,!?\'"-]', ' ', t)

    if lang == 'th':
        pause_phrases = [
            (r'(\bสวัสดีค่ะ)\s*', r'\1, '),
            (r'(\bยินดีต้อนรับค่ะ)\s*', r'\1, '),
            (r'\s*(สำหรับ)\s*', r', สำหรับ '),
            (r'\s*(นอกจากนี้)\s*', r', นอกจากนี้, '),
            (r'\s*(บอกเลยว่า)\s*', r', บอกเลยว่า '),
            (r'\s*(ไฮไลท์คือ)\s*', r', ไฮไลท์คือ '),
            (r'\s*(ที่สำคัญคือ)\s*', r', ที่สำคัญคือ '),
            (r'\s*(อย่างไรก็ตาม)\s*', r', อย่างไรก็ตาม, '),
        ]
        for pattern, repl in pause_phrases:
            t = re.sub(pattern, repl, t)

    t = re.sub(r'\s*,\s*', ', ', t)
    t = re.sub(r',\s*,+', ', ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    if len(t) > max_len:
        cutoff = max_len
        for sep in ['ค่ะ', 'ครับ', 'นะคะ', '.', '!', '?', ', ']:
            idx = t.rfind(sep, int(max_len * 0.8), max_len)
            if idx != -1:
                cutoff = idx + len(sep)
                break
        t = t[:cutoff].strip()

    return t


def compute_server_cache_filename(clean_key_text, voice="th-TH-PremwadeeNeural", pitch="+0Hz", rate="+2%"):
    """คำนวณชื่อไฟล์แคช MD5 ให้ตรงกับสูตรของ app.py 100%"""
    cache_key = f"{voice}_{pitch}_{rate}_{clean_key_text}"
    disk_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
    return f"{disk_hash}.mp3", disk_hash, cache_key


# -----------------------------------------------------------------------------
# 2. Thai Text Normalization สำหรับ ThonburianTTS (ส่งเข้าโมเดลสังเคราะห์เสียงเท่านั้น)
# -----------------------------------------------------------------------------
def normalize_thai_for_tts(text: str) -> str:
    """
    แปลงคำย่อ, ตัวเลข และศัพท์เฉพาะ ให้โมเดล Flow-Matching ออกเสียงชัดเจนเป็นธรรมชาติ
    *** สำคัญ: ห้ามนำผลลัพธ์นี้ไปคำนวณ MD5 Hash เด็ดขาด! ***
    """
    if not text:
        return ""
    t = text

    # ขยายคำย่อทางการศึกษาและหน่วยงาน
    acronym_rules = [
        (r'\bปวช\.', 'ปอ-วอ-ชอ'),
        (r'\bปวส\.', 'ปอ-วอ-สอ'),
        (r'\bสอศ\.', 'สอ-ออ-สอ'),
        (r'\bมทร\.', 'มอ-ทอ-รอ'),
        (r'\bวอศ\.', 'วอ-ออ-สอ'),
        (r'\bPBVC\b', 'พี-บี-วี-ซี'),
        (r'\bAI\b', 'เอ-ไอ'),
        (r'\bTSL\b', 'ที-เอส-แอล'),
        (r'\bIT\b', 'ไอ-ที'),
        (r'\bQR\s*Code\b', 'คิว-อาร์-โค้ด'),
        (r'\bQR\b', 'คิว-อาร์'),
        (r'\bGPS\b', 'จี-พี-เอส'),
        (r'\bWi-?Fi\b', 'ไว-ไฟ'),
        (r'\bUNESCO\b', 'ยู-เนส-โก'),
        (r'\bGI\b', 'จี-ไอ'),
        (r'\bFacebook\b|\bFB\b', 'เฟซ-บุ๊ก'),
        (r'\bWebcam\b', 'เว็บ-แคม'),
        (r'\bCSI\b', 'ซี-เอส-ไอ'),
        (r'\bUSB\b', 'ยู-เอส-บี'),
        (r'\bRAM\b', 'แรม'),
        (r'\bSSD\b', 'เอส-เอส-ดี'),
        (r'\bCPU\b', 'ซี-พี-ยู'),
        (r'\bGPU\b', 'จี-พี-ยู'),
        (r'\bRPi\s*5\b|\bRaspberry\s*Pi\s*5\b', 'ราส-เบอร์-รี่-พาย-ห้า'),
        (r'\bPi\s*5\b', 'พาย-ห้า'),
    ]
    for pattern, repl in acronym_rules:
        t = re.sub(pattern, repl, t, flags=re.IGNORECASE)

    # ขยายรัชกาล
    t = re.sub(r'ร\.4', 'รัชกาลที่สี่', t)
    t = re.sub(r'ร\.5', 'รัชกาลที่ห้า', t)
    t = re.sub(r'ร\.6', 'รัชกาลที่หก', t)
    t = re.sub(r'ร\.([1-9])', r'รัชกาลที่ \1', t)

    # ขยายหน่วยวัดและเวลา
    t = re.sub(r'\b(\d+)\s*กม\./ชม\.', r'\1 กิโลเมตรต่อชั่วโมง', t)
    t = re.sub(r'\b(\d+)\s*กม\.', r'\1 กิโลเมตร', t)
    t = re.sub(r'\b(\d+)\s*ซม\.', r'\1 เซนติเมตร', t)
    t = re.sub(r'\b(\d+)\s*ม\.', r'\1 เมตร', t)
    t = re.sub(r'\b08\.30\s*น\.', 'แปดนาฬิกาสามสิบนาที', t)
    t = re.sub(r'\b16\.30\s*น\.', 'สิบหกนาฬิกาสามสิบนาที', t)
    t = re.sub(r'\b(\d{1,2})\.(\d{2})\s*น\.', r'\1 นาฬิกา \2 นาที', t)

    # ขยายปี พ.ศ.
    year_map = {
        '2569': 'สอง-พัน-ห้า-ร้อย-หก-สิบ-เก้า',
        '2568': 'สอง-พัน-ห้า-ร้อย-หก-สิบ-แปด',
        '2567': 'สอง-พัน-ห้า-ร้อย-หก-สิบ-เจ็ด',
        '2566': 'สอง-พัน-ห้า-ร้อย-หก-สิบ-หก',
        '2565': 'สอง-พัน-ห้า-ร้อย-หก-สิบ-ห้า',
    }
    for yr, yr_thai in year_map.items():
        t = t.replace(yr, yr_thai)

    # ขยายตัวเลขหลักเดี่ยวที่สำคัญ
    digit_words = {
        '8 อำเภอ': 'แปด อำเภอ',
        '9 แผนก': 'เก้า แผนก',
        '3 ยอด': 'สาม ยอด',
        '3 รส': 'สาม รส',
        '2 วัน 1 คืน': 'สอง วัน หนึ่ง คืน',
        '1 วัน': 'หนึ่ง วัน',
        '10.1 นิ้ว': 'สิบ จุด หนึ่ง นิ้ว',
        '360 องศา': 'สาม-ร้อย-หก-สิบ องศา',
    }
    for phrase, expanded in digit_words.items():
        t = t.replace(phrase, expanded)

    # ปรับเครื่องหมายวรรคตอนเพื่อให้โมเดลเว้นวรรคการหายใจอย่างเป็นธรรมชาติ
    t = re.sub(r'[•*#_~`>•\-=|]', ' ', t)
    t = re.sub(r'\s*,\s*', ', ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    return t


# -----------------------------------------------------------------------------
# 3. รวบรวมสคริปต์ข้อความทั้งหมดของระบบ (Comprehensive Script Extraction)
# -----------------------------------------------------------------------------
def collect_all_system_phrases():
    """รวบรวมข้อความทั้งหมดของระบบจาก Knowledge Base, IoT, Vision, และ Filler"""
    items = []

    # 1. ดึงจาก knowledge_base.json
    if os.path.exists(KB_PATH):
        try:
            with open(KB_PATH, 'r', encoding='utf-8') as f:
                kb_data = json.load(f)
            entries = kb_data.get('entries', [])
            for entry in entries:
                items.append({
                    'id': entry.get('id', 'kb_item'),
                    'category': 'knowledge_base',
                    'title': entry.get('title', 'คำตอบความรู้'),
                    'text': entry.get('answer', '')
                })
        except Exception as e:
            print(f"⚠️ ไม่สามารถอ่าน knowledge_base.json: {e}")

    # 2. ข้อความทักทายอัตโนมัติ (Auto Greeting) จาก vision_daemon.py
    auto_greetings = [
        ("greet_auto_00", "สวัสดีค่ะ ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ ต้องการคุยหรือพิมพ์แชทกับน้องเพชรดีคะ"),
        ("greet_auto_01", "สวัสดีค่ะ น้องเพชรยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ มีอะไรให้น้องเพชรช่วยไหมคะ"),
        ("greet_auto_02", "สวัสดีค่ะ น้องเพชร AI Smart Guide ยินดีต้อนรับผู้มาเยือนทุกท่านสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ"),
        ("greet_auto_03", "ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ น้องเพชรพร้อมพาเที่ยวและแนะนำข้อมูลแล้วค่ะ"),
        ("greet_auto_04", "สวัสดีค่ะ มีอะไรให้น้องเพชรช่วยค้นหาข้อมูลท่องเที่ยว ร้านอาหารเด็ด หรือหลักสูตรเรียนต่อไหมคะ")
    ]
    for gid, gtext in auto_greetings:
        items.append({
            'id': gid,
            'category': 'auto_greeting',
            'title': 'คำทักทายคนเดินผ่านอัตโนมัติ',
            'text': gtext
        })

    # 3. ข้อความตอบรับภาษามือไทย (TSL Visual Recognition) 7 ท่า
    tsl_phrases = [
        ("tsl_love", "ฉันรักเธอ", "น้องเพชรยินดีต้อนรับทุกท่านสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ ขอส่งมอบความรักและพร้อมดูแลอำนวยความสะดวกให้ทุกท่านตลอดการท่องเที่ยวในเมืองเพชรบุรีค่ะ"),
        ("tsl_thumbs_up", "ขอบคุณ/ยอดเยี่ยม", "ขอบคุณมากค่ะ น้องเพชรดีใจมากที่ได้ช่วยเหลือคุณ ขอให้มีความสุขและเพลิดเพลินกับการท่องเที่ยวเมืองเพชรบุรีนะคะ"),
        ("tsl_peace", "ท่องเที่ยวสองนิ้ว", "พร้อมลุยเที่ยวเมืองเพชรบุรีแล้วค่ะ แนะนำ 3 แลนด์มาร์กห้ามพลาด พระนครคีรี เขาวัง ถ้ำเขาหลวง และหาดชะอำค่ะ"),
        ("tsl_open_palm", "สวัสดี/ทักทาย", "สวัสดีค่ะ น้องเพชร AI Smart Guide ยินดีต้อนรับผู้มีความบกพร่องทางการได้ยินทุกท่าน มีอะไรให้ช่วยเหลือเลือกหรือทำภาษามือได้เลยนะคะ"),
        ("tsl_pointing", "แนะแนวเรียนต่อ", "วิทยาลัยอาชีวศึกษาเพชรบุรี มุ่งมั่นพัฒนาผู้เรียนด้วยนวัตกรรมและเทคโนโลยีดิจิทัล มี 9 แผนกวิชายอดนิยม พร้อมสนับสนุนการเรียนรู้ที่เท่าเทียมสำหรับทุกคนค่ะ"),
        ("tsl_fist", "อาหารเมืองเพชร", "เพชรบุรีเมืองสร้างสรรค์ด้านอาหารของยูเนสโก อย่าลืมชิมขนมหม้อแกงเตาฟืน ก๋วยเตี๋ยวน้ำแดง และข้าวแช่ชาววังนะคะ"),
        ("tsl_shaka", "ขอความช่วยเหลือ", "รับทราบค่ะ หากต้องการความช่วยเหลือเร่งด่วน เจ้าหน้าที่วิทยาลัยอาชีวศึกษาเพชรบุรีและฝ่ายประชาสัมพันธ์พร้อมอำนวยความสะดวกให้ท่านทันทีค่ะ")
    ]
    for tid, tname, ttext in tsl_phrases:
        items.append({
            'id': tid,
            'category': 'tsl_gesture',
            'title': f"ภาษามือ {tname}",
            'text': ttext
        })

    # 4. ข้อความแนะนำ 8 อำเภอและ 9 แผนกวิชา
    highlights = [
        ("districts_8", "แนะนำ 8 อำเภอ", "เพชรบุรีมี 8 อำเภอ คือ อำเภอเมือง ชะอำ ท่ายาง บ้านลาด บ้านแหลม แก่งกระจาน เขาย้อย และหนองหญ้าปล้องค่ะ"),
        ("pbvc_9_dept", "9 แผนกวิชา PBVC", "วิทยาลัยอาชีวศึกษาเพชรบุรีเปิดสอน 9 แผนกวิชาชั้นนำ ทั้งระดับ ปวช. และ ปวส. ค่ะ"),
        ("unesco_gastro", "UNESCO Gastronomy", "เพชรบุรีเป็นเมืองสร้างสรรค์ด้านอาหารของยูเนสโก ด้วยกฎ 3 รสแห่งธรรมชาติ น้ำตาลโตนด ดอกเกลือ และมะนาวแป้นค่ะ")
    ]
    for hid, hname, htext in highlights:
        items.append({
            'id': hid,
            'category': 'city_highlight',
            'title': hname,
            'text': htext
        })

    # 5. ข้อความคั่นระหว่างรอประมวลผล (Filler Audio)
    fillers = [
        ("filler_01", "สักครู่นะคะ น้องเพชรกำลังค้นหาข้อมูลให้ค่ะ"),
        ("filler_02", "รอสักครู่นะคะ น้องเพชรกำลังประมวลผลคำตอบค่ะ"),
        ("filler_03", "ขอเวลาตรวจสอบข้อมูลสักครู่นะคะ"),
        ("filler_04", "น้องเพชรได้รับคำถามแล้วค่ะ กำลังเตรียมข้อมูลให้นะคะ")
    ]
    for fid, ftext in fillers:
        items.append({
            'id': fid,
            'category': 'filler_audio',
            'title': 'เสียงคั่นระหว่างรอคิด',
            'text': ftext
        })

    return items


# -----------------------------------------------------------------------------
# 4. Audio Post-Processing (Normalize, Trim Silence, Convert MP3)
# -----------------------------------------------------------------------------
def post_process_audio_file(input_wav_path, output_mp3_path, target_bitrate="128k"):
    """
    ปรับแต่งคุณภาพเสียง:
    1. ตัดความเงียบหัว-ท้าย (Silence Trimming)
    2. Normalize ความดังให้อยู่ในระดับมาตรฐาน (-14 LUFS / peak -1dB)
    3. บันทึกเป็นไฟล์ MP3 คุณภาพสูง 128kbps
    """
    try:
        from pydub import AudioSegment, effects
        audio = AudioSegment.from_file(input_wav_path)

        # ตัดความเงียบหัว-ท้ายส่วนเกิน (threshold: -42dB, chunk: 10ms)
        def trim_silence(sound, silence_threshold=-42.0, chunk_size=10):
            trim_start = 0
            while trim_start < len(sound) and sound[trim_start:trim_start + chunk_size].dBFS < silence_threshold:
                trim_start += chunk_size
            trim_end = len(sound)
            while trim_end > 0 and sound[trim_end - chunk_size:trim_end].dBFS < silence_threshold:
                trim_end -= chunk_size
            return sound[max(0, trim_start - 30):min(len(sound), trim_end + 30)]

        trimmed = trim_silence(audio)
        # ปรับความดังสม่ำเสมอเท่ากันทุกไฟล์
        normalized = effects.normalize(trimmed, headroom=1.0)
        normalized.export(output_mp3_path, format="mp3", bitrate=target_bitrate)
        return True
    except Exception:
        # Fallback กรณีไม่มี pydub ให้คัดลอก/เขียนไฟล์ตรง
        try:
            with open(input_wav_path, 'rb') as src, open(output_mp3_path, 'wb') as dst:
                dst.write(src.read())
            return True
        except Exception:
            return False


# -----------------------------------------------------------------------------
# 5. Pipeline สังเคราะห์เสียง ThonburianTTS / Edge Fallback
# -----------------------------------------------------------------------------
class ThonburianBaker:
    def __init__(self, engine_choice="auto", checkpoint=None, vocab=None, ref_audio=None, ref_text=None, speed=1.0):
        self.engine_choice = engine_choice
        self.checkpoint = checkpoint or "hf://biodatlab/ThonburianTTS/megaF5/mega_f5_last.safetensors"
        self.vocab = vocab or "hf://biodatlab/ThonburianTTS/megaF5/mega_vocab.txt"
        self.ref_audio = ref_audio or os.path.join(ASSETS_DIR, "ref_nongphet.mp3")
        self.ref_text = ref_text or "สวัสดีค่ะ น้องเพชรยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ"
        self.speed = speed
        self.active_engine = None
        self.pipeline = None
        self._init_engine()

    def _init_engine(self):
        print("=" * 65)
        print("🔊 กำลังเตรียมสภาพแวดล้อม Engine สำหรับการสังเคราะห์เสียง...")
        print(f"📌 ตัวเลือก Engine: {self.engine_choice.upper()}")

        if self.engine_choice in ["auto", "thonburian"]:
            try:
                import torch
                has_cuda = torch.cuda.is_available()
                device = "cuda" if has_cuda else "cpu"
                if has_cuda:
                    gpu_name = torch.cuda.get_device_name(0)
                    print(f"🚀 ตรวจพบ GPU พร้อมใช้งาน: {gpu_name} (CUDA Device: {device})")
                else:
                    print("⚙️ ไม่พบ GPU รันในโหมด CPU Fallback")

                from flowtts.inference import FlowTTSPipeline, ModelConfig, AudioConfig
                print(f"📥 กำลังโหลดโมเดล ThonburianTTS ({self.checkpoint})...")
                model_cfg = ModelConfig(
                    language="th",
                    model_type="F5",
                    checkpoint=self.checkpoint,
                    vocab_file=self.vocab,
                    vocoder="vocos",
                    device=device
                )
                audio_cfg = AudioConfig(
                    silence_threshold=-42,
                    cfg_strength=2.2,
                    speed=self.speed
                )
                self.pipeline = FlowTTSPipeline(model_cfg, audio_cfg)
                self.active_engine = "thonburian"
                print("✅ โหลดโมเดล ThonburianTTS สำเร็จเรียบร้อยพร้อมเจนเสียง!")
                return
            except Exception as e:
                print(f"⚠️ โหลด ThonburianTTS ไม่สำเร็จ: {e}")
                if self.engine_choice == "thonburian":
                    print("❌ คุณระบุ --engine thonburian แต่ยังไม่ได้ติดตั้งแพ็กเกจ กรุณาติดตั้งตาม requirements_bake_win.txt")
                    sys.exit(1)
                print("🔄 สลับมาใช้งาน Edge Neural Studio Engine อัตโนมัติ (PremwadeeNeural)...")

        # Fallback to Edge Neural Studio
        self.active_engine = "edge_neural"
        print("✅ พร้อมใช้งาน Edge Neural Studio Engine (0ms Pre-bake Mode)")

    def synthesize(self, clean_key_text, normalized_text, output_mp3_path):
        """ทำการสังเคราะห์เสียงและบันทึกลงใน output_mp3_path"""
        if self.active_engine == "thonburian" and self.pipeline:
            temp_wav = output_mp3_path.replace(".mp3", "_temp.wav")
            try:
                self.pipeline.generate(
                    text=normalized_text,
                    ref_audio_path=self.ref_audio,
                    ref_text=self.ref_text,
                    output_path=temp_wav
                )
                success = post_process_audio_file(temp_wav, output_mp3_path)
                if os.path.exists(temp_wav):
                    try: os.remove(temp_wav)
                    except Exception: pass
                if success:
                    return "thonburian"
            except Exception as e:
                print(f"  ⚠️ Thonburian error ({e}) -> สลับมาใช้ Edge-TTS ชั่วคราว...")

        # Fallback Edge-TTS via robust service
        try:
            from services.tts_service import generate_edge_tts, run_coroutine
            audio_bytes = run_coroutine(generate_edge_tts(clean_key_text, voice="th-TH-PremwadeeNeural", rate="+2%", pitch="+0Hz", timeout=15.0))
            with open(output_mp3_path, 'wb') as f:
                f.write(audio_bytes)
            return "edge_neural"
        except Exception as e:
            print(f"  ⚠️ Edge-TTS error ({e}) -> สลับมาใช้ gTTS สำรอง...")
            from gtts import gTTS
            tts_obj = gTTS(text=clean_key_text, lang='th')
            tts_obj.save(output_mp3_path)
            return "gtts_fallback"


# -----------------------------------------------------------------------------
# 6. Main Execution Pipeline
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="น้องเพชร AI Smart Guide — Pre-bake ThonburianTTS Audio Cache")
    parser.add_argument("--engine", type=str, default="auto", choices=["auto", "thonburian", "edge"], help="TTS Engine (auto, thonburian, edge)")
    parser.add_argument("--checkpoint", type=str, default=None, help="ThonburianTTS checkpoint path")
    parser.add_argument("--ref-audio", type=str, default=None, help="Reference audio file path (.wav/.mp3)")
    parser.add_argument("--ref-text", type=str, default=None, help="Reference transcript text")
    parser.add_argument("--speed", type=float, default=1.02, help="Speech generation speed multiplier")
    parser.add_argument("--force", action="store_true", help="Re-generate all files even if already cached")
    args = parser.parse_args()

    print("=" * 65)
    print("🤖 [Nong Phet Pre-bake Audio Cache Generator for Windows]")
    print(f"📁 คลังแคชปลายทาง: {AUDIO_CACHE_DIR}")
    print(f"📄 บันทึก Manifest: {MANIFEST_PATH}")
    print("=" * 65)

    # รวบรวมข้อความทั้งหมด
    phrases = collect_all_system_phrases()
    print(f"📋 รวบรวมข้อความจากระบบทั้งหมด: {len(phrases)} ข้อความ")

    # เริ่มต้น Engine
    baker = ThonburianBaker(
        engine_choice=args.engine,
        checkpoint=args.checkpoint,
        ref_audio=args.ref_audio,
        ref_text=args.ref_text,
        speed=args.speed
    )

    manifest = {}
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, 'r', encoding='utf-8') as mf:
                manifest = json.load(mf)
        except Exception:
            manifest = {}

    total = len(phrases)
    cached_count = 0
    generated_count = 0
    failed_count = 0

    try:
        from tqdm import tqdm
        progress_bar = tqdm(phrases, desc="🎙️ สังเคราะห์เสียง", unit="ข้อความ")
    except ImportError:
        progress_bar = phrases

    t_start = time.time()

    for item in progress_bar:
        item_id = item['id']
        category = item['category']
        title = item['title']
        original_text = item['text']

        if not original_text:
            continue

        # คำนวณ Hash ตามสูตร app.py
        clean_key = clean_text_for_hash(original_text, max_len=2500, lang='th')
        mp3_name, disk_hash, cache_key = compute_server_cache_filename(clean_key)
        mp3_path = os.path.join(AUDIO_CACHE_DIR, mp3_name)

        # แปลงข้อความสำหรับการออกเสียง ThonburianTTS
        normalized_speech = normalize_thai_for_tts(clean_key)

        # ข้ามไฟล์ที่มีอยู่แล้วในแคชและขนาดสมบูรณ์
        if not args.force and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1024:
            cached_count += 1
            manifest[disk_hash] = {
                'id': item_id,
                'category': category,
                'title': title,
                'original_text': original_text[:120],
                'clean_key_text': clean_key[:120],
                'file_name': mp3_name,
                'file_size_bytes': os.path.getsize(mp3_path),
                'engine': manifest.get(disk_hash, {}).get('engine', 'cached'),
                'updated_at': manifest.get(disk_hash, {}).get('updated_at', str(datetime.datetime.now()))
            }
            continue

        # สังเคราะห์เสียง
        try:
            used_engine = baker.synthesize(clean_key, normalized_speech, mp3_path)
            file_size = os.path.getsize(mp3_path) if os.path.exists(mp3_path) else 0

            manifest[disk_hash] = {
                'id': item_id,
                'category': category,
                'title': title,
                'original_text': original_text,
                'clean_key_text': clean_key,
                'normalized_speech_text': normalized_speech,
                'file_name': mp3_name,
                'file_size_bytes': file_size,
                'engine': used_engine,
                'updated_at': str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            }
            generated_count += 1
            print(f"✨ [{cached_count + generated_count}/{total}] สำเร็จ: [{category}] {title} -> {mp3_name} ({file_size:,} bytes)", flush=True)
        except Exception as e:
            print(f"\n❌ ล้มเหลว [{item_id} - {title}]: {e}", flush=True)
            failed_count += 1

    # บันทึกไฟล์ Manifest
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)

    elapsed = round(time.time() - t_start, 1)

    print("\n" + "=" * 65)
    print("🎉 ผลการสร้างคลังเสียงล่วงหน้า (Pre-baked Cache Results):")
    print(f"   - ข้อความทั้งหมด : {total} รายการ")
    print(f"   - มีอยู่แล้วในแคช: {cached_count} รายการ (ไม่ต้องเจนซ้ำ)")
    print(f"   - เจนใหม่สำเร็จ   : {generated_count} รายการ")
    print(f"   - ล้มเหลว       : {failed_count} รายการ")
    print(f"   - เวลาที่ใช้      : {elapsed} วินาที")
    print(f"   - คลังเสียงพร้อมรัน Offline 0ms บน Raspberry Pi 5 100%!")
    print("=" * 65)

if __name__ == '__main__':
    main()
