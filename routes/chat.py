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
from services.gemini_service import (
    SYSTEM_PROMPT, extract_suggestions, detect_message_language,
    generate_gemini_response, is_gemini_available
)
from services.knowledge_service import (
    semantic_retriever, match_local_knowledge, get_local_knowledge_reply
)
from services.analytics_service import record_interaction
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

def send_chat_response(user_message, reply_text, suggestions, engine, detected_intent, intent_th, confidence, source, language, base_emotion, rag_score=None):
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
    return jsonify(resp)

@chat_bp.route('/chat', methods=['POST'])
def chat():
    """
    Route สำหรับประมวลผลข้อความแชทด้วย Hybrid AI Architecture:
    1. Local Machine Learning Model: จำแนก Intent และคำนวณ Confidence ในเครื่อง
    2. Local Knowledge Base: ตอบคำถามเฉพาะทางทันทีเมื่อพบความมั่นใจสูงเพื่อความเร็วระดับมิลลิวินาที
    3. Google Gemini 2.5 Flash: ส่งต่อเพื่อตอบบทสนทนาเชิงลึก พร้อมทำ Context Steering ด้วย Intent จาก ML
    4. Two-tier Fallbacks: มีระบบสำรองทั้ง Gemini Flash-Lite และ Local Knowledge เมื่อออฟไลน์
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
        if rag_match:
            if len(state.SESSION_LAST_TOPIC) >= state.MAX_SESSION_TOPICS:
                state.SESSION_LAST_TOPIC.popitem(last=False)
            state.SESSION_LAST_TOPIC[session_id] = rag_match['id']
            reply_text = rag_match['reply']
            suggestions = rag_match.get('suggestions') or extract_suggestions(reply_text)
            logger.info(f"⚡ [Semantic RAG] Local Hit [{rag_match['id']}] (Score: {rag_match['score']:.4f}, Intent: {detected_intent})")
            record_interaction(user_message, detected_intent, confidence, 'semantic_rag', language)

            # บันทึกประวัติสนทนาเพื่อความต่อเนื่องของบริบทข้ามรอบ (Multi-turn Context Buffer)
            if session_id not in state.chat_histories:
                state.chat_histories[session_id] = []
            state.chat_histories[session_id].append({'role': 'user', 'parts': [{'text': user_message}]})
            state.chat_histories[session_id].append({'role': 'model', 'parts': [{'text': reply_text}]})
            if len(state.chat_histories[session_id]) > 12:
                state.chat_histories[session_id] = state.chat_histories[session_id][-12:]
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
                rag_score=rag_match['score']
            )

        local_reply = match_local_knowledge(user_message, detected_intent, confidence, language)
        if local_reply:
            logger.info(f"⚡ [Hybrid AI] Direct Local Response (Intent: {detected_intent}, Conf: {confidence:.2f})")
            record_interaction(user_message, detected_intent, confidence, 'local_model', language)
            suggestions = extract_suggestions(local_reply)

            # บันทึกประวัติสนทนาเพื่อความต่อเนื่องของบริบทข้ามรอบ (Multi-turn Context Buffer)
            if session_id not in state.chat_histories:
                state.chat_histories[session_id] = []
            state.chat_histories[session_id].append({'role': 'user', 'parts': [{'text': user_message}]})
            state.chat_histories[session_id].append({'role': 'model', 'parts': [{'text': local_reply}]})
            if len(state.chat_histories[session_id]) > 12:
                state.chat_histories[session_id] = state.chat_histories[session_id][-12:]
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

    # 3. RAG-Augmented Local SLM (Ollama)
    if not force_llm:
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
                    reply_text = slm_result['reply']
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
                        base_emotion=target_emotion
                    )
        except ImportError:
            pass

    # 4. Google Gemini 2.5 Flash Cloud AI (ประมวลผลคำตอบและการสนทนาขั้นสูง)
    if is_gemini_available():
        try:
            rag_top = semantic_retriever.retrieve(user_message, intent=detected_intent)
            rag_ctx = rag_top['reply'] if rag_top else None
            gemini_reply = generate_gemini_response(
                user_message=user_message,
                history=state.chat_histories.get(session_id),
                rag_context=rag_ctx,
                language=language
            )
            if gemini_reply:
                suggestions = extract_suggestions(gemini_reply)
                logger.info(f"✨ [Gemini 2.5 Flash] Response (Intent: {detected_intent}, Conf: {confidence:.2f})")
                record_interaction(user_message, detected_intent, confidence, 'gemini_flash', language)

                if session_id not in state.chat_histories:
                    state.chat_histories[session_id] = []
                state.chat_histories[session_id].append({'role': 'user', 'parts': [{'text': user_message}]})
                state.chat_histories[session_id].append({'role': 'model', 'parts': [{'text': gemini_reply}]})
                if len(state.chat_histories[session_id]) > 12:
                    state.chat_histories[session_id] = state.chat_histories[session_id][-12:]

                return send_chat_response(
                    user_message=user_message,
                    reply_text=gemini_reply,
                    suggestions=suggestions,
                    engine='gemini_flash',
                    detected_intent=detected_intent,
                    intent_th=intent_th,
                    confidence=confidence,
                    source='gemini_2.5_flash',
                    language=language,
                    base_emotion=target_emotion
                )
        except Exception as ge:
            logger.warning(f"⚠️ Gemini chat processing error ({ge}) -> fallback to offline")

    # 5. Pure Offline Intelligent Knowledge & Semantic RAG Response
    reply_text = get_local_knowledge_reply(user_message, language, intent=detected_intent)
    suggestions = extract_suggestions(reply_text)
    record_interaction(user_message, detected_intent, confidence, 'offline_local_ai', language)

    if session_id not in state.chat_histories:
        state.chat_histories[session_id] = []
    state.chat_histories[session_id].append({'role': 'user', 'parts': [{'text': user_message}]})
    state.chat_histories[session_id].append({'role': 'model', 'parts': [{'text': reply_text}]})
    if len(state.chat_histories[session_id]) > 12:
        state.chat_histories[session_id] = state.chat_histories[session_id][-12:]

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

@chat_bp.route('/match_course', methods=['POST'])
def match_course():
    data = request.json or {}
    interests = data.get('interests', '')
    strengths = data.get('strengths', '')
    dream_job = data.get('dream_job', '')
    
    text = (interests + " " + strengths + " " + dream_job).lower()
    if any(k in text for k in ['คอม', 'ไอที', 'โปรแกรม', 'เกม', 'เว็บ', 'it', 'computer', 'ai', 'ดิจิทัล', 'เทคโน', 'กราฟิก']):
        rec = (
            "🎓 **ผลการวิเคราะห์หลักสูตรที่เหมาะสมกับคุณ (Future Career Blueprint)**\n\n"
            "🏆 **[Top Recommended Major]:** **สาขาวิชาเทคโนโลยีธุรกิจดิจิทัล / เทคโนโลยีสารสนเทศ (Match Score: 98%)**\n\n"
            "🎯 **[Why You Fit]:** คุณมีความสนใจและจุดเด่นด้านเทคโนโลยี ดิจิทัล และคอมพิวเตอร์ ซึ่งตรงกับทักษะศตวรรษที่ 21 ที่ตลาดแรงงานต้องการสูงสุด\n\n"
            "🚀 **[Core Superpowers]:**\n"
            "• พัฒนาเว็บไซต์ แอปพลิเคชัน และระบบ AI อัจฉริยะ\n"
            "• การบริหารจัดการข้อมูล การตลาดดิจิทัล และอีคอมเมิร์ซ\n"
            "• กราฟิกดีไซน์ มัลติมีเดีย และคอนเทนต์สร้างสรรค์\n\n"
            "💼 **[Career Paths & Salaries]:** นักพัฒนาเว็บ/ซอฟต์แวร์, นักการตลาดดิจิทัล, เจ้าหน้าที่ไอที (เงินเดือนเริ่มต้น 18,000 - 35,000+ บาท)\n\n"
            "🥈 **[Alternative Major]:** สาขาวิชาการบัญชีดิจิทัล (Digital Accounting)"
        )
    elif any(k in text for k in ['อาหาร', 'ทำอาหาร', 'ขนม', 'ครัว', 'เชฟ', 'cook', 'chef', 'เบเกอรี่', 'food']):
        rec = (
            "🎓 **ผลการวิเคราะห์หลักสูตรที่เหมาะสมกับคุณ (Future Career Blueprint)**\n\n"
            "🏆 **[Top Recommended Major]:** **สาขาวิชาอาหารและโภชนาการ (Match Score: 97%)**\n\n"
            "🎯 **[Why You Fit]:** เพชรบุรีคือเมืองสร้างสรรค์ด้านอาหารของ UNESCO (City of Gastronomy) การเรียนด้านอาหารที่ PBVC จะปลดล็อกศักยภาพสู่การเป็นเชฟมืออาชีพ\n\n"
            "🚀 **[Core Superpowers]:**\n"
            "• ศิลปะการประกอบอาหารไทยฟิวชั่น และอาหารตะวันตก\n"
            "• เทคนิคการทำเบเกอรี่ ขนมไทย และของหวานชาววังชั้นสูง\n"
            "• การจัดการธุรกิจร้านอาหารและการควบคุมต้นทุน\n\n"
            "💼 **[Career Paths & Salaries]:** เชฟภัตตาคาร, ผู้เชี่ยวชาญด้านอาหาร, เจ้าของคาเฟ่/ธุรกิจอาหาร (เงินเดือนเริ่มต้น 18,000 - 40,000+ บาท)\n\n"
            "🥈 **[Alternative Major]:** สาขาวิชาการโรงแรม (Hotel Management)"
        )
    elif any(k in text for k in ['โรงแรม', 'บริการ', 'ท่องเที่ยว', 'มัคคุเทศก์', 'ไกด์', 'tour', 'hotel']):
        rec = (
            "🎓 **ผลการวิเคราะห์หลักสูตรที่เหมาะสมกับคุณ (Future Career Blueprint)**\n\n"
            "🏆 **[Top Recommended Major]:** **สาขาวิชาการโรงแรมและการท่องเที่ยว (Match Score: 96%)**\n\n"
            "🎯 **[Why You Fit]:** เหมาะกับผู้มีใจรักงานบริการ มนุษยสัมพันธ์ยอดเยี่ยม และต้องการทำงานในอุตสาหกรรมการท่องเที่ยวระดับสากล\n\n"
            "🚀 **[Core Superpowers]:**\n"
            "• การบริหารงานส่วนหน้าโรงแรมและงานบริการลูกค้าระดับ 5 ดาว\n"
            "• ทักษะการสื่อสารภาษาต่างประเทศ (อังกฤษ จีน)\n"
            "• การจัดนำเที่ยวและมัคคุเทศก์มืออาชีพ\n\n"
            "💼 **[Career Paths & Salaries]:** ผู้จัดการงานโรงแรม, เจ้าหน้าที่สายการบิน, มัคคุเทศก์ (เงินเดือนเริ่มต้น 17,000 - 35,000+ บาท)\n\n"
            "🥈 **[Alternative Major]:** สาขาวิชาการตลาด (Digital Marketing)"
        )
    else:
        rec = (
            "🎓 **ผลการวิเคราะห์หลักสูตรที่เหมาะสมกับคุณ (Future Career Blueprint)**\n\n"
            "🏆 **[Top Recommended Major]:** **สาขาวิชาการบัญชี / การตลาดดิจิทัล (Match Score: 95%)**\n\n"
            "🎯 **[Why You Fit]:** เป็นสาขาวิชาหลักที่ทุกองค์กรและทุกธุรกิจต้องการตัวมากที่สุด พร้อมโอกาสต่อยอดเป็นผู้ประกอบการรุ่นใหม่\n\n"
            "🚀 **[Core Superpowers]:**\n"
            "• การวางแผนกลยุทธ์ธุรกิจและบริหารการเงินอย่างเป็นระบบ\n"
            "• การใช้ระบบคอมพิวเตอร์และ AI ช่วยวิเคราะห์ข้อมูลการตลาด\n"
            "• การสร้างแบรนด์และการค้าออนไลน์ในยุคดิจิทัล\n\n"
            "💼 **[Career Paths & Salaries]:** นักการเงินการบัญชี, ที่ปรึกษาธุรกิจ, ผู้ประกอบการออนไลน์ (เงินเดือนเริ่มต้น 16,000 - 30,000+ บาท)\n\n"
            "🥈 **[Alternative Major]:** สาขาวิชาเทคโนโลยีธุรกิจดิจิทัล"
        )
    return jsonify({'recommendation': rec, 'status': 'success', 'engine': 'offline_course_matcher'})

@chat_bp.route('/reset', methods=['POST'])
def reset():
    session_id = session.get('session_id')
    if session_id and session_id in state.chat_histories:
        del state.chat_histories[session_id]
    session['session_id'] = str(uuid.uuid4())
    return jsonify({'status': 'reset_complete'})

