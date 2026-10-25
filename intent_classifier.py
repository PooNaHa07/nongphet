#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
โมดูลสำหรับโหลดโมเดล Machine Learning (model.pkl และ vectorizer.pkl)
เพื่อทำนายหมวดหมู่เจตนาของผู้ใช้ (Intent Classification) พร้อมคำนวณค่าความมั่นใจ (Confidence Score)
ใช้งานร่วมกับระบบ Hybrid AI ของ "น้องเพชร AI Smart Guide"
"""

import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import joblib
import numpy as np
from pythainlp.tokenize import word_tokenize
from pythainlp.util import normalize


def thai_text_tokenizer(text):
    """
    ฟังก์ชันตัดคำภาษาไทย (ต้องมีชื่อและโครงสร้างเดียวกับตอนฝึกสอนโมเดลใน train_intent.py)
    """
    if not isinstance(text, str):
        return []
    cleaned = normalize(text.strip().lower())
    tokens = word_tokenize(cleaned, engine="newmm", keep_whitespace=False)
    return [t for t in tokens if len(t.strip()) > 0]


class NongPhetIntentClassifier:
    """
    คลาสตัวจัดการโมเดลจำแนกเจตนาคำถามภาษาไทยภายในเครื่อง (Local ML Inference Engine)
    """

    # คำอธิบายชื่อหมวดหมู่ภาษาไทยสำหรับนำไปแสดงผลบนหน้าจอ UI หรือส่งต่อใน System Prompt
    INTENT_DESCRIPTIONS = {
        "travel": "การท่องเที่ยวและสถานที่สำคัญในจังหวัดเพชรบุรี",
        "food": "อาหารพื้นเมือง ขนมหวาน และของฝากเมืองเพชร",
        "admission": "แนะแนวศึกษาต่อ หลักสูตร และการรับสมัคร วิทยาลัยอาชีวศึกษาเพชรบุรี",
        "greeting": "การทักทาย แนะนำตัว และการสนทนาทั่วไป",
        "general_faq": "ข้อมูลทั่วไป สภาพอากาศ การเดินทาง และสิ่งอำนวยความสะดวก"
    }

    def __init__(self, model_path="model.pkl", vectorizer_path="vectorizer.pkl"):
        self.model = None
        self.vectorizer = None
        self.is_ready = False

        # ตรวจสอบทั้งในโฟลเดอร์ปัจจุบันและในโฟลเดอร์ ml_artifacts
        if not os.path.exists(model_path) and os.path.exists(os.path.join("ml_artifacts", model_path)):
            model_path = os.path.join("ml_artifacts", model_path)
        if not os.path.exists(vectorizer_path) and os.path.exists(os.path.join("ml_artifacts", vectorizer_path)):
            vectorizer_path = os.path.join("ml_artifacts", vectorizer_path)

        self._load_artifacts(model_path, vectorizer_path)

    def _load_artifacts(self, model_path, vectorizer_path):
        """โหลดไฟล์โมเดลและตัวแปลงเวกเตอร์เข้าสู่หน่วยความจำ"""
        try:
            if not os.path.exists(model_path) or not os.path.exists(vectorizer_path):
                print(f"[Warning] ไม่พบไฟล์ {model_path} หรือ {vectorizer_path} กรุณารัน python train_intent.py ก่อน")
                return

            # ป้องกันปัญหา Pickle ModuleMismatch เมื่อโหลด vectorizer จากโมดูลอื่น
            import __main__
            if not hasattr(__main__, 'thai_text_tokenizer'):
                __main__.thai_text_tokenizer = thai_text_tokenizer

            self.vectorizer = joblib.load(vectorizer_path)
            self.model = joblib.load(model_path)
            self.is_ready = True
            print("✅ [Local ML] โหลดโมเดลจำแนกเจตนา (Intent Classifier) สำเร็จพร้อมใช้งาน")
        except Exception as e:
            print(f"❌ [Local ML Error] เกิดข้อผิดพลาดในการโหลดโมเดล: {e}")
            self.is_ready = False

    def predict(self, text: str) -> dict:
        """
        ทำนายหมวดหมู่เจตนา (Intent) จากข้อความภาษาไทยของผู้ใช้
        
        พารามิเตอร์:
            text (str): ข้อความคำถามจากผู้ใช้
            
        ผลลัพธ์ (dict):
            {
                "intent": ชื่อหมวดหมู่ที่ทำนายได้ (เช่น 'travel', 'admission'),
                "intent_th": คำอธิบายหมวดหมู่ภาษาไทย,
                "confidence": ค่าความมั่นใจ (0.00 - 1.00),
                "all_scores": คะแนนความน่าจะเป็นของทุกหมวดหมู่,
                "tokens": รายการคำที่ตัดได้จาก PyThaiNLP,
                "engine": "local_tfidf_svm" หรือ "fallback_keyword"
            }
        """
        if not text or not isinstance(text, str) or not text.strip():
            return {
                "intent": "greeting",
                "intent_th": self.INTENT_DESCRIPTIONS["greeting"],
                "confidence": 0.0,
                "all_scores": {},
                "tokens": [],
                "engine": "empty_input"
            }

        # กรณีโมเดลพร้อมใช้งาน ให้ทำนายด้วย TF-IDF + Classifier
        if self.is_ready and self.model is not None and self.vectorizer is not None:
            try:
                tokens = thai_text_tokenizer(text)
                features = self.vectorizer.transform([text])

                # คำนวณความน่าจะเป็นของแต่ละคลาส (Probability)
                if hasattr(self.model, "predict_proba"):
                    probs = self.model.predict_proba(features)[0]
                    classes = self.model.classes_
                    best_idx = int(np.argmax(probs))
                    predicted_intent = str(classes[best_idx])
                    confidence = float(probs[best_idx])
                    all_scores = {str(cls): round(float(p), 4) for cls, p in zip(classes, probs)}
                else:
                    # กรณีโมเดลไม่มี predict_proba ให้ใช้ decision_function แปลงเป็น Softmax
                    decision = self.model.decision_function(features)[0]
                    exp_scores = np.exp(decision - np.max(decision))
                    probs = exp_scores / exp_scores.sum()
                    classes = self.model.classes_
                    best_idx = int(np.argmax(probs))
                    predicted_intent = str(classes[best_idx])
                    confidence = float(probs[best_idx])
                    all_scores = {str(cls): round(float(p), 4) for cls, p in zip(classes, probs)}

                return {
                    "intent": predicted_intent,
                    "intent_th": self.INTENT_DESCRIPTIONS.get(predicted_intent, "ทั่วไป"),
                    "confidence": round(confidence, 4),
                    "all_scores": all_scores,
                    "tokens": tokens,
                    "engine": "local_ml_model"
                }
            except Exception as e:
                print(f"[Local ML Prediction Error]: {e}")

        # ระบบสำรอง (Rule-based Fallback) กรณีไฟล์ .pkl สูญหายหรือยังไม่ได้เทรน
        return self._rule_based_fallback(text)

    def _rule_based_fallback(self, text: str) -> dict:
        """ระบบสำรองโดยใช้คีย์เวิร์ดหากโมเดล ML มีปัญหา"""
        msg = text.lower()
        if any(k in msg for k in ["เรียน", "สาขา", "สมัคร", "อาชีวะ", "ปวช", "ปวส", "ค่าเทอม", "ดิจิทัล", "บัญชี"]):
            intent = "admission"
        elif any(k in msg for k in ["กิน", "อาหาร", "ขนม", "หม้อแกง", "ข้าวแช่", "ก๋วยเตี๋ยว", "โตนด", "อร่อย", "ของฝาก"]):
            intent = "food"
        elif any(k in msg for k in ["เที่ยว", "เขาวัง", "พระนครคีรี", "ถ้ำ", "หาด", "ชะอำ", "วัด", "แก่งกระจาน", "ทริป"]):
            intent = "travel"
        elif any(k in msg for k in ["อากาศ", "ฝน", "เดินทาง", "กี่กิโล", "รถตู้", "รถไฟ", "โรงพยาบาล", "แผนที่"]):
            intent = "general_faq"
        else:
            intent = "greeting"

        return {
            "intent": intent,
            "intent_th": self.INTENT_DESCRIPTIONS[intent],
            "confidence": 0.75,
            "all_scores": {intent: 0.75},
            "tokens": thai_text_tokenizer(text),
            "engine": "keyword_fallback"
        }


# ==============================================================================
# ส่วนทดสอบการทำงานของคลาสโดยตรง (รัน python intent_classifier.py เพื่อทดสอบ)
# ==============================================================================
if __name__ == "__main__":
    classifier = NongPhetIntentClassifier()
    
    sample_queries = [
        "อยากไปดูลำแสงสวรรค์ที่ถ้ำเขาหลวงต้องไปช่วงกี่โมงครับ",
        "วิทยาลัยอาชีวศึกษาเพชรบุรีเปิดรับสมัครสาขาเทคโนโลยีธุรกิจดิจิทัลไหม",
        "แนะนำร้านขนมหม้อแกงกับข้าวแช่อร่อยๆ ในเมืองเพชรหน่อย",
        "สวัสดีครับน้องเพชร แนะนำตัวให้ฟังหน่อย",
        "วันนี้ที่เพชรบุรีอากาศร้อนไหม ฝนจะตกหรือเปล่า"
    ]

    print("\n🔍 ทดสอบการจำแนกข้อความภาษาไทย (Inference Test):")
    print("-" * 70)
    for q in sample_queries:
        res = classifier.predict(q)
        print(f"คำถาม   : {q}")
        print(f"คำที่ตัดได้ : {res['tokens']}")
        print(f"ผลทำนาย : {res['intent']} ({res['intent_th']}) | ความมั่นใจ: {res['confidence']*100:.1f}%")
        print("-" * 70)