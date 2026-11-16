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

if __name__ == '__main__':
    unittest.main()

