# -*- coding: utf-8 -*-
"""
services/knowledge_manager.py — Dynamic Knowledge Base (RAG Retrainable Database) Engine
จัดการฐานข้อมูลความรู้สำหรับน้องเพชร AI Smart Guide:
รองรับ Create, Read, Update, Delete (CRUD), Auto-Backup, และ On-the-fly Vector Re-indexing
"""
import os
import json
import shutil
import datetime
import logging
from typing import Dict, Any, List, Optional
from semantic_retriever import get_semantic_retriever

logger = logging.getLogger("nongphet.kb_manager")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_PATH = os.path.join(BASE_DIR, 'knowledge_base.json')
KB_BACKUP_PATH = os.path.join(BASE_DIR, 'knowledge_base.json.bak')

LAST_REINDEX_TIME = datetime.datetime.now()

class KnowledgeBaseManager:
    def __init__(self, kb_path: str = KB_PATH):
        self.kb_path = kb_path
        self._data: Dict[str, Any] = {"version": "1.0.0", "entries": []}
        self.load()

    def load(self) -> bool:
        if not os.path.exists(self.kb_path):
            logger.warning(f"Knowledge base not found at {self.kb_path}")
            return False
        try:
            with open(self.kb_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
            return True
        except Exception as e:
            logger.error(f"Error loading knowledge base: {e}")
            return False

    def save(self) -> bool:
        """บันทึกข้อมูลลง knowledge_base.json พร้อมสร้างไฟล์สำรอง .bak เสมอ"""
        try:
            if os.path.exists(self.kb_path):
                shutil.copyfile(self.kb_path, KB_BACKUP_PATH)

            temp_path = self.kb_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            
            # Atomic replace
            if os.path.exists(self.kb_path):
                os.replace(temp_path, self.kb_path)
            else:
                os.rename(temp_path, self.kb_path)

            return True
        except Exception as e:
            logger.error(f"Error saving knowledge base: {e}")
            return False

    def list_entries(self, search: Optional[str] = None, intent: Optional[str] = None) -> List[Dict[str, Any]]:
        self.load()
        entries = self._data.get("entries", [])
        filtered = []

        q = (search or "").strip().lower()
        target_intent = (intent or "").strip().lower()

        for e in entries:
            if target_intent and target_intent != 'all' and e.get("intent", "").lower() != target_intent:
                continue

            if q:
                title = e.get("title", "").lower()
                eid = e.get("id", "").lower()
                ans = e.get("answer", "").lower()
                kws = " ".join(e.get("keywords", [])).lower()
                questions = " ".join(e.get("questions", [])).lower()
                if q not in title and q not in eid and q not in ans and q not in kws and q not in questions:
                    continue

            filtered.append(e)

        return filtered

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        self.load()
        for e in self._data.get("entries", []):
            if e.get("id") == entry_id:
                return e
        return None

    def add_entry(self, entry_data: Dict[str, Any], auto_reindex: bool = True) -> Dict[str, Any]:
        self.load()
        eid = entry_data.get("id", "").strip()
        if not eid:
            # สร้าง ID อัตโนมัติจาก intent และ timestamp
            intent = entry_data.get("intent", "general")
            now_suffix = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            eid = f"{intent}_{now_suffix}"

        # ตรวจสอบ ID ซ้ำ
        if self.get_entry(eid):
            raise ValueError(f"รหัสหัวข้อ (ID: {eid}) มีอยู่ในระบบแล้ว กรุณาใช้รหัสอื่น")

        # จัดเตรียมฟิลด์มาตรฐาน
        new_entry = {
            "id": eid,
            "intent": entry_data.get("intent", "general_faq"),
            "title": entry_data.get("title", "ไม่มีชื่อหัวข้อ"),
            "keywords": [k.strip() for k in entry_data.get("keywords", []) if k.strip()],
            "questions": [q.strip() for q in entry_data.get("questions", []) if q.strip()],
            "answer": entry_data.get("answer", "").strip(),
            "suggestions": [s.strip() for s in entry_data.get("suggestions", []) if s.strip()],
            "updated_at": datetime.datetime.now().isoformat()
        }

        self._data.setdefault("entries", []).append(new_entry)
        self.save()

        reindex_info = None
        if auto_reindex:
            reindex_info = self.reindex()

        return {"status": "success", "entry": new_entry, "reindex": reindex_info}

    def update_entry(self, entry_id: str, entry_data: Dict[str, Any], auto_reindex: bool = True) -> Dict[str, Any]:
        self.load()
        entries = self._data.get("entries", [])
        found_idx = -1
        for idx, e in enumerate(entries):
            if e.get("id") == entry_id:
                found_idx = idx
                break

        if found_idx == -1:
            raise KeyError(f"ไม่พบหัวข้อความรู้รหัส {entry_id}")

        existing = entries[found_idx]
        existing["intent"] = entry_data.get("intent", existing.get("intent", "general_faq"))
        existing["title"] = entry_data.get("title", existing.get("title", ""))
        if "keywords" in entry_data:
            existing["keywords"] = [k.strip() for k in entry_data["keywords"] if k.strip()]
        if "questions" in entry_data:
            existing["questions"] = [q.strip() for q in entry_data["questions"] if q.strip()]
        if "answer" in entry_data:
            existing["answer"] = entry_data["answer"].strip()
        if "suggestions" in entry_data:
            existing["suggestions"] = [s.strip() for s in entry_data["suggestions"] if s.strip()]
        existing["updated_at"] = datetime.datetime.now().isoformat()

        entries[found_idx] = existing
        self.save()

        reindex_info = None
        if auto_reindex:
            reindex_info = self.reindex()

        return {"status": "success", "entry": existing, "reindex": reindex_info}

    def delete_entry(self, entry_id: str, auto_reindex: bool = True) -> Dict[str, Any]:
        self.load()
        entries = self._data.get("entries", [])
        original_len = len(entries)
        self._data["entries"] = [e for e in entries if e.get("id") != entry_id]

        if len(self._data["entries"]) == original_len:
            raise KeyError(f"ไม่พบหัวข้อความรู้รหัส {entry_id}")

        self.save()

        reindex_info = None
        if auto_reindex:
            reindex_info = self.reindex()

        return {"status": "success", "deleted_id": entry_id, "reindex": reindex_info}

    def reindex(self) -> Dict[str, Any]:
        """สั่งให้ Semantic Retriever ทำการอ่านฐานข้อมูลใหม่และคำนวณ TF-IDF เวกเตอร์ใหม่ทันที"""
        global LAST_REINDEX_TIME
        retriever = get_semantic_retriever(kb_path=self.kb_path)
        stats = retriever.reload()
        LAST_REINDEX_TIME = datetime.datetime.now()
        stats["reindexed_at"] = LAST_REINDEX_TIME.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Knowledge Base Re-indexed: {stats}")
        return stats

    def get_stats(self) -> Dict[str, Any]:
        self.load()
        entries = self._data.get("entries", [])
        intents_count: Dict[str, int] = {}
        total_questions = 0

        for e in entries:
            it = e.get("intent", "general_faq")
            intents_count[it] = intents_count.get(it, 0) + 1
            total_questions += len(e.get("questions", []))

        return {
            "total_entries": len(entries),
            "total_questions": total_questions,
            "intents_distribution": intents_count,
            "last_reindexed": LAST_REINDEX_TIME.strftime("%Y-%m-%d %H:%M:%S"),
            "file_size_kb": round(os.path.getsize(self.kb_path) / 1024, 1) if os.path.exists(self.kb_path) else 0
        }

# Singleton instance
kb_manager = KnowledgeBaseManager()

