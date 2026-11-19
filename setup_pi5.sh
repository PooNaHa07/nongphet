#!/bin/bash
# ==============================================================================
# โครงการ: น้องเพชร AI Smart Guide
# สคริปต์: ติดตั้งสภาพแวดล้อมอัตโนมัติบน Raspberry Pi 5 (setup_pi5.sh)
# ระบบปฏิบัติการ: Raspberry Pi OS 64-bit (Debian 12 Bookworm)
# ==============================================================================

set -e

echo "=================================================================="
echo "🚀 เริ่มต้นการติดตั้งระบบ น้องเพชร AI Smart Guide บน Raspberry Pi 5"
echo "=================================================================="

# 1. อัปเดตรายการแพ็กเกจระบบ
echo "📦 [1/6] กำลังอัปเดตระบบปฏิบัติการและติดตั้งไลบรารีพื้นฐาน..."
sudo apt-get update -y
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    unclutter \
    alsa-utils \
    sox \
    libopenblas-dev \
    libportaudio2 \
    libasound2-dev \
    fonts-thai-tlwg
# Bookworm ใช้ชื่อ chromium (รุ่นเก่าใช้ chromium-browser) / เสียงใช้ PipeWire ของระบบ ไม่ต้องลง pulseaudio
sudo apt-get install -y chromium || sudo apt-get install -y chromium-browser || true

# 2. เพิ่มสิทธิ์การเข้าถึงอุปกรณ์ฮาร์ดแวร์ให้ User ปัจจุบัน
echo "🔑 [2/6] เพิ่มสิทธิ์เข้าถึงอุปกรณ์เสียง, กล้อง, และพอร์ตสื่อสาร..."
sudo usermod -a -G dialout,audio,video,gpio,spi $USER || true

# 3. สร้าง Python Virtual Environment ตามมาตรฐาน PEP 668 ของ Debian Bookworm
echo "🐍 [3/6] สร้างสภาพแวดล้อม Python (.venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "  ==> สร้างโฟลเดอร์ .venv สำเร็จ"
fi

# 4. ติดตั้ง Python Dependencies
echo "📥 [4/6] ติดตั้งไลบรารี Python จาก requirements.txt..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pygame || true

# 5. ให้สิทธิ์รันสคริปต์รันระบบ
echo "⚙️ [5/6] กำหนดสิทธิ์ Execute ให้ไฟล์สคริปต์..."
chmod +x start_kiosk.sh || true
chmod +x emotion_display.py || true

# 6. ติดตั้ง Systemd Services (เว็บด้วย gunicorn, กล้อง, ESP32) จากไฟล์ใน systemd/
echo "🔄 [6/6] ติดตั้ง Systemd Services สำหรับการเปิดเครื่องแล้วรันทันที..."
if [ "$(pwd)" != "/home/pi/nongphet" ] || [ "$USER" != "pi" ]; then
    echo "⚠️ ไฟล์ใน systemd/ ตั้งค่าไว้สำหรับผู้ใช้ pi ที่ /home/pi/nongphet (ตอนนี้: $USER ที่ $(pwd))"
    echo "   แก้ User/WorkingDirectory ใน systemd/*.service ก่อน แล้วรัน: sudo bash systemd/install_services.sh"
else
    sudo bash systemd/install_services.sh
fi

echo ""
echo "=================================================================="
echo "✅ ติดตั้งระบบเรียบร้อยสมบูรณ์แล้ว!"
echo "👉 คำสั่งรันระบบแบบแมนนวล: ./start_kiosk.sh"
echo "👉 ดูสถานะ Service: sudo systemctl status nongphet nongphet-vision nongphet-esp32"
echo "👉 คำสั่งเปิดจอแสดงอารมณ์: python emotion_display.py --test"
echo "💡 แนะนำให้ Reboot เครื่อง 1 ครั้ง เพื่อให้สิทธิ์ User มีผลสมบูรณ์: sudo reboot"
echo "=================================================================="
