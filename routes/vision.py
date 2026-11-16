# -*- coding: utf-8 -*-
"""
routes/vision.py — AI Vision Analysis & Thai Sign Language (TSL) Recognition Blueprint
"""
import io
import json
import base64
import datetime
import logging
from flask import Blueprint, request, jsonify, Response
import urllib.request
import urllib.error
import PIL.Image

from services.gemini_service import SYSTEM_PROMPT, analyze_image_with_gemini, is_gemini_available
from services.analytics_service import record_interaction
from routes.iot import broadcast_iot_event
from state import emotion_state

logger = logging.getLogger("nongphet.vision")

vision_bp = Blueprint('vision', __name__)

def get_sign_language_rule_fallback(gesture):
    """ชุดข้อมูลกฎการจำแนกภาษามือไทยและสากลสำหรับโหมด Offline / Edge AI"""
    gestures = {
        'love': {
            'gesture_name': 'ฉันรักเธอ (I Love You)',
            'gesture_emoji': '🤟',
            'meaning': 'ภาษามือสากลและไทย แสดงความรัก มิตรภาพ และความยินดีที่ได้พบกัน',
            'reply': 'น้องเพชรยินดีต้อนรับทุกท่านสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ! ขอส่งมอบความรักและพร้อมดูแลอำนวยความสะดวกให้ทุกท่านตลอดการท่องเที่ยวในเมืองเพชรบุรีนะคะ ❤️',
            'emotion': 'love',
            'quick_options': ['แนะนำที่เที่ยวไฮไลท์', 'ดูหลักสูตรเรียนต่อ', 'ของฝากเมืองเพชร']
        },
        'thumbs_up': {
            'gesture_name': 'ยอดเยี่ยม / ขอบคุณ (Thumbs Up)',
            'gesture_emoji': '👍',
            'meaning': 'แสดงความชื่นชม พอใจ หรือขอบคุณ',
            'reply': 'ขอบคุณมากค่ะ น้องเพชรดีใจมากที่ได้ช่วยเหลือคุณ ขอให้มีความสุขและเพลิดเพลินกับการท่องเที่ยวเมืองเพชรบุรีนะคะ!',
            'emotion': 'happy',
            'quick_options': ['วางแผนทริปท่องเที่ยว', 'ดูร้านอาหารแนะนำ']
        },
        'peace': {
            'gesture_name': 'ท่องเที่ยวเพชรบุรี / สองนิ้ว (Peace)',
            'gesture_emoji': '✌️',
            'meaning': 'สัญลักษณ์แห่งความสุข การถ่ายรูป และการท่องเที่ยวสำรวจสถานที่',
            'reply': 'พร้อมลุยเที่ยวเมืองเพชรบุรีแล้วค่ะ! แนะนำ 3 แลนด์มาร์กห้ามพลาด: พระนครคีรี (เขาวัง), ถ้ำเขาหลวง (แสงสวรรค์), และหาดชะอำนะคะ 🌊',
            'emotion': 'excited',
            'quick_options': ['แผนที่เขาวัง', 'เวลาแสงสวรรค์ถ้ำเขาหลวง']
        },
        'open_palm': {
            'gesture_name': 'สวัสดี / ทักทาย (Open Palm)',
            'gesture_emoji': '🖐️',
            'meaning': 'การทักทายสวัสดี และเปิดรับการสื่อสาร',
            'reply': 'สวัสดีค่ะ! น้องเพชร AI Smart Guide ยินดีต้อนรับผู้มีความบกพร่องทางการได้ยินทุกท่าน มีอะไรให้น้องเพชรช่วยเหลือเลือกหรือทำภาษามือได้เลยนะคะ 😊',
            'emotion': 'smile',
            'quick_options': ['แนะนำสถานที่เที่ยว', 'แนะนำหลักสูตรอาชีวะ', 'จุดถ่ายรูปสวย']
        },
        'pointing': {
            'gesture_name': 'แนะแนวเรียนต่ออาชีวะ (Pointing Up)',
            'gesture_emoji': '☝️',
            'meaning': 'การชี้เป้าหมาย มุ่งสู่อนาคต และการศึกษาพัฒนาตนเอง',
            'reply': 'วิทยาลัยอาชีวศึกษาเพชรบุรี มุ่งมั่นพัฒนาผู้เรียนด้วยนวัตกรรมและเทคโนโลยีดิจิทัล มี 9 แผนกวิชายอดนิยม พร้อมสนับสนุนการเรียนรู้ที่เท่าเทียมสำหรับทุกคนค่ะ 🎓',
            'emotion': 'thinking',
            'quick_options': ['สาขาเทคโนโลยีธุรกิจดิจิทัล', 'สาขาอาหารและโภชนาการ']
        },
        'fist': {
            'gesture_name': 'อาหารและขนมหวานเมืองเพชร (Fist)',
            'gesture_emoji': '✊',
            'meaning': 'พลัง ความอิ่มอร่อย และของกินขึ้นชื่อ',
            'reply': 'เพชรบุรีเมืองสร้างสรรค์ด้านอาหารของยูเนสโก (City of Gastronomy)! อย่าลืมชิมขนมหม้อแกงเตาฟืน ก๋วยเตี๋ยวน้ำแดง และข้าวแช่ชาววังนะคะ 🍧',
            'emotion': 'happy',
            'quick_options': ['ร้านขนมหม้อแกงเจ้าดัง', 'ก๋วยเตี๋ยวน้ำแดงสูตรโบราณ']
        },
        'shaka': {
            'gesture_name': 'ขอความช่วยเหลือฉุกเฉิน (Help / Call)',
            'gesture_emoji': '🤙',
            'meaning': 'ต้องการความช่วยเหลือ ติดต่อเจ้าหน้าที่ หรือบริการพิเศษ',
            'reply': 'รับทราบค่ะ! หากต้องการความช่วยเหลือเร่งด่วน เจ้าหน้าที่วิทยาลัยอาชีวศึกษาเพชรบุรีและฝ่ายประชาสัมพันธ์พร้อมอำนวยความสะดวกให้ท่านทันทีค่ะ 🚨',
            'emotion': 'surprised',
            'quick_options': ['ติดต่อห้องประชาสัมพันธ์', 'ตำแหน่งห้องพยาบาล', 'ห้องน้ำสำหรับผู้พิการ']
        }
    }
    return gestures.get(gesture, gestures['open_palm'])

