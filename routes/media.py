# -*- coding: utf-8 -*-
"""
routes/media.py — Text-to-Speech (TTS) & Weather Blueprint

นโยบายเสียงเดียวทั้งระบบ: ทุกเส้นทางพูดด้วยเสียงจาก voice_profile() (ตั้งค่าใน config.Config)
ไม่มีเสียงสำรองที่เป็นคนอื่น ถ้าสร้างเสียงน้องเพชรไม่ได้ จะตอบ 503 ให้หน้าเว็บแสดงข้อความอย่างเดียว
ข้อยกเว้นเดียว: หน้าทดลองเสียง /tts-preview ส่ง preview=1 มาเพื่อลอง pitch/rate อื่น (ไม่บันทึกลงแคช)
"""
import base64
import logging
import random
from flask import Blueprint, request, jsonify, Response, render_template

from services.tts_service import (
    get_cached_tts, save_cached_tts, voice_profile, speech_cache_key, prepare_speech_input,
    extract_first_sentence_for_speech, clean_text_for_speech,
    generate_speech, run_coroutine, iter_audio_stream, edge_wait_budget, edge_tts_available
)
from services.azure_speech import azure_enabled, azure_status

logger = logging.getLogger("nongphet.media")

media_bp = Blueprint('media', __name__)

FILLER_PHRASES = [
    "ได้เลยค่าา แป๊บนึงน้าา",
    "อื้อหืออ เรื่องนี้นะคะ สักครู่น้าา",
    "อ๋ออ ได้เลยค่ะ เดี๋ยวค้นให้นะคะ",
    "รับทราบเลยค่าา รอแป๊บนึงน้าา",
    "สักครู่นะคะ น้องเพชรเตรียมข้อมูลให้เดี๋ยวนี้เลยค่าา"
]


def _is_preview(source):
    return str(source.get('preview', '')).lower() in ('1', 'true', 'yes')


def resolve_voice(lang, source):
    """
    คืน (voice, pitch, rate, use_cache)
    ค่าปกติ: เสียงน้องเพชรตาม config เสมอ (ไม่สนใจ pitch/rate ที่หน้าเว็บส่งมา เพื่อให้ทุกหน้าโทนเดียวกัน)
    preview=1: ใช้ pitch/rate ที่ส่งมาได้ แต่ไม่บันทึกลงแคช กันโทนอื่นปนเข้ามา
    """
    voice, pitch, rate = voice_profile(lang)
    if _is_preview(source):
        return voice, source.get('pitch') or pitch, source.get('rate') or rate, False
    return voice, pitch, rate, True


def _no_voice_response(reason):
    return jsonify({
        'status': 'no_voice',
        'error': reason,
        'message': 'ไม่มีเสียงน้องเพชรสำหรับข้อความนี้ (แสดงข้อความอย่างเดียว)'
    }), 503


@media_bp.route('/tts', methods=['POST'])
def tts():
    data = request.json or {}
    text = data.get('text', '').strip()
    lang = data.get('lang', data.get('language', 'th'))
    fast_mode = data.get('fast_mode', False) and data.get('first_sentence', False)

    if not text:
        return jsonify({'error': 'Text is empty'}), 400

    target_text = extract_first_sentence_for_speech(text, lang=lang, max_len=500) if fast_mode else text
    clean_text = clean_text_for_speech(prepare_speech_input(target_text), max_len=2500, voice_gender='female', lang=lang)
    voice, pitch, rate, use_cache = resolve_voice(lang, data)
    volume = data.get('volume', '+0%')
    cache_key = speech_cache_key(clean_text, voice, pitch, rate)

    # 1. เสียงที่อัดเก็บไว้แล้ว (ทำงานได้แม้ไม่มีเน็ต)
    if use_cache:
        cached_b64, cache_type = get_cached_tts(cache_key)
        if cached_b64:
            return jsonify({
                'audio_base64': cached_b64,
                'audio_format': 'mp3',
                'engine': f'cache-{cache_type}',
                'voice': voice, 'rate': rate, 'pitch': pitch,
                'latency_ms': 0,
                'status': 'success'
            })

    # 2. สร้างเสียงน้องเพชรสดด้วย Edge-TTS (ต้องใช้เน็ต) แล้วเก็บลงแคช
    try:
        audio_bytes = run_coroutine(generate_speech(clean_text, voice=voice, rate=rate, pitch=pitch, volume=volume),
                                    timeout=edge_wait_budget(clean_text))
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        if use_cache:
            save_cached_tts(cache_key, audio_bytes, audio_base64)
        return jsonify({
            'audio_base64': audio_base64,
            'audio_format': 'mp3',
            'engine': 'neural',
            'voice': voice, 'rate': rate, 'pitch': pitch,
            'status': 'success'
        })
    except Exception as e:
        logger.warning(f"🔇 [TTS] สร้างเสียงน้องเพชรไม่ได้ ({e}) -> แสดงข้อความอย่างเดียว")
        return _no_voice_response(str(e))


