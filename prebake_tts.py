#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
อัดเสียงน้องเพชรเก็บไว้ล่วงหน้า (Pre-bake) ด้วย "เสียงเดียวทั้งระบบ" ตาม config.Config
เพื่อให้คำตอบที่ใช้บ่อยเล่นได้ทันที และยังมีเสียงแม้ไม่มีอินเทอร์เน็ต

สิ่งที่อัดเก็บ:
  - คำตอบทุกหัวข้อในฐานความรู้ (knowledge_base.json)
  - คำทักทาย คำคั่นเวลา และประโยคที่ระบบพูดบ่อย
  - ประโยคภาษาอังกฤษ/จีนพื้นฐาน

วิธีใช้ (ต้องต่ออินเทอร์เน็ต):
  python prebake_tts.py            อัดเฉพาะประโยคที่ยังไม่มีเสียง
  python prebake_tts.py --audit    ตรวจว่ามีไฟล์เสียงคนอื่นปนอยู่ในแคชหรือไม่
  python prebake_tts.py --clean    ลบไฟล์เสียงที่ไม่ใช่เสียงน้องเพชรออกจากแคช

ต้องรันใหม่ทุกครั้งที่: เปลี่ยนเสียง/โทนใน config.py หรือแก้คำตอบในฐานความรู้
(ประโยคที่ยังไม่ได้อัด ระบบจะสร้างและเก็บให้เองตอนพูดครั้งแรกขณะมีเน็ต)
"""
import os
import sys
import json
import asyncio
import argparse
import hashlib

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from services import tts_service  # noqa: E402
from services.azure_speech import azure_enabled  # noqa: E402
from services.voice_server_client import omnivoice_enabled  # noqa: E402
from services.tts_service import NO_VOICE_PHRASES  # noqa: E402
from services.tts_service import (  # noqa: E402
    clean_text_for_speech, generate_speech, save_cached_tts, voice_profile,
    speech_cache_key, audit_audio_cache, is_canonical_voice_audio, prepare_speech_input,
    AUDIO_CACHE_DIR, EdgeTTSOffline, _mark_edge_ok,
)

KNOWLEDGE_BASE_FILE = os.path.join(BASE_DIR, 'knowledge_base.json')

# ประโยคที่ระบบพูดบ่อย (นอกเหนือจากคำตอบในฐานความรู้)
THAI_PHRASES = [
    # คำคั่นเวลา
    "ได้เลยค่าา แป๊บนึงน้าา",
    "อื้อหืออ เรื่องนี้นะคะ สักครู่น้าา",
    "อ๋ออ ได้เลยค่ะ เดี๋ยวค้นให้นะคะ",
    "รับทราบเลยค่าา รอแป๊บนึงน้าา",
    "สักครู่นะคะ น้องเพชรเตรียมข้อมูลให้เดี๋ยวนี้เลยค่าา",
    "สักครู่นะคะ น้องเพชรกำลังค้นหาข้อมูลให้ค่ะ",
    "รอสักครู่นะคะ น้องเพชรกำลังประมวลผลคำตอบค่ะ",
    "ขอเวลาตรวจสอบข้อมูลสักครู่นะคะ",
    "น้องเพชรได้รับคำถามแล้วค่ะ กำลังเตรียมข้อมูลให้นะคะ",
    # คำทักทายและแนะนำตัว (รวมประโยคทักทายอัตโนมัติเมื่อมีคนเข้าใกล้)
    "สวัสดีค่ะ ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ ต้องการคุยหรือพิมพ์แชทกับน้องเพชรดีคะ",
    "สวัสดีค่ะ น้องเพชรยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ มีอะไรให้น้องเพชรช่วยแนะนำไหมคะ",
    "ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ น้องเพชรพร้อมพาเที่ยวและแนะนำข้อมูลแล้วค่ะ",
    "ว่ายังไงคะ น้องเพชรพร้อมช่วยเหลือค่ะ",
    "ได้ยินแล้วค่ะ สอบถามน้องเพชรได้เลยนะคะ",
    "น้องเพชรพร้อมฟังคำถามจากคุณแล้วค่ะ สอบถามได้เลยนะคะ",
    "สวัสดีค่ะ มีอะไรให้น้องเพชรช่วยไหมคะ",
    "เพชรบุรีมี 8 อำเภอ คือ อำเภอเมือง ชะอำ ท่ายาง บ้านลาด บ้านแหลม แก่งกระจาน เขาย้อย และหนองหญ้าปล้องค่ะ",
    "วิทยาลัยอาชีวศึกษาเพชรบุรีเปิดสอน 11 สาขาวิชา ทั้งระดับ ปวช. ปวส. และปริญญาตรีสายเทคโนโลยีในบางสาขาค่ะ",
    "เพชรบุรีเป็นเมืองสร้างสรรค์ด้านอาหารของยูเนสโก ด้วยกฎ 3 รสแห่งธรรมชาติ น้ำตาลโตนด ดอกเกลือ และมะนาวแป้นค่ะ",
    "หากต้องการสอบถามเพิ่มเติม เรียกหาน้องเพชรได้เสมอนะคะ",
    "ขอบคุณที่แวะมาคุยกับน้องเพชรนะคะ ขอให้มีความสุขกับการท่องเที่ยวเพชรบุรีค่ะ",
    "น้องเพชรพร้อมช่วยค้นหาข้อมูลท่องเที่ยว ร้านอาหารเด็ด และหลักสูตรการเรียนแล้วค่ะ",
    "ยินดีต้อนรับค่ะ สอบถามข้อมูลท่องเที่ยว อาหาร หรือการเรียนในวิทยาลัยได้เลยนะคะ",
    "ได้เลยค่ะ น้องเพชรขอแนะนำดังนี้นะคะ",
]

ENGLISH_PHRASES = [
    "Hello! Welcome to Phetchaburi Vocational College. How can I help you today?",
    "Welcome to Phetchaburi! I am Nong Phet, your smart AI guide.",
    "I'm listening! How can I assist you?",
    "Phetchaburi has 8 wonderful districts with beaches, mountains, and cultural heritage.",
    "Phetchaburi is a UNESCO Creative City of Gastronomy with exquisite traditional cuisines.",
    "Feel free to ask me anything about travel attractions or our college courses!",
    "Have a wonderful day exploring Phetchaburi!",
    "Here is the travel recommendation for you!",
]

CHINESE_PHRASES = [
    "您好！欢迎来到佛丕职业学院，我是小佩特，很高兴为您服务！",
    "我在呢！请问有什么可以帮您？",
    "佛丕府拥有8个充满魅力的县区，包括七岩海滩和国家公园。",
    "佛丕府是联合国教科文组织评选的美食之都，拥有独特的甜咸酸三种风味。",
    "随时欢迎向我咨询景点、美食和学院专业信息！",
    "祝您在佛丕府度过愉快的时光！",
    "好的，小佩特为您推荐以下内容！",
]

def collect_items():
    """คืนรายการ (lang, label, text)"""
    items = []
    try:
        with open(KNOWLEDGE_BASE_FILE, encoding='utf-8') as f:
            kb = json.load(f)
        for entry in kb.get('entries', []):
            if entry.get('answer'):
                items.append(('th', f"KB:{entry.get('id')}", entry['answer']))
    except Exception as e:
        print(f"⚠️ อ่านฐานความรู้ไม่ได้: {e}")
    items += [('th', 'phrase', t) for t in THAI_PHRASES]
    items += [('en', 'phrase', t) for t in ENGLISH_PHRASES]
    items += [('zh', 'phrase', t) for t in CHINESE_PHRASES]
    # ประโยคกลาง: พูดแทนเมื่อคำตอบใดยังไม่มีเสียง (ต้องมีเสียงเสมอ)
    items = [(lang, 'no-voice', t) for lang, t in NO_VOICE_PHRASES.items()] + items
    return items


def cache_path_for(cache_key):
    return os.path.join(AUDIO_CACHE_DIR, hashlib.md5(cache_key.encode('utf-8')).hexdigest() + '.mp3')


def plan_item(lang, text):
    """คำนวณ (ข้อความที่จะส่งให้ TTS, คีย์แคช, voice, pitch, rate) ให้ตรงกับเส้นทาง /tts"""
    voice, pitch, rate = voice_profile(lang)
    clean = clean_text_for_speech(prepare_speech_input(text), max_len=2500, voice_gender='female', lang=lang)
    return clean, speech_cache_key(clean, voice, pitch, rate), voice, pitch, rate


def has_canonical_file(cache_key):
    path = cache_path_for(cache_key)
    if not os.path.exists(path):
        return False
    with open(path, 'rb') as f:
        return is_canonical_voice_audio(f.read(65536))


# อัดเสียงทีละประโยคแบบเว้นจังหวะ: บริการเสียงของ Microsoft จำกัดความถี่ ถ้ายิงถี่จะค้างหรือตอบ "No audio"
PAUSE_BETWEEN_ITEMS = 1.5
# Azure แพ็กเกจฟรีจำกัดจำนวนคำขอต่อนาที จึงเว้นจังหวะมากขึ้นเมื่อใช้ Azure
PAUSE_BETWEEN_ITEMS_AZURE = 3.5
PASSES = 3
PAUSE_BETWEEN_PASSES = 15


async def bake_one(clean, cache_key, voice, pitch, rate, attempts=2):
    last = None
    for attempt in range(attempts):
        _mark_edge_ok()  # สคริปต์นี้ตั้งใจลองซ้ำเอง ไม่ใช้ตัวพักการเชื่อมต่อของเซิร์ฟเวอร์
        try:
            audio = await generate_speech(clean, voice=voice, rate=rate, pitch=pitch, timeout=30.0, retries=1)
            if audio:
                save_cached_tts(cache_key, audio)
                return len(audio)
        except (EdgeTTSOffline, RuntimeError) as e:
            last = e
        await asyncio.sleep(3 * (attempt + 1))
    raise RuntimeError(last or 'no audio')


async def prebake_all(force=False):
    # สคริปต์อัดเสียงรอเสียงท่อนแรกได้นานกว่าตอนใช้งานจริง (ไม่มีคนยืนรอ)
    tts_service.FIRST_AUDIO_TIMEOUT = 25.0
    voice, pitch, rate = voice_profile('th')
    print("=" * 65)
    print("🎙️  อัดเสียงน้องเพชรล่วงหน้า (เสียงเดียวทั้งระบบ)")
    print(f"   เสียงภาษาไทย: {voice}  Pitch {pitch}  Rate {rate}")
    engine = ('เซิร์ฟเวอร์เสียง OmniVoice ในบูธ' if omnivoice_enabled() else
              'Azure Speech (ทางการ) + Edge-TTS สำรอง' if azure_enabled() else 'Edge-TTS (ยังไม่ได้ตั้งค่า Azure)')
    print(f"   บริการหลัก: {engine}")
    print(f"   โฟลเดอร์: {AUDIO_CACHE_DIR}")
    print("=" * 65)

    items = collect_items()
    pending = []
    skipped = 0
    for lang, label, text in items:
        clean, key, v, p, r = plan_item(lang, text)
        if not clean:
            continue
        if force and os.path.exists(cache_path_for(key)):
            os.remove(cache_path_for(key))
        elif has_canonical_file(key):
            skipped += 1
            continue
        pending.append((lang, label, clean, key, v, p, r))

    done = 0
    for n in range(1, PASSES + 1):
        if not pending:
            break
        if n > 1:
            print(f"\n🔁 รอบที่ {n}: ลองใหม่ {len(pending)} ประโยคที่ยังไม่สำเร็จ (รอ {PAUSE_BETWEEN_PASSES} วินาที)...")
            await asyncio.sleep(PAUSE_BETWEEN_PASSES)
        failed_this_pass = []
        for item in pending:
            lang, label, clean, key, v, p, r = item
            print(f"  🎙️ [{lang}] {label}: {clean[:40]}...", end=" ", flush=True)
            try:
                size = await bake_one(clean, key, v, p, r)
                print(f"✅ ({size // 1024} KB)")
                done += 1
            except Exception as e:
                print(f"❌ {str(e)[:60]}")
                failed_this_pass.append(item)
            # เซิร์ฟเวอร์เสียงในบูธไม่จำกัดความถี่ จึงไม่ต้องเว้นจังหวะ
            await asyncio.sleep(0.05 if omnivoice_enabled() else
                                PAUSE_BETWEEN_ITEMS_AZURE if azure_enabled() else PAUSE_BETWEEN_ITEMS)
        pending = failed_this_pass

    print("\n" + "=" * 65)
    print(f"สรุป: ทั้งหมด {len(items)} | อัดใหม่ {done} | มีอยู่แล้ว {skipped} | ไม่สำเร็จ {len(pending)}")
    for _, label, clean, *_ in pending:
        print(f"   ยังไม่มีเสียง: {label} {clean[:40]}...")
    if pending:
        print("ให้รันสคริปต์ซ้ำอีกครั้งภายหลัง (จะอัดเฉพาะที่ยังขาด)")
    print("=" * 65)
    return len(pending)


def main():
    parser = argparse.ArgumentParser(description="อัดเสียงน้องเพชรล่วงหน้า (เสียงเดียวทั้งระบบ)")
    parser.add_argument('--audit', action='store_true', help='ตรวจหาไฟล์เสียงที่ไม่ใช่เสียงน้องเพชรในแคช')
    parser.add_argument('--clean', action='store_true', help='ลบไฟล์เสียงที่ไม่ใช่เสียงน้องเพชรออกจากแคช')
    parser.add_argument('--force', action='store_true', help='อัดใหม่ทั้งหมด แม้มีไฟล์อยู่แล้ว')
    args = parser.parse_args()

    if args.audit or args.clean:
        bad = audit_audio_cache(delete=args.clean)
        if not bad:
            print("✅ ไฟล์เสียงในแคชเป็นรูปแบบเสียงน้องเพชรทั้งหมด")
        for name, fmt in bad:
            print(f"{'🗑️ ลบแล้ว' if args.clean else '⚠️ ไม่ใช่เสียงน้องเพชร'}: {name} {fmt}")
        return

    failed = asyncio.run(prebake_all(force=args.force))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
