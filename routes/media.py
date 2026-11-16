# -*- coding: utf-8 -*-
"""
routes/media.py — Text-to-Speech (TTS), Live Multimodal WebSocket & Weather Blueprint
"""
import io
import os
import base64
import datetime
import logging
from flask import Blueprint, request, jsonify, Response, render_template
from gtts import gTTS

from config import Config
from services.tts_service import (
    get_pythaitts_engine, get_cached_tts, save_cached_tts,
    extract_first_sentence_for_speech, clean_text_for_speech,
    generate_edge_tts, run_coroutine, iter_audio_stream
)

logger = logging.getLogger("nongphet.media")

media_bp = Blueprint('media', __name__)

FILLER_PHRASES = [
    "ได้เลยค่าา แป๊บนึงน้าา",
    "อื้อหืออ เรื่องนี้นะคะ สักครู่น้าา",
    "อ๋ออ ได้เลยค่ะ เดี๋ยวค้นให้นะคะ",
    "รับทราบเลยค่าา รอแป๊บนึงน้าา",
    "สักครู่นะคะ น้องเพชรเตรียมข้อมูลให้เดี๋ยวนี้เลยค่าา"
]

@media_bp.route('/tts', methods=['POST'])
def tts():
    data = request.json or {}
    text = data.get('text', '').strip()
    lang = data.get('lang', data.get('language', 'th'))
    fast_mode = data.get('fast_mode', False) and data.get('first_sentence', False)
    
    if not text:
        return jsonify({'error': 'Text is empty'}), 400

    if fast_mode:
        target_text = extract_first_sentence_for_speech(text, lang=lang, max_len=500)
    else:
        target_text = text

    clean_text = clean_text_for_speech(target_text, max_len=2500, voice_gender='female', lang=lang)

    # กำหนดพารามิเตอร์เสียงมาตรฐานประจำตัวน้องเพชร (Canonical Voice)
    volume = data.get('volume', '+0%')
    if lang == 'en':
        voice = 'en-US-AriaNeural'
        rate = '+3%'
        pitch = '+0Hz'
    elif lang == 'zh':
        voice = 'zh-CN-XiaoxiaoNeural'
        rate = '+3%'
        pitch = '+0Hz'
    else:
        # ภาษาไทย: บังคับใช้เสียงผู้หญิง th-TH-PremwadeeNeural เท่านั้น (ปิดเสียงผู้ชาย)
        voice = 'th-TH-PremwadeeNeural'
        pitch = data.get('pitch', '+0Hz')
        rate = data.get('rate', '+2%')

    cache_key = f"{voice}_{pitch}_{rate}_{clean_text}"

    # -------------------------------------------------------------------------
    # ลำดับที่ 1: ตรวจสอบ Pre-baked Audio Cache จาก RAM หรือ Disk เสมอ (0ms Standalone)
    # -------------------------------------------------------------------------
    cached_b64, cache_type = get_cached_tts(cache_key)
    if cached_b64:
        return jsonify({
            'audio_base64': cached_b64,
            'audio_format': 'mp3',
            'engine': f'cache-{cache_type}',
            'voice': voice,
            'rate': rate,
            'pitch': pitch,
            'latency_ms': 0,
            'status': 'success'
        })

    # -------------------------------------------------------------------------
    # ลำดับที่ 2: Edge Neural TTS (พร้อม Fast-Fail Auto-Reconnect และ Timeout 6.0s)
    # -------------------------------------------------------------------------
    try:
        audio_bytes = run_coroutine(generate_edge_tts(clean_text, voice=voice, rate=rate, pitch=pitch, volume=volume, timeout=6.0), timeout=12.0)
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        save_cached_tts(cache_key, audio_bytes, audio_base64)
        return jsonify({
            'audio_base64': audio_base64,
            'audio_format': 'mp3',
            'engine': 'edge-neural',
            'voice': voice,
            'rate': rate,
            'pitch': pitch,
            'status': 'success'
        })
    except Exception as e:
        logger.warning(f"Edge-TTS failed/timeout ({e}) -> ตกชั้นมาใช้ On-Device Fallback Engine...")

    # -------------------------------------------------------------------------
    # ลำดับที่ 3: สลับมา On-Device PyThaiTTS (fastthaig2p) ออฟไลน์ทันทีบน Raspberry Pi 5
    # -------------------------------------------------------------------------
    if lang == 'th':
        try:
            pytts = get_pythaitts_engine()
            if pytts:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_f:
                    tmp_wav_path = tmp_f.name
                try:
                    pytts.tts(clean_text, filename=tmp_wav_path)
                    with open(tmp_wav_path, 'rb') as f:
                        wav_bytes = f.read()
                    audio_base64 = base64.b64encode(wav_bytes).decode('utf-8')
                    save_cached_tts(cache_key, wav_bytes, audio_base64)
                    return jsonify({
                        'audio_base64': audio_base64,
                        'audio_format': 'wav',
                        'engine': 'pythaitts-fallback',
                        'voice': 'fastthaig2p',
                        'status': 'success'
                    })
                finally:
                    if os.path.exists(tmp_wav_path):
                        try:
                            os.remove(tmp_wav_path)
                        except Exception:
                            pass
        except Exception as pe:
            logger.warning(f"PyThaiTTS Error ({pe}) -> falling back to gTTS")

    # -------------------------------------------------------------------------
    # ลำดับที่ 4: สำรองขั้นสุดท้ายด้วย gTTS (ไม่บันทึกลงแคช เพื่อรักษาความถูกต้องของเสียงเปรมวดี)
    # -------------------------------------------------------------------------
    try:
        tts_obj = gTTS(text=clean_text, lang=lang if lang in ['th', 'en', 'zh'] else 'th')
        fp = io.BytesIO()
        tts_obj.write_to_fp(fp)
        raw_bytes = fp.getvalue()
        audio_base64 = base64.b64encode(raw_bytes).decode('utf-8')
        return jsonify({
            'audio_base64': audio_base64,
            'audio_format': 'mp3',
            'engine': 'gtts-fallback',
            'status': 'success'
        })
    except Exception as e2:
        logger.error(f"All TTS engines failed: {e2}")
        return jsonify({'error': str(e2)}), 500

