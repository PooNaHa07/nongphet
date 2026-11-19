# -*- coding: utf-8 -*-
"""
routes/chat.py — Conversational AI, Trip Planning & Course Matching Blueprint
"""
import time
import re
import uuid
import datetime
import logging
from flask import Blueprint, request, jsonify, session
from intent_classifier import NongPhetIntentClassifier
from services.text_utils import extract_suggestions, detect_message_language
from services import web_answer_service
from services.knowledge_service import (
    semantic_retriever, match_local_knowledge, get_local_knowledge_reply
)
from services.analytics_service import record_interaction
from services.arm_service import extract_gesture_tag
import state

logger = logging.getLogger("nongphet.chat")

chat_bp = Blueprint('chat', __name__)

# Initialize local intent classifier
intent_classifier = NongPhetIntentClassifier()

SELF_ECHO_MARKERS = (
    "ยินดีต้อนรับสู่น้องเพชร",
    "ผู้ช่วยอัจฉริยะประจำวิทยาลัย",
    "ผู้ช่วยอัจฉริยะประจำจังหวัดเพชรบุรี",
    "น้องเพชรยินดีต้อนรับสู่วิทยาลัย",
)

INTENT_EMOTION_MAP = {
    'travel': 'excited',
    'food': 'excited',
    'admission': 'smile',
    'greeting': 'smile',
    'general_faq': 'smile',
    'general': 'smile',
    'emergency': 'surprised',
    'love': 'love'
}

def resolve_living_emotion(user_message: str, reply_text: str, default_emotion: str = 'smile') -> str:
    """
    วิเคราะห์บทสนทนาแบบ Realtime เพื่อกำหนดอารมณ์ใบหน้าน้องเพชร (Screen 2):
    - love: ความรัก จีบ เขิน ชมว่าน่ารัก คนสร้างหล่อ
    - wink: ขี้เล่น ให้กำลังใจ หายเหนื่อย ยืมเงิน แกล้ง มุกตลก
    - excited: ท่องเที่ยว อาหาร ขนมหม้อแกง ทะเล ตื่นเต้น แต่งกลอน
    - surprised: ตกใจ อุบัติเหตุ เรื่องด่วน แจ้งเตือน
    - thinking: คำถามคิดวิเคราะห์ เปรียบเทียบ
    - smile/happy: สนทนาทั่วไป อบอุ่น เป็นมิตร
    """
    combined = (str(user_message) + " " + str(reply_text)).lower()
    
    # 1. Love / Blushing
    if any(k in combined for k in ['น่ารัก', 'แฟน', 'รักนะ', 'จีบ', 'เขิน', 'หล่อ', 'ชอบน้องเพชร', 'คนสร้าง', 'เนื้อคู่', 'หัวใจ', 'love']):
        return 'love'
        
    # 2. Wink / Playful / Cheering / Banter
    if any(k in combined for k in ['กำลังใจ', 'เหนื่อย', 'สู้ๆ', 'ยืมเงิน', 'ฮ่าๆ', '555', 'หยอก', 'กวน', 'มุก', 'พักผ่อน', 'หายเหนื่อย', 'แกล้ง']):
        return 'wink'
        
    # 3. Excited / Stars / Delights / Food & Travel / Poetry
    if any(k in combined for k in ['ว้าว', 'ตื่นเต้น', 'สุดยอด', 'ของกิน', 'หม้อแกง', 'หาดชะอำ', 'เขาวัง', 'แก่งกระจาน', 'เที่ยว', 'ทริป', 'กลอน', 'บทกวี', 'กาพย์']):
        return 'excited'
        
    # 4. Surprised / Emergency
    if any(k in combined for k in ['ตกใจ', 'ฉุกเฉิน', 'อุบัติเหตุ', 'อันตราย', 'ด่วน', 'จริงเหรอ', 'จริงดิ', 'แย่แล้ว']):
        return 'surprised'
        
    # 5. Thinking / Deep questions
    if any(k in combined for k in ['ทำไม', 'เปรียบเทียบ', 'วิเคราะห์', 'คำนวณ', 'ยังไงนะ']):
        return 'thinking'
        
    return default_emotion if default_emotion in ['smile', 'happy', 'excited', 'love', 'wink', 'surprised', 'thinking'] else 'smile'

