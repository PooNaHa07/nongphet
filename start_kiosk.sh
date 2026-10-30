#!/bin/bash
# ==============================================================================
# โครงการ: น้องเพชร AI Smart Guide
# สคริปต์: สั่งเปิดระบบเข้าสู่โหมด Kiosk เต็มหน้าจอสัมผัส (start_kiosk.sh)
# อุปกรณ์เป้าหมาย: Raspberry Pi 5 + จอสัมผัส 10.1 นิ้ว (Hardware GPU Accelerated)
# ==============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🤖 กำลังเริ่มต้นระบบ น้องเพชร AI Smart Guide Kiosk..."

# 1. กำหนดค่า Display Environment Variable สำหรับการสั่งงานผ่าน SSH ให้เปิดขึ้นจอ 10 นิ้วจริง
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

# 2. ตรวจสอบชื่อคำสั่งของ Chromium บน Raspberry Pi OS (Debian Bookworm ใช้ 'chromium')
if command -v chromium &> /dev/null; then
    CHROME_BIN="chromium"
elif command -v chromium-browser &> /dev/null; then
    CHROME_BIN="chromium-browser"
elif command -v google-chrome &> /dev/null; then
    CHROME_BIN="google-chrome"
else
    echo "⚠️ ไม่พบ Chromium ในระบบ กำลังตรวจสอบการติดตั้ง..."
    CHROME_BIN="chromium"
fi

# 3. ตรวจสอบและรัน Flask Server หากยังไม่ได้รัน
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

# 4. ปิดการดับหน้าจอและซ่อนเคอร์เซอร์เมาส์อัตโนมัติบนจอสัมผัส
xset s noblank 2>/dev/null || true
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
if command -v unclutter &> /dev/null; then
    unclutter -idle 1.0 -root &
fi

# 5. เริ่มต้นเปิดจอแสดงอารมณ์ส่วนหัว (หากต่อจอ SPI หรือ Framebuffer /dev/fb1)
if [ -e "/dev/fb1" ]; then
    echo "👀 ตรวจพบจอแสดงอารมณ์ส่วนหัว (/dev/fb1) กำลังเริ่มต้นไดรเวอร์..."
    python emotion_display.py --fb /dev/fb1 > /tmp/emotion_display.log 2>&1 &
fi

# 6. เปิด Chromium ในโหมด Kiosk เต็มหน้าจอสัมผัส 10.1 นิ้ว พร้อมเร่งความเร็วฮาร์ดแวร์ GPU สำหรับ Pi 5
echo "🖥️ กำลังเปิดหน้าจอสัมผัสหลักในโหมด Fullscreen Kiosk บนจอ 10.1 นิ้ว..."
$CHROME_BIN \
    --kiosk \
    --start-maximized \
    --noerrdialogs \
    --disable-infobars \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    --touch-events=enabled \
    --enable-gpu-rasterization \
    --enable-zero-copy \
    --ignore-gpu-blocklist \
    --enable-features=VaapiVideoDecoder,CanvasOopRasterization,OverlayScrollbar \
    --window-position=0,0 \
    http://127.0.0.1:5000/kiosk