@media_bp.route('/api/tts/filler', methods=['GET', 'POST'])
def tts_filler():
    """
    ส่งเสียง Filler Audio สำหรับเล่นคั่นเวลาทันที (0ms Standalone)
    เมื่อระบบต้องประมวลผลคำถามสดยาวๆ ช่วยให้ผู้ใช้งานไม่รู้สึกว่าหุ่นยนต์ค้าง
    """
    import random
    idx_param = request.args.get('index')
    if idx_param is not None and idx_param.isdigit():
        idx = int(idx_param) % len(FILLER_PHRASES)
        filler_text = FILLER_PHRASES[idx]
    else:
        filler_text = random.choice(FILLER_PHRASES)

    clean_text = clean_text_for_speech(filler_text, max_len=500, voice_gender='female', lang='th')
    voice = 'th-TH-PremwadeeNeural'
    rate = '+2%'
    pitch = '+0Hz'
    cache_key = f"{voice}_{pitch}_{rate}_{clean_text}"

    # ตรวจสอบในแคช 0ms
    cached_b64, cache_type = get_cached_tts(cache_key)
    if cached_b64:
        return jsonify({
            'status': 'success',
            'text': filler_text,
            'audio_base64': cached_b64,
            'audio_format': 'mp3',
            'engine': f'filler-cache-{cache_type}',
            'latency_ms': 0
        })

    # ถ้ายังไม่มีในแคช ให้เจนผ่าน Edge-TTS และเซฟลงแคช
    try:
        audio_bytes = run_coroutine(generate_edge_tts(clean_text, voice=voice, rate=rate, pitch=pitch, timeout=8.0))
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        save_cached_tts(cache_key, audio_bytes, audio_base64)
        return jsonify({
            'status': 'success',
            'text': filler_text,
            'audio_base64': audio_base64,
            'audio_format': 'mp3',
            'engine': 'edge-neural',
            'latency_ms': 0
        })
    except Exception as e:
        logger.warning(f"Filler TTS fallback error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@media_bp.route('/api/tts/stream', methods=['GET', 'POST'])
def tts_stream():
    """
    Streaming HTTP Audio Response (Chunked Transfer)
    ส่งข้อมูล MP3 ออกทันที เหมาะสำหรับ HTML5 Audio element หรือเล่นเสียงสด
    """
    if request.method == 'POST':
        data = request.json or {}
        text = data.get('text', '').strip()
        lang = data.get('lang', data.get('language', 'th'))
        pitch = data.get('pitch', '+0Hz')
        rate = data.get('rate', '+2%')
    else:
        text = request.args.get('text', '').strip()
        lang = request.args.get('lang', 'th')
        pitch = request.args.get('pitch', '+0Hz')
        rate = request.args.get('rate', '+2%')

    if not text:
        return jsonify({'error': 'text is required'}), 400

    if lang == 'en':
        voice = 'en-US-AriaNeural'
        rate = '+3%'
        pitch = '+0Hz'
    elif lang == 'zh':
        voice = 'zh-CN-XiaoxiaoNeural'
        rate = '+3%'
        pitch = '+0Hz'
    else:
        voice = 'th-TH-PremwadeeNeural'

    return Response(
        iter_audio_stream(text, voice=voice, rate=rate, pitch=pitch),
        mimetype="audio/mpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Type": "audio/mpeg"
        }
    )

