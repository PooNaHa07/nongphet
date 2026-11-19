# -*- coding: utf-8 -*-
"""
tests/test_retriever.py — Unit Tests for Semantic Retriever & Local RAG
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from semantic_retriever import get_semantic_retriever, expand_query_with_synonyms

class TestSemanticRetriever(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = get_semantic_retriever()

    def test_retriever_is_ready(self):
        self.assertTrue(self.retriever.is_ready, "Semantic retriever should be loaded and ready")
        self.assertGreater(len(self.retriever.entries), 0, "Knowledge base entries should not be empty")

    def test_synonym_expansion(self):
        expanded = expand_query_with_synonyms("เขาวัง")
        self.assertIn("พระนครคีรี", expanded)
        
        expanded_food = expand_query_with_synonyms("หม้อแกง")
        self.assertIn("ขนมหม้อแกง", expanded_food)

    def test_retrieve_khao_wang(self):
        result = self.retriever.retrieve("เขาวังเปิดกี่โมง ค่าเข้าเท่าไหร่")
        self.assertIsNotNone(result, "Should retrieve entry for Khao Wang")
        self.assertIn("เขาวัง", result['reply'])
        self.assertGreater(result['score'], 0.20)

    def test_retrieve_top_k(self):
        results = self.retriever.retrieve_top_k("ของกินเมืองเพชร มีอะไรอร่อยบ้าง", k=3)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 3)

    def test_retrieve_non_matching(self):
        # Queries with completely irrelevant text shouldn't return false high scores
        result = self.retriever.retrieve("มนุษย์ต่างดาวบุกดาวอังคารด้วยจรวดความเร็วแสง")
        if result:
            self.assertLess(result['score'], 0.50)

class TestAnswerVariants(unittest.TestCase):
    ENTRY = {
        'id': 'test_variant', 'answer': 'คำตอบหลัก', 'speech': 'พูดหลักค่ะ',
        'answer_variants': [{'answer': 'คำตอบสอง', 'speech': 'พูดสองค่ะ'}, {'answer': '  '}],
    }

    def test_variants_include_main_and_skip_empty(self):
        from semantic_retriever import answer_variants_of
        got = answer_variants_of(self.ENTRY)
        self.assertEqual([v['answer'] for v in got], ['คำตอบหลัก', 'คำตอบสอง'])
        self.assertEqual(answer_variants_of({'answer': 'a', 'speech': 'b'}), [{'answer': 'a', 'speech': 'b'}])

    def test_pick_keeps_answer_and_speech_together(self):
        from semantic_retriever import pick_answer_variant
        seen = set()
        for _ in range(60):
            v = pick_answer_variant(self.ENTRY)
            self.assertIn((v['answer'], v['speech']), {('คำตอบหลัก', 'พูดหลักค่ะ'), ('คำตอบสอง', 'พูดสองค่ะ')})
            seen.add(v['answer'])
        self.assertEqual(seen, {'คำตอบหลัก', 'คำตอบสอง'})

    def test_retrieve_returns_one_of_the_variants(self):
        r = get_semantic_retriever()
        entry = next(e for e in r.entries if e['id'] == 'kiosk_thanks_001')
        pairs = {(entry['answer'], entry['speech'])} | {(v['answer'], v['speech']) for v in entry['answer_variants']}
        for _ in range(10):
            m = r.retrieve('ขอบคุณมากนะ')
            self.assertEqual(m['id'], 'kiosk_thanks_001')
            self.assertIn((m['reply'], m['speech']), pairs)


class TestNewFaqTopics(unittest.TestCase):
    CASES = [
        ('ขอบคุณนะ', 'kiosk_thanks_001'),
        ('ตู้นี้ใช้ยังไง', 'kiosk_howto_001'),
        ('น้องเพชรอายุเท่าไหร่', 'witty_personal_001'),
        ('แล้วที่พักล่ะ', 'travel_stay_001'),
        ('หาดปึกเตียนอยู่ที่ไหน', 'travel_beaches_001'),
        ('วัดเขาบันไดอิฐอยู่ที่ไหน', 'travel_khao_bandai_it_001'),
        ('แข่งวัวลานคืออะไร', 'travel_festival_001'),
        ('ขนมตาลซื้อที่ไหน', 'food_palm_001'),
        ('ค่าเทอมเท่าไหร่', 'college_fee_001'),
        ('ปวช กับ ปวส ต่างกันยังไง', 'college_levels_001'),
    ]

    def test_new_topics_reach_right_entry(self):
        r = get_semantic_retriever()
        wrong = []
        for q, expected in self.CASES:
            m = r.retrieve(q)
            if not m or m['id'] != expected:
                wrong.append(f"{q} -> {m and m['id']}")
        self.assertEqual(wrong, [])

    def test_college_money_and_levels_say_check_with_college(self):
        r = get_semantic_retriever()
        for eid in ('college_fee_001', 'college_levels_001'):
            entry = next(e for e in r.entries if e['id'] == eid)
            self.assertIn('โปรดตรวจสอบกับวิทยาลัย', entry['answer'])
            self.assertIn('โปรดตรวจสอบกับวิทยาลัย', entry['speech'])


if __name__ == '__main__':
    unittest.main()

