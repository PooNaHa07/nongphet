# น้องเพชร AI Smart Guide

น้องเพชรคือ AI Guide ของวิทยาลัยอาชีวศึกษาเพชรบุรี ช่วยแนะนำสถานที่ท่องเที่ยว ร้านอาหาร ข้อมูลสถานศึกษา ในจังหวัดเพชรบุรี

## คุณสมบัติ
- **Chat:** พูดคุยภาษาไทย/อังกฤษ สอบถามข้อมูลเกี่ยวกับเพชรบุรี
- **Vision:** อัปโหลดรูปภาพเพื่อสอบถามว่าคือสถานที่ใด
- **TTS:** ระบบอ่านข้อความภาษาไทย (กดไอคอนลำโพงที่ข้อความของน้องเพชร)
- **STT:** สั่งงานด้วยเสียง (กดไอคอนไมโครโฟน)

## วิธีการติดตั้งและรันโปรแกรม

1. ตรวจสอบว่าติดตั้ง Python แล้ว
2. เปิด Terminal/Command Prompt แล้วเข้าไปที่โฟลเดอร์นี้
3. ติดตั้ง Dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. ตั้งค่า API Key ของ Google Gemini
   - เข้าไปรับ API Key ได้ที่ [Google AI Studio](https://aistudio.google.com/)
   - เปิดไฟล์ `config.py` แล้วนำ API Key มาใส่แทน `YOUR_GEMINI_API_KEY_HERE` 
   - หรือตั้งค่าผ่าน Environment Variable `GEMINI_API_KEY`
5. รันเซิร์ฟเวอร์
   ```bash
   python app.py
   ```
6. เปิด Web Browser ไปที่ [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Tech Stack
- Backend: Python Flask
- AI: Google Gemini (gemini-2.5-flash) ผ่าน `google-genai` SDK + Local Intent Classifier (ML)
- TTS: Neural Voice Edge-TTS & `gTTS`
- STT: Web Speech API (ใน Browser)
- Emotion Engine: Realtime Vector Face Animation (Dual-Display Sync)
- Frontend: HTML, Tailwind CSS, Vanilla JS

## การติดตั้งและใช้งานบน Raspberry Pi 5 (สเปกจริงแบบ A)
โปรเจกต์นี้รองรับการติดตั้งและรันบน **Raspberry Pi 5** ในโหมด Kiosk ตู้หุ่นยนต์ประชาสัมพันธ์อัตโนมัติ:
- 📖 อ่านคู่มือการต่อสายอุปกรณ์: [PI5_HARDWARE_GUIDE.md](file:///d:/nongphet/PI5_HARDWARE_GUIDE.md)
- 🚀 ติดตั้งอัตโนมัติบน Pi 5: รัน `./setup_pi5.sh`
- 🖥️ เปิดโหมด Fullscreen Kiosk: รัน `./start_kiosk.sh`
- 👀 หน้าจอแสดงอารมณ์ส่วนหัว (2.4 - 3.5 นิ้ว): เปิดที่ `http://127.0.0.1:5000/emotion` หรือรัน `python emotion_display.py`