def send_chat_response(user_message, reply_text, suggestions, engine, detected_intent, intent_th, confidence, source, language, base_emotion, rag_score=None, gesture=None, speech=None, extra=None):
    """ส่งต่อคำตอบพร้อมซิงค์อารมณ์ใบหน้าน้องเพชร (Screen 2) และบันทึกลง State"""
    final_emotion = resolve_living_emotion(user_message, reply_text, base_emotion)
    state.emotion_state['current'] = final_emotion
    state.emotion_state['timestamp'] = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        from routes.iot import broadcast_iot_event
        broadcast_iot_event({
            'event': 'emotion_changed',
            'state': final_emotion,
            'timestamp': state.emotion_state['timestamp'],
            'source': 'chat_persona'
        })
    except Exception as e:
        logger.debug(f"Emotion broadcast note: {e}")

    # ท่าทางแขนประกอบอารมณ์/เจตนา (ไม่ขัดขวางการตอบแชทหากระบบแขนมีปัญหา)
    try:
        from services import arm_service
        if gesture:
            # ท่าที่ LLM เลือกเองผ่านแท็ก [gesture:x] มาก่อนการเดาจากอารมณ์
            arm_service.trigger_gesture(gesture, source='llm_tag')
        else:
            arm_service.react_to_chat(detected_intent, final_emotion)
    except Exception as e:
        logger.debug(f"Arm gesture note: {e}")

    resp = {
        'reply': reply_text,
        'suggestions': suggestions,
        'status': 'success',
        'language': language,
        'engine': engine,
        'detected_intent': detected_intent,
        'intent': detected_intent,
        'intent_th': intent_th,
        'confidence': round(confidence, 4),
        'source': source,
        'emotion': final_emotion
    }
    if rag_score is not None:
        resp['rag_score'] = rag_score
    if speech:
        # บทพูดสั้นของหัวข้อนี้: หน้าจอแสดง reply เต็ม แต่น้องเพชรพูดแค่ speech
        resp['speech'] = speech
    if extra:
        resp.update(extra)
    return jsonify(resp)

def _try_web_answer(user_message, detected_intent, intent_th, confidence, language, target_emotion):
    """ชั้นสำรอง: ค้นคำตอบจากเว็บ (Gemini + Google Search) คืน response หรือ None ถ้าใช้ไม่ได้"""
    if not web_answer_service.should_use_web(user_message, detected_intent):
        return None
    web = web_answer_service.answer(user_message, language)
    if not web:
        return None
    record_interaction(user_message, detected_intent, confidence, 'web_search', language)
    return send_chat_response(
        user_message=user_message,
        reply_text=web['reply'],
        suggestions=extract_suggestions(web['reply']),
        engine='web_search',
        detected_intent=detected_intent,
        intent_th=intent_th,
        confidence=confidence,
        source=f"web_search:{web['model']}",
        language=language,
        base_emotion='happy',
        speech=web['speech'],
        extra={'sources': web['sources'], 'search_html': web['search_html']}
    )


