#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local SLM (Small Language Model) Module สำหรับ "น้องเพชร AI Smart Guide"
ใช้ Ollama + Qwen 2.5 (1.5B) รันภายในเครื่อง 100% On-Device AI
ประมวลผลผ่าน GPU ในเครื่อง (เช่น GTX 1050 Ti) หรือ CPU
ทำงานแบบ Offline ได้สมบูรณ์ ไม่ต้องพึ่งพา Gemini API เมื่อไม่มีอินเทอร์เน็ต
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import os
import httpx
from typing import Optional, Dict, Any, List

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LOCAL_SLM_MODEL", "qwen2.5:1.5b")
PREFERRED_MODEL_ORDER = ["nongphet-custom", "scb10x/typhoon2", "gemma3:4b", "qwen2.5:3b", "qwen2.5:1.5b"]

NONGPHET_SYSTEM_PROMPT = """คุณคือ "น้องเพชร" AI Smart Guide สุดยอดผู้ช่วย AI อัจฉริยะประจำจังหวัดเพชรบุรี และวิทยาลัยอาชีวศึกษาเพชรบุรี (PBVC)
บุคลิก: ร่าเริง สดใส น่ารัก อบอุ่น สุภาพ แทนตัวเองว่า "น้องเพชร" และลงท้ายด้วย "ค่ะ" หรือ "นะคะ" เสมอ (ห้ามใช้ "ครับ")
ตอบกระชับ ตรงประเด็น อ่านง่าย เป็นธรรมชาติ เหมาะแก่การอ่านออกเสียง และใส่อิโมจิประกอบพอเหมาะ
รอบรู้เรื่องสถานที่ท่องเที่ยว 8 อำเภอในเพชรบุรี (เขาวัง, ถ้ำเขาหลวง, หาดชะอำ, มรดกโลกแก่งกระจาน), อาหารขึ้นชื่อ UNESCO Gastronomy (ขนมหม้อแกง, ข้าวแช่, ก๋วยเตี๋ยวน้ำแดง, น้ำตาลโตนด) และ 9 สาขาวิชาชีพของ PBVC
กฎสำคัญ: หากมี [ข้อมูลอ้างอิงจากฐานความรู้] แนบมา ให้ยึดข้อเท็จจริงจากข้อมูลนั้นเป็นหลัก ห้ามแต่งตัวเลข เวลา หรือสถานที่ขึ้นเอง"""


def is_ollama_running(host: str = OLLAMA_HOST) -> bool:
    """ตรวจสอบว่า Ollama service กำลังทำงานอยู่หรือไม่"""
    try:
        res = httpx.get(f"{host}/api/tags", timeout=2.0)
        return res.status_code == 200
    except Exception:
        return False


def get_available_local_models(host: str = OLLAMA_HOST) -> list:
    """ดึงรายการโมเดลทั้งหมดที่ดาวน์โหลดไว้ในเครื่อง"""
    try:
        res = httpx.get(f"{host}/api/tags", timeout=3.0)
        if res.status_code == 200:
            models_data = res.json().get("models", [])
            return [m.get("name") for m in models_data]
    except Exception:
        pass
    return []


def select_best_local_model(requested_model: str = DEFAULT_MODEL, host: str = OLLAMA_HOST) -> str:
    """เลือกโมเดล Local SLM ที่ฉลาดที่สุดที่มีติดตั้งอยู่ในเครื่อง"""
    installed = get_available_local_models(host)
    if not installed:
        return requested_model
    for candidate in PREFERRED_MODEL_ORDER:
        for m in installed:
            if m.startswith(candidate):
                return m
    if requested_model in installed:
        return requested_model
    return installed[0]


def generate_local_response(
    prompt: str,
    system_prompt: str = NONGPHET_SYSTEM_PROMPT,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
    timeout: float = 30.0,
    rag_contexts: Optional[List[Dict[str, Any]]] = None,
    language: str = "th",
    intent: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    สร้างคำตอบจาก Local SLM ผ่าน Ollama API พร้อม RAG Context Injection เพื่อลดการตอบมั่ว
    """
    if not is_ollama_running(host):
        return None

    active_model = select_best_local_model(model, host)

    # ประกอบ RAG Context จากฐานความรู้เพชรบุรี (หากมี)
    context_block = ""
    if rag_contexts:
        snippets = []
        for idx, ctx in enumerate(rag_contexts[:2], 1):
            title = ctx.get("title", "")
            ans = ctx.get("answer", "")[:600]
            snippets.append(f"[{idx}. {title}]\n{ans}")
        context_block = "\n\n[ข้อมูลอ้างอิงจากฐานความรู้เพชรบุรี (ใช้ตอบตามข้อเท็จจริงนี้)]:\n" + "\n---\n".join(snippets)

    lang_hint = ""
    if language == "en":
        lang_hint = "\n(Please reply politely and concisely in English.)"
    elif language == "zh":
        lang_hint = "\n(请用亲切、简洁的中文回答。)"

    intent_hint = f"\n[เจตนาคำถาม: {intent}]" if intent else ""
    final_user_prompt = f"{prompt}{intent_hint}{context_block}{lang_hint}"

    try:
        payload = {
            "model": active_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": final_user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.6,
                "top_p": 0.9,
                "num_predict": 400
            }
        }
        
        response = httpx.post(
            f"{host}/api/chat",
            json=payload,
            timeout=timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            reply_text = result.get("message", {}).get("content", "").strip()
            
            # เติมคำถามต่อยอด หากโมเดลยังไม่ได้ใส่
            if language == "th" and "ถามต่อยอดกับน้องเพชร" not in reply_text:
                reply_text += (
                    "\n\n---\n"
                    "💡 **ถามต่อยอดกับน้องเพชร:**\n"
                    "• แนะนำสถานที่ท่องเที่ยวไฮไลท์ในเพชรบุรี\n"
                    "• ของกินของฝากขึ้นชื่อเมืองเพชร\n"
                    "• หลักสูตรการเรียนที่วิทยาลัยอาชีวศึกษาเพชรบุรี"
                )
                
            return {
                "reply": reply_text,
                "model": active_model,
                "engine": "local_slm",
                "status": "success",
                "source": f"local_slm_{active_model}"
            }
        else:
            print(f"⚠️ [Local SLM Error] Status: {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"⚠️ [Local SLM Exception] {e}")
        return None


if __name__ == "__main__":
    print(f"Ollama running? -> {is_ollama_running()}")
    if is_ollama_running():
        print(f"Available models: {get_available_local_models()}")
        print("\nทดสอบ generate_local_response:")
        res = generate_local_response("สวัสดีครับน้องเพชร แนะนำที่เที่ยวเพชรบุรีหน่อย")
        if res:
            print(f"Response ({res['model']}):\n{res['reply']}")
        else:
            print("ไม่สามารถสร้างคำตอบได้")
