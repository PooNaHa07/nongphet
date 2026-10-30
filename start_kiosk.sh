#!/bin/bash
# ==============================================================================
# โครงการ: น้องเพชร AI Smart Guide
# สคริปต์: สั่งเปิดระบบเข้าสู่โหมด Kiosk เต็มหน้าจอสัมผัส (start_kiosk.sh)
# อุปกรณ์เป้าหมาย: Raspberry Pi 5 + จอสัมผัส 10.1 นิ้ว (Hardware GPU Accelerated)
# ==============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🤖 กำลังเริ่มต้นระบบ น้องเพชร AI Smart Guide Kiosk..."

# 1. ตรวจสอบและรัน Flask Server หากยังไม่ได้รัน
if ! curl -s http://127.0.0.1:5000/api/iot/status > /dev/null; then
    echo "⚡ เริ่มต้น Flask Server..."
    if [ -d "venv" ]; then
        source venv/bin/activate
    elif [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    python app.py > /tmp/nongphet_flask.log 2>&1 &
    
    # รอนับเวลาให้ Flask พร้อมทำงาน
    echo "⏳ กำลังรอให้เซิร์ฟเวอร์พร้อมทำงาน..."
    for i in {1..20}; do
        if curl -s http://127.0.0.1:5000/api/iot/status > /dev/null; then
            echo "✅ Flask Server พร้อมใช้งานแล้ว!"
            break
        fi
        sleep 1
    done
fi

# 2. ปิดการดับหน้าจอและซ่อนเคอร์เซอร์เมาส์อัตโนมัติบนจอสัมผัส
xset s noblank || true
xset s off || true
xset -dpms || true
unclutter -idle 1.0 -root &

# 3. เริ่มต้นเปิดจอแสดงอารมณ์ส่วนหัว (หากต่อจอ SPI หรือ Framebuffer /dev/fb1)
if [ -e "/dev/fb1" ]; then
    echo "👀 ตรวจพบจอแสดงอารมณ์ส่วนหัว (/dev/fb1) กำลังเริ่มต้นไดรเวอร์..."
    python emotion_display.py --fb /dev/fb1 > /tmp/emotion_display.log 2>&1 &
fi

# 4. เปิด Chromium Browser ในโหมด Kiosk พร้อมเร่งความเร็วฮาร์ดแวร์ GPU สำหรับ Pi 5
echo "🖥️ กำลังเปิดหน้าจอสัมผัสหลักในโหมด Fullscreen Kiosk (GPU Accelerated 60 FPS)..."
chromium-browser \
    --kiosk \
    --start-maximized \
    --noerrdialogs \
    --disable-infobars \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    --enable-gpu-rasterization \
    --enable-zero-copy \
    --ignore-gpu-blocklist \
    --enable-features=VaapiVideoDecoder,CanvasOopRasterization,OverlayScrollbar \
    --window-position=0,0 \
    http://127.0.0.1:5000?mode=kiosk