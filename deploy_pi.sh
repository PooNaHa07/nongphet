#!/bin/bash
# ==============================================================================
# deploy_pi.sh — ส่งโค้ดน้องเพชรไป Raspberry Pi 5 ผ่าน SSH (ไม่ต้องมี rsync)
#
# รันจาก Git Bash ที่โฟลเดอร์โปรเจกต์:
#     bash deploy_pi.sh                 # ใช้ raspberrypi.local (ถ้าไม่ตอบใช้ 192.168.1.162)
#     bash deploy_pi.sh 192.168.1.50    # ระบุที่อยู่เอง
#     bash deploy_pi.sh --setup         # ครั้งแรก: ส่งไฟล์ + ติดตั้งระบบ (setup_pi5.sh)
#
# ต้องตั้ง SSH key ก่อน (ครั้งเดียว) ดู docs/SSH_KEY_SETUP.md
#
# ไม่ส่งไฟล์เหล่านี้ (ของเครื่องนี้เท่านั้น / Pi มีของตัวเอง):
#   .env (Pi ใช้ค่าของตัวเอง เช่น VOICE_SERVER_URL ชี้มาที่โน้ตบุ๊ก), .venv*, .git,
#   เสียงต้นแบบ/ตัวอย่าง (voices/, voice_samples/), log, cloudflared.exe (Windows),
#   ข้อมูลระหว่างใช้งาน (analytics_data.json, data/web_answers_pending.json, *.bak)
# ==============================================================================
set -e
cd "$(dirname "$0")"

PI_USER="pi"
PI_DIR="/home/pi/nongphet"
RUN_SETUP=0
PI_HOST=""
for arg in "$@"; do
    case "$arg" in
        --setup) RUN_SETUP=1 ;;
        *) PI_HOST="$arg" ;;
    esac
done
if [ -z "$PI_HOST" ]; then
    PI_HOST="raspberrypi.local"
    ping -n 1 -w 1500 "$PI_HOST" >/dev/null 2>&1 || ping -c 1 -W 2 "$PI_HOST" >/dev/null 2>&1 || PI_HOST="192.168.1.162"
fi
TARGET="${PI_USER}@${PI_HOST}"
SSH_OPTS="-o ConnectTimeout=8 -o BatchMode=yes"

echo "========================================================"
echo "  Deploy NongPhet -> ${TARGET}:${PI_DIR}"
echo "========================================================"

if ! ssh $SSH_OPTS "$TARGET" true 2>/dev/null; then
    echo "[ERROR] เข้า ${TARGET} ด้วย SSH key ไม่ได้"
    echo "        ตั้งค่า SSH key ก่อน (ครั้งเดียว): ดู docs/SSH_KEY_SETUP.md"
    exit 1
fi

echo "[*] กำลังแพ็กและส่งไฟล์ (ไม่รวม .env, .venv, voices, log)..."
tar -czf - \
    --exclude='./.git' --exclude='./.venv' --exclude='./.venv-voice' --exclude='./venv' \
    --exclude='./.claude' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='./.env' --exclude='./voices' --exclude='./voice_samples' \
    --exclude='*.log' --exclude='*.log.*' --exclude='*.bak' --exclude='*.tmp' \
    --exclude='./cloudflared.exe' --exclude='./analytics_data.json' \
    --exclude='./data/web_answers_pending.json' \
    . | ssh $SSH_OPTS "$TARGET" "mkdir -p '$PI_DIR' && tar -xzf - -C '$PI_DIR' && echo '[*] แตกไฟล์บน Pi เรียบร้อย'"

if [ "$RUN_SETUP" = "1" ]; then
    echo "[*] ติดตั้งระบบบน Pi (setup_pi5.sh) ใช้เวลาหลายนาทีในครั้งแรก..."
    ssh -t "$TARGET" "cd '$PI_DIR' && bash setup_pi5.sh"
else
    echo "[*] อัปเดตไลบรารี Python และรีสตาร์ทบริการ..."
    ssh $SSH_OPTS "$TARGET" "cd '$PI_DIR' && (test -d .venv || python3 -m venv .venv) && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart nongphet nongphet-vision nongphet-esp32 2>/dev/null; systemctl is-active nongphet || true"
fi

if ! ssh $SSH_OPTS "$TARGET" "test -f '$PI_DIR/.env'"; then
    echo ""
    echo "[WARN] ยังไม่มี .env บน Pi: สร้างที่ ${PI_DIR}/.env (ดู docs/PI5_HARDWARE_GUIDE.md หัวข้อ OmniVoice)"
fi

echo "========================================================"
echo "  Deploy เสร็จ: http://${PI_HOST}:5000/kiosk"
echo "========================================================"
