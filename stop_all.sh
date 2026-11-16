#!/bin/bash
# ==============================================================================
# โครงการ: น้องเพชร AI Smart Guide
# สคริปต์: สั่งหยุดการทำงานของทุกระบบ (Flask, Vision Daemon, Chromium Kiosk)
# ==============================================================================

echo "🛑 กำลังหยุดการทำงานของระบบ น้องเพชร AI Smart Guide..."

# 1. ปิด Chromium Kiosk
killall -9 chromium chromium-browser google-chrome 2>/dev/null || true

# 2. ปิด Vision Daemon
pkill -f "python.*vision_daemon.py" 2>/dev/null || true

# 2.1 ปิดบริดจ์ ESP32
pkill -f "python.*esp32_listener.py" 2>/dev/null || true

# 3. ปิด Flask Web Application
pkill -f "python.*app.*\.py" 2>/dev/null || true

# 4. ปิด Emotion Display SPI Driver (ถ้ามี)
pkill -f "python.*emotion_display.py" 2>/dev/null || true

echo "✅ ทุกเซอร์วิสของน้องเพชรหยุดการทำงานเรียบร้อยแล้ว"