@chat_bp.route('/chat', methods=['POST'])
def chat():
    """
    Route สำหรับประมวลผลข้อความแชท (ในเครื่องเป็นหลัก เว็บเป็นชั้นสำรอง):
    1. Local Machine Learning Model: จำแนก Intent และคำนวณ Confidence ในเครื่อง
    2. Semantic RAG / Local Knowledge Base: ตอบคำถามเฉพาะทางทันทีเมื่อพบความมั่นใจสูง
       (คะแนนต่ำกว่า WEB_PREFER_BELOW = ไม่แน่ใจ ลองค้นเว็บก่อน ถ้าค้นไม่ได้ใช้คำตอบนี้)
    3. Web Search (Gemini + Google Search): เฉพาะคำถามที่ฐานความรู้ตอบไม่ได้ และไม่ใช่เรื่องวิทยาลัย
    4. Local SLM (Ollama): ตอบบทสนทนาเปิดพร้อมบริบทจากฐานความรู้ (ถ้าติดตั้งและเปิดใช้งาน)
    5. Offline Fallback: คำตอบจากฐานความรู้ในเครื่องเมื่อทุกชั้นข้างต้นตอบไม่ได้
    """
    data = request.json or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'response': 'สวัสดีค่ะ มีอะไรให้น้องเพชรช่วยไหมคะ'}), 400
    if len(user_message) > 1000:
        user_message = user_message[:1000]

    # กรองเสียงสะท้อนของหุ่นยนต์เอง (Anti-Echo Guardrail)
    if any(marker in user_message for marker in SELF_ECHO_MARKERS):
        return jsonify({
            'reply': 'น้องเพชรพร้อมฟังคำถามจากคุณแล้วค่ะ สอบถามได้เลยนะคะ 😊',
            'suggestions': ['แนะนำสถานที่ท่องเที่ยวให้หน่อย', 'แนะนำของกินหน่อย', 'วิทยาลัยเปิดสอนสาขาอะไรบ้าง'],
            'status': 'success',
            'language': 'th',
            'engine': 'anti_echo_guard',
            'detected_intent': 'greeting',
            'intent': 'greeting',
            'confidence': 1.0,
            'emotion': 'happy'
        })
    
    # ระบบตรวจจับภาษาอัตโนมัติ
    raw_lang = data.get('language')
    if not raw_lang or raw_lang == 'auto':
        language = detect_message_language(user_message, 'th')
    else:
        detected = detect_message_language(user_message, raw_lang)
        if detected in ['en', 'zh'] and not re.search(r'[\u0e00-\u0e7f]', user_message):
            language = detected
        else:
            language = raw_lang

    force_llm = data.get('force_llm', False)

    # 1. Local Machine Learning Model
    ml_result = intent_classifier.predict(user_message)
    detected_intent = ml_result.get('intent', 'unknown')
    intent_th = ml_result.get('intent_th', 'ไม่ระบุ')
    confidence = float(ml_result.get('confidence', 0.0))
    target_emotion = INTENT_EMOTION_MAP.get(detected_intent, 'happy')

    session_id = data.get('session_id') or session.get('session_id', 'default_user')

    # ตรวจจับคำขอสร้างสรรค์ (แต่งกลอน, บทกวี, แต่งเพลง, เล่านิทาน) ให้ส่งไปประมวลผลด้วย Local SLM ทันที
    is_creative = bool(re.search(r'(กลอน|บทกวี|กาพย์|แต่งเพลง|เล่านิทาน|นิยาย|poem|poetry)', user_message, re.IGNORECASE))

    # 2. Semantic RAG & Local Knowledge Base
    if not force_llm and language == 'th':
        last_topic_id = state.SESSION_LAST_TOPIC.get(session_id)
        rag_match = semantic_retriever.retrieve(
            user_message,
            intent=detected_intent,
            context_entry_id=last_topic_id
        )
        # คะแนน RAG ต่ำ = ไม่แน่ใจว่าตรงหัวข้อ (เช่น ถามสถานที่ที่ไม่มีในฐานความรู้) -> ลองค้นเว็บก่อน
        if rag_match and rag_match['score'] < web_answer_service.prefer_web_below():
            web_resp = _try_web_answer(user_message, detected_intent, intent_th, confidence, language, target_emotion)
            if web_resp is not None:
                return web_resp
        if rag_match:
            if len(state.SESSION_LAST_TOPIC) >= state.MAX_SESSION_TOPICS:
                state.SESSION_LAST_TOPIC.popitem(last=False)
            state.SESSION_LAST_TOPIC[session_id] = rag_match['id']
            reply_text = rag_match['reply']
            suggestions = rag_match.get('suggestions') or extract_suggestions(reply_text)
            logger.info(f"⚡ [Semantic RAG] Local Hit [{rag_match['id']}] (Score: {rag_match['score']:.4f}, Intent: {detected_intent})")
            record_interaction(user_message, detected_intent, confidence, 'semantic_rag', language)
            return send_chat_response(
                user_message=user_message,
                reply_text=reply_text,
                suggestions=suggestions,
                engine='semantic_rag',
                detected_intent=detected_intent,
                intent_th=intent_th,
                confidence=confidence,
                source=f"semantic_rag:{rag_match['id']}",
                language=language,
                base_emotion=target_emotion,
                rag_score=rag_match['score'],
                speech=rag_match.get('speech')
            )

        local_reply = match_local_knowledge(user_message, detected_intent, confidence, language)
        if local_reply:
            logger.info(f"⚡ [Hybrid AI] Direct Local Response (Intent: {detected_intent}, Conf: {confidence:.2f})")
            record_interaction(user_message, detected_intent, confidence, 'local_model', language)
            suggestions = extract_suggestions(local_reply)
            return send_chat_response(
                user_message=user_message,
                reply_text=local_reply,
                suggestions=suggestions,
                engine='local_model',
                detected_intent=detected_intent,
                intent_th=intent_th,
                confidence=confidence,
                source='local_knowledge_base',
                language=language,
                base_emotion=target_emotion
            )

    # 3. ฐานความรู้ในเครื่องตอบไม่ได้ -> ค้นจากเว็บ (Gemini + Google Search) ถ้ามีเน็ตและตั้งค่าไว้
    if not is_creative:
        web_resp = _try_web_answer(user_message, detected_intent, intent_th, confidence, language, target_emotion)
        if web_resp is not None:
            return web_resp

    # 4. RAG-Augmented Local SLM (Ollama) — force_llm ข้ามฐานความรู้มาที่นี่โดยตรง
    try:
        from local_slm import generate_local_response, is_ollama_running
        if is_ollama_running():
            rag_contexts = [] if is_creative else semantic_retriever.retrieve_top_k(user_message, k=2, intent=detected_intent, min_score=0.38)
            slm_result = generate_local_response(
                user_message,
                rag_contexts=rag_contexts,
                language=language,
                intent=intent_th
            )
            if slm_result:
                reply_text, llm_gesture = extract_gesture_tag(slm_result['reply'])
                suggestions = extract_suggestions(reply_text)
                logger.info(f"🦙 [Local SLM+RAG] Response (Intent: {detected_intent}, Conf: {confidence:.2f})")
                record_interaction(user_message, detected_intent, confidence, 'local_slm', language)
                return send_chat_response(
                    user_message=user_message,
                    reply_text=reply_text,
                    suggestions=suggestions,
                    engine='local_slm',
                    detected_intent=detected_intent,
                    intent_th=intent_th,
                    confidence=confidence,
                    source=slm_result.get('source', 'local_slm'),
                    language=language,
                    base_emotion=target_emotion,
                    gesture=llm_gesture
                )
    except ImportError:
        pass

    # 5. Pure Offline Intelligent Knowledge & Semantic RAG Response
    reply_text = get_local_knowledge_reply(user_message, language, intent=detected_intent)
    suggestions = extract_suggestions(reply_text)
    record_interaction(user_message, detected_intent, confidence, 'offline_local_ai', language)

    return send_chat_response(
        user_message=user_message,
        reply_text=reply_text,
        suggestions=suggestions,
        engine='offline_local_ai',
        detected_intent=detected_intent,
        intent_th=intent_th,
        confidence=confidence,
        source='local_smart_knowledge',
        language=language,
        base_emotion=target_emotion
    )

