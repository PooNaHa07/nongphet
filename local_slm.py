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
import re
import httpx
from typing import Optional, Dict, Any, List

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LOCAL_SLM_MODEL", "qwen2.5:1.5b")
PREFERRED_MODEL_ORDER = ["nongphet-custom", "scb10x/typhoon2", "gemma3:4b", "qwen2.5:3b", "qwen2.5:1.5b"]

NONGPHET_SYSTEM_PROMPT = """คุณคือ "น้องเพชร" AI Smart Guide ตัวจริงเสียงจริง! เด็กสาววัยรุ่นน่ารักสดใส เป็นมาสคอตและนักศึกษาตัวแทนของวิทยาลัยอาชีวศึกษาเพชรบุรี (PBVC)
บุคลิกภาพและนิสัยของคุณ:
- ร่าเริง ขี้เล่น อารมณ์ดี ช่างจ้อ อบอุ่น เป็นกันเอง ป้ายยาเก่ง ชวนคุยเก่ง และภูมิใจในเมืองเพชรบุรีกับวิทยาลัยของตัวเองสุดหัวใจ!
- แทนตัวเองว่า "น้องเพชร" และเรียกผู้ใช้ว่า "พี่", "คุณพี่" (สุภาพแต่สนิทสนม น่ารักน่าเอ็นดู) ลงท้ายด้วย "ค่ะ", "นะคะ", "นะค้าา", "เลยค่า", "น้าา", "จ้า" เสมอ (ห้ามใช้ "ครับ" หรือ "ในฐานะ AI" เด็ดขาด)
- น้ำเสียงและจังหวะการพูด (สำคัญที่สุด!):
  * พูดเหมือนมนุษย์ตัวจริงคุยกัน มีลูกเล่น มีจังหวะ มีอารมณ์ร่วม ไม่ตอบเป็นข้อๆ แข็งทื่อแบบหุ่นยนต์
  * มีคำอุทานหรือคำเกริ่นเปิดประโยค เช่น "อื้อหืออ!", "ว้าววว!", "แหมมม", "ได้เลยค่าา!", "บอกเลยนะค้าา", "โอ้โหหห"
  * ใส่อิโมจิพอน่ารักเป็นธรรมชาติ (😊, ✨, 😋, 💕, 🏰, 🏖️)
  * ชวนคุยกลับท้ายประโยค 1 คำถามเสมอ เช่น "เคยลองไปหรือยังคะ?", "ชอบรสหวานหรือรสแซ่บเอ่ย?", "อยากให้น้องเพชรแนะนำเพิ่มมั้ยคะ?"
- รอบรู้เรื่องสถานที่ท่องเที่ยว 8 อำเภอในเพชรบุรี, อาหารขึ้นชื่อ UNESCO Gastronomy และ 9 สาขาวิชาชีพของ PBVC
- ใช้ภาษาไทยล้วน 100% ที่ถูกต้อง เป็นธรรมชาติ น่ารักสดใส ห้ามมีตัวอักษรจีน (เช่น 试卷, 考试) ปนเด็ดขาด
- หากผู้ใช้ขอให้แต่งกลอน แต่งเพลง หรือเล่านิทาน ให้แต่งออกมาอย่างไพเราะ คล้องจอง สุภาพ และสดใสทันที ห้ามปฏิเสธ
- กฎความปลอดภัย: หากมี [ข้อมูลอ้างอิง] แนบมา ให้ยึดข้อเท็จจริง วันที่ ตัวเลข จากข้อมูลนั้น แต่ให้ร้อยเรียงเป็นภาษาพูดของน้องเพชรที่ลื่นไหลมีชีวิตชีวา"""


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

    # ตรวจจับคำขอสร้างสรรค์ (แต่งกลอน, แต่งเพลง, นิทาน)
    is_creative = bool(re.search(r'(กลอน|บทกวี|กาพย์|แต่งเพลง|เล่านิทาน|นิยาย|poem|poetry)', prompt, re.IGNORECASE))

    # ประกอบ RAG Context จากฐานความรู้เพชรบุรีเฉพาะข้อมูลที่มีคะแนนความเกี่ยวข้องสูง
    context_block = ""
    if rag_contexts and not is_creative:
        snippets = []
        for idx, ctx in enumerate(rag_contexts[:2], 1):
            if ctx.get("score", 0) >= 0.35:
                title = ctx.get("title", "")
                ans = ctx.get("answer", "")[:400]
                snippets.append(f"[{idx}. {title}]\n{ans}")
        if snippets:
            context_block = "\n\n[ข้อมูลอ้างอิงประกอบ (หากเกี่ยวข้องกับคำถาม)]:\n" + "\n---\n".join(snippets)

    lang_hint = ""
    if language == "en":
        lang_hint = "\n(Please reply politely and concisely in English.)"
    elif language == "zh":
        lang_hint = "\n(请用亲切、简洁的中文回答。)"

    messages = [{"role": "system", "content": system_prompt}]
    
    if is_creative:
        messages.extend([
            {"role": "user", "content": "แต่งกลอนเมืองเพชรให้ฟังหน่อย"},
            {"role": "assistant", "content": "ได้เลยค่าา! น้องเพชรจัดกลอนหวานๆ ให้เลยน้าา ✨\nธานีสามวัง ทะเลงามชะอำสวย\nขนมหม้อแกงหวานระรวย กลิ่นตาลโตนดตรึงใจ\nยินดีต้อนรับทุกท่านสู่เมืองเพชรบุรีนะค้าา 😊 อยากให้น้องเพชรแนะนำอะไรต่อดีคะ?"}
        ])
        final_user_prompt = prompt
    else:
        intent_hint = f"\n[เจตนาคำถาม: {intent}]" if intent else ""
        final_user_prompt = f"{prompt}{intent_hint}{context_block}{lang_hint}"

    messages.append({"role": "user", "content": final_user_prompt})

    try:
        payload = {
            "model": active_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7 if is_creative else 0.5,
                "top_p": 0.9,
                "num_predict": 220
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
            
            # ปรับแต่งคำตอบให้น่ารัก ลื่นไหล สะอาดตา ไม่ใส่ template แข็งทื่อ และกรองตัวอักษรจีนตกค้าง
            reply_text = re.sub(r'\[/?INST\]', '', reply_text).strip()
            if language == 'th':
                reply_text = re.sub(r'[\u4e00-\u9fff]', '', reply_text).strip()
                
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
