# -*- coding: utf-8 -*-
"""
tests/test_knowledge_manager.py — Unit & Dynamic Retraining Tests for RAG Knowledge Base
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.knowledge_manager import kb_manager
from semantic_retriever import get_semantic_retriever

class TestKnowledgeBaseManager(unittest.TestCase):
    def setUp(self):
        self.test_entry_id = "test_robotics_quantum_9999"

    def tearDown(self):
        # Clean up test entry if present
        try:
            if kb_manager.get_entry(self.test_entry_id):
                kb_manager.delete_entry(self.test_entry_id, auto_reindex=True)
        except Exception:
            pass

    def test_list_and_stats(self):
        entries = kb_manager.list_entries()
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 0)

        stats = kb_manager.get_stats()
        self.assertIn("total_entries", stats)
        self.assertIn("total_questions", stats)
        self.assertGreater(stats["total_entries"], 0)

    def test_add_and_instant_ai_learning(self):
        """
        การทดสอบขั้นสูง: เพิ่มข้อมูลหลักสูตรใหม่ แล้วให้ AI ตอบกลับคำถามนั้นทันที
        เพื่อพิสูจน์การทำงานของ Retrainable Database ต่อหน้าคณะกรรมการ
        """
        new_data = {
            "id": self.test_entry_id,
            "intent": "admission",
            "title": "สาขาวิชาหุ่นยนต์ควอนตัมและปัญญาประดิษฐ์ชั้นสูง",
            "keywords": ["หุ่นยนต์ควอนตัม", "quantum", "วิทยาการหุ่นยนต์"],
            "questions": [
                "มีสาขาหุ่นยนต์ควอนตัมไหม",
                "อยากเรียนหุ่นยนต์ควอนตัมสมัครยังไง"
            ],
            "answer": "วิทยาลัยอาชีวศึกษาเพชรบุรีเปิดสอนหลักสูตรหุ่นยนต์ควอนตัมแล้วค่ะ สนใจสมัครได้ที่ฝ่ายวิชาการค่ะ",
            "suggestions": ["ค่าเทอมหุ่นยนต์ควอนตัม"]
        }

        # 1. เพิ่มข้อมูลและสั่ง Hot Re-index
        add_res = kb_manager.add_entry(new_data, auto_reindex=True)
        self.assertEqual(add_res["status"], "success")

        # 2. ตรวจสอบว่ามีข้อมูลอยู่ในคลัง
        found = kb_manager.get_entry(self.test_entry_id)
        self.assertIsNotNone(found)
        self.assertEqual(found["title"], new_data["title"])

        # 3. ให้ Semantic Retriever ทดสอบ Live Inference
        retriever = get_semantic_retriever()
        matched = retriever.retrieve("มีสาขาหุ่นยนต์ควอนตัมไหม")
        self.assertIsNotNone(matched, "AI should retrieve the newly added curriculum")
        self.assertEqual(matched["id"], self.test_entry_id)
        self.assertIn("หุ่นยนต์ควอนตัม", matched["reply"])

        # 4. ลบข้อมูลและ Re-index คืนค่าเดิม
        del_res = kb_manager.delete_entry(self.test_entry_id, auto_reindex=True)
        self.assertEqual(del_res["status"], "success")
        self.assertIsNone(kb_manager.get_entry(self.test_entry_id))

if __name__ == '__main__':
    unittest.main()

