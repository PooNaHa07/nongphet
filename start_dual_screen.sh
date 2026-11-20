#!/bin/bash
# ==============================================================================
# โครงการ: น้องเพชร AI Smart Guide
# สคริปต์: สั่งเปิดระบบแบบแยก 2 หน้าจอพร้อมกันอัตโนมัติ (start_dual_screen.sh)
# จอที่ 1 (ส่วนหัว/ใบหน้าหุ่นยนต์): http://127.0.0.1:5000/emotion
# จอที่ 2 (หน้าอก/จอสัมผัส 10.1 นิ้ว): http://127.0.0.1:5000/kiosk
# ทั้งสองหน้าจอเชื่อมโยงอารมณ์ คลื่นเสียง ปากขยับ และสายตาแบบ Real-time 0ms
# ==============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🤖 กำลังเริ่มต้นระบบ น้องเพชร AI Smart Guide (Dual-Screen Mode)..."

# 1. กำหนด Display Environment Variables
if [ -z "$XDG_RUNTIME_DIR" ] && [ -d "/run/user/$(id -u)" ]; then
    export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [ -z "$WAYLAND_DISPLAY" ] && [ -e "$XDG_RUNTIME_DIR/wayland-0" ]; then
    export WAYLAND_DISPLAY="wayland-0"
fi
if [ -z "$DISPLAY" ]; then
    export DISPLAY=":0"
fi
if [ -z "$XAUTHORITY" ] && [ -f "$HOME/.Xauthority" ]; then
    export XAUTHORITY="$HOME/.Xauthority"
fi

# 2. ตรวจสอบคำสั่ง Chromium
if command -v chromium &> /dev/null; then
    CHROME_BIN="chromium"
elif command -v chromium-browser &> /dev/null; then
    CHROME_BIN="chromium-browser"
elif command -v google-chrome &> /dev/null; then
    CHROME_BIN="google-chrome"
else
    CHROME_BIN="chromium"
fi

# 3. รัน Flask Server หากยังไม่ได้รัน
if ! curl -s http://127.0.0.1:5000/api/iot/status > /dev/null; then
    echo "⚡ เริ่มต้น Flask Server..."
    if [ -d "venv" ]; then
        source venv/bin/activate
    elif [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    python app_new.py > /tmp/nongphet_flask.log 2>&1 &
    
    echo "⏳ กำลังรอให้เซิร์ฟเวอร์พร้อมทำงาน..."
    for i in {1..20}; do
        if curl -s http://127.0.0.1:5000/api/iot/status > /dev/null; then
            echo "✅ Flask Server พร้อมใช้งานแล้ว!"
            break
        fi
        sleep 1
    done
fi

# 3.1 ตรวจสอบและรัน Vision Daemon (Computer Vision & Auto Greeting)
if ! curl -s http://127.0.0.1:5002/status > /dev/null; then
    echo "📷 เริ่มต้น Vision Daemon (ระบบตรวจจับคนเดินผ่าน & Auto Greeting)..."
    python vision_daemon.py > /tmp/nongphet_vision.log 2>&1 &
    sleep 1
    if curl -s http://127.0.0.1:5002/status > /dev/null; then
        echo "✅ Vision Daemon พร้อมใช้งานแล้ว (Port 5002)!"
    fi
fi

# 3.2 เริ่มบริดจ์ ESP32 (แขน/ไฟ LED/อัลตราโซนิก) ถ้ายังไม่ได้รันและไม่ได้ใช้ systemd
# --wait: ยังไม่เสียบบอร์ดก็รอเงียบๆ ไม่กระทบระบบอื่น
if ! pgrep -f "esp32_listener.py" > /dev/null && ! systemctl is-active --quiet nongphet-esp32 2>/dev/null; then
    echo "🦾 เริ่มต้นบริดจ์ ESP32 (รอบอร์ดอัตโนมัติ)..."
    python esp32_listener.py --wait > /tmp/nongphet_esp32.log 2>&1 &
fi

# 4. ปิดการพักหน้าจอ
xset s noblank 2>/dev/null || true
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true

# 5. เคลียร์โพรเซส Chromium เดิม
echo "🔄 กำลังเตรียมสภาพแวดล้อม Dual-Screen..."
killall -9 chromium chromium-browser 2>/dev/null || true
sleep 0.5

# ตัวเลือกพารามิเตอร์ประสิทธิภาพ GPU และเร่งความเร็ว 60 FPS
CHROME_FLAGS="--noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-session-crashed-bubble \
    --disable-sync \
    --disable-background-networking \
    --disable-component-update \
    --autoplay-policy=no-user-gesture-required \
    --use-fake-ui-for-media-stream \
    --touch-events=enabled \
    --enable-gpu-rasterization \
    --enable-zero-copy \
    --ignore-gpu-blocklist \
    --enable-features=VaapiVideoDecoder,CanvasOopRasterization,OverlayScrollbar"

# 6. เปิด จอที่ 1: หน้าจอแสดงอารมณ์ใบหน้าน้องเพชร (/emotion?dual=1 - โหมดจอคู่ ปิดเสียงซ้ำซ้อน)
echo "👀 [จอที่ 1] กำลังเปิดหน้าจอแสดงอารมณ์ส่วนหัว (/emotion?dual=1)..."
$CHROME_BIN \
    $CHROME_FLAGS \
    --kiosk \
    --user-data-dir=/tmp/nongphet_emotion_profile \
    --window-position=0,0 \
    http://127.0.0.1:5000/emotion?dual=1 > /dev/null 2>&1 &

sleep 1

# 7. เปิด จอที่ 2: หน้าจอสัมผัสหลัก 10.1 นิ้ว (/kiosk)
echo "📱 [จอที่ 2] กำลังเปิดหน้าจอสัมผัสหลัก 10.1 นิ้ว (/kiosk)..."
$CHROME_BIN \
    $CHROME_FLAGS \
    --kiosk \
    --user-data-dir=/tmp/nongphet_kiosk_profile \
    --window-position=1280,0 \
    http://127.0.0.1:5000/kiosk > /dev/null 2>&1 &

echo "🎉 เปิดระบบ 2 หน้าจอเชื่อมต่อกันสำเร็จสมบูรณ์แบบ!"

