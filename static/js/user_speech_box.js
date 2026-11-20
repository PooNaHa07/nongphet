// -----------------------------------------------------------------------------
// กล่องข้อความ "คุณพูดว่า..." บนจอใบหน้า (/emotion)
// แสดงสถานะเสียงพูดของผู้ใช้: กำลังฟัง -> กำลังแปลงเสียงเป็นข้อความ -> ข้อความที่พูด
// รับจากเซิร์ฟเวอร์ผ่าน SSE (/api/iot/events, event "user_speech") เพราะจอ kiosk อยู่คนละโปรไฟล์เบราว์เซอร์
// แสดงทั้งโหมด face-only (บูธ) และโหมด HUD
// -----------------------------------------------------------------------------
(function () {
    const FINAL_SHOW_MS = 9000;      // ข้อความที่พูดค้างไว้นานเท่านี้
    const PENDING_MAX_MS = 20000;    // กันสถานะ "กำลังฟัง/กำลังแปลง" ค้างถ้าสัญญาณหาย

    let box = null, icon = null, label = null, text = null, hideTimer = null;

    function build() {
        const style = document.createElement('style');
        style.textContent = `
            #userSpeechBox {
                position: fixed; left: 50%; bottom: 4vh; transform: translate(-50%, 12px);
                max-width: min(86vw, 900px); padding: 14px 26px; border-radius: 22px;
                background: rgba(2, 6, 23, 0.82); border: 1px solid rgba(250, 204, 21, 0.45);
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.45); backdrop-filter: blur(10px);
                color: #fef9c3; font-family: 'Prompt', 'Sarabun', 'Noto Sans Thai', sans-serif;
                display: flex; align-items: center; gap: 14px; z-index: 60;
                opacity: 0; pointer-events: none; transition: opacity .25s ease, transform .25s ease;
            }
            #userSpeechBox.show { opacity: 1; transform: translate(-50%, 0); }
            #userSpeechBox .usb-icon { font-size: clamp(22px, 3.2vw, 34px); flex: none; }
            #userSpeechBox .usb-body { display: flex; flex-direction: column; min-width: 0; }
            #userSpeechBox .usb-label { font-size: clamp(12px, 1.4vw, 16px); color: #fde68a; opacity: .85; }
            #userSpeechBox .usb-text {
                font-size: clamp(18px, 2.6vw, 30px); font-weight: 600; line-height: 1.35; color: #fffbeb;
                overflow-wrap: anywhere;
            }
            #userSpeechBox.pending .usb-text { display: none; }
            #userSpeechBox.pending .usb-label { font-size: clamp(16px, 2.2vw, 24px); opacity: 1; }
            #userSpeechBox.pending .usb-icon { animation: usbPulse 1s ease-in-out infinite; }
            @keyframes usbPulse { 50% { transform: scale(1.18); opacity: .6; } }
        `;
        document.head.appendChild(style);

        box = document.createElement('div');
        box.id = 'userSpeechBox';
        box.setAttribute('role', 'status');
        box.setAttribute('aria-live', 'polite');
        box.innerHTML = '<span class="usb-icon"></span><div class="usb-body"><span class="usb-label"></span><span class="usb-text"></span></div>';
        icon = box.querySelector('.usb-icon');
        label = box.querySelector('.usb-label');
        text = box.querySelector('.usb-text');
        document.body.appendChild(box);
    }

    function hide() {
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
        if (box) box.classList.remove('show');
    }

    function show(state, said) {
        if (!box) build();
        if (hideTimer) clearTimeout(hideTimer);
        if (state === 'clear') return hide();
        if (state === 'final') {
            box.classList.remove('pending');
            icon.textContent = '🗣️';
            label.textContent = 'คุณพูดว่า';
            text.textContent = `“${said}”`;      // textContent: ไม่ตีความเป็น HTML
            hideTimer = setTimeout(hide, FINAL_SHOW_MS);
        } else {
            box.classList.add('pending');
            icon.textContent = state === 'listening' ? '🎙️' : '⏳';
            label.textContent = state === 'listening' ? 'น้องเพชรกำลังฟัง...' : 'กำลังแปลงเสียงเป็นข้อความ...';
            text.textContent = '';
            hideTimer = setTimeout(hide, PENDING_MAX_MS);
        }
        box.classList.add('show');
    }

    function connect() {
        if (typeof EventSource === 'undefined') return;
        const es = new EventSource('/api/iot/events');
        es.onmessage = (event) => {
            let data;
            try { data = JSON.parse(event.data); } catch (e) { return; }
            if (data.event === 'user_speech') show(data.state, data.text || '');
            else if (data.event === 'user_left') hide();
        };
        // เบราว์เซอร์เชื่อมต่อใหม่เองตามมาตรฐาน SSE
    }

    window.showUserSpeech = show;   // ใช้ทดสอบ/สั่งจากหน้าอื่นได้
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', connect);
    else connect();
})();