@chat_bp.route('/api/voice/command', methods=['POST'])
def voice_command():
    """
    คำสั่งเสียง/พิมพ์สั้นๆ (เปิดหน้า หยุดพูด ยิ้ม โบกมือ กี่โมง ...) ตรวจก่อนส่งเข้าแชต ทำงานในเครื่องทันที
    คืน {'command': {...}} หรือ {'command': None} ถ้าไม่ใช่คำสั่ง (หน้าจอส่งต่อให้ /chat ตอบตามปกติ)
    """
    from services import voice_command_service
    data = request.json or {}
    cmd = voice_command_service.parse(data.get('text', ''))
    if not cmd:
        return jsonify({'status': 'success', 'command': None})
    if cmd.get('gesture'):
        try:
            from services import arm_service
            cmd['arm'] = arm_service.trigger_gesture(cmd['gesture'], source='voice_command', force=True).get('status')
        except Exception as e:
            logger.debug(f"Voice command arm note: {e}")
    if cmd['ui'].get('help'):
        cmd['help'] = voice_command_service.help_list()
    logger.info(f"🎙️ [Voice Command] {cmd['name']} <- {data.get('text', '')!r}")
    return jsonify({'status': 'success', 'command': cmd})


@chat_bp.route('/api/voice/commands', methods=['GET'])
def voice_command_list():
    """ตัวอย่างคำสั่งเสียงสำหรับการ์ด "ลองพูดว่า..." """
    from services import voice_command_service
    return jsonify({'status': 'success', 'groups': voice_command_service.help_list()})


