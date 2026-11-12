#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
สคริปต์สร้างชุดข้อมูล Fine-tuning (.jsonl) และ Ollama Modelfile สำหรับ "น้องเพชร AI Smart Guide"
1. สร้างไฟล์ ml_artifacts/nongphet_finetune.jsonl (รูปแบบ ChatML สำหรับ Unsloth / LoRA Fine-tuning บน Colab ฟรี)
2. สร้างไฟล์ Modelfile สำหรับรันคำสั่ง `ollama create nongphet-custom -f Modelfile` ได้ทันที
"""

import os
import json
from local_slm import NONGPHET_SYSTEM_PROMPT

OUTPUT_DIR = "ml_artifacts"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_finetune_dataset():
    kb_path = "knowledge_base.json"
    if not os.path.exists(kb_path):
        print(f"❌ ไม่พบไฟล์ {kb_path}")
        return 0

    with open(kb_path, "r", encoding="utf-8") as f:
        kb_data = json.load(f)

    records = []
    for entry in kb_data.get("entries", []):
        answer = entry.get("answer", "").strip()
        suggestions = entry.get("suggestions", [])
        if suggestions and "ถามต่อยอดกับน้องเพชร" not in answer:
            sug_lines = "\n".join([f"• {s}" for s in suggestions])
            full_answer = f"{answer}\n\n---\n💡 **ถามต่อยอดกับน้องเพชร:**\n{sug_lines}"
        else:
            full_answer = answer

        for q in entry.get("questions", []):
            records.append({
                "messages": [
                    {"role": "system", "content": NONGPHET_SYSTEM_PROMPT},
                    {"role": "user", "content": q.strip()},
                    {"role": "assistant", "content": full_answer}
                ]
            })

    jsonl_path = os.path.join(OUTPUT_DIR, "nongphet_finetune.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as out:
        for rec in records:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"✅ สร้างชุดข้อมูล Fine-tune (.jsonl) สำเร็จ: {jsonl_path} ({len(records)} คู่บทสนทนา)")
    return len(records)


def build_ollama_modelfile():
    modelfile_content = f"""FROM qwen2.5:1.5b
PARAMETER temperature 0.6
PARAMETER top_p 0.9
PARAMETER num_ctx 4096

SYSTEM \"\"\"{NONGPHET_SYSTEM_PROMPT}\"\"\"
"""
    modelfile_path = "Modelfile"
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile_content)
    print(f"✅ สร้างไฟล์ {modelfile_path} สำเร็จ (สามารถรัน `ollama create nongphet-custom -f Modelfile` เพื่อสร้างโมเดลเฉพาะตัว)")


if __name__ == "__main__":
    build_finetune_dataset()
    build_ollama_modelfile()

