#!/bin/bash
# ==============================================================================
# สคริปต์ติดตั้ง Systemd Services สำหรับน้องเพชรบน Raspberry Pi 5
# รันคำสั่ง: sudo bash systemd/install_services.sh
# ==============================================================================

if [ "$EUID" -ne 0 ]; then
    echo "⚠️ กรุณารันด้วยสิทธิ์ root: sudo bash systemd/install_services.sh"
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "⚙️ กำลังคัดลอกไฟล์ systemd service เข้าสู่ /etc/systemd/system/..."
cp "$SCRIPT_DIR/nongphet.service" /etc/systemd/system/
cp "$SCRIPT_DIR/nongphet-vision.service" /etc/systemd/system/

echo "🔄 ทำการ reload systemd daemon..."
systemctl daemon-reload

echo "🚀 เปิดใช้งาน (Enable) ให้เริ่มทำงานอัตโนมัติตอนเปิดเครื่อง Pi 5..."
systemctl enable nongphet.service
systemctl enable nongphet-vision.service

echo "▶️ สั่งเริ่มทำงานทันที..."
systemctl restart nongphet.service
systemctl restart nongphet-vision.service

echo "✅ ติดตั้ง Systemd Services เสร็จสมบูรณ์แล้ว!"
echo "ตรวจสอบสถานะด้วยคำสั่ง:"
echo "  sudo systemctl status nongphet"
echo "  sudo systemctl status nongphet-vision"