@chat_bp.route('/plan_trip', methods=['POST'])
def plan_trip():
    data = request.json or {}
    trip_type = data.get('trip_type', '1 วัน')
    preferences = data.get('preferences', 'ทั่วไป')
    budget = data.get('budget', 'ปานกลาง')
    
    if "2 วัน" in trip_type or "ค้างคืน" in trip_type:
        plan = (
            "🗺️ **แผนการท่องเที่ยวเพชรบุรี 2 วัน 1 คืน (Smart Offline Edition)**\n\n"
            "🎯 **[Concept & Theme]:** เที่ยวครบธานี 3 วัง สัมผัสหาดทรายชะอำ และดื่มด่ำอาหาร UNESCO Gastronomy\n\n"
            "⏰ **[Timeline รายวัน]:**\n"
            "• **วันที่ 1 (อำเภอเมือง & ชะอำ):**\n"
            "  - 08:30 น. ขึ้นเคเบิลคาร์ชม **พระนครคีรี (เขาวัง)** นมัสการพระธาตุจอมเพชร\n"
            "  - 10:30 น. ชม 'ลำแสงสุริยาสวรรค์' ส่องกระทบพระพุทธรูปโบราณที่ **ถ้ำเขาหลวง**\n"
            "  - 12:00 น. ลิ้มลอง **ก๋วยเตี๋ยวน้ำแดง** รสเด็ด และข้าวแช่ชาววังต้นตำรับ\n"
            "  - 14:00 น. เช็คอินที่พักริมหาดชะอำ พักผ่อนและเล่นน้ำทะเล\n"
            "  - 18:00 น. ทานอาหารทะเลสดๆ ที่ **ตลาดสะพานปลาชะอำ**\n\n"
            "• **วันที่ 2 (มฤคทายวัน & ของฝาก):**\n"
            "  - 09:00 น. สัมผัสลมทะเลที่ **พระราชนิเวศน์มฤคทายวัน** พระราชวังไม้สักทองริมหาด\n"
            "  - 11:30 น. แวะชิมขนมผิงและทอดมันปลากรายโบราณที่ **ตลาดน้ำท่ายาง**\n"
            "  - 13:30 น. ซื้อ **ขนมหม้อแกงเตาฟืน** และ **น้ำตาลโตนดแท้ GI** ของดีเมืองเพชร\n\n"
            "💡 **[Local Pro Tips]:** สวมรองเท้าเดินสบาย และแต่งกายสุภาพเมื่อเข้าชมเขตพระราชวัง\n"
            "💰 **[Budget Breakdown]:** ประมาณ 1,500 - 2,500 บาท/ท่าน (รวมที่พักและอาหาร)"
        )
    else:
        plan = (
            "🗺️ **แผนการท่องเที่ยวเพชรบุรี 1 วันเต็ม (Day Trip Smart Offline)**\n\n"
            "🎯 **[Concept & Theme]:** สัมผัสมนต์เสน่ห์ธานี 3 วัง ไหว้พระขอพร และตระเวนชิมของอร่อยเมืองเพชร\n\n"
            "⏰ **[Timeline รายชั่วโมง]:**\n"
            "• **08:30 น.** เริ่มต้นที่ **พระนครคีรี (เขาวัง)** ขึ้นรถรางไฟฟ้าเคเบิลคาร์ ชมวิวเมืองเพชร 360 องศา\n"
            "• **10:30 น.** ชมความมหัศจรรย์ของลำแสงธรรมชาติที่ **ถ้ำเขาหลวง**\n"
            "• **12:00 น.** รับประทานอาหารกลางวัน: **ก๋วยเตี๋ยวน้ำแดง** และชิม **ข้าวแช่ชาววัง** คลายร้อน\n"
            "• **13:30 น.** ชมภาพจิตรกรรมฝาผนังอยุธยาและศาลาการเปรียญไม้สักที่ **วัดใหญ่สุวรรณาราม**\n"
            "• **15:00 น.** เดินเล่นถ่ายรูปสตรีทอาร์ทชิคๆ ริมแม่น้ำเพชรบุรี และแวะคาเฟ่คลองกระแชง\n"
            "• **16:30 น.** แวะซื้อ **ขนมหม้อแกงเตาฟืน** และของฝากเมืองเพชรแท้ 100% ก่อนเดินทางกลับ\n\n"
            "💡 **[Local Pro Tips]:** เวลาที่แสงลงช่องถ้ำเขาหลวงสวยที่สุดคือ 09:30 - 11:30 น.\n"
            "💰 **[Budget Breakdown]:** ประมาณ 500 - 800 บาท/ท่าน"
        )
    return jsonify({'plan': plan, 'status': 'success', 'engine': 'offline_local_planner'})

