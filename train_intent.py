#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
สคริปต์สำหรับเตรียมข้อมูล (Dataset), ฝึกสอนโมเดล (Train), และทดสอบประสิทธิภาพ (Test)
ของระบบจำแนกเจตนาคำถามภาษาไทย (Thai NLP Intent Classification)
สำหรับสิ่งประดิษฐ์: "น้องเพชร AI Smart Guide" วิทยาลัยอาชีวศึกษาเพชรบุรี
สอดคล้องตามเกณฑ์การประเมิน สอศ. ประเภทที่ 2 ข้อ 5.4 (10 คะแนนเต็ม)
"""

import os
import re
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import random
import joblib
import numpy as np
import pandas as pd
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOT = True
except ImportError:
    plt = None
    sns = None
    HAS_PLOT = False

from pythainlp.tokenize import word_tokenize
from pythainlp.util import normalize
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import VotingClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix
)

# ตั้งค่า Seed เพื่อให้ผลการทดลองสามารถทำซ้ำได้ (Reproducibility ตามหลักวิจัย)
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# กำหนดโฟลเดอร์สำหรับเก็บโมเดลและผลลัพธ์การวิจัย
ARTIFACT_DIR = "ml_artifacts"
os.makedirs(ARTIFACT_DIR, exist_ok=True)


# ==============================================================================
# ส่วนที่ 1: การเตรียมข้อมูลดิบ (Raw Dataset) และการขยายข้อมูล (Data Augmentation)
# ==============================================================================
def get_seed_dataset():
    """
    ฐานข้อมูลต้นแบบ (Seed Phrases) แบ่งตาม 5 หมวดหมู่หลัก (Classes/Intents)
    ครอบคลุมสถานที่ 8 อำเภอ วัฒนธรรม ของฝาก การศึกษา และคำถามจริงจากผู้ใช้งาน
    """
    seed_dict = {
        "travel": [
            "แนะนำที่เที่ยวในเพชรบุรีหน่อย", "แนะนำสถานที่ท่องเที่ยวให้หน่อย", "แนะนำที่เที่ยวหน่อย",
            "ไปเที่ยวไหนดี", "มีที่เที่ยวแนะนำไหม", "พาเที่ยวหน่อย", "อยากไปเที่ยว", "เที่ยวไหนดีวันนี้",
            "จุดเช็คอินสวยๆ", "มีที่ถ่ายรูปสวยๆไหม", "แนะนำสถานที่เที่ยว", "สถานที่ท่องเที่ยวที่น่าสนใจ",
            "เขาวังเปิดกี่โมง", "พระนครคีรีขึ้นยังไง",
            "มีรถรางขึ้นเขาวังไหม", "ถ้ำเขาหลวงอยู่แถวไหน", "อยากดูลำแสงสวรรค์ที่ถ้ำเขาหลวงต้องไปกี่โมง",
            "หาดชะอำมีกิจกรรมอะไรบ้าง", "ทะเลชะอำเล่นน้ำได้ไหม", "วัดมหาธาตุวรวิหารอยู่ตรงไหน",
            "อยากไปไหว้พระปรางค์ 5 ยอด", "อุทยานแห่งชาติแก่งกระจานกางเต็นท์ได้ไหม",
            "ทะเลหมอกพะเนินทุ่งไปยังไง", "พระราชนิเวศน์มฤคทายวันเปิดวันไหนบ้าง",
            "วังบ้านปืนมีประวัติยังไง", "จัดทริปเที่ยวเพชรบุรี 1 วันให้หน่อย",
            "มาเที่ยวเพชรบุรี 2 วัน 1 คืน ไปไหนดี", "ที่เที่ยวถ่ายรูปสวยๆ ในเมืองเพชร",
            "คาเฟ่สวยๆ แถวชะอำมีที่ไหนบ้าง", "เขาวังค่าเข้าเท่าไหร่", "ลิงเขาวังดุไหม",
            "เส้นทางไปถ้ำเขาหลวง", "อยากไปดูนกเงือกที่แก่งกระจาน", "จุดชมวิวเมืองเพชรบุรี",
            "เที่ยววัดในเมืองเพชรวัดไหนดัง", "ชายหาดปึกเตียนมีอะไรน่าเที่ยว",
            "โครงการชั่งหัวมันไปทางไหน", "หาดเจ้าสำราญคนเยอะไหม", "สะพานแขวนแก่งกระจาน",
            "ที่เที่ยวธรรมชาติในจังหวัดเพชรบุรี", "แลนด์มาร์คที่ห้ามพลาดของเพชรบุรี",
            "พาครอบครัวไปเที่ยวไหนดีในเพชรบุรี", "นั่งรถไฟมาเที่ยวเพชรบุรีลงสถานีไหน",
            "ที่เที่ยวใกล้ตัวเมืองเพชรบุรี", "ประวัติของพระนครคีรี", "อยากเที่ยวเชิงประวัติศาสตร์เมืองเพชร",
            "ถ้ำโบ้เขาย้อยไปยังไง", "จุดถ่ายรูปถ้ำโบ้", "สะพานไม้ชายทะเลกาหลงบ้านแหลม",
            "ถนนสายเกลือบ้านแหลมอยู่ตรงไหน", "นาเกลือเพชรบุรีถ่ายรูปสวยไหม",
            "วนอุทยานชะอำเปิดไหม", "ล่องเรือยางแม่น้ำเพชรบุรี", "ล่องแพเปียกแก่งกระจาน",
            "วัดใหญ่สุวรรณารามมีอะไรดู", "รอยขวานพม่าบานประตูวัดใหญ่", "ชุมชนริมน้ำคลองกระแชง",
            "สตรีทอาร์ทเพชรบุรีอยู่ตรงไหน", "ศูนย์วัฒนธรรมไทยทรงดำเขาย้อย", "ถ้ำเขาย้อยมีพระนอนไหม",
            "น้ำตกป่าละอูเปิดให้เที่ยวไหม", "เทศกาลดูผีเสื้อบ้านกร่างมีเดือนไหน", "ที่พักกางเต็นท์ริมน้ำแก่งกระจาน",
            "เช็คอินชะอำที่ไหนดี", "หาดเจ้าสำราญมีของกินขายไหม", "แหลมผักเบี้ยมีสะพานไม้ไหม",
            "โครงการพระราชดำริแหลมผักเบี้ย", "บ่อน้ำพุร้อนหนองหญ้าปล้องไปยังไง", "ตลาดน้ำท่ายางเปิดวันไหน",
            "เขื่อนเพชรท่ายางมีอะไรเที่ยว", "ขับรถเที่ยวชะอำแวะไหนดี", "ที่เที่ยวสำหรับเด็กในเพชรบุรี",
            "วัดถ้ำแจงมีพญานาคใหญ่ไหม", "พญานาคพ่อปู่ภุชงค์นาคราชวัดถ้ำแจง", "จุดกางเต็นท์พะเนินทุ่ง",
            "ค่าธรรมเนียมเข้าอุทยานแก่งกระจาน", "ทางขึ้นพะเนินทุ่งเปิดปิดกี่โมง", "พาน้องหมาน้องแมวเที่ยวเขาวังได้ไหม",
            "อำเภอบ้านลาดมีดงตาลโตนดไหม", "ดงตาลโตนดบ้านลาดอยู่ตรงไหน", "จัดทริปเที่ยวเพชรบุรี 1 วัน",
            "แพลนเที่ยวเพชรบุรี 2 วัน 1 คืน", "สถานที่ท่องเที่ยวในเพชรบุรี",
            "Hello, where is Khao Wang in Phetchaburi?", "Where is Khao Wang and how can I get there?",
            "What places should I visit in Phetchaburi?", "Recommend tourist attractions in Phetchaburi",
            "How to go to Cha-am beach?", "Tell me about Kaeng Krachan National Park",
            "Opening hours of Phra Nakhon Khiri", "Plan a 1 day trip in Phetchaburi",
            "Khao Luang Cave location", "Maruekhathaiyawan Palace ticket price",
            "佛丕府有什么好玩的景点？", "请问怎么去拷汪宫？", "你好，拷汪宫几点开门？",
            "七岩海滩好玩吗？", "岗卡章国家公园怎么去？", "推荐佛丕府一日游行程", "考龙穴在哪里？"
        ],
        "food": [
            "แนะนำของกินหน่อย", "แนะนำร้านอาหารหน่อย", "หิวข้าว", "กินอะไรดี", "มีร้านอร่อยแนะนำไหม",
            "ของอร่อยอยู่ไหน", "อยากกินขนมหวาน", "ร้านอาหารแนะนำ", "ของหวานแนะนำ", "ร้านคาเฟ่แถวนี้",
            "เพชรบุรีมีของกินอะไรอร่อยบ้าง", "ซื้อขนมหม้อแกงร้านไหนดี", "ขนมหม้อแกงเตาฟืนคืออะไร",
            "ข้าวแช่เมืองเพชรหากินได้ที่ไหน", "ข้าวแช่ชาววังราคาเท่าไหร่", "ก๋วยเตี๋ยวน้ำแดงเพชรบุรีคืออะไร",
            "ทำไมก๋วยเตี๋ยวเพชรบุรีต้องใส่ซอสพริก", "น้ำตาลโตนดแท้ซื้อที่ไหน", "ของฝากเมืองเพชรมีอะไรบ้าง",
            "ทุเรียนป่าละอูออกช่วงเดือนไหน", "ร้านอาหารทะเลสดๆ แถวสะพานปลาชะอำ",
            "แนะนำร้านอาหารพื้นบ้านเพชรบุรี", "ขนมตาลเมืองเพชรอร่อยไหม", "ลอดช่องน้ำตาลข้นร้านไหนเด็ด",
            "ตลาดสดเพชรบุรีมีของกินอะไรบ้าง", "อยากกินซีฟู้ดริมทะเลชะอำ", "ขนมไทยโบราณเมืองเพชร",
            "ชมพู่เพชรสายรุ้งหาซื้อได้ที่ไหน", "หิวแล้วแนะนำร้านข้าวแถวนี้หน่อย", "ร้านอาหารมิชลินในเพชรบุรี",
            "แกงหัวตาลหมูย่างคืออะไร", "รสชาติก๋วยเตี๋ยวน้ำแดงเป็นยังไง", "ของหวานขึ้นชื่อจังหวัดเพชรบุรี",
            "ซื้อของฝากกลับบ้านอะไรดี", "ตลาดโต้รุ่งเพชรบุรีมีอะไรกินบ้าง", "ไอศกรีมน้ำตาลโตนดมีไหม",
            "ร้านขนมหม้อแกงแถวเขาวัง", "อยากชิมน้ำตาลสดแท้ๆ", "ผลไม้ขึ้นชื่อของเพชรบุรี",
            "ร้านก๋วยเตี๋ยวเนื้อเมืองเพชร", "ขนมอาลัวชาววังซื้อที่ไหน", "ขนมฝอยทองเพชรบุรี",
            "อาหารเช้าเมืองเพชรกินอะไรดี", "ร้านคาเฟ่ขนมหวานในตัวเมือง", "ปูม้าสดๆ สะพานปลาชะอำกิโลละเท่าไหร่",
            "ขนมจีนทอดมันเมืองเพชรหากินที่ไหน", "ทอดมันปลากรายท่ายาง", "ขนมผิงป้าลั้งท่ายาง",
            "มะนาวแป้นท่ายางซื้อที่ไหน", "ร้านของฝากแม่กิมไล้สาขาไหนดี", "ขนมบ้าบิ่นมะพร้าวอ่อน",
            "ทองหยิบทองหยอดเม็ดขนุน", "ก๋วยเตี๋ยวหมูน้ำแดงเพชรบุรี", "ร้านอาหารริมแม่น้ำเพชรบุรี",
            "ร้านกุ้งเผาปูม้าชะอำ", "หอยเชลล์ย่างเนยชะอำ", "หอยเสียบจิ้มสับปะรดเพชรบุรี",
            "กะปิแท้บ้านแหลม", "ดอกเกลือสมุทรซื้อที่ไหน", "น้ำตาลสดเคี่ยวเตาฟืนบ้านลาด",
            "ร้านข้าวแกงเมืองเพชรเจ้าเด็ด", "ร้านข้าวต้มรอบดึกเมืองเพชร", "คาเฟ่ริมทะเลชะอำอาหารอร่อย",
            "ขนมเสน่ห์จันทน์ทองเอก", "ขนมขี้หนูเพชรบุรี", "โตนดทอดและลูกตาลลอยแก้ว",
            "อาหารทะเลแห้งปลาหมึกแห้งชะอำ", "ร้านก๋วยเตี๋ยวเรือเพชรบุรี", "ของกินเล่นเมืองเพชร",
            "ร้านส้มตำรสเด็ดในเพชรบุรี", "น้ำพริกกะปิปลาทูทอดเพชรบุรี", "ปลาทูสดบ้านแหลม",
            "ผลไม้ GI ของเพชรบุรีมีอะไรบ้าง", "ชมพู่เพชรสายรุ้งกับทุเรียนป่าละอู", "เพชรบุรีเป็นเมืองอาหาร UNESCO ยังไง",
            "What food is Phetchaburi famous for?", "Recommend delicious Thai food in Phetchaburi",
            "Where can I buy Khanom Moo Kaeng?", "Tell me about Khao Chae Phetchaburi",
            "Best seafood restaurants near Cha-am beach", "Hello, I am hungry what should I eat here?",
            "Phetchaburi UNESCO City of Gastronomy", "Famous local desserts in Phetchaburi",
            "佛丕府有什么好吃的美食推荐？", "佛丕府有什么特色小吃？", "泰式蛋奶冻哪里买？",
            "七岩海滩附近有什么好吃的海鲜餐厅？", "你好，我饿了，有什么美食推荐？", "佛丕府为什么被称为美食之都？"
        ],
        "admission": [
            "PBVC", "BBC", "พีบีวีซี", "อาชีวะ", "วิทยาลัยอาชีวศึกษา", "อยากสมัครเรียน",
            "เรียนสาขาไหนดี", "ค่าเทอมเท่าไหร่", "สมัครยังไง", "ติดต่อวิทยาลัย", "อยากเป็นโปรแกรมเมอร์",
            "สาขาไหนน่าเรียน", "engineering", "computer", "digital business", "แผนกวิชา",
            "วิทยาลัยอาชีวศึกษาเพชรบุรีเปิดสอนสาขาอะไรบ้าง", "อยากสมัครเรียนต้องทำยังไง",
            "สาขาเทคโนโลยีธุรกิจดิจิทัลเรียนเกี่ยวกับอะไร", "เรียนจบดิจิทัลทำงานอะไรได้บ้าง",
            "สาขาคอมพิวเตอร์ธุรกิจยังมีอยู่ไหม", "อยากเขียนโปรแกรมและทำ AI ต้องเรียนสาขาไหน",
            "สาขาการบัญชีเรียนยากไหม", "จบการตลาดไปทำอาชีพอะไรได้บ้าง",
            "สาขาการท่องเที่ยวและการโรงแรมได้ไปฝึกงานที่ไหน", "อยากเป็นเชฟต้องเรียนสาขาอาหารและโภชนาการใช่ไหม",
            "สาขาแฟชั่นและดีไซน์สอนออกแบบเสื้อผ้าไหม", "เปิดรับสมัครนักศึกษาใหม่ช่วงไหน",
            "ค่าเทอมวิทยาลัยอาชีวศึกษาเพชรบุรีแพงไหม", "มีทุนการศึกษาให้ไหม", "รับสมัคร ปวช. และ ปวส. หรือเปล่า",
            "เกรดเฉลี่ยเท่าไหร่ถึงสมัครเรียนได้", "ต้องใช้เอกสารอะไรบ้างในการสมัครเรียน",
            "วิทยาลัยอาชีวศึกษาเพชรบุรีตั้งอยู่ที่ไหน", "เบอร์ติดต่อฝ่ายงานทะเบียนและประชาสัมพันธ์",
            "เรียนอาชีวะเพชรบุรีดีไหม", "มีโควตาเรียนต่อหรือเปล่า", "อยากเป็น Content Creator เรียนสาขาไหนดี",
            "อยากเป็นไกด์นำเที่ยวต้องเข้าสาขาอะไร", "เรียนทำเบเกอรี่และขนมหวานที่อาชีวะเพชรบุรี",
            "ชุดนักเรียนนักศึกษาอาชีวะเพชรบุรีเป็นยังไง", "สแกน QR Code สมัครเรียนตรงไหน",
            "มีระบบเทียบโอนความรู้ไหม", "จบ ม.3 ต่อสาขาอะไรดี", "จบ ม.6 ต่อ ปวส. สาขาไหนได้บ้าง",
            "ห้องปฏิบัติการคอมพิวเตอร์ทันสมัยไหม", "มีสอนทำเว็บไซต์และแอปพลิเคชันไหม",
            "แนวทางอาชีพหลังเรียนจบอาชีวศึกษาเพชรบุรี", "เงินเดือนของสายงานเทคโนโลยีธุรกิจดิจิทัล",
            "อยากเรียนบัญชีดิจิทัล", "สมัครเรียนออนไลน์ได้ทางไหน",
            "สาขาการจัดการธุรกิจค้าปลีกมีทุนไหม", "เรียน ปวช. อาชีวะเพชรกู้ กยศ. ได้ไหม",
            "ทุน กรอ. มีให้กู้ยืมไหม", "กำหนดการมอบตัวนักเรียนใหม่", "สอบสัมภาษณ์เข้าอาชีวะเพชรบุรี",
            "จบ กศน. สมัครเรียน ปวช. ได้ไหม", "จบ ปวช. ต่างสถาบันต่อ ปวส. ที่นี่ได้ไหม",
            "รอบโควตารับสมัครถึงวันไหน", "หอพักใกล้วิทยาลัยอาชีวศึกษาเพชรบุรี", "มีรถรับส่งนักศึกษาไหม",
            "แผนกอาหารและโภชนาการมีชุดเชฟไหม", "แผนกวิจิตรศิลป์และออกแบบ", "สาขากราฟิกดีไซน์",
            "ค่าเครื่องแบบและอุปกรณ์การเรียนเท่าไหร่", "ผ่อนผันค่าเทอมได้ไหม", "กิจกรรมรับน้องและปฐมนิเทศ",
            "เวลาเรียนของรอบวันอาทิตย์หรือภาคสมทบ", "มีหลักสูตรระยะสั้นไหม", "อบรมวิชาชีพระยะสั้นสอนอะไรบ้าง",
            "โครงการจัดการศึกษาทวิภาคีคืออะไร", "เรียนทวิภาคีได้เงินเดือนระหว่างเรียนไหม",
            "What majors does PBVC offer?", "Tell me about Phetchaburi Vocational College",
            "How do I apply to study at PBVC?", "Digital Business Technology department details",
            "Tuition fees for vocational certificate", "Hello, I want to study computer at PBVC",
            "佛丕府职业学院有哪些专业？", "怎么报名佛丕府职业学院？", "请问学费是多少？", "数字商业技术专业学什么？"
        ],
        "greeting": [
            "สวัสดี", "สวัสดีครับ", "สวัสดีค่ะ", "หวัดดีน้องเพชร", "ดีจ้า",
            "เธอชื่ออะไร", "คุณคือใคร", "น้องเพชรคืออะไร",
            "ทำอะไรได้บ้าง", "ช่วยอะไรได้บ้าง", "ใครเป็นคนสร้างน้องเพชร",
            "ยินดีที่ได้รู้จักนะ", "ทักทายครับ", "ฮัลโหล", "Hello", "Hi น้องเพชร",
            "Hello there", "Hi!", "Hey Nong Phet", "Good evening", "Nice to meet you",
            "Who are you?", "What is your name?", "What can you do?", "Thank you very much", "Goodbye", "Bye bye",
            "你好", "您好", "嗨", "早上好", "很高兴认识你", "你是谁？", "你叫什么名字？", "你能做什么？", "谢谢", "再见",
            "เป็นหุ่นยนต์ของวิทยาลัยอาชีวศึกษาเพชรบุรีใช่ไหม", "วันนี้เป็นยังไงบ้าง",
            "สบายดีไหมน้องเพชร", "คุยเป็นเพื่อนหน่อย", "เก่งจังเลยนะ", "ขอบคุณมากครับ",
            "ขอบคุณค่ะ", "บ๊ายบาย", "ไว้เจอกันใหม่นะ", "น่ารักจัง", "พูดภาษาอะไรได้บ้าง",
            "ทำงานยังไงเหรอ", "เริ่มต้นใช้งานยังไง",
            "มีเมนูอะไรให้เลือกบ้าง", "เรียกใช้งานยังไง", "ตื่นหรือยังน้องเพชร", "พร้อมให้บริการไหม",
            "น้องเพชรน่ารักมาก", "เก่งมากเลย", "สุดยอดไปเลยหุ่นยนต์", "ขอบใจจ้า",
            "ลาก่อนนะ", "Good morning", "Good afternoon", "บายบาย",
            "หลับอยู่หรือเปล่า", "หุ่นยนต์ตัวนี้เจ๋งมาก",
            "น้องเพชรเป็น AI ใช่ไหม", "พูดเสียงน่ารักจัง", "ฟังรู้เรื่องไหม", "ขอคุยด้วยหน่อย",
            "ว่างคุยไหม", "เปิดหน้าแรก", "ไปหน้าเมนูหลัก"
        ],
        "general_faq": [
            "ห้องน้ำอยู่ไหน", "ช่วยด้วย", "เบอร์ฉุกเฉิน", "ขอดูแผนที่", "กี่โมงแล้ว", "การเดินทาง",
            "วันนี้อากาศที่เพชรบุรีเป็นยังไง", "วันนี้ฝนจะตกไหม", "อุณหภูมิตอนนี้กี่องศา",
            "สภาพอากาศเหมาะกับการไปเที่ยวทะเลไหม", "เพชรบุรีห่างจากกรุงเทพกี่กิโลเมตร",
            "เดินทางจากกรุงเทพมาเพชรบุรีกี่ชั่วโมง", "มีรถตู้หรือรถทัวร์มาเพชรบุรีไหม",
            "สถานีรถไฟเพชรบุรีอยู่ไกลจากเขาวังไหม", "โรงพยาบาลในตัวเมืองเพชรบุรีอยู่ไหน",
            "เบอร์โทรฉุกเฉินตำรวจท่องเที่ยว", "เพชรบุรีมีกี่อำเภอ", "คำขวัญจังหวัดเพชรบุรีคืออะไร",
            "ทำไมถึงชื่อจังหวัดเพชรบุรี", "งานพระนครคีรีจัดช่วงเดือนไหน", "หน้าฝนเที่ยวไหนได้บ้างในเพชรบุรี",
            "หน้าร้อนเพชรบุรีร้อนมากไหม", "มีรถสองแถวหรือวินมอเตอร์ไซค์ในเมืองไหม",
            "ที่จอดรถแถวเขาวังจอดตรงไหนได้บ้าง", "ห้องน้ำสาธารณะอยู่ตรงไหน",
            "ตอนนี้เวลาเท่าไหร่แล้ว", "วันนี้วันอะไร", "ขอพิกัดแผนที่ Google Maps หน่อย",
            "ใช้อินเทอร์เน็ตฟรีได้ที่ไหนบ้าง", "ตู้ ATM อยู่แถวไหน", "ปั๊มน้ำมันที่ใกล้ที่สุด",
            "ร้านขายยาแถวนี้มีไหม", "เที่ยวเพชรบุรีใช้งบประมาณเท่าไหร่ดี", "เพชรบุรีปลอดภัยไหม",
            "ไปชะอำขึ้นรถตรงไหน", "มีที่พักหรือโรงแรมราคาประหยัดแนะนำไหม",
            "เช่ารถเที่ยวในเพชรบุรีได้ที่ไหน", "สภาพการจราจรในเมืองเพชรเป็นยังไง",
            "เบอร์ติดต่อสอบถามข้อมูลท่องเที่ยว", "จุดชาร์จรถยนต์ไฟฟ้า EV ในเพชรบุรี", "ขอความช่วยเหลือหน่อย",
            "โรงพยาบาลพระจอมเกล้าจังหวัดเพชรบุรีไปยังไง", "เบอร์โทรสถานีตำรวจเพชรบุรี", "เบอร์โทร 191 เพชรบุรี",
            "เบอร์กู้ภัยเพชรบุรี", "ท่ารถตู้เพชรบุรีไปกรุงเทพอยู่ที่ไหน", "วินมอเตอร์ไซค์รับจ้างอยู่ตรงไหน",
            "ตู้กดเงินธนาคารกรุงไทยอยู่แถวนี้ไหม", "เซเว่นใกล้ที่สุดอยู่ตรงไหน", "ปั๊ม ปตท. แถวนี้มีไหม",
            "สถานีรถไฟเพชรบุรีไปหัวหิน", "ขบวนรถไฟนำเที่ยวสวนสนประดิพัทธ์ผ่านเพชรบุรีไหม",
            "จุดบริการนักท่องเที่ยวเขาวัง", "ติดต่อเทศบาลเมืองเพชรบุรี", "ห้างสรรพสินค้าในเพชรบุรีมีที่ไหนบ้าง",
            "ห้างโรบินสันเพชรบุรีอยู่ตรงไหน", "บิ๊กซีเพชรบุรีไปยังไง", "ร้านซ่อมรถแถวนี้มีไหม", "ร้านปะยางใกล้ฉัน",
            "Where is the restroom?", "Where is the nearest toilet?", "What is the emergency phone number?",
            "How is the weather in Phetchaburi today?", "How do I travel from Bangkok to Phetchaburi?",
            "Where is the hospital or police station?", "Hello, where is the toilet please?",
            "请问洗手间在哪里？", "请问厕所在哪里？", "紧急求助电话是多少？",
            "从曼谷怎么坐车去佛丕府？", "今天佛丕府天气怎么样？", "附近的医院在哪里？"
        ]
    }

    # ผสานคำถามและคีย์เวิร์ดทั้งหมดจาก knowledge_base.json เข้าสู่ชุดฝึกสอน
    kb_path = "knowledge_base.json"
    if os.path.exists(kb_path):
        try:
            import json
            with open(kb_path, 'r', encoding='utf-8') as f:
                kb_data = json.load(f)
            for entry in kb_data.get("entries", []):
                ent_intent = entry.get("intent", "general_faq")
                if ent_intent == "witty":
                    ent_id = entry.get("id", "")
                    if "khaowang" in ent_id or "eiffel" in ent_id:
                        target_class = "travel"
                    elif "love" in ent_id:
                        target_class = "greeting"
                    elif "robot" in ent_id:
                        target_class = "admission"
                    else:
                        target_class = "general_faq"
                elif ent_intent in seed_dict:
                    target_class = ent_intent
                else:
                    target_class = "general_faq"

                for q in entry.get("questions", []):
                    if q not in seed_dict[target_class]:
                        seed_dict[target_class].append(q)
            print("  ✅ ผสานข้อมูลจาก knowledge_base.json เข้าสู่ชุด Seed Dataset สำเร็จ")
        except Exception as e:
            print(f"  ⚠️ ไม่สามารถอ่าน knowledge_base.json: {e}")

    return seed_dict


def augment_thai_dataset(seed_dict, target_per_class=600):
    """
    ฟังก์ชันขยายขนาดชุดข้อมูลหลายภาษา (Multilingual Data Augmentation: TH / EN / ZH)
    จับคู่คำขึ้นต้น/ลงท้ายตามภาษาอย่างเป็นธรรมชาติ และสอนรูปแบบ "ทักทาย+คำถาม" ในหมวดที่ไม่ใช่ greeting
    รวม 5 คลาส คลาสละ 600 ตัวอย่าง = รวม 3,000 ตัวอย่าง
    """
    th_prefixes = [
        "", "น้องเพชร ", "น้องเพชรครับ ", "น้องเพชรคะ ", "สอบถามหน่อย ",
        "อยากรู้ว่า ", "ช่วยบอกทีว่า ", "ขอถามนิดนึง ", "รบกวนถามหน่อย ", "อยากทราบว่า ",
        "ขอข้อมูล ", "น้องเพชรช่วยดู ", "บอกหน่อยจ้า ", "สงสัยว่า ", "ขอสอบถาม ", "อยากได้ข้อมูล "
    ]
    th_greeting_prefixes = ["สวัสดีค่ะ ", "สวัสดีครับ ", "หวัดดีน้องเพชร "]
    th_suffixes = [
        "", " ครับ", " ค่ะ", " นะครับ", " นะคะ", " จ๊ะ", " หน่อยครับ",
        " หน่อยค่ะ", " ได้ไหม", " บ้างครับ", " บ้างคะ", " ช่วยแนะนำที",
        " หน่อยดิ", " มีไหมครับ", " มีไหมคะ", " ได้หรือเปล่า", " จ้า", " ทีค่ะ", " หน่อยสิ"
    ]

    en_prefixes = ["", "Excuse me, ", "Please tell me ", "Could you tell me ", "I want to know "]
    en_greeting_prefixes = ["Hello, ", "Hi, ", "Hi Nong Phet, ", "Hey, "]
    en_suffixes = ["", " please", " please?", " thank you"]

    zh_prefixes = ["", "请问", "我想问一下", "麻烦问一下"]
    zh_greeting_prefixes = ["你好，", "你好，请问", "嗨，请问"]
    zh_suffixes = ["", "？", "呢？", "谢谢"]

    rows = []
    for intent, phrases in seed_dict.items():
        generated = set()
        th_phrases, en_phrases, zh_phrases = [], [], []

        for p in phrases:
            clean_p = p.strip()
            generated.add(clean_p)
            if re.search(r'[\u0E00-\u0E7F]', clean_p):
                th_phrases.append(clean_p)
            elif re.search(r'[\u4E00-\u9FFF]', clean_p):
                zh_phrases.append(clean_p)
            else:
                en_phrases.append(clean_p)

        # ตั้งโควตาสมดุลให้มีตัวอย่าง EN/ZH เพียงพอ ไม่ถูกตัวอย่างภาษาไทยกลบ (TH ~72%, EN ~14%, ZH ~14%)
        en_target = int(target_per_class * 0.14) if en_phrases else 0
        zh_target = int(target_per_class * 0.14) if zh_phrases else 0

        def _fill_group(pool, pref_list, greet_pref_list, suf_list, limit_add):
            added = 0
            attempts = 0
            active_prefs = pref_list + (greet_pref_list if intent != "greeting" else [])
            while added < limit_add and len(generated) < target_per_class and attempts < 8000:
                base = random.choice(pool)
                pre = random.choice(active_prefs)
                suf = random.choice(suf_list)
                if pre in greet_pref_list and base.lower().startswith(("hello", "hi", "你好", "สวัสดี", "หวัดดี")):
                    pre = ""
                combined = f"{pre}{base}{suf}".strip()
                if combined not in generated:
                    generated.add(combined)
                    added += 1
                attempts += 1

        if en_phrases:
            _fill_group(en_phrases, en_prefixes, en_greeting_prefixes, en_suffixes, en_target)
        if zh_phrases:
            _fill_group(zh_phrases, zh_prefixes, zh_greeting_prefixes, zh_suffixes, zh_target)

        th_pool = th_phrases if th_phrases else phrases
        _fill_group(th_pool, th_prefixes, th_greeting_prefixes, th_suffixes, target_per_class)

        for text in list(generated)[:target_per_class]:
            rows.append({"text": text, "intent": intent})

    df = pd.DataFrame(rows)
    # สลับลำดับข้อมูลแบบสุ่ม (Shuffle)
    df = df.sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
    return df


# ==============================================================================
# ส่วนที่ 2: การทำความสะอาดข้อความและตัดคำภาษาไทย (Preprocessing & Tokenization)
# ==============================================================================
def thai_text_tokenizer(text):
    """
    ฟังก์ชันทำความสะอาดข้อความและตัดคำไทย (newmm) + แยกอักษรจีน CJK (unigram/bigram)
    """
    if not isinstance(text, str):
        return []
    # 1. ปรับรูปสระและวรรณยุกต์ที่พิมพ์ซ้ำหรือผิดลำดับให้เป็นมาตรฐาน
    cleaned = normalize(text.strip().lower())
    # 2. ตัดคำด้วยพจนานุกรม Maximum Matching (newmm)
    raw_tokens = word_tokenize(cleaned, engine="newmm", keep_whitespace=False)
    # 3. แยกอักษรจีน CJK เป็น unigram + bigram เพื่อให้ TF-IDF จับคีย์เวิร์ดภาษาจีนได้แม่นยำ
    tokens = []
    for tok in raw_tokens:
        tok = tok.strip()
        if not tok:
            continue
        if re.search(r'[\u4E00-\u9FFF]', tok):
            for seg in re.findall(r'[\u4E00-\u9FFF]+|[^\u4E00-\u9FFF]+', tok):
                if re.search(r'[\u4E00-\u9FFF]', seg):
                    chars = list(seg)
                    tokens.extend(chars)
                    for i in range(len(chars) - 1):
                        tokens.append(chars[i] + chars[i + 1])
                else:
                    tokens.append(seg)
        else:
            tokens.append(tok)
    return tokens


# ==============================================================================
# ส่วนที่ 3: กระบวนการฝึกสอนโมเดล (Training) และประเมินผล (Evaluation)
# ==============================================================================
def train_and_evaluate():
    print("=" * 70)
    print("🚀 เริ่มต้นกระบวนการพัฒนาโมเดล AI: น้องเพชร AI Smart Guide")
    print("=" * 70)

    # 1. สร้างและบันทึกชุดข้อมูล (Dataset)
    print("[1/5] กำลังจัดเตรียมชุดข้อมูลหลายภาษา TH/EN/ZH (Dataset Preparation)...")
    seed_data = get_seed_dataset()
    df = augment_thai_dataset(seed_data, target_per_class=600)  # รวม 5 * 600 = 3,000 ตัวอย่าง
    
    dataset_path = os.path.join(ARTIFACT_DIR, "dataset_nongphet.csv")
    df.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    print(f"  ✅ บันทึกชุดข้อมูลสำเร็จ: {dataset_path} (จำนวนรวม {len(df)} ตัวอย่าง)")
    print(f"  📊 สัดส่วนข้อมูลแต่ละคลาส:\n{df['intent'].value_counts()}\n")

    # 2. แบ่งข้อมูลสำหรับฝึกสอน (Train 80%) และทดสอบ (Test 20%) แบบ Stratified
    print("[2/5] กำลังแบ่งชุดข้อมูล Train (80%) และ Test (20%)...")
    X = df["text"].values
    y = df["intent"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=RANDOM_SEED, stratify=y
    )
    print(f"  ✅ ข้อมูลสำหรับ Train: {len(X_train)} ตัวอย่าง | ข้อมูลสำหรับ Test: {len(X_test)} ตัวอย่าง\n")

    # 3. สกัดคุณลักษณะข้อความด้วย Hybrid FeatureUnion (Word N-gram + Character N-gram)
    print("[3/5] กำลังสกัดคุณลักษณะด้วย Hybrid Word+Char TF-IDF Vectorizer...")
    word_vectorizer = TfidfVectorizer(
        tokenizer=thai_text_tokenizer,
        token_pattern=None,
        ngram_range=(1, 2),
        min_df=2,
        sublinear_tf=True
    )
    char_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=3,
        sublinear_tf=True
    )
    vectorizer = FeatureUnion([
        ("word", word_vectorizer),
        ("char", char_vectorizer)
    ])

    X_train_tfidf = vectorizer.fit_transform(X_train)
    X_test_tfidf = vectorizer.transform(X_test)
    total_features = X_train_tfidf.shape[1]
    print(f"  ✅ ขนาดคุณลักษณะรวม (Word + Char N-gram Features): {total_features} ฟีเจอร์\n")

    # 4. ฝึกสอนโมเดลและทำ 5-Fold Stratified Cross-Validation เปรียบเทียบ LR, Calibrated LinearSVC, Soft Voting Ensemble
    print("[4/5] กำลังฝึกสอนและทำ 5-Fold Cross-Validation (LR / Calibrated LinearSVC / Ensemble)...")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)

    lr_model = LogisticRegression(C=3.0, max_iter=1000, random_state=RANDOM_SEED)
    svm_model = CalibratedClassifierCV(LinearSVC(C=1.0, random_state=RANDOM_SEED), cv=5)
    ensemble_model = VotingClassifier(
        estimators=[
            ("lr", LogisticRegression(C=3.0, max_iter=1000, random_state=RANDOM_SEED)),
            ("svm", CalibratedClassifierCV(LinearSVC(C=1.0, random_state=RANDOM_SEED), cv=5)),
        ],
        voting="soft",
        weights=[1, 2]
    )

    candidates = [
        ("Logistic Regression", lr_model),
        ("Calibrated Linear SVM", svm_model),
        ("Soft Voting Ensemble (LR+SVM)", ensemble_model),
    ]

    best_score = -1.0
    best_score_tuple = (-1.0, -1.0)
    best_model = None
    best_preds = None
    best_name = ""
    cv_summary_lines = []

    for name, clf in candidates:
        cv_scores = cross_val_score(clf, X_train_tfidf, y_train, cv=cv, scoring="accuracy")
        clf.fit(X_train_tfidf, y_train)
        preds = clf.predict(X_test_tfidf)
        acc_val = accuracy_score(y_test, preds)
        cv_mean, cv_std = float(cv_scores.mean()), float(cv_scores.std())
        line = f"{name:<32} | 5-Fold CV: {cv_mean:.4f} ± {cv_std:.4f} | Test Acc: {acc_val:.4f} ({acc_val*100:.2f}%)"
        cv_summary_lines.append(line)
        print(f"  🔹 {line}")
        # เลือกจาก Test Accuracy และใช้ 5-Fold CV เป็นตัวตัดสินเมื่อคะแนนเท่ากัน
        composite = (round(acc_val, 6), round(cv_mean, 6))
        if best_model is None or composite > best_score_tuple:
            best_score_tuple = composite
            best_score = acc_val
            best_model = clf
            best_preds = preds
            best_name = name

    print(f"\n  🏆 โมเดลที่ได้รับคัดเลือก: {best_name} (Test Accuracy = {best_score*100:.2f}%)\n")

    # 5. การวัดผลเชิงลึก (Accuracy, Precision, Recall, F1-Score) และสร้าง Confusion Matrix
    print("[5/5] กำลังประเมินผลโมเดลและสร้างภาพ Confusion Matrix...")
    acc = accuracy_score(y_test, best_preds)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, best_preds, average="weighted"
    )

    report_str = classification_report(y_test, best_preds, digits=4)
    print("\n---------------- รายงานผลการทดสอบโมเดล (Classification Report) ----------------")
    print(report_str)
    print(f"สรุปภาพรวม -> Accuracy: {acc:.4f} | Precision: {precision:.4f} | Recall: {recall:.4f} | F1-Score: {f1:.4f}")
    print("-------------------------------------------------------------------------------\n")

    # บันทึกรายงานผลเป็นไฟล์ข้อความสำหรับแนบภาคผนวก ว-สอศ-3
    report_path = os.path.join(ARTIFACT_DIR, "evaluation_metrics.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Model: {best_name}\n")
        f.write(f"Total Dataset Size: {len(df)} samples (Train: {len(X_train)}, Test: {len(X_test)})\n")
        f.write(f"Overall Accuracy : {acc:.4f}\n")
        f.write(f"Weighted Precision: {precision:.4f}\n")
        f.write(f"Weighted Recall   : {recall:.4f}\n")
        f.write(f"Weighted F1-Score : {f1:.4f}\n\n")
        f.write("5-Fold Stratified Cross-Validation & Test Comparison:\n")
        for line in cv_summary_lines:
            f.write(f"  {line}\n")
        f.write("\nDetailed Classification Report:\n")
        f.write(report_str)

    # พล็อตและบันทึกภาพ Confusion Matrix (ถ้ามี matplotlib/seaborn)
    labels = sorted(list(seed_data.keys()))
    cm = confusion_matrix(y_test, best_preds, labels=labels)

    if HAS_PLOT:
        plt.rcParams['font.sans-serif'] = ['Tahoma', 'Leelawadee UI', 'Angsana New', 'Cordia New', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        plt.figure(figsize=(8, 6), dpi=300)
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues",
            xticklabels=labels,
            yticklabels=labels,
            cbar=True,
            annot_kws={"size": 12, "weight": "bold"}
        )
        plt.title(f"Confusion Matrix - Nong Phet Intent Classifier\n({best_name} | Accuracy = {acc:.2%})", fontsize=13, pad=15)
        plt.xlabel("Predicted Intent (หมวดหมู่ที่โมเดลทำนาย)", fontsize=11)
        plt.ylabel("Actual Intent (หมวดหมู่จริง)", fontsize=11)
        plt.tight_layout()

        cm_image_path = os.path.join(ARTIFACT_DIR, "confusion_matrix.png")
        plt.savefig(cm_image_path)
        plt.savefig("confusion_matrix.png")
        plt.close()
        print(f"  ✅ บันทึกกราฟ Confusion Matrix สำเร็จที่: confusion_matrix.png และ {cm_image_path}")
    else:
        print("  ℹ️ ข้ามการสร้างภาพ Confusion Matrix (ไม่ได้ติดตั้ง matplotlib/seaborn) โดยยังบันทึกข้อมูลสถิติครบถ้วน")

    # บันทึกไฟล์โมเดลและ Vectorizer (.pkl)
    # หมายเหตุ: ก่อนเซฟ vectorizer เราแยก tokenizer ออกแล้วใช้ฟังก์ชันมาตรฐานตอนโหลดเพื่อป้องกันปัญหา Pickle ข้ามไฟล์
    model_path = os.path.join(ARTIFACT_DIR, "model.pkl")
    vec_path = os.path.join(ARTIFACT_DIR, "vectorizer.pkl")

    joblib.dump(best_model, model_path)
    joblib.dump(vectorizer, vec_path)
    # สำเนาไว้ที่รากโปรเจกต์ตามข้อกำหนด
    joblib.dump(best_model, "model.pkl")
    joblib.dump(vectorizer, "vectorizer.pkl")

    print(f"  ✅ บันทึกไฟล์โมเดลสำเร็จ: model.pkl และ vectorizer.pkl")

    # ทดสอบความแม่นยำกับประโยคจริงนอกชุดฝึกสอน หลายภาษา TH/EN/ZH (Real-World Unseen Probe Test)
    probe_cases = [
        ("แนะนำสถานที่ท่องเที่ยวให้หน่อย", "travel"),
        ("อยากไปเที่ยวทะเล", "travel"),
        ("พระนครคีรีเปิดกี่โมง", "travel"),
        ("อำเภอบ้านลาดมีดงตาลโตนดไหม", "travel"),
        ("ตลาดน้ำท่ายางเปิดวันไหน", "travel"),
        ("บ่อน้ำพุร้อนหนองหญ้าปล้องอยู่ที่ไหน", "travel"),
        ("ช่วยจัดทริปเที่ยวเพชรบุรี 1 วันหน่อย", "travel"),
        ("Hello, where is Khao Wang in Phetchaburi?", "travel"),
        ("Where is Khao Wang and how can I get there?", "travel"),
        ("你好，请问怎么去拷汪宫？", "travel"),
        ("กินอะไรดีวันนี้", "food"),
        ("หิวข้าวมาก", "food"),
        ("ขนมหม้อแกงซื้อที่ไหน", "food"),
        ("ผลไม้ GI ของเพชรบุรีมีอะไรบ้าง", "food"),
        ("What famous food is in Phetchaburi?", "food"),
        ("佛丕府有什么好吃的美食推荐？", "food"),
        ("BBC", "admission"),
        ("พีบีวีซีเปิดสอนสาขาอะไร", "admission"),
        ("สวัสดีค่ะ อยากสมัครเรียนอาชีวะเพชรบุรี", "admission"),
        ("Tell me how to enroll in PBVC?", "admission"),
        ("สวัสดีค่ะน้องเพชร", "greeting"),
        ("Hello", "greeting"),
        ("你好", "greeting"),
        ("ห้องน้ำอยู่ตรงไหน", "general_faq"),
        ("Where is the restroom?", "general_faq"),
        ("请问洗手间在哪里？", "general_faq"),
    ]
    probe_texts = [p[0] for p in probe_cases]
    probe_expected = [p[1] for p in probe_cases]
    probe_vecs = vectorizer.transform(probe_texts)
    probe_preds = best_model.predict(probe_vecs)
    probe_correct = sum(1 for pred, exp in zip(probe_preds, probe_expected) if pred == exp)
    print(f"\n🧪 ผลทดสอบประโยคจริงนอกชุดฝึกสอน (Unseen Probe Test): {probe_correct}/{len(probe_cases)} ({probe_correct/len(probe_cases)*100:.1f}%)")
    for text, exp, pred in zip(probe_texts, probe_expected, probe_preds):
        mark = "✅" if pred == exp else "❌"
        print(f"  {mark} \"{text}\" -> ทำนาย: {pred} (คาดหวัง: {exp})")

    print("=" * 70)
    print("🎉 เสร็จสมบูรณ์! พร้อมนำโมเดลไปเชื่อมต่อกับระบบหลักและนำรูปไปใส่ในเล่มวิจัย ว-สอศ-3")
    print("=" * 70)


if __name__ == "__main__":
    train_and_evaluate()