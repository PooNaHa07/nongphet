# -*- coding: utf-8 -*-
"""
tests/test_college_info.py — ข้อมูลวิทยาลัยต้องตรงกับแหล่งทางการ (data/college_official.json)
และคำถามที่พบบ่อยต้องไปถึงหัวข้อที่ถูกต้อง
"""
import os
import sys
import json
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from semantic_retriever import SemanticRetriever

KB = json.load(open(os.path.join(ROOT, 'knowledge_base.json'), encoding='utf-8'))
OFFICIAL = json.load(open(os.path.join(ROOT, 'data', 'college_official.json'), encoding='utf-8'))
ENTRIES = {e['id']: e for e in KB['entries']}
COLLEGE_IDS = [i for i in ENTRIES if i.startswith(('admission_', 'college_'))]


class TestCollegeFacts(unittest.TestCase):
    def test_contact_matches_official(self):
        ans = ENTRIES['college_contact_001']['answer']
        self.assertIn('300 ถนนราชวิถี', ans)
        self.assertIn('032-425-557', ans)
        self.assertIn('pbpvc.ac.th', ans)

    def test_no_known_wrong_facts_left(self):
        blob = json.dumps(KB, ensure_ascii=False)
        for wrong in ('272 ถนนดำเนินเกษม', '032-425-467', '032-425-470', 'www.pbvc.ac.th', '9 สาขา', 'PBVC'):
            self.assertNotIn(wrong, blob, wrong)

    def test_no_unsourced_claims_in_college_answers(self):
        for i in COLLEGE_IDS:
            ans = ENTRIES[i]['answer']
            for claim in ('100%', 'เงินเดือน', 'Match Score'):
                self.assertNotIn(claim, ans, f'{i}: {claim}')

    def test_overview_lists_all_official_majors(self):
        ans = ENTRIES['admission_branches_001']['answer']
        self.assertIn('11 สาขา', ans)
        for name in ('การบัญชี', 'การจัดการสำนักงาน', 'การตลาด', 'เทคโนโลยีธุรกิจดิจิทัล', 'ดิจิทัลกราฟิก',
                     'วิจิตรศิลป์', 'แฟชั่นและสิ่งทอ', 'อาหารและโภชนาการ', 'คหกรรม', 'การโรงแรม', 'การท่องเที่ยว'):
            self.assertIn(name, ans)

    def test_programs_come_from_official_data(self):
        depts = {d['department']: d for d in OFFICIAL['departments']}
        for prog in depts['การตลาด']['programs']:
            self.assertIn(prog['level'], ENTRIES['admission_mkt_001']['answer'])

    def test_logistics_answer_says_not_offered(self):
        self.assertIn('ไม่มีสาขาโลจิสติกส์', ENTRIES['admission_logistics_001']['answer'])

    def test_unverified_admission_details_are_flagged(self):
        self.assertIn('โปรดตรวจสอบกับวิทยาลัย', ENTRIES['admission_apply_001']['answer'])

    def test_every_college_answer_cites_source(self):
        for i in COLLEGE_IDS:
            self.assertIn('ข้อมูลจากเว็บไซต์วิทยาลัย', ENTRIES[i]['answer'], i)


class TestCollegeRetrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = SemanticRetriever(os.path.join(ROOT, 'knowledge_base.json'))

    CASES = [
        ('วิทยาลัยมีสาขาอะไรบ้าง', 'admission_branches_001'),
        ('เบอร์โทรวิทยาลัย', 'college_contact_001'),
        ('วิทยาลัยอยู่ที่ไหน', 'college_contact_001'),
        ('สมัครเรียนต้องใช้เอกสารอะไร', 'admission_apply_001'),
        ('ใครเป็นผู้อำนวยการวิทยาลัย', 'college_director_001'),
        ('ประวัติวิทยาลัย', 'college_about_001'),
        ('วิทยาลัยมีปริญญาตรีไหม', 'admission_bachelor_001'),
        ('ระบบทวิภาคีคืออะไร', 'admission_dve_001'),
        ('สาขาการบัญชีเรียนอะไร', 'admission_acct_001'),
        ('สาขาการจัดการสำนักงานเรียนอะไร', 'admission_office_001'),
        ('สาขาการตลาดเรียนอะไร', 'admission_mkt_001'),
        ('สาขาคอมพิวเตอร์ธุรกิจเรียนอะไร', 'admission_dbt_001'),
        ('สาขาดิจิทัลกราฟิกเรียนอะไร', 'admission_digital_graphic_001'),
        ('สาขาวิจิตรศิลป์เรียนอะไร', 'admission_fine_arts_001'),
        ('สาขาแฟชั่นและสิ่งทอเรียนอะไร', 'admission_fashion_001'),
        ('อยากเป็นเชฟเรียนสาขาไหน', 'admission_culinary_001'),
        ('สาขาคหกรรมเรียนอะไร', 'admission_home_econ_001'),
        ('สาขาการโรงแรมเรียนอะไร', 'admission_hotel_001'),
        ('อยากเป็นไกด์เรียนสาขาไหน', 'admission_tourism_001'),
        ('มีสาขาโลจิสติกส์ไหม', 'admission_logistics_001'),
    ]

    def test_questions_reach_right_topic(self):
        wrong = []
        for q, expected in self.CASES:
            hit = self.r.retrieve(q)
            got = hit['id'] if hit else None
            if got != expected:
                wrong.append(f'{q} -> {got} (ควรเป็น {expected})')
        self.assertEqual(wrong, [])


class TestCourseMatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app_new import app
        cls.client = app.test_client()

    def test_matches_real_major_without_made_up_scores(self):
        res = self.client.post('/match_course', json={'interests': 'ชอบวาดรูปและออกแบบกราฟิก'})
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(data['matches'][0]['id'], 'admission_digital_graphic_001')
        self.assertNotIn('Match Score', data['recommendation'])
        self.assertNotIn('เงินเดือน', data['recommendation'])

    def test_no_match_lists_majors(self):
        data = self.client.post('/match_course', json={'interests': 'ไม่รู้'}).get_json()
        self.assertEqual(data['matches'], [])
        self.assertIn('11 สาขา', data['recommendation'])


if __name__ == '__main__':
    unittest.main()