# ตัวแนะนำสาขา: จับคู่ความสนใจกับ 11 สาขาที่เปิดสอนจริง แล้วดึงรายละเอียดจากฐานความรู้ (ข้อมูลทางการ)
# ไม่ใส่คะแนนความเหมาะสมหรือเงินเดือน เพราะไม่มีแหล่งข้อมูลรองรับ
COURSE_RULES = [
    ('admission_dbt_001', 'เทคโนโลยีธุรกิจดิจิทัลและคอมพิวเตอร์ธุรกิจ',
     ['คอม', 'ไอที', 'โปรแกรม', 'เขียนโค้ด', 'เว็บ', 'แอป', 'เกม', 'it', 'computer', 'ai', 'ดิจิทัล', 'เทคโน', 'เครือข่าย']),
    ('admission_digital_graphic_001', 'ดิจิทัลกราฟิก',
     ['กราฟิก', 'ออกแบบ', 'ตัดต่อ', 'วิดีโอ', 'ภาพเคลื่อนไหว', 'แอนิเมชัน', 'โปสเตอร์', 'design', 'graphic']),
    ('admission_fine_arts_001', 'วิจิตรศิลป์', ['วาดรูป', 'วาดภาพ', 'ศิลปะ', 'ระบายสี', 'ปั้น', 'จิตรกรรม', 'art']),
    ('admission_acct_001', 'การบัญชี', ['บัญชี', 'ตัวเลข', 'คำนวณ', 'การเงิน', 'ภาษี', 'คณิต', 'account']),
    ('admission_mkt_001', 'การตลาด', ['ขาย', 'ค้าขาย', 'ออนไลน์', 'การตลาด', 'โฆษณา', 'ธุรกิจ', 'แม่ค้า', 'marketing']),
    ('admission_office_001', 'การจัดการสำนักงาน', ['เอกสาร', 'สำนักงาน', 'เลขา', 'ธุรการ', 'ประสานงาน', 'office']),
    ('admission_culinary_001', 'อาหารและโภชนาการ', ['อาหาร', 'ทำอาหาร', 'ขนม', 'ครัว', 'เชฟ', 'เบเกอรี่', 'cook', 'chef', 'food']),
    ('admission_home_econ_001', 'คหกรรม', ['ดอกไม้', 'แกะสลัก', 'ใบตอง', 'งานฝีมือ', 'ประดิษฐ์', 'ดูแลเด็ก', 'ผู้สูงอายุ']),
    ('admission_fashion_001', 'แฟชั่นและสิ่งทอ', ['แฟชั่น', 'เสื้อผ้า', 'ตัดเย็บ', 'เย็บผ้า', 'แต่งตัว', 'ผ้า', 'fashion']),
    ('admission_hotel_001', 'การโรงแรม', ['โรงแรม', 'บริการ', 'ต้อนรับ', 'เครื่องดื่ม', 'บาร์', 'hotel']),
    ('admission_tourism_001', 'การท่องเที่ยว', ['ท่องเที่ยว', 'ไกด์', 'มัคคุเทศก์', 'เที่ยว', 'ภาษาอังกฤษ', 'ทัวร์', 'อีเวนต์', 'tour']),
]


