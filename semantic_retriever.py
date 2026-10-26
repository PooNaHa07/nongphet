#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semantic Retriever Module สำหรับ "น้องเพชร AI Smart Guide"
ใช้เทคนิค TF-IDF Cosine Similarity + N-gram + Keyword Boosting ร่วมกับ PyThaiNLP
ช่วยค้นหาคำตอบจาก Local Knowledge Base ได้อย่างรวดเร็ว (<20ms) และแม่นยำสูง
ทำงานแบบ On-Device 100% โดยไม่ต้องพึ่งพา Cloud หรือ API ภายนอก
"""

import os
import sys
import json
import re
import numpy as np
from typing import Optional, Dict, Any, List

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from pythainlp.tokenize import word_tokenize
from pythainlp.util import normalize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def thai_tokenizer(text: str) -> List[str]:
    """ฟังก์ชันตัดคำภาษาไทยสำหรับ TF-IDF Vectorizer"""
    if not isinstance(text, str):
        return []
    cleaned = normalize(text.strip().lower())
    # เอาอักขระพิเศษที่ไม่จำเป็นออก แต่คงตัวอักษรไทย-อังกฤษ และตัวเลข
    cleaned = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s]', ' ', cleaned)
    tokens = word_tokenize(cleaned, engine="newmm", keep_whitespace=False)
    return [t.strip() for t in tokens if len(t.strip()) > 0]


class SemanticRetriever:
    """
    คลาสค้นหาคำตอบเชิงความหมาย (Semantic RAG) จาก knowledge_base.json
    """

    def __init__(self, kb_path: str = "knowledge_base.json", threshold: float = 0.30):
        self.kb_path = kb_path
        self.threshold = threshold
        self.entries: List[Dict[str, Any]] = []
        self.corpus_texts: List[str] = []
        self.entry_indices: List[int] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self.is_ready: bool = False
        
        self.load_knowledge_base()

    def load_knowledge_base(self):
        """โหลดข้อมูล knowledge_base.json และสร้าง TF-IDF Index"""
        if not os.path.exists(self.kb_path):
            # ตรวจสอบใน path อื่นๆ เผื่อกรณีรันจาก subdirectory
            base_dir = os.path.dirname(os.path.abspath(__file__))
            alt_path = os.path.join(base_dir, self.kb_path)
            if os.path.exists(alt_path):
                self.kb_path = alt_path
            else:
                print(f"⚠️ [SemanticRetriever] ไม่พบไฟล์ {self.kb_path}")
                self.is_ready = False
                return

        try:
            with open(self.kb_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.entries = data.get("entries", [])
            self.corpus_texts = []
            self.entry_indices = []

            # สร้าง Document Corpus โดยขยายทั้งคำถามหลัก, ตัวอย่างคำถาม, คำค้น (keywords) และหัวเรื่อง
            for idx, entry in enumerate(self.entries):
                title = entry.get("title", "")
                keywords = " ".join(entry.get("keywords", []))
                questions = entry.get("questions", [])
                
                # เพิ่มแต่ละคำถามเป็น 1 document ย่อย พร้อมแนบคีย์เวิร์ด
                for q in questions:
                    doc = f"{title} {keywords} {q} {q}"
                    self.corpus_texts.append(doc)
                    self.entry_indices.append(idx)
                
                # เพิ่ม document รวมของ entry นั้นด้วย
                doc_full = f"{title} {keywords} " + " ".join(questions)
                self.corpus_texts.append(doc_full)
                self.entry_indices.append(idx)

            if not self.corpus_texts:
                print("⚠️ [SemanticRetriever] ไม่มีข้อมูลคำถามใน Knowledge Base")
                self.is_ready = False
                return

            # สร้างและ Fit TF-IDF Vectorizer (รองรับทั้งคำเดี่ยวและคำคู่ n-gram 1-2)
            self.vectorizer = TfidfVectorizer(
                tokenizer=thai_tokenizer,
                token_pattern=None,
                ngram_range=(1, 2),
                sublinear_tf=True
            )
            self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus_texts)
            self.is_ready = True
            print(f"✅ [SemanticRetriever] โหลดฐานความรู้สำเร็จ ({len(self.entries)} หัวข้อ, {len(self.corpus_texts)} รูปแบบคำถาม)")

        except Exception as e:
            print(f"❌ [SemanticRetriever Error] โหลดฐานข้อมูลล้มเหลว: {e}")
            self.is_ready = False

    def retrieve(self, query: str, intent: Optional[str] = None, custom_threshold: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        ค้นหาคำตอบที่ตรงที่สุดกับคำถาม query
        
        พารามิเตอร์:
            query (str): คำถามของผู้ใช้
            intent (str): เจตนาที่ทำนายได้จาก Intent Classifier (ถ้ามี เพื่อช่วยกรอง/บูสต์)
            custom_threshold (float): ค่าเกณฑ์ความคล้ายคลึงขั้นต่ำ (ถ้าไม่ระบุจะใช้ค่า default)
            
        ผลลัพธ์ (dict หรือ None):
            ข้อมูลคำตอบ พร้อมคะแนนความมั่นใจ
        """
        if not self.is_ready or not query or not query.strip():
            return None

        effective_threshold = custom_threshold if custom_threshold is not None else self.threshold
        query_clean = query.strip()

        try:
            query_vec = self.vectorizer.transform([query_clean])
            similarities = cosine_similarity(query_vec, self.tfidf_matrix)[0]

            # จัดกลุ่มคะแนนตาม entry index หาคะแนนสูงสุดของแต่ละ entry
            entry_best_scores: Dict[int, float] = {}
            for doc_idx, sim in enumerate(similarities):
                e_idx = self.entry_indices[doc_idx]
                if sim > entry_best_scores.get(e_idx, 0.0):
                    entry_best_scores[e_idx] = float(sim)

            if not entry_best_scores:
                return None

            # เพิ่มคะแนนโบนัส (Boosting) สำหรับ Exact Keyword Matches และ Intent Matches
            q_lower = query_clean.lower()
            boosted_scores: Dict[int, float] = {}
            for e_idx, base_score in entry_best_scores.items():
                entry = self.entries[e_idx]
                score = base_score

                # บูสต์หากคำค้นตรงกับ keywords ของ entry
                kw_matches = sum(1 for kw in entry.get("keywords", []) if kw.lower() in q_lower)
                if kw_matches > 0:
                    score += min(0.35, kw_matches * 0.15)

                # บูสต์หาก Intent จากโมเดล ML ตรงกับ Intent ของ entry
                if intent and intent != "general_faq" and entry.get("intent") == intent:
                    score += 0.10

                boosted_scores[e_idx] = score

            # หา entry ที่ได้คะแนนสูงสุด
            best_idx = max(boosted_scores, key=boosted_scores.get)
            best_score = boosted_scores[best_idx]

            # ตรวจสอบว่าผ่านเกณฑ์ขั้นต่ำหรือไม่
            if best_score < effective_threshold:
                return None

            matched_entry = self.entries[best_idx]
            
            # ดึงคำตอบและจัดรูปแบบ
            answer_text = matched_entry.get("answer", "")
            suggestions = matched_entry.get("suggestions", [])
            
            # หากคำตอบยังไม่มีท้ายบล็อก แนะนำคำถามต่อยอด ให้แนบคำแนะนำไปด้วย
            if "ถามต่อยอดกับน้องเพชร" not in answer_text and suggestions:
                sug_str = "\n".join([f"• {s}" for s in suggestions])
                full_reply = f"{answer_text}\n\n---\n💡 **ถามต่อยอดกับน้องเพชร:**\n{sug_str}"
            else:
                full_reply = answer_text

            return {
                "id": matched_entry.get("id"),
                "intent": matched_entry.get("intent"),
                "title": matched_entry.get("title"),
                "reply": full_reply,
                "suggestions": suggestions,
                "score": round(best_score, 4),
                "source": "semantic_rag",
                "engine": "semantic_rag"
            }

        except Exception as e:
            print(f"❌ [SemanticRetriever Search Error] {e}")
            return None


