#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local SLM (Small Language Model) Module สำหรับ "น้องเพชร AI Smart Guide"
ใช้ Ollama + Qwen 2.5 (1.5B) รันภายในเครื่อง 100% On-Device AI
ประมวลผลผ่าน GPU ในเครื่อง (เช่น GTX 1050 Ti) หรือ CPU
ทำงานแบบ Offline ได้สมบูรณ์ ไม่ต้องพึ่งพา Cloud AI ใดๆ
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
import time
import httpx
from typing import Optional, Dict, Any, List

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# ระบุโมเดลเองได้ด้วย LOCAL_SLM_MODEL (ถ้าตั้งไว้และติดตั้งอยู่ จะใช้ตัวนี้เสมอ)
EXPLICIT_MODEL = os.environ.get("LOCAL_SLM_MODEL", "").strip()
DEFAULT_MODEL = EXPLICIT_MODEL or "qwen2.5:1.5b"
# ลำดับเลือกอัตโนมัติ: เฉพาะโมเดลเล็กที่รันบน Raspberry Pi 5 ได้ลื่น
# (โมเดล 3B ขึ้นไป เช่น gemma3:4b / typhoon2 ช้าและกิน RAM จนเครื่องค้างได้ ต้องเลือกเองผ่าน LOCAL_SLM_MODEL)
PREFERRED_MODEL_ORDER = ["nongphet-custom", "qwen2.5:1.5b"]

# ปิด Local SLM ทั้งหมดได้ด้วย LOCAL_SLM_ENABLED=0 (แชทจะตอบจากฐานความรู้ในเครื่องอย่างเดียว เร็วที่สุด)
LOCAL_SLM_ENABLED = os.environ.get("LOCAL_SLM_ENABLED", "1").lower() not in ("0", "false", "no", "off")
# จำกัดความยาวคำตอบและเวลารอ เพื่อไม่ให้หน้าจอค้างนานบน CPU ของ Pi
MAX_TOKENS = int(os.environ.get("LOCAL_SLM_MAX_TOKENS", "160"))
REQUEST_TIMEOUT = float(os.environ.get("LOCAL_SLM_TIMEOUT", "20"))
# ให้ Ollama ค้างโมเดลไว้ในหน่วยความจำ ไม่ต้องโหลดใหม่ทุกคำถาม (โหลดใหม่ใช้เวลาหลายวินาที)
KEEP_ALIVE = os.environ.get("LOCAL_SLM_KEEP_ALIVE", "30m")
# จำนวนเธรด CPU ที่ Ollama ใช้ (0 = ให้ Ollama เลือกเอง) แนะนำ 3 บน Pi 5 เพื่อเหลือ 1 คอร์ให้ระบบอื่น
NUM_THREADS = int(os.environ.get("LOCAL_SLM_THREADS", "0"))

# แคชผลการเช็ก Ollama กันยิง HTTP ซ้ำหลายรอบต่อหนึ่งคำถาม
_STATUS_TTL = 10.0
_MODELS_TTL = 60.0
SLOW_BACKOFF_SEC = 60.0
_status_cache = {"ts": 0.0, "running": False}
_models_cache = {"ts": 0.0, "models": []}

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


def _fetch_tags(host: str):
    """เรียก /api/tags ครั้งเดียว แล้วอัปเดตแคชทั้งสถานะและรายชื่อโมเดล"""
    now = time.time()
    try:
        res = httpx.get(f"{host}/api/tags", timeout=1.5)
        running = res.status_code == 200
        models = [m.get("name") for m in res.json().get("models", [])] if running else []
    except Exception:
        running, models = False, []
    _status_cache.update(ts=now, running=running)
    if running:
        _models_cache.update(ts=now, models=models)
    return running


def is_ollama_running(host: str = OLLAMA_HOST) -> bool:
    """ตรวจสอบว่า Ollama service กำลังทำงานอยู่หรือไม่ (แคชผล 10 วินาที)"""
    if not LOCAL_SLM_ENABLED:
        return False
    if time.time() - _status_cache["ts"] < _STATUS_TTL:
        return _status_cache["running"]
    return _fetch_tags(host)


def get_available_local_models(host: str = OLLAMA_HOST) -> list:
    """ดึงรายการโมเดลทั้งหมดที่ดาวน์โหลดไว้ในเครื่อง (แคชผล 60 วินาที)"""
    if time.time() - _models_cache["ts"] >= _MODELS_TTL:
        _fetch_tags(host)
    return list(_models_cache["models"])


def select_best_local_model(requested_model: str = DEFAULT_MODEL, host: str = OLLAMA_HOST) -> str:
    """เลือกโมเดล Local SLM: ใช้ LOCAL_SLM_MODEL ถ้าระบุไว้ ไม่งั้นเลือกโมเดลเล็กตามลำดับที่กำหนด"""
    installed = get_available_local_models(host)
    if not installed:
        return requested_model
    if EXPLICIT_MODEL:
        for m in installed:
            if m == EXPLICIT_MODEL or m.startswith(EXPLICIT_MODEL + ":") or m.split(":")[0] == EXPLICIT_MODEL:
                return m
    for candidate in PREFERRED_MODEL_ORDER:
        for m in installed:
            if m.startswith(candidate):
                return m
    # ไม่หยิบโมเดลอื่นที่ติดตั้งไว้มาใช้เอง (อาจเป็นโมเดลใหญ่ที่ทำให้ Pi ค้าง) ถ้าไม่มีโมเดลที่รองรับ
    # Ollama จะตอบ 404 แล้วแชทจะตอบจากฐานความรู้ในเครื่องแทน
    return requested_model


def generate_local_response(
    prompt: str,
    system_prompt: str = NONGPHET_SYSTEM_PROMPT,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
    timeout: Optional[float] = None,
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
        options = {
            "temperature": 0.7 if is_creative else 0.5,
            "top_p": 0.9,
            "num_predict": MAX_TOKENS
        }
        if NUM_THREADS > 0:
            options["num_thread"] = NUM_THREADS
        payload = {
            "model": active_model,
            "messages": messages,
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": options
        }

        response = httpx.post(
            f"{host}/api/chat",
            json=payload,
            timeout=timeout if timeout is not None else REQUEST_TIMEOUT
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
    except httpx.TimeoutException:
        # เครื่องช้าเกินไป (CPU เต็ม/โมเดลใหญ่) -> พัก Local SLM ชั่วคราว ให้คำถามถัดไปตอบจากฐานความรู้ทันทีแทนการรอซ้ำ
        _status_cache.update(ts=time.time() + SLOW_BACKOFF_SEC, running=False)
        print(f"⚠️ [Local SLM] ตอบช้าเกิน {timeout if timeout is not None else REQUEST_TIMEOUT:g}s -> พักใช้ {SLOW_BACKOFF_SEC:g}s")
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
