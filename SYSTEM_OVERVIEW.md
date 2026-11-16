# น้องเพชร AI Smart Guide — เอกสารสถาปัตยกรรมและโครงสร้างระบบทั้งหมด

## 1. ภาพรวมโครงการ (Project Overview)

**"น้องเพชร AI Smart Guide"** คือหุ่นยนต์ประชาสัมพันธ์และไกด์นำเที่ยวอัจฉริยะ (AI Robot Kiosk) ผลงานนวัตกรรมสิ่งประดิษฐ์ของ**วิทยาลัยอาชีวศึกษาเพชรบุรี (PBVC)** ออกแบบตามมาตรฐานเกณฑ์การประเมินสิ่งประดิษฐ์คนรุ่นใหม่ สอศ. ประเภทหุ่นยนต์และปัญญาประดิษฐ์

ระบบผสมผสานระหว่าง **Edge Computing บน Raspberry Pi 5** สำหรับงานที่ต้องการความเร็วสูงและทำงานแบบออฟไลน์ได้ (Local ML Intent Classification, Semantic Retrieval, Face & Gaze Tracking, Universal Design Thai Sign Language) ร่วมกับ **Cloud Multimodal AI (Google Gemini 2.5 Flash)** สำหรับการวิเคราะห์ภาพสถานที่ท่องเที่ยวเชิงลึกและการสนทนาแบบเปิด (Open-domain conversational AI)

---

## 2. ผังสถาปัตยกรรมระบบ (System Architecture)

```
+-----------------------------------------------------------------------------------+
|                            USER INPUT / SENSORY LAYER                             |
|  - USB Microphone (STT)      - 10.1" Capacitive Touch Display (Kiosk UI)          |
|  - USB Camera / CSI (OpenCV) - Ultrasonic & Presence Detection (IoT Sensor)       |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
|                        APPLICATION LAYER (Raspberry Pi 5)                         |
|                                                                                   |
|  [Modular Flask Server - app_new.py / app.py] (Port 5000)                        |
|   ├── routes/chat.py      : รับส่งข้อความ, จัดการบทสนทนา, Edge Intent Fallback     |
|   ├── routes/vision.py    : Multimodal Vision, TSL Sign Language, Video Proxy     |
|   ├── routes/knowledge.py : Dynamic RAG Knowledge Base CRUD & Retrain APIs       |
|   ├── routes/iot.py       : Sensor Triggers, SSE Stream, Gaze Tracking            |
|   ├── routes/admin.py     : Command Controls, CSV Analytics Export, Live Mirror   |
|   └── routes/media.py     : Edge-TTS Streaming Audio (/api/tts/stream)           |
|                                                                                   |
|  [Computer Vision Daemon - vision_daemon.py] (Port 5002)                          |
|   ├── Multi-Backend: YOLOv8n ──> MediaPipe ──> OpenCV Cascade ──> Simulation     |
|   ├── Auto Greeting Trigger (ระยะ 1.5 - 2.5 ม., 25s Cooldown)                      |
|   ├── Gaze / Eye Tracking (ส่งพิกัด X, Y สู่ /api/emotion/gaze ทุก 120ms)         |
|   └── MJPEG Live Video Server (/video_feed, /snapshot.jpg, /status)               |
+-----------------------------------------------------------------------------------+
            │                                             │
            ▼ (Offline Edge)                              ▼ (Cloud AI)
+---------------------------------------+   +---------------------------------------+
|          LOCAL EDGE AI ENGINE         |   |         CLOUD MULTIMODAL ENGINE       |
|  - Semantic Retriever (TF-IDF + Cosine|   |  - Google Gemini 2.5 Flash            |
|    Similarity with Hot Reloading)     |   |  - Fallback: Gemini 2.0 Flash         |
|  - Local Rule Engine (< 50ms latency) |   |  - Deep Cultural & Travel Knowledge   |
|  - TSL 21-Joint Geometric Classifier  |   |  - Multimodal Photo Verification      |
|  - Edge-TTS / PyThaiTTS Audio Stream  |   |                                       |
+---------------------------------------+   +---------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
|                            OUTPUT & PRESENTATION LAYER                            |
|  - จอสัมผัสหลัก 10.1 นิ้ว (/kiosk) : แสดงผลข้อมูลการท่องเที่ยว หลักสูตร และแชต     |
|  - จอส่วนหัวแสดงอารมณ์ (/emotion)  : แสดงลูกตาสบตา (Gaze), อารมณ์, ปากขยับตามเสียง |
|  - ลำโพง USB คุณภาพสูง             : สตรีมเสียงภาษาไทยธรรมชาติผ่าน Edge-TTS        |
|  - แผงควบคุมผู้ดูแล (/admin)       : Live Visor Mirror, Metrics, Telemetry, Export|
+-----------------------------------------------------------------------------------+
```

