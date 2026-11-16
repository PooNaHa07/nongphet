# -*- coding: utf-8 -*-
"""
tests/test_intent.py — Unit Tests for Nong Phet Intent Classifier
"""
import unittest
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intent_classifier import NongPhetIntentClassifier, thai_text_tokenizer

class TestIntentClassifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier = NongPhetIntentClassifier()

    def test_tokenizer_thai(self):
        tokens = thai_text_tokenizer("เขาวังอยู่ที่ไหน")
        self.assertIsInstance(tokens, list)
        self.assertTrue(len(tokens) > 0)
        self.assertTrue("เขาวัง" in tokens or ("เขา" in tokens and "วัง" in tokens))

    def test_tokenizer_chinese(self):
        tokens = thai_text_tokenizer("你好 拷汪宫")
        self.assertIsInstance(tokens, list)
        self.assertTrue(len(tokens) > 0)

    def test_travel_intent(self):
        queries = [
            "พระนครคีรี เขาวัง ไปยังไง",
            "ถ้ำเขาหลวง แสงสวรรค์เปิดกี่โมง",
            "หาดชะอำ เล่นบานาน่าโบ๊ทได้ไหม",
            "อุทยานแห่งชาติแก่งกระจาน ทะเลหมอกพะเนินทุ่ง"
        ]
        for q in queries:
            result = self.classifier.predict(q)
            self.assertEqual(result['intent'], 'travel', f"Failed for query: {q}")
            self.assertGreaterEqual(result['confidence'], 0.5)

    def test_food_intent(self):
        queries = [
            "ขนมหม้อแกงเตาฟืน ซื้อที่ไหนอร่อย",
            "ร้านก๋วยเตี๋ยวน้ำแดงเมืองเพชร มีร้านไหนแนะนำ",
            "ข้าวแช่ชาววัง เพชรบุรี มีเครื่องเคียงอะไรบ้าง",
            "น้ำตาลโตนดแท้ ดงตาลบ้านลาด"
        ]
        for q in queries:
            result = self.classifier.predict(q)
            self.assertEqual(result['intent'], 'food', f"Failed for query: {q}")
            self.assertGreaterEqual(result['confidence'], 0.5)

    def test_admission_intent(self):
        queries = [
            "วิทยาลัยอาชีวศึกษาเพชรบุรี มีสาขาอะไรบ้าง",
            "สมัครเรียน ปวช. และ ปวส. ต้องใช้เกรดเท่าไหร่",
            "สาขาเทคโนโลยีธุรกิจดิจิทัล เรียนอะไรบ้าง",
            "ระบบทวิภาคี มีรายได้ระหว่างเรียนไหม"
        ]
        for q in queries:
            result = self.classifier.predict(q)
            self.assertEqual(result['intent'], 'admission', f"Failed for query: {q}")
            self.assertGreaterEqual(result['confidence'], 0.5)

    def test_greeting_intent(self):
        queries = [
            "สวัสดีครับ",
            "สวัสดีจ้า น้องเพชร",
            "หวัดดี ยินดีที่ได้รู้จัก",
            "hello nong phet"
        ]
        for q in queries:
            result = self.classifier.predict(q)
            self.assertEqual(result['intent'], 'greeting', f"Failed for query: {q}")

    def test_empty_query_handling(self):
        result = self.classifier.predict("")
        self.assertIn('intent', result)
        self.assertIn('confidence', result)

if __name__ == '__main__':
    unittest.main()