# Global instance สำหรับนำไป import ใช้งานได้ทันที
_retriever_instance: Optional[SemanticRetriever] = None

def get_semantic_retriever(kb_path: str = "knowledge_base.json") -> SemanticRetriever:
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = SemanticRetriever(kb_path=kb_path)
    return _retriever_instance


if __name__ == "__main__":
    retriever = SemanticRetriever()
    test_queries = [
        "เขาวังเปิดกี่โมง ค่าเข้าเท่าไหร่",
        "มีลิงดุไหมที่พระนครคีรี",
        "ถ้ำเขาหลวงแสงส่องตอนไหนสวยสุด",
        "อยากกินหม้อแกงเตาฟืน แนะนำหน่อย",
        "ข้าวแช่เมืองเพชรมีอะไรบ้าง กินยังไง",
        "สาขาดิจิทัลเรียนอะไรบ้าง จบแล้วทำอะไร",
        "ระบบทวิภาคีดีไหม ได้เงินไหม",
        "ไปเพชรบุรียังไง มีรถตู้ไหม",
        "ยืมตังค์หน่อยน้องเพชร",
        "เขาวังอยู่เชียงใหม่ใช่ไหม",
        "หอไอเฟลเพชรบุรีอยู่ที่ไหน",
        "อากาศเป็นไงช่วงไหนน่าเที่ยว"
    ]

    print("\n🔍 --- ทดสอบ Semantic Retriever ---")
    for q in test_queries:
        res = retriever.retrieve(q)
        if res:
            print(f"\nQ: {q}")
            print(f"🎯 Matched: [{res['id']}] {res['title']} (Score: {res['score']:.4f})")
            print(f"A: {res['reply'][:120]}...")
        else:
            print(f"\nQ: {q} -> ❌ ไม่พบคำตอบที่มั่นใจ (Score < Threshold)")
