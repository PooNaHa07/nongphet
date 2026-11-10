#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-baked Audio Caching Script for น้องเพชร AI Smart Guide
สร้างไฟล์เสียงล่วงหน้า (Pre-generate) สำหรับคำตอบยอดนิยม 3 ภาษา (ไทย, อังกฤษ, จีน)
เพื่อการตอบสนองที่รวดเร็วระดับ 0ms (Zero Latency Instant Cache Hit)
"""
import sys
import os
import asyncio
import hashlib

# เพิ่ม path ให้ import โมดูลจากโปรเจกต์ได้
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (
    clean_text_for_speech,
    generate_edge_tts,
    save_cached_tts,
    AUDIO_CACHE_DIR
)

PREBAKE_PHRASES = [
    # -------------------------------------------------------------------------
    # 1. ภาษาไทย (th-TH-PremwadeeNeural)
    # -------------------------------------------------------------------------
    {
        'lang': 'th',
        'voice': 'th-TH-PremwadeeNeural',
        'rate': '+2%',
        'pitch': '+0Hz',
        'texts': [
            "สวัสดีค่ะ น้องเพชรยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ มีอะไรให้น้องเพชรช่วยแนะนำไหมคะ",
            "ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ น้องเพชรพร้อมพาเที่ยวและแนะนำข้อมูลแล้วค่ะ",
            "ว่ายังไงคะ น้องเพชรพร้อมช่วยเหลือค่ะ",
            "ได้ยินแล้วค่ะ สอบถามน้องเพชรได้เลยนะคะ",
            "เพชรบุรีมี 8 อำเภอ คือ อำเภอเมือง ชะอำ ท่ายาง บ้านลาด บ้านแหลม แก่งกระจาน เขาย้อย และหนองหญ้าปล้องค่ะ",
            "วิทยาลัยอาชีวศึกษาเพชรบุรีเปิดสอน 9 แผนกวิชาชั้นนำ ทั้งระดับ ปวช. และ ปวส. ค่ะ",
            "เพชรบุรีเป็นเมืองสร้างสรรค์ด้านอาหารของยูเนสโก ด้วยกฎ 3 รสแห่งธรรมชาติ น้ำตาลโตนด ดอกเกลือ และมะนาวแป้นค่ะ",
            "หากต้องการสอบถามเพิ่มเติม เรียกหาน้องเพชรได้เสมอนะคะ",
            "ขอบคุณที่แวะมาคุยกับน้องเพชรนะคะ ขอให้มีความสุขกับการท่องเที่ยวเพชรบุรีค่ะ",
            "น้องเพชรพร้อมช่วยค้นหาข้อมูลท่องเที่ยว ร้านอาหารเด็ด และหลักสูตรการเรียนแล้วค่ะ",
            "ยินดีต้อนรับค่ะ สอบถามข้อมูลท่องเที่ยว อาหาร หรือการเรียนในวิทยาลัยได้เลยนะคะ",
            "ได้เลยค่ะ น้องเพชรขอแนะนำดังนี้นะคะ",
            "ขออภัยค่ะ ขณะนี้น้องเพชรยังไม่สามารถเชื่อมต่ออินเทอร์เน็ตได้ แต่ยังสามารถตอบคำถามท้องถิ่นได้อยู่นะคะ"
        ]
    },
    # -------------------------------------------------------------------------
    # 2. ภาษาอังกฤษ (en-US-AriaNeural)
    # -------------------------------------------------------------------------
    {
        'lang': 'en',
        'voice': 'en-US-AriaNeural',
        'rate': '+3%',
        'pitch': '+0Hz',
        'texts': [
            "Hello! Welcome to Phetchaburi Vocational College. How can I help you today?",
            "Welcome to Phetchaburi! I am Nong Phet, your smart AI guide.",
            "I'm listening! How can I assist you?",
            "Phetchaburi has 8 wonderful districts with beaches, mountains, and cultural heritage.",
            "Phetchaburi is a UNESCO Creative City of Gastronomy with exquisite traditional cuisines.",
            "Feel free to ask me anything about travel attractions or our college courses!",
            "Have a wonderful day exploring Phetchaburi!",
            "Here is the travel recommendation for you!"
        ]
    },
    # -------------------------------------------------------------------------
    # 3. ภาษาจีน (zh-CN-XiaoxiaoNeural)
    # -------------------------------------------------------------------------
    {
        'lang': 'zh',
        'voice': 'zh-CN-XiaoxiaoNeural',
        'rate': '+3%',
        'pitch': '+0Hz',
        'texts': [
            "您好！欢迎来到佛丕职业学院，我是小佩特，很高兴为您服务！",
            "我在呢！请问有什么可以帮您？",
            "佛丕府拥有8个充满魅力的县区，包括七岩海滩和国家公园。",
            "佛丕府是联合国教科文组织评选的美食之都，拥有独特的甜咸酸三种风味。",
            "随时欢迎向我咨询景点、美食和学院专业信息！",
            "祝您在佛丕府度过愉快的时光！",
            "好的，小佩特为您推荐以下内容！"
        ]
    }
]

async def prebake_all():
    print("=" * 65)
    print("🚀 [Pre-bake Audio] เริ่มต้นสร้างไฟล์เสียงล่วงหน้า (0ms Instant Cache)")
    print(f"📁 โฟลเดอร์ปลายทาง: {AUDIO_CACHE_DIR}")
    print("=" * 65)

    total = 0
    success = 0
    already_cached = 0

    for group in PREBAKE_PHRASES:
        lang = group['lang']
        voice = group['voice']
        rate = group['rate']
        pitch = group['pitch']
        print(f"\n🌐 กำลังประมวลผลกลุ่มภาษา: {lang.upper()} (Voice: {voice})")

        for text in group['texts']:
            total += 1
            clean_text = clean_text_for_speech(text, max_len=350, voice_gender='female', lang=lang)
            cache_key = f"{voice}_{pitch}_{rate}_{clean_text}"
            disk_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
            disk_path = os.path.join(AUDIO_CACHE_DIR, f"{disk_hash}.mp3")

            if os.path.exists(disk_path) and os.path.getsize(disk_path) > 0:
                print(f"  ⚡ [มีอยู่แล้วใน Cache] {text[:35]}...")
                already_cached += 1
                success += 1
                continue

            try:
                print(f"  🎙️ [กำลังสร้างเสียง] {text[:35]}...", end=" ", flush=True)
                audio_bytes = await generate_edge_tts(clean_text, voice=voice, rate=rate, pitch=pitch, timeout=12.0)
                if audio_bytes and len(audio_bytes) > 0:
                    save_cached_tts(cache_key, audio_bytes)
                    print(f"✅ สำเร็จ ({len(audio_bytes) // 1024} KB)")
                    success += 1
                else:
                    print("❌ ล้มเหลว (ข้อมูลว่างเปล่า)")
            except Exception as e:
                print(f"❌ Error: {e}")

    print("\n" + "=" * 65)
    print(f"🎉 สรุปผลการ Pre-bake Audio:")
    print(f"   - ทั้งหมด: {total} ข้อความ")
    print(f"   - สำเร็จ: {success} ข้อความ (แคชเดิม: {already_cached}, สร้างใหม่: {success - already_cached})")
    print(f"   - ประสิทธิภาพเสียงตอนนี้: 0ms Instant Response สำหรับคำถามยอดนิยม!")
    print("=" * 65)

if __name__ == '__main__':
    asyncio.run(prebake_all())