@media_bp.route('/api/tts/presets', methods=['GET'])
def get_tts_presets():
    """ส่งรายการโหมดเสียงสังเคราะห์ (เฉพาะเสียงผู้หญิง)"""
    presets = [
        {
            "id": "default",
            "name": "เสียงมาตรฐานน้องเพชร (ค่าเริ่มต้น)",
            "description": "เสียงผู้หญิงน้องเพชร th-TH-PremwadeeNeural (Pitch +2Hz, Rate +5%) น่ารักสดใส จังหวะพูดเป็นธรรมชาติ",
            "voice": "th-TH-PremwadeeNeural",
            "pitch": "+2Hz",
            "rate": "+5%"
        },
        {
            "id": "cute_girl",
            "name": "น้องเพชรเด็กหญิงสดใส (+35Hz)",
            "description": "เสียงเด็กหญิงน่ารักสดใส สไตล์มาสคอตเด็ก",
            "voice": "th-TH-PremwadeeNeural",
            "pitch": "+35Hz",
            "rate": "+10%"
        },
        {
            "id": "cute_chibi",
            "name": "มาสคอตตัวจิ๋ว (Chibi Anime)",
            "description": "เสียงเล็กแหลมหวาน น่ารักสไตล์มาสคอตการ์ตูนญี่ปุ่น",
            "voice": "th-TH-PremwadeeNeural",
            "pitch": "+45Hz",
            "rate": "+12%"
        }
    ]
    return jsonify({'status': 'success', 'presets': presets})

@media_bp.route('/tts-preview', methods=['GET'])
def tts_preview_page():
    """หน้าทดสอบและเปรียบเทียบเสียงสังเคราะห์แบบโต้ตอบได้ (Interactive Voice Studio)"""
    return render_template('tts_preview.html')

@media_bp.route('/weather', methods=['GET'])
def get_weather():
    """สภาพอากาศเมืองเพชรบุรีแบบ Offline Local Information"""
    return jsonify({
        'weather': 'สภาพอากาศจังหวัดเพชรบุรีวันนี้ อุณหภูมิประมาณ 30-32°C ท้องฟ้าโปร่ง อากาศแจ่มใส เหมาะแก่การท่องเที่ยวค่ะ ☀️',
        'status': 'success',
        'engine': 'offline_local_weather'
    })

@media_bp.route('/api/live-token', methods=['GET', 'POST'])
def get_live_token():
    return jsonify({
        'status': 'offline',
        'message': 'ระบบทำงานในโหมด Offline 100%'
    })

@media_bp.route('/api/live-prompt', methods=['GET'])
def get_live_prompt():
    return jsonify({
        'status': 'offline',
        'message': 'ระบบทำงานในโหมด Offline 100%'
    })

