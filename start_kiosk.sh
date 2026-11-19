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

# 2.9 ติดตั้งแบบ systemd แล้ว (setup_pi5.sh): รอให้ service พร้อม ห้ามเปิดเซิร์ฟเวอร์ซ้อนบนพอร์ตเดียวกัน
#     (ตอนบูต จอ kiosk อาจเปิดก่อน gunicorn พร้อม)
if systemctl is-enabled --quiet nongphet 2>/dev/null; then
    echo "⏳ รอระบบน้องเพชร (systemd: nongphet) พร้อมทำงาน..."
    for i in {1..90}; do
        curl -s http://127.0.0.1:5000/api/iot/status > /dev/null && break
        sleep 1
    done
    # กล้อง: ถ้า service กล้องเปิดใช้อยู่ ให้ systemd ดูแล ไม่ต้องเปิดเองด้านล่าง
    systemctl is-enabled --quiet nongphet-vision 2>/dev/null && NONGPHET_VISION_BY_SYSTEMD=1
fi

# 3. ตรวจสอบและรัน Flask Server หากยังไม่ได้รัน
if ! curl -s http://127.0.0.1:5000/api/iot/status > /dev/null; then
    echo "⚡ เริ่มต้น Flask Server..."
    if [ -d "venv" ]; then
        source venv/bin/activate
    elif [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    python app_new.py > /tmp/nongphet_flask.log 2>&1 &
    
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

# 3.1 ตรวจสอบและรัน Vision Daemon (Computer Vision & Auto Greeting)
if [ -z "$NONGPHET_VISION_BY_SYSTEMD" ] && ! curl -s http://127.0.0.1:5002/status > /dev/null; then
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

# 6. เคลียร์เบราว์เซอร์เดิมที่อาจเปิดค้างอยู่ เพื่อบังคับเปิดโหมด Kiosk ตัวใหม่ที่สะอาดและเต็มจอ
echo "🔄 กำลังเตรียมสภาพแวดล้อม Kiosk..."
killall -9 chromium chromium-browser 2>/dev/null || true
sleep 0.5

# 7. หาจอที่ต่ออยู่ (labwc/Wayland): จอสัมผัส 1280x800 = หน้า kiosk, อีกจอ = หน้าตาน้องเพชร (/emotion)
#    บังคับเลือกจอเองได้ใน .env เช่น  KIOSK_OUTPUT=HDMI-A-2  EMOTION_OUTPUT=HDMI-A-1
#    ดูชื่อจอด้วยคำสั่ง: wlr-randr
KIOSK_OUTPUT=$(grep -E '^KIOSK_OUTPUT=' .env 2>/dev/null | cut -d= -f2 | tr -d '\r" ')
EMOTION_OUTPUT=$(grep -E '^EMOTION_OUTPUT=' .env 2>/dev/null | cut -d= -f2 | tr -d '\r" ')
OUTPUTS=""      # แต่ละบรรทัด: ชื่อจอ x y กว้าง สูง
if command -v wlr-randr > /dev/null 2>&1; then
    OUTPUTS=$(wlr-randr 2>/dev/null | awk '
        /^[^ ]/            { name=$1; on=0; w=""; h=""; next }
        /Enabled: yes/     { on=1 }
        /current/          { split($1, m, "x"); w=m[1]; h=m[2] }
        /Position:/        { split($2, p, ","); if (on && w != "") print name, p[1], p[2], w, h }')
fi
SCREEN_COUNT=$(printf '%s\n' "$OUTPUTS" | grep -c . || true)

[ -z "$KIOSK_OUTPUT" ] && KIOSK_OUTPUT=$(printf '%s\n' "$OUTPUTS" | awk '$4==1280 && $5==800 {print $1; exit}')
[ -z "$KIOSK_OUTPUT" ] && KIOSK_OUTPUT=$(printf '%s\n' "$OUTPUTS" | awk 'NR==1 {print $1}')
[ -z "$EMOTION_OUTPUT" ] && EMOTION_OUTPUT=$(printf '%s\n' "$OUTPUTS" | awk -v k="$KIOSK_OUTPUT" '$1!=k {print $1; exit}')
KIOSK_GEO=$(printf '%s\n' "$OUTPUTS" | awk -v o="$KIOSK_OUTPUT" '$1==o {print $2, $3, $4, $5}')
EMOTION_GEO=$(printf '%s\n' "$OUTPUTS" | awk -v o="$EMOTION_OUTPUT" '$1==o {print $2, $3, $4, $5}')
echo "🖥️ พบจอ ${SCREEN_COUNT} จอ: kiosk=${KIOSK_OUTPUT:-?} emotion=${EMOTION_OUTPUT:--}"

CHROME_FLAGS="--kiosk --noerrdialogs --disable-infobars --no-first-run \
    --disable-session-crashed-bubble --disable-sync --disable-background-networking \
    --disable-component-update --disable-pinch --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required --use-fake-ui-for-media-stream \
    --touch-events=enabled --enable-gpu-rasterization --enable-zero-copy --ignore-gpu-blocklist \
    --enable-features=VaapiVideoDecoder,CanvasOopRasterization,OverlayScrollbar"

# เปิดหน้าเว็บเต็มจอบนจอที่ระบุ: $1=URL  $2=โฟลเดอร์โปรไฟล์  $3="x y กว้าง สูง" (ว่าง = จอเดียว)
# จอคู่ต้องใช้ XWayland (--ozone-platform=x11) เพราะ Chromium บน Wayland ไม่สนตำแหน่งหน้าต่าง
open_screen() {
    local url="$1" profile="$2" geo="$3" place=""
    if [ -n "$geo" ]; then
        set -- $geo
        place="--ozone-platform=x11 --window-position=$1,$2 --window-size=$3,$4"
    fi
    $CHROME_BIN $CHROME_FLAGS $place --user-data-dir="$profile" "$url" > /dev/null 2>&1 &
}

if [ "$SCREEN_COUNT" -ge 2 ] && [ -n "$EMOTION_GEO" ]; then
    # จอสัมผัสต้องรับแตะเฉพาะจอ kiosk (ไม่งั้นแตะแล้วไปโดนอีกจอ)
    RC="$HOME/.config/labwc/rc.xml"
    if [ -f "$RC" ] && ! grep -q "mapToOutput=\"$KIOSK_OUTPUT\"" "$RC"; then
        sed -i '/<touch [^>]*\/>/d' "$RC"
        sed -i "s#</openbox_config>#  <touch deviceName=\"\" mapToOutput=\"$KIOSK_OUTPUT\" mouseEmulation=\"no\" />\n</openbox_config>#" "$RC"
        labwc --reconfigure 2>/dev/null || true
        echo "👆 ตั้งจอสัมผัสให้แตะได้เฉพาะจอ $KIOSK_OUTPUT"
    fi
    echo "👀 [จอหน้าตา $EMOTION_OUTPUT] เปิด /emotion (ไม่ส่งเสียง ให้จอ kiosk เป็นผู้พูด)"
    open_screen "http://127.0.0.1:5000/emotion?dual=1" /tmp/nongphet_emotion_profile "$EMOTION_GEO"
    sleep 1
    echo "📱 [จอสัมผัส $KIOSK_OUTPUT] เปิด /kiosk"
    open_screen "http://127.0.0.1:5000/kiosk" /tmp/nongphet_kiosk_profile "$KIOSK_GEO"
    echo "🎉 เปิด 2 จอเรียบร้อย: kiosk + emotion"
else
    echo "📱 พบจอเดียว: เปิดหน้า kiosk เต็มจอ (ต่อจอที่ 2 แล้วรีบูต เพื่อเปิดหน้าตาน้องเพชรอัตโนมัติ)"
    open_screen "http://127.0.0.1:5000/kiosk" /tmp/nongphet_kiosk_profile ""
    echo "🎉 เปิดโหมด Kiosk บนหน้าจอสัมผัส 10.1 นิ้ว สำเร็จเรียบร้อยแล้ว!"
fi
