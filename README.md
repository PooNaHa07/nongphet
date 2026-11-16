# น้องเพชร AI Smart Guide (PBVC) — นวัตกรรมหุ่นยนต์และ AI ต้อนรับอัจฉริยะ

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/framework-Flask%203.0+-green.svg)](https://flask.palletsprojects.com/)
[![OpenCV](https://img.shields.io/badge/vision-OpenCV%20YuNet%20ONNX-orange.svg)](https://opencv.org/)
[![Hardware](https://img.shields.io/badge/target-Raspberry%20Pi%205%208GB-red.svg)](https://www.raspberrypi.com/)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

**"น้องเพชร AI Smart Guide"** คือหุ่นยนต์ประชาสัมพันธ์และไกด์นำเที่ยวอัจฉริยะ (AI Interactive Robot Kiosk) ผลงานนวัตกรรมสิ่งประดิษฐ์ของ**วิทยาลัยอาชีวศึกษาเพชรบุรี (PBVC)** ออกแบบตามมาตรฐานเกณฑ์การประเมินสิ่งประดิษฐ์คนรุ่นใหม่ สอศ. ประเภทหุ่นยนต์และปัญญาประดิษฐ์

ระบบผสานพลังระหว่าง **Edge Computing บน Raspberry Pi 5** สำหรับงานที่ต้องการความเร็วสูงและทำงานแบบออฟไลน์ได้ (Local ML Intent Classifier, Semantic Retrieval, YuNet Face & Gaze Tracking, Universal Design Thai Sign Language) ร่วมกับ **Cloud Multimodal AI (Google Gemini 2.5 Flash)** สำหรับการวิเคราะห์ภาพสถานที่ท่องเที่ยวเชิงลึกและการสนทนาแบบเปิดอย่างเป็นธรรมชาติ

---

## 🌟 ฟีเจอร์หลัก (Key Features)

### 1. 👁️ ระบบการมองเห็นอัจฉริยะและการตรวจจับการมองจอจริง (Attention Gating & Vision Daemon)
- **OpenCV YuNet ONNX Deep Learning**: ตรวจจับใบหน้าและ 5 จุด Landmark (ตาสองข้าง, จมูก, มุมปาก) ด้วยความเร็วสูง (>16-25 FPS บนอุปกรณ์ Edge)
- **Attention Gating (ตรวจการมองจอจริงก่อนทัก)**: ประเมินมุมองศาการหันศีรษะ (Yaw / Pitch) และสัดส่วนระยะตากับสันจมูก จะทักทายเฉพาะเมื่อผู้มาติดต่อ **หันหน้าสบตามองจอจริง** ($|\text{Yaw}| \le 22^\circ$) ตัดปัญหาทักคนที่เพียงเดินผ่านทางเดิน
- **Smart Motion Gaze Tracking**: ส่งพิกัดเป้าหมาย $(X, Y)$ ให้ดวงตาน้องเพชรบน Screen 2 กวาดสายตามองสบตาผู้ใช้ได้อย่างนุ่มนวลด้วยอัลกอริทึม Exponential Moving Average (EMA)
- **No Repeat & Session Reset**: ล็อกเซสชันไม่ทักทายซ้ำตราบใดที่ผู้ใช้ยังคงอยู่หน้าตู้ และจะรีเซ็ตต้อนรับคนใหม่เมื่อผู้ใช้ออกไปเกิน 4 วินาที

### 2. 🗣️ ระบบการสนทนาและโต้ตอบด้วยเสียง (Voice Pipeline & Turn-Taking)
- **Instant Pre-baked Cache (0ms Latency)**: สังเคราะห์เสียงตอบคำถามยอดนิยมล่วงหน้า (3 ภาษา: ไทย, อังกฤษ, จีน) เล่นเสียงตอบกลับทันทีโดยไม่ต้องรอเครือข่าย
- **Voice Turn-Taking & Echo Prevention**: ควบคุมจังหวะพูด-ฟังแบบ Half-Duplex ตัดไมค์ทันทีเมื่อหุ่นยนต์พูด ป้องกันไมโครโฟนดูดเสียงตัวเอง (Self-Echo) พร้อมระยะพักเสียงสะท้อน (Acoustic Decay 350ms)
- **Voice Barge-In**: ผู้ใช้สามารถพูดแทรกหรือแตะหน้าจอเพื่อขัดจังหวะการเล่าเรื่องยาวๆ ได้ทันที
- **Earcon Feedback**: สัญญาณเสียงนุ่มนวล ปิ๊ง! (Listen Chime) และ ปุ๊ง! (Done Chime) ช่วยให้ผู้ใช้ทราบจังหวะเริ่มพูด

### 3. 🧠 สถาปัตยกรรม Hybrid AI & Semantic RAG (Offline + Cloud)
- **Local Machine Learning**: Scikit-Learn Multilingual Intent Classifier จำแนกเจตนาคำถาม (ท่องเที่ยว, อาหาร, หลักสูตรวิทยาลัย, การเดินทาง, ทักทาย)
- **Dynamic Semantic RAG**: ค้นหาคำตอบจากคลังความรู้ `knowledge_base.json` ด้วย TF-IDF Cosine Similarity และ Synonym Expansion แม่นยำ รวดเร็ว และรองรับ Hot-Reload โดยไม่ต้องรีสตาร์ทแอป
- **Google Gemini 2.5 Flash / 2.0 Flash**: ตอบคำถามเชิงลึก วางแผนทริปท่องเที่ยว 1-2 วัน และวิเคราะห์รูปภาพถ่ายสถานที่

### 4. 🤟 Universal Design — ภาษามือไทย (Thai Sign Language: TSL)
- ตรวจจับจุดข้อต่อนิ้วมือ 21 จุดผ่านกล้อง เพื่อแปลภาษามือพื้นฐานสำหรับผู้บกพร่องทางการได้ยิน ส่งเสริมความเท่าเทียมในการเข้าถึงข้อมูลท่องเที่ยวและสถานศึกษา

### 5. 🖥️ สถาปัตยกรรม Dual-Screen Kiosk
- **Screen 1 (Main Interaction Screen - 10.1" Touch)**: หน้าจอโต้ตอบ แชท ค้นหาข้อมูล เมนูแนะนำ และคลังความรู้
- **Screen 2 (Emotion Avatar Screen)**: หน้าจอแสดงสีหน้าอารมณ์น้องเพชร (ยิ้ม, ดีใจ, รับฟัง, คิด, สบตาตามผู้ใช้, แสดงการขยับปาก Lip-Sync ตามเสียงพูด)

---

## 🏗️ สถาปัตยกรรมระบบ (System Architecture)

```
+-----------------------------------------------------------------------------------+
|                            USER INPUT / SENSORY LAYER                             |
|  - USB Microphone (STT)      - 10.1" Capacitive Touch Display (Kiosk UI)          |
|  - USB Camera (OpenCV YuNet) - Ultrasonic & Presence Detection (IoT Sensor)       |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
|                        APPLICATION LAYER (Raspberry Pi 5 / PC)                    |
|                                                                                   |
|  [Modular Flask Server - app.py / app_new.py] (Port 5000)                         |
|   ├── routes/chat.py      : รับส่งข้อความ, จัดการบทสนทนา, Semantic RAG            |
|   ├── routes/vision.py    : Multimodal Vision, TSL Sign Language                  |
|   ├── routes/knowledge.py : Dynamic RAG Knowledge Base CRUD & Retrain APIs       |
|   ├── routes/iot.py       : Sensor Triggers, SSE Stream, Gaze Tracking            |
|   ├── routes/admin.py     : Telemetry Dashboard & Mission Control                 |
|   ├── routes/display.py   : Dual-Screen Emotion Display & QR Mobile Handoff       |
|   └── routes/media.py     : Edge Neural TTS, Pre-baked Cache, Weather             |
|                                                                                   |
|  [Computer Vision Daemon - vision_daemon.py] (Port 5002)                          |
|   ├── YuNet ONNX Face & Landmark Detector (16-25 FPS)                             |
|   ├── Attention Gating (คำนวณ Yaw / Pitch ตรวจการมองจอจริงก่อนทัก)                 |
|   ├── Gaze Smoothing (EMA 0.65/0.35 ส่งพิกัดสายตาไปที่ /api/emotion/gaze)         |
|   └── MJPEG Live Video Stream (/video_feed, /snapshot.jpg, /status)               |
+-----------------------------------------------------------------------------------+
             │                                             │
             ▼ (Offline Edge)                              ▼ (Cloud AI)
+---------------------------------------+   +---------------------------------------+
|          LOCAL EDGE AI ENGINE         |   |         CLOUD MULTIMODAL ENGINE       |
|  - Semantic Retriever (TF-IDF +       |   |  - Google Gemini 2.5 Flash            |
|    Cosine Similarity with Hot Reload) |   |  - Fallback: Gemini 2.0 Flash         |
|  - Local ML Intent Classifier         |   |  - Deep Cultural & Travel Knowledge   |
|  - TSL 21-Joint Geometric Classifier  |   |  - Multimodal Photo Verification      |
|  - Pre-baked Audio Cache (0ms)        |   |                                       |
+---------------------------------------+   +---------------------------------------+
```

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
nongphet/
├── app.py                      # Main Modular Flask Application Entry Point
├── app_new.py                  # Entry Point Compatibility Alias
├── vision_daemon.py            # AI Computer Vision Daemon & MJPEG Streamer (Port 5002)
├── config.py                   # System Configuration & API Keys
├── state.py                    # Centralized Shared Mutable State
├── intent_classifier.py        # Scikit-Learn Multilingual Intent Classifier
├── semantic_retriever.py       # TF-IDF RAG Knowledge Retriever
├── prebake_tts.py              # Script สร้างแคชเสียงคำตอบ 0ms ล่วงหน้า
├── knowledge_base.json         # ฐานข้อมูลความรู้การท่องเที่ยวและวิทยาลัย (42+ หมวด)
├── requirements.txt            # รายการ Dependencies หลักของระบบ
│
├── routes/                     # Modular Flask Blueprints
│   ├── chat.py                 # จัดการแชทและการสืบค้นความรู้
│   ├── vision.py               # วิเคราะห์รูปภาพและภาษามือ TSL
│   ├── media.py                # ระบบเสียงสังเคราะห์ TTS & สภาพอากาศ
│   ├── iot.py                  # จัดการเซนเซอร์ตรวจจับและอีเวนต์ SSE
│   ├── admin.py                # หน้าแดชบอร์ดและการตั้งค่าระบบ
│   ├── display.py              # แสดงผลหน้าจอที่ 2 (Emotion Avatar)
│   └── knowledge.py            # API จัดการฐานความรู้และการเรียนรู้แบบทันที
│
├── services/                   # Business Logic & External Services
│   ├── tts_service.py          # Edge-TTS, Cache Manager, Text Normalizer
│   ├── gemini_service.py       # Gemini API SDK Client
│   └── analytics_service.py    # บันทึกสถิติผู้เข้าชม
│
├── models/                     # Deep Learning Models
│   └── face_detection_yunet_2023mar.onnx  # OpenCV YuNet Face & Landmark Model
│
├── ml_artifacts/               # Intent Classification Artifacts
│   ├── model.pkl               # Trained Classifier Model
│   ├── vectorizer.pkl          # TF-IDF Vectorizer
│   └── dataset_nongphet.csv    # Training Dataset
│
├── static/                     # Web Assets (CSS, JS, Audio, Images)
│   ├── js/                     # Client Scripts (main.js, iot.js, chat.js, emotion.js)
│   └── audio/cache/            # Pre-baked Zero-Latency MP3 Audio Cache
│
├── templates/                  # Jinja2 HTML Templates
│   ├── index.html              # หน้าจอหลักแบบ Responsive
│   ├── kiosk.html              # หน้าจอสำหรับ Kiosk Touchscreen (Screen 1)
│   ├── emotion.html            # หน้าจอใบหน้าน้องเพชร (Screen 2)
│   ├── dashboard.html          # หน้าจอควบคุมและมอนิเตอร์ (Mission Control)
│   └── tts_preview.html        # สตูดิโอปรับแต่งและทดสอบเสียงพูด
│
├── tests/                      # Automated Unit & Integration Tests (39 Tests)
│   ├── test_intent.py          # ทดสอบการจำแนกเจตนาคำถาม
│   ├── test_knowledge_manager.py # ทดสอบ Dynamic RAG และการเรียนรู้ทันที
│   ├── test_retriever.py       # ทดสอบ Semantic Similarity
│   ├── test_routes.py          # ทดสอบ Flask Routes และ SSE IoT Events
│   ├── test_tts.py             # ทดสอบระบบเสียงและการจัดวรรคตอน
│   └── test_vision_attention.py # ทดสอบ Head Pose & Attention Gating
│
├── run.bat / run.ps1           # สคริปต์เปิดระบบแบบคลิกเดียวบน Windows
├── start_kiosk.sh              # สคริปต์รัน Kiosk Mode บน Raspberry Pi 5
└── systemd/                    # Linux Service Daemons สำหรับรันอัตโนมัติเมื่อเปิดเครื่อง
```

---

## 🚀 วิธีการติดตั้งและรันโปรแกรม

### 1. ติดตั้ง Dependencies
```bash
# Clone repository
git clone https://github.com/PooNaHa07/nongphet.git
cd nongphet

# สร้าง Virtual Environment และเปิดใช้งาน
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# ติดตั้งแพ็กเกจที่จำเป็น
pip install -r requirements.txt
```

### 2. ตั้งค่า API Key
เปิดไฟล์ `config.py` หรือกำหนดผ่าน Environment Variable:
```bash
# Windows PowerShell
$env:GEMINI_API_KEY="AIzaSy..."

# Linux / Raspberry Pi
export GEMINI_API_KEY="AIzaSy..."
```

### 3. รันโปรแกรมแบบ One-Click

#### บน Windows:
```powershell
# รันผ่าน PowerShell (เปิดทั้ง Flask, Vision Daemon, และ Browser อัตโนมัติ)
.\run.ps1

# หรือดับเบิลคลิกไฟล์:
run.bat
```

#### บน Raspberry Pi 5:
```bash
# รัน Kiosk Mode เต็มหน้าจอ
./start_kiosk.sh

# หรือรัน Dual-Screen Mode (จอสัมผัส + จอแสดงใบหน้า)
./start_dual_screen.sh
```

---

## 🧪 การรันชุดทดสอบอัตโนมัติ (Automated Tests)

ระบบมีชุดทดสอบครอบคลุมทุกโมดูลหลัก ทั้ง Intent Classifier, RAG Semantic Search, Edge-TTS, REST APIs, และ Attention Gating:

```bash
python run_tests.py
```
ผลลัพธ์:
```text
Ran 39 tests in 0.600s
OK
📊 สรุปผลการทดสอบ: รันทั้งหมด 39 รายการ
✅ การทดสอบทั้งหมดผ่านเรียบร้อย (ALL TESTS PASSED)!
```

---

## 📍 แดชบอร์ดและ URL สำคัญ
- **หน้าหลัก (Kiosk Screen):** [http://localhost:5000/kiosk](http://localhost:5000/kiosk)
- **หน้าจอใบหน้าน้องเพชร (Screen 2):** [http://localhost:5000/emotion](http://localhost:5000/emotion)
- **หน้าควบคุมระบบ (Mission Control):** [http://localhost:5000/admin/dashboard](http://localhost:5000/admin/dashboard)
- **สตูดิโอปรับแต่งเสียง (Voice Studio):** [http://localhost:5000/tts-preview](http://localhost:5000/tts-preview)
- **ไลฟ์สตรีมมุมมองกล้อง AI (Vision Stream):** [http://localhost:5002/video_feed](http://localhost:5002/video_feed)

---

## 👥 ผู้พัฒนาและลิขสิทธิ์
- **วิทยาลัยอาชีวศึกษาเพชรบุรี (Phetchaburi Vocational College - PBVC)**
- สำนักงานคณะกรรมการการอาชีวศึกษา (สอศ.) กระทรวงศึกษาธิการ
- ลิขสิทธิ์ซอฟต์แวร์ภายใต้เงื่อนไข [MIT License](LICENSE)