def _course_summary(entry_id):
    """ดึงบรรทัดหลักสูตรและอาชีพจากคำตอบในฐานความรู้ (แหล่งเดียวกับที่น้องเพชรตอบในแชท)"""
    try:
        from services.knowledge_manager import kb_manager
        entry = kb_manager.get_entry(entry_id) or {}
    except Exception:
        entry = {}
    keep = []
    for line in (entry.get('answer') or '').split('\n'):
        s = line.strip()
        if s.startswith(('- ปวช', '- ปวส', '- ปริญญา', '• **อาชีพ', '• **หลักสูตร', '• มีนักเรียน')):
            keep.append(line)
    return '\n'.join(keep)


@chat_bp.route('/match_course', methods=['POST'])
def match_course():
    data = request.json or {}
    text = ' '.join(str(data.get(k, '')) for k in ('interests', 'strengths', 'dream_job')).lower()

    scored = []
    for entry_id, name, words in COURSE_RULES:
        hits = [w for w in words if w in text]
        if hits:
            scored.append((len(hits), entry_id, name, hits))
    scored.sort(key=lambda x: -x[0])

    if not scored:
        rec = (
            "🎓 **น้องเพชรช่วยแนะนำสาขาให้ค่ะ**\n\n"
            "ยังจับคู่ความสนใจกับสาขาไม่ได้ ลองบอกสิ่งที่ชอบเพิ่มอีกนิดนะคะ เช่น คอมพิวเตอร์ วาดรูป ทำอาหาร ค้าขาย หรืองานบริการ\n\n"
            "วิทยาลัยอาชีวศึกษาเพชรบุรี (PBPVC) เปิดสอน 11 สาขา: " + ', '.join(name for _, name, _ in COURSE_RULES)
        )
        return jsonify({'recommendation': rec, 'status': 'success', 'engine': 'offline_course_matcher', 'matches': []})

    _, best_id, best_name, best_hits = scored[0]
    parts = [
        "🎓 **สาขาที่น้องเพชรแนะนำ**\n",
        f"🏆 **สาขาวิชา{best_name}**",
        f"🎯 เพราะคุณสนใจเรื่อง: {', '.join(best_hits)}",
    ]
    summary = _course_summary(best_id)
    if summary:
        parts += ['', summary]
    if len(scored) > 1:
        parts += ['', '🥈 **สาขาที่น่าสนใจรองลงมา**: ' + ', '.join(f"สาขาวิชา{n}" for _, _, n, _ in scored[1:3])]
    parts += ['', '📌 ข้อมูลจากเว็บไซต์วิทยาลัย (พ.ย. 2569) สอบถามเพิ่มเติม โทร 032-425-557']
    return jsonify({
        'recommendation': '\n'.join(parts),
        'status': 'success',
        'engine': 'offline_course_matcher',
        'matches': [{'id': i, 'name': n} for _, i, n, _ in scored[:3]],
    })


@chat_bp.route('/reset', methods=['POST'])
def reset():
    session_id = session.get('session_id')
    if session_id:
        state.SESSION_LAST_TOPIC.pop(session_id, None)
    session['session_id'] = str(uuid.uuid4())
    return jsonify({'status': 'reset_complete'})