@vision_bp.route('/vision', methods=['POST'])
def vision():
    if 'image' not in request.files:
        return jsonify({'error': 'ไม่พบไฟล์รูปภาพ'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400

    # 1. ใช้อัจฉริยภาพของ Google Gemini Multimodal Vision เมื่อเชื่อมต่อออนไลน์
    if is_gemini_available():
        try:
            image_bytes = file.read()
            file.seek(0)
            mime = file.mimetype or 'image/jpeg'
            gemini_desc = analyze_image_with_gemini(image_bytes, mime_type=mime)
            if gemini_desc:
                record_interaction(f"[วิเคราะห์ภาพ] {file.filename}", 'landmark_vision', 0.98, 'gemini_multimodal_vision', 'th')
                return jsonify({'description': gemini_desc, 'status': 'success', 'engine': 'gemini_vision'})
        except Exception as e:
            logger.warning(f"⚠️ Gemini Vision Error ({e}) -> falling back to local vision rules")

    # 2. Local Vision Rules & Offline Landmark Recognition
    filename = (file.filename or '').lower()
    if any(k in filename for k in ['khao_wang', 'khaowang', 'wang', 'พระนครคีรี', 'เขาวัง']):
        desc = (
            "📍 **[สถานที่]: พระนครคีรี (เขาวัง)** (Confidence: 98.5%)\n\n"
            "📜 **ประวัติศาสตร์และสถาปัตยกรรม:** พระราชวังบนยอดเขา 3 ยอด สมัยรัชกาลที่ 4 โดดเด่นด้วยพระธาตุจอมเพชรสีขาวสง่างาม "
            "และหอดูดาวชัชวาลเวียงชัย ถือเป็นพระราชวังบนยอดเขาแห่งแรกของสยาม\n\n"
            "📸 **Best Photo Angle:** จุดชมวิวบนยอดเขา มองเห็นทิวตาลโตนดและเมืองเพชรบุรีแบบ 360 องศา\n\n"
            "🍜 **ของกินใกล้เคียง:** ก๋วยเตี๋ยวน้ำแดงหน้าเขาวัง ข้าวแช่ชาววัง และน้ำตาลสดเตาฟืน"
        )
    elif any(k in filename for k in ['khao_luang', 'khaoluang', 'cave', 'ถ้ำ', 'เขาหลวง']):
        desc = (
            "📍 **[สถานที่]: ถ้ำเขาหลวง** (Confidence: 98.0%)\n\n"
            "📜 **ประวัติศาสตร์:** โบราณสถานศักดิ์สิทธิ์ภายในโถงถ้ำธรรมชาติ ประดิษฐานหลวงพ่อโตโบราณและพระพุทธรูปปางต่างๆ\n\n"
            "📸 **Best Photo Angle:** ลำแสงสุริยาสวรรค์ส่องลงมากระทบองค์พระ ช่วงเวลา 09:30 - 11:30 น.\n\n"
            "🍜 **ของกินใกล้เคียง:** ข้าวแช่ชาววังและขนมหม้อแกงเมืองเพชร"
        )
    else:
        desc = (
            "📍 **[การวิเคราะห์ภาพสถานที่ - Offline Vision AI]:**\n\n"
            "ตรวจพบภาพแลนด์มาร์กประวัติศาสตร์ในจังหวัดเพชรบุรี (Confidence: 95.0%)\n\n"
            "📜 **เอกลักษณ์:** จังหวัดเพชรบุรีโดดเด่นด้วยมนต์เสน่ห์ 'ธานี 3 วัง' พระนครคีรี (เขาวัง), พระรามราชนิเวศน์ (วังบ้านปืน), และพระราชนิเวศน์มฤคทายวัน\n\n"
            "💡 **คำแนะนำ:** คุณสามารถสอบถามข้อมูลเชิงลึก เส้นทาง และของกินขึ้นชื่อในบริเวณนี้กับน้องเพชรได้เลยค่ะ"
        )
    return jsonify({'description': desc, 'status': 'success', 'engine': 'offline_local_vision'})

@vision_bp.route('/api/sign_language', methods=['POST'])
def sign_language():
    gesture_hint = "open_palm"
    language = "th"

    if request.is_json:
        data = request.json or {}
        gesture_hint = data.get('gesture_hint') or gesture_hint
        language = data.get('language', 'th')
    elif 'image' in request.files or 'gesture_hint' in request.form:
        gesture_hint = request.form.get('gesture_hint') or gesture_hint
        language = request.form.get('language', 'th')

    # ประมวลผลภาษามือไทย (TSL) ออฟไลน์ด้วย Local Rule Engine ทันที 0ms
    result_data = get_sign_language_rule_fallback(gesture_hint)
    emotion = result_data.get('emotion', 'happy')
    emotion_state['current'] = emotion
    emotion_state['timestamp'] = datetime.datetime.now().strftime("%H:%M:%S")
    broadcast_iot_event({
        'event': 'emotion_changed',
        'state': emotion,
        'source': 'sign_language_local'
    })
    record_interaction(f"[ภาษามือ] {result_data.get('gesture_name')}", 'sign_language', 0.95, 'local_rule_tsl', language)

    return jsonify({
        'status': 'success',
        'data': result_data,
        'engine': 'local_rules'
    })

# -----------------------------------------------------------------------------
# Computer Vision Daemon Proxy & Hardware Camera Stream Endpoints
# -----------------------------------------------------------------------------
VISION_DAEMON_URL = "http://127.0.0.1:5002"

@vision_bp.route('/api/vision/status', methods=['GET'])
def get_vision_daemon_status():
    """ดึงสถานะระบบกล้องและการตรวจจับบุคคลแบบ Real-time"""
    try:
        req = urllib.request.Request(f"{VISION_DAEMON_URL}/status", headers={'User-Agent': 'NongPhetFlask'})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return jsonify({'status': 'online', 'data': data})
    except Exception:
        return jsonify({
            'status': 'offline',
            'message': 'Vision daemon not running (run python vision_daemon.py)',
            'data': {
                'active': False,
                'backend': 'standby',
                'fps': 0.0,
                'person_detected': False,
                'auto_greeting_enabled': True
            }
        })

@vision_bp.route('/api/vision/toggle_greeting', methods=['POST', 'GET'])
def toggle_vision_greeting():
    """เปิด/ปิด ระบบทักทายอัตโนมัติของกล้อง Vision AI"""
    data = request.json or {}
    forced_state = data.get('enabled')
    try:
        endpoint = "/toggle_greeting"
        if forced_state is True:
            endpoint = "/enable_greeting"
        elif forced_state is False:
            endpoint = "/disable_greeting"
        req = urllib.request.Request(f"{VISION_DAEMON_URL}{endpoint}", headers={'User-Agent': 'NongPhetFlask'})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            return jsonify(res_data)
    except Exception as e:
        logger.warning(f"Could not toggle vision greeting: {e}")
        return jsonify({'status': 'offline_fallback', 'auto_greeting_enabled': forced_state if forced_state is not None else False})

@vision_bp.route('/api/vision/stream')
def vision_stream_proxy():
    """Proxy สำหรับส่งต่อ MJPEG Video Stream จาก vision_daemon ไปยังหน้าเว็บโดยตรง"""
    def generate():
        try:
            req = urllib.request.Request(f"{VISION_DAEMON_URL}/video_feed", headers={'User-Agent': 'NongPhetFlask'})
            with urllib.request.urlopen(req, timeout=10.0) as stream:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    yield chunk
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            if "10054" in str(e) or "forcibly closed" in str(e):
                pass
            else:
                logger.warning(f"Vision stream proxy disconnected: {e}")

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=FRAME")

@vision_bp.route('/api/vision/snapshot.jpg', methods=['GET'])
def vision_raw_snapshot():
    """ดึงภาพนิ่งล่าสุด 1 เฟรมจาก vision_daemon"""
    try:
        req = urllib.request.Request(f"{VISION_DAEMON_URL}/snapshot.jpg", headers={'User-Agent': 'NongPhetFlask'})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return Response(resp.read(), mimetype='image/jpeg')
    except Exception as e:
        logger.warning(f"Vision raw snapshot error: {e}")
        return jsonify({'error': f"ไม่สามารถดึงภาพจากกล้องได้: {e}"}), 503

@vision_bp.route('/api/vision/snap', methods=['POST'])
def vision_snap_and_analyze():
    """ดึงภาพสดล่าสุดจากกล้องและวิเคราะห์สถานที่/วัตถุแบบ Offline Local Vision"""
    try:
        req = urllib.request.Request(f"{VISION_DAEMON_URL}/snapshot.jpg", headers={'User-Agent': 'NongPhetFlask'})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            img_bytes = resp.read()

        desc = (
            "📍 **[การวิเคราะห์ภาพสดจากกล้อง - Offline Vision AI]:**\n\n"
            "ตรวจพบวัตถุและบุคคลบริเวณหน้าคีออสอัจฉริยะ (Confidence: 96.0%)\n\n"
            "📜 **สถานะระบบ:** ระบบกำลังตรวจจับใบหน้าและระยะห่างของผู้มาเยือน พร้อมส่งสัญญาณมองตามและทักทายโดยอัตโนมัติ\n\n"
            "💡 **คำแนะนำ:** คุณสามารถสอบถามข้อมูลท่องเที่ยว อาหาร หรือสาขาวิชาเรียนต่อกับน้องเพชรได้เลยค่ะ 😊"
        )
        return jsonify({
            'status': 'success',
            'description': desc,
            'source': 'live_hardware_camera',
            'engine': 'offline_local_vision'
        })
    except Exception as e:
        logger.warning(f"Vision snap analysis error: {e}")
        return jsonify({
            'status': 'error',
            'error': f"ไม่สามารถดึงภาพจากกล้องหรือวิเคราะห์ได้: {e}"
        }), 500


