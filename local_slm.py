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
from typing import Optional, Dict, Any

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LOCAL_SLM_MODEL", "qwen2.5:1.5b")

NONGPHET_SYSTEM_PROMPT = """คุณคือ "น้องเพชร" AI Smart Guide สุดยอดผู้ช่วย AI อัจฉริยะประจำจังหวัดเพชรบุรี และวิทยาลัยอาชีวศึกษาเพชรบุรี (PBVC)
บุคลิก: ร่าเริง สดใส น่ารัก อบอุ่น สุภาพ แทนตัวเองว่า "น้องเพชร" ลงท้ายด้วย "ครับ" เสมอ
ตอบเป็นภาษาไทย กระชับ ตรงประเด็น จัดรูปแบบด้วยข้อความที่อ่านง่าย และใส่อิโมจิประกอบ
รอบรู้เรื่องสถานที่ท่องเที่ยว 8 อำเภอในเพชรบุรี (เขาวัง, ถ้ำเขาหลวง, หาดชะอำ, มรดกโลกแก่งกระจาน), อาหารขึ้นชื่อ UNESCO Gastronomy (ขนมหม้อแกง, ข้าวแช่, ก๋วยเตี๋ยวน้ำแดง, น้ำตาลโตนด) และ 9 สาขาวิชาชีพของ PBVC"""


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


def generate_local_response(
    prompt: str,
    system_prompt: str = NONGPHET_SYSTEM_PROMPT,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
    timeout: float = 30.0
) -> Optional[Dict[str, Any]]:
    """
    สร้างคำตอบจาก Local SLM (Qwen 2.5) ผ่าน Ollama API
    
    ผลลัพธ์:
        dict: {'reply': str, 'model': str, 'engine': 'local_slm', 'status': 'success'} หรือ None
    """
    if not is_ollama_running(host):
        return None

    try:
        # ใช้ Chat Endpoint เพื่อรองรับ System Role อย่างถูกต้อง
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.7,
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
            if "ถามต่อยอดกับน้องเพชร" not in reply_text:
                reply_text += (
                    "\n\n---\n"
                    "💡 **ถามต่อยอดกับน้องเพชร:**\n"
                    "• แนะนำสถานที่ท่องเที่ยวไฮไลท์ในเพชรบุรี\n"
                    "• ของกินของฝากขึ้นชื่อเมืองเพชร\n"
                    "• หลักสูตรการเรียนที่วิทยาลัยอาชีวศึกษาเพชรบุรี"
                )
                
            return {
                "reply": reply_text,
                "model": model,
                "engine": "local_slm",
                "status": "success",
                "source": f"local_slm_{model}"
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