---

## 3. รายละเอียดโมดูลหลัก (Core Subsystems)

### 3.1 ฐานข้อมูลความรู้แบบเรียนรู้ใหม่ได้ (Retrainable RAG Knowledge Base)
- **แหล่งข้อมูล:** `data/phetchaburi_knowledge.json`
- **การจัดการ:** ผ่านหน้าเว็บ Admin UI สไตล์ Cyberpunk ที่ `/admin/knowledge`
- **ความสามารถ:**
  - เพิ่ม/ลบ/แก้ไขข้อมูลสถานที่ ท่องเที่ยว ข่าวสาร และหลักสูตรวิทยาลัยได้ทันที
  - กลไก **Atomic Write** เขียนลงไฟล์ชั่วคราวแล้ว rename พร้อมสำรองไฟล์ `.bak` อัตโนมัติ ป้องกันข้อมูลสูญหาย
  - ระบบ **Live Re-indexing**: AI คำนวณเวกเตอร์ TF-IDF ใหม่ในหน่วยความจำทันทีโดยไม่ต้อง Restart Server
  - **Live Verification Simulator**: กรรมการสามารถทดลองพิมพ์ข้อความเพื่อตรวจสอบค่าความมั่นใจ (Confidence Score) และผลลัพธ์ของ AI ได้สดๆ บนหน้าจอ

### 3.2 ระบบมองเห็นและการทักทายอัตโนมัติ (Computer Vision & Auto Greeting)
- **สคริปต์ควบคุม:** `vision_daemon.py`
- **Multi-Backend Architecture:** สลับ backend อัตโนมัติอย่างชาญฉลาด:
  1. `ultralytics` YOLOv8n (หากติดตั้งโมเดล)
  2. `mediapipe` (Hand & Face Detection)
  3. `opencv-python-headless` (Haar Cascade & HOG) — ทำงานเบามากบน Pi 5 CPU (&lt; 15% CPU load)
  4. `--simulate` โหมดจำลองสำหรับทดสอบบนคอมพิวเตอร์ที่ไม่มีฮาร์ดแวร์กล้อง
- **Auto Greeting:** เมื่อพบคนยืนอยู่ด้านหน้าติดต่อกัน 3 เฟรม จะยิง Event ไปที่ `/api/iot/trigger` เพื่อให้หุ่นยนต์พูดทักทายต้อนรับทันที โดยมี Cooldown 25 วินาที
- **Gaze & Eye Tracking:** คำนวณจุดศูนย์กลางใบหน้าเทียบกับแกนกล้อง ส่งเป็นพิกัด `(x, y)` ไปยัง `/api/emotion/gaze` ทำให้ดวงตาหุ่นยนต์บนจอส่วนหัวหันมองตามคนแบบเรียลไทม์
- **MJPEG Video Streaming:** สตรีมภาพสดความละเอียด 640x480 ที่พอร์ต 5002 พร้อม Proxy ผ่าน `/api/vision/stream` แสดงบนแผงควบคุม Dashboard