@media_bp.route('/api/tts/filler', methods=['GET', 'POST'])
def tts_filler():
    """
    ส่งเสียง Filler Audio สำหรับเล่นคั่นเวลาทันที (0ms Standalone)
    เมื่อระบบต้องประมวลผลคำถามสดยาวๆ ช่วยให้ผู้ใช้งานไม่รู้สึกว่าหุ่นยนต์ค้าง
    """
    idx_param = request.args.get('index')
    if idx_param is not None and idx_param.isdigit():
        filler_text = FILLER_PHRASES[int(idx_param) % len(FILLER_PHRASES)]
    else:
        filler_text = random.choice(FILLER_PHRASES)

    clean_text = clean_text_for_speech(prepare_speech_input(filler_text), max_len=2500, voice_gender='female', lang='th')
    voice, pitch, rate = voice_profile('th')
    cache_key = speech_cache_key(clean_text, voice, pitch, rate)

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

    try:
        audio_bytes = run_coroutine(generate_speech(clean_text, voice=voice, rate=rate, pitch=pitch),
                                    timeout=edge_wait_budget(clean_text))
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        save_cached_tts(cache_key, audio_bytes, audio_base64)
        return jsonify({
            'status': 'success',
            'text': filler_text,
            'audio_base64': audio_base64,
            'audio_format': 'mp3',
            'engine': 'neural',
            'latency_ms': 0
        })
    except Exception as e:
        logger.warning(f"Filler TTS unavailable: {e}")
        return _no_voice_response(str(e))


@media_bp.route('/api/tts/stream', methods=['GET', 'POST'])
def tts_stream():
    """
    Streaming HTTP Audio Response (Chunked Transfer)
    ส่งข้อมูล MP3 ออกทันที เหมาะสำหรับ HTML5 Audio element หรือเล่นเสียงสด
    """
    source = (request.json or {}) if request.method == 'POST' else request.args
    text = (source.get('text') or '').strip()
    lang = source.get('lang', source.get('language', 'th'))
    if not text:
        return jsonify({'error': 'text is required'}), 400

    voice, pitch, rate, use_cache = resolve_voice(lang, source)
    return Response(
        iter_audio_stream(text, lang=lang, voice=voice, pitch=pitch, rate=rate, use_cache=use_cache),
        mimetype="audio/mpeg",
        headers={
            "Cache-Control": "public, max-age=86400" if use_cache else "no-store",
            "Content-Type": "audio/mpeg"
        }
    )


@media_bp.route('/api/tts/status', methods=['GET'])
def tts_status():
    """ตรวจว่าระบบเสียงพร้อมแค่ไหน (ไม่เปิดเผยคีย์)"""
    voice, pitch, rate = voice_profile('th')
    return jsonify({
        'status': 'success',
        'voice': {'name': voice, 'pitch': pitch, 'rate': rate},
        'primary_engine': 'azure' if azure_enabled() else 'edge',
        'azure': azure_status(),
        'edge_available': edge_tts_available(),
    })


@media_bp.route('/api/tts/presets', methods=['GET'])
def get_tts_presets():
    """
    รายการโทนเสียงสำหรับหน้าทดลองเสียง /tts-preview
    ระบบจริงใช้ค่า "default" (ตาม config) เสมอ ตัวเลือกอื่นมีไว้ฟังเปรียบเทียบเท่านั้น
    """
    voice, pitch, rate = voice_profile('th')
    presets = [
        {
            "id": "default",
            "name": "เสียงน้องเพชร (ที่ระบบใช้จริง)",
            "description": f"{voice} (Pitch {pitch}, Rate {rate}) — ทุกหน้าจอพูดด้วยเสียงนี้เสียงเดียว",
            "voice": voice, "pitch": pitch, "rate": rate
        },
        {
            "id": "original",
            "name": "เปรมวดีเสียงปกติ (เปรียบเทียบ)",
            "description": "เสียงเดิมก่อนปรับ (Pitch +0Hz, Rate +2%)",
            "voice": voice, "pitch": "+0Hz", "rate": "+2%"
        },
        {
            "id": "cute_girl",
            "name": "แหลมขึ้นอีก (+35Hz) (เปรียบเทียบ)",
            "description": "เสียงเด็กหญิงสดใส",
            "voice": voice, "pitch": "+35Hz", "rate": "+10%"
        }
    ]
    return jsonify({'status': 'success', 'presets': presets, 'active': 'default'})


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