### 3.3 การรองรับภาษามือไทย (Universal Design Thai Sign Language)
- รองรับการสื่อสารกับผู้มีความบกพร่องทางการได้ยินด้วยการตรวจจับพิกัดข้อนิ้ว 21 ตำแหน่ง (MediaPipe 21 Landmarks)
- จำแนก 7 ท่าทางหลักด้วยกฎเรขาคณิต (Geometric Rules) บนเครื่องออฟไลน์:
  - 🤟 `love`: ฉันรักเธอ / ยินดีต้อนรับ
  - 👍 `thumbs_up`: ขอบคุณ / ยอดเยี่ยม
  - ✌️ `peace`: เที่ยวเพชรบุรี / แนะนำสถานที่ท่องเที่ยว
  - 🖐️ `open_palm`: สวัสดี / ทักทาย
  - ☝️ `pointing`: ข้อมูลหลักสูตรอาชีวะ / การเรียนต่อ
  - ✊ `fist`: แนะนำของกินและของฝากเมืองเพชร
  - 🤙 `shaka`: ขอความช่วยเหลือฉุกเฉิน / บริการพิเศษ

### 3.4 โครงสร้างสถาปัตยกรรมโค้ดแบบโมดูลาร์ (Modular Codebase)
โปรเจกต์ถูกจัดระเบียบตามหลัก Clean Architecture:
- `app_new.py`: ไฟล์ Entrypoint ขนาดกะทัดรัด ลงทะเบียน Blueprints ทั้งหมด
- `state.py`: จุดรวม Shared State ป้องกัน Circular Import
- `services/`:
  - `gemini_service.py`: บริการเชื่อมต่อ Google GenAI SDK (Primary & Fallback)
  - `knowledge_service.py`: บริการคลังความรู้แบบออฟไลน์
  - `knowledge_manager.py`: บริการจัดการข้อมูลความรู้แบบ Safe CRUD & Persistence
  - `analytics_service.py`: บริการบันทึกสถิติและวิเคราะห์พฤติกรรมผู้เข้าชม
  - `tts_service.py`: บริการสร้างเสียงพูดภาษาไทย Edge-TTS แบบ Streaming
- `routes/`:
  - `chat.py`, `vision.py`, `knowledge.py`, `iot.py`, `admin.py`, `display.py`, `media.py`
- `tests/`: ชุดทดสอบอัตโนมัติ Unit & Integration Tests รันผ่าน `python run_tests.py`

---

## 4. คู่มือการเปิดใช้งานและคำสั่งสำคัญ

### รันระบบบนคอมพิวเตอร์ทั่วไป (โหมดทดสอบ):
```bash
# 1. รันเซิร์ฟเวอร์หลัก (Terminal 1)
python app_new.py

# 2. รันระบบมองเห็นจำลอง (Terminal 2)
python vision_daemon.py --simulate

# 3. รันชุดทดสอบความถูกต้อง
python run_tests.py
```

### รันระบบบน Raspberry Pi 5 (ฮาร์ดแวร์จริง):
```bash
# รันโหมดหน้าจอเดียว (Kiosk 10.1 นิ้ว)
./start_kiosk.sh

# รันโหมด 2 หน้าจอพร้อมกัน (จอหน้าอก Kiosk + จอส่วนหัวแสดงอารมณ์)
./start_dual_screen.sh

# หยุดการทำงานทุกเซอร์วิส
./stop_all.sh

# ตั้งค่าให้เริ่มทำงานอัตโนมัติตอนเสียบปลั๊กไฟ (Systemd Service)
sudo bash systemd/install_services.sh
```

---

## 5. การเชื่อมต่อหน้าจอและแดชบอร์ด
- หน้าจอสัมผัสหลักตู้คีออส: `http://localhost:5000/kiosk` หรือ `http://localhost:5000/`
- หน้าจอแสดงอารมณ์และใบหน้าน้องเพชร: `http://localhost:5000/emotion`
- แดชบอร์ดมอนิเตอร์และควบคุมระยะไกล: `http://localhost:5000/admin`
- หน้าจัดการฐานข้อมูลความรู้ RAG (สำหรับกรรมการ): `http://localhost:5000/admin/knowledge`
