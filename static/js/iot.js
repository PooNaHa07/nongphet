/**
 * nongphet AI Smart Guide - ESP32 Embedded IoT & Camera Smart Presence Integration
 * Implements Vocational Standard 4.2 (GPIO Control, Ultrasonic Sensor HC-SR04, Camera AI Presence)
 */

let iotEventSource = null;
let lastAutoGreetTime = 0;
let lastPresenceTriggerTime = 0;
let lastPresenceToastTime = 0;
const PRESENCE_TRIGGER_COOLDOWN_MS = 30000;
let isCameraSensorActive = false;
let cameraSensorStream = null;
let cameraDetectionInterval = null;
let cameraConsecutiveDetections = 0;
let prevFrameData = null;

function showIoTToast(distance, timestamp, source = 'esp32_hardware', customText = null) {
    let toast = document.getElementById('iotAlertToast');
    let timeEl = document.getElementById('iotToastTime');
    let msgEl = document.getElementById('iotToastMsg');
    let titleText = document.getElementById('iotToastTitleText');
    let iconEl = document.getElementById('iotToastIcon');
    let distDisp = document.getElementById('iotDistanceDisplay');

    // ถ้ายังไม่มี toast ใน DOM (เช่น บน kiosk.html) ให้สร้างขึ้นมาโดยอัตโนมัติ
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'iotAlertToast';
        toast.className = 'fixed top-4 right-4 sm:top-6 sm:right-6 z-50 transform transition-all duration-300 translate-y-[-140%] opacity-0 pointer-events-none max-w-md w-[92vw] sm:w-full shadow-2xl';
        toast.innerHTML = `
            <div class="p-3.5 sm:p-4 rounded-2xl bg-slate-900/95 border border-cyan-400/50 shadow-2xl backdrop-blur-xl text-white flex items-center gap-3">
                <div id="iotToastIcon" class="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-xl text-cyan-300 shrink-0 shadow animate-pulse">
                    <i class="fa-solid fa-person-walking"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between">
                        <h4 id="iotToastTitle" class="text-xs font-black text-cyan-300 flex items-center gap-1.5">
                            <span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
                            <span id="iotToastTitleText">ตรวจพบคนหยุดมองระบบ!</span>
                        </h4>
                        <span id="iotToastTime" class="text-[9px] text-slate-400 font-mono-code">00:00:00</span>
                    </div>
                    <p id="iotToastMsg" class="text-xs text-slate-200 mt-0.5 truncate"></p>
                </div>
            </div>
        `;
        document.body.appendChild(toast);
        timeEl = document.getElementById('iotToastTime');
        msgEl = document.getElementById('iotToastMsg');
        titleText = document.getElementById('iotToastTitleText');
        iconEl = document.getElementById('iotToastIcon');
    }

    if (timeEl) timeEl.textContent = timestamp || new Date().toLocaleTimeString();

    if (source === 'camera_eye_contact' || source === 'camera_ai') {
        if (titleText) titleText.textContent = '👀 กล้อง AI: มีคนมาหยุดมองระบบ!';
        if (msgEl) msgEl.textContent = customText || 'สวัสดีค่ะ ยินดีต้อนรับสู่น้องเพชร AI Smart Guide';
        if (iconEl) iconEl.innerHTML = '<i class="fa-solid fa-face-smile text-cyan-300"></i>';
        if (distDisp) distDisp.textContent = 'พบคนหยุดมอง 📷';
    } else if (source === 'manual_simulation') {
        if (titleText) titleText.textContent = 'จำลอง: ตรวจพบคนหยุดมอง!';
        if (msgEl) msgEl.textContent = customText || `จำลองพบผู้ใช้ระยะ ${distance || 45} ซม.`;
        if (iconEl) iconEl.innerHTML = '<i class="fa-solid fa-bolt text-amber-300"></i>';
        if (distDisp) distDisp.textContent = `${distance || 45} cm (จำลอง)`;
    } else {
        if (titleText) titleText.textContent = '📡 เซนเซอร์: ตรวจพบผู้ใช้!';
        if (msgEl) msgEl.textContent = customText || `พบผู้ใช้ในระยะ ${distance} ซม. (Ultrasonic HC-SR04)`;
        if (iconEl) iconEl.innerHTML = '<i class="fa-solid fa-person-walking text-emerald-300"></i>';
        if (distDisp) distDisp.textContent = `${distance} cm (ตรวจพบ)`;
    }

    toast.classList.remove('translate-y-[-140%]', 'opacity-0', 'pointer-events-none');
    toast.classList.add('translate-y-0', 'opacity-100');

    setTimeout(() => {
        toast.classList.add('translate-y-[-140%]', 'opacity-0', 'pointer-events-none');
        toast.classList.remove('translate-y-0', 'opacity-100');
        if (distDisp && !isCameraSensorActive) distDisp.textContent = 'ปกติ (พร้อมใช้งาน)';
    }, 5500);
}

// โหมดสลับเข้าสู่กล้องตอบโต้ Live ทันทีเมื่อตรวจพบคน (Default: true)
let autoLiveOnPresence = false;

function toggleAutoLiveOnPresence(enabled) {
    autoLiveOnPresence = enabled;
    const toast = document.getElementById('iotAlertToast');
    const msgEl = document.getElementById('iotToastMsg');
    const titleText = document.getElementById('iotToastTitleText');
    const iconEl = document.getElementById('iotToastIcon');
    if (toast && titleText && msgEl && iconEl) {
        titleText.textContent = enabled ? 'โหมดตอบโต้ Real-time: เปิด' : 'โหมดตอบโต้ Real-time: ปิด';
        msgEl.textContent = enabled ? 'เมื่อตรวจพบคน ระบบจะเปิดกล้องตอบโต้สดอัตโนมัติ' : 'เมื่อตรวจพบคน ระบบจะทักทายด้วยเสียงปกติ';
        iconEl.innerHTML = enabled ? '<i class="fa-solid fa-video text-rose-400"></i>' : '<i class="fa-solid fa-volume-high text-blue-400"></i>';
        toast.classList.remove('translate-y-[-140%]', 'opacity-0', 'pointer-events-none');
        toast.classList.add('translate-y-0', 'opacity-100');
        setTimeout(() => {
            toast.classList.add('translate-y-[-140%]', 'opacity-0', 'pointer-events-none');
            toast.classList.remove('translate-y-0', 'opacity-100');
        }, 2500);
    }
}

function updateLiveSensorHud(distance, source) {
    const hudBadge = document.getElementById('liveSensorHudBadge');
    const hudText = document.getElementById('liveSensorHudText');
    const pulseEl = document.getElementById('liveSensorHudPulse');
    if (hudText) {
        const srcLabel = source === 'camera_ai' ? '📷 กล้อง AI' : (source === 'manual_simulation' ? '⚡ จำลองตรวจพบ' : '📡 HC-SR04');
        hudText.textContent = `${srcLabel}: ตรวจพบคน (${distance || 45} ซม.) • โต้ตอบสด`;
    }
    if (hudBadge) {
        hudBadge.className = 'flex items-center gap-1.5 bg-emerald-950/90 backdrop-blur-md px-3 py-1 rounded-full border border-emerald-400 text-[10px] text-emerald-300 font-mono-code shadow-lg animate-pulse';
    }
    if (pulseEl) {
        pulseEl.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-ping';
    }
}

function triggerAutoGreeting(distance, source = 'esp32_hardware', customText = null) {
    const now = Date.now();
    // ป้องกันการกล่าวทักทายซ้ำซ้อนภายใน 25 วินาที
    if (now - lastAutoGreetTime < 25000) return;
    lastAutoGreetTime = now;

    // อัปเดตสถานะเซนเซอร์บนหน้าจอ Live HUD
    updateLiveSensorHud(distance, source);

    // สั่งให้ ESP32 สลับไฟ LED เป็นสถานะพูดโต้ตอบ (Speaking - GPIO 2 กะพริบเร็ว)
    fetch('/api/iot/led', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: 'speaking' })
    }).catch(() => {});

    // รายการประโยคทักทายที่อบอุ่นและเป็นมิตรของน้องเพชร
    const greetingQuotes = [
        "สวัสดีค่ะ ยินดีต้อนรับสู่น้องเพชร AI ผู้ช่วยอัจฉริยะประจำวิทยาลัยอาชีวศึกษาเพชรบุรี มีอะไรให้น้องเพชรช่วยแนะนำ สอบถามได้เลยนะคะ",
        "สวัสดีค่ะ! ยินดีต้อนรับสู่น้องเพชร AI ค่ะ แตะที่หน้าจอเพื่อเลือกดูหลักสูตร ที่เที่ยว หรือพูดคุยกับน้องเพชรได้เลยนะคะ",
        "สวัสดีค่ะ ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ น้องเพชรพร้อมแนะนำข้อมูลการศึกษาและสถานที่ท่องเที่ยวเพชรบุรีแล้วค่ะ"
    ];
    const welcomeText = customText || greetingQuotes[Math.floor(Math.random() * greetingQuotes.length)];

    // แสดงข้อความต้อนรับบนจอ (Toast / Floating Banner)
    showIoTToast(distance, new Date().toLocaleTimeString(), source, welcomeText);

    // ปลุกหน้าจอ Kiosk และกลับสู่หน้า welcome หากหน้าจอพักอยู่
    if (typeof resetKioskIdleTimer === 'function') resetKioskIdleTimer();
    const activeScreen = document.querySelector('.screen-view.active');
    if (!activeScreen) {
        if (typeof navigateTo === 'function') navigateTo('screen-welcome');
    }

    // หากเปิดโหมด Auto Live (สลับเข้ากล้องตอบโต้ Real-time ทันที)
    if (autoLiveOnPresence) {
        if (typeof navigateTo === 'function') {
            navigateTo('screen-live');
        }

        setTimeout(async () => {
            if (typeof liveIsActive !== 'undefined' && !liveIsActive) {
                if (typeof startLiveSession === 'function') {
                    try {
                        if (isCameraSensorActive) {
                            stopCameraSensor();
                        }
                        await startLiveSession();
                    } catch (e) {
                        console.error('Auto start live error:', e);
                    }
                }
            } else if (typeof updateLiveAISubtitle === 'function') {
                updateLiveAISubtitle(`ตรวจพบบุคคลยืนอยู่หน้ากล้อง (ระยะ ${distance || 45} ซม.) น้องเพชรพร้อมคุยและมองเห็นคุณแล้วครับ! 😊`);
            }
        }, 400);
    } else {
        // โหมดอัตโนมัติ: พูดทักทายต้อนรับด้วยเสียงภาษาไทย (Neural TTS)
        // หลังพูดจบให้เปิดโหมดคุยสด hands-free อัตโนมัติ
        if (typeof playTTS === 'function') {
            playTTS(welcomeText, null, () => {
                // TTS จบ -> เปิดโหมด Realtime Voice อัตโนมัติ
                if (typeof toggleRealtimeVoiceMode === 'function' && typeof isRealtimeVoiceActive !== 'undefined' && !isRealtimeVoiceActive) {
                    console.log('🎙️ [Kiosk Auto Voice] Greeting จบ -> เปิดโหมดคุยสด hands-free');
                    toggleRealtimeVoiceMode(true);
                }
            });
        }
    }

    // คืนค่าไฟ LED เป็น Idle สว่างค้างเมื่อพูดเสร็จ
    setTimeout(() => {
        fetch('/api/iot/led', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: 'idle' })
        }).catch(() => {});
    }, 6500);
}

// -----------------------------------------------------------------------------
// Real-time Camera AI Human Presence Detection (ตรวจจับคนมาหยุดมองอัตโนมัติ)
// -----------------------------------------------------------------------------
async function toggleCameraSensor(forcedState, silent = false) {
    if (forcedState !== undefined) {
        isCameraSensorActive = forcedState;
    } else {
        isCameraSensorActive = !isCameraSensorActive;
    }

    const btn = document.getElementById('btnToggleCameraSensor');
    let video = document.getElementById('cameraSensorVideo');
    const previewContainer = document.getElementById('cameraSensorPreview');
    const statusText = document.getElementById('cameraSensorStatus');

    // ถ้าไม่มี <video> ในหน้า (เช่น บน kiosk.html) ให้สร้างแท็ก hidden video อัตโนมัติ
    if (!video) {
        video = document.createElement('video');
        video.id = 'cameraSensorVideo';
        video.autoplay = true;
        video.playsInline = true;
        video.muted = true;
        video.style.display = 'none';
        document.body.appendChild(video);
    }

    if (isCameraSensorActive) {
        try {
            const constraints = {
                video: {
                    facingMode: 'user',
                    width: { ideal: 320 },
                    height: { ideal: 240 }
                },
                audio: false
            };
            cameraSensorStream = await navigator.mediaDevices.getUserMedia(constraints);
            if (video) {
                video.srcObject = cameraSensorStream;
                await video.play();
            }
            if (previewContainer) previewContainer.classList.remove('hidden');
            if (btn) {
                btn.className = 'w-full py-1.5 px-2 bg-rose-600/30 hover:bg-rose-600/40 text-rose-300 border border-rose-500/40 rounded-lg text-[10px] font-bold flex items-center justify-center gap-1.5 transition active:scale-95 shadow';
                btn.innerHTML = '<i class="fa-solid fa-camera-slash"></i> <span>ปิดกล้องตรวจจับคน</span>';
            }
            if (statusText) {
                statusText.textContent = '🟢 กำลังตรวจจับคน...';
                statusText.className = 'font-mono-code text-emerald-400 font-bold';
            }

            console.log('📷 [Smart Sensor] กล้องตรวจจับคนมาหยุดมองเริ่มต้นทำงานเรียบร้อยแล้ว');
            startCameraDetectionLoop();
        } catch (e) {
            console.warn('Camera Sensor standby:', e);
            if (!silent) {
                if (typeof showAppToast === 'function') {
                    showAppToast('ไม่สามารถเปิดกล้องได้ กรุณาอนุญาตสิทธิ์กล้องในเบราว์เซอร์', 'warning');
                }
            }
            isCameraSensorActive = false;
            if (previewContainer) previewContainer.classList.add('hidden');
        }
    } else {
        stopCameraSensor();
        if (previewContainer) previewContainer.classList.add('hidden');
        if (btn) {
            btn.className = 'w-full py-1.5 px-2 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 rounded-lg text-[10px] font-bold flex items-center justify-center gap-1.5 transition active:scale-95 shadow';
            btn.innerHTML = '<i class="fa-solid fa-camera"></i> <span>เปิดกล้องตรวจจับคน (Webcam)</span>';
        }
        if (statusText) {
            statusText.textContent = 'กล้องปิดอยู่';
            statusText.className = 'font-mono-code text-slate-400';
        }
    }
}

function stopCameraSensor() {
    if (cameraDetectionInterval) {
        clearInterval(cameraDetectionInterval);
        cameraDetectionInterval = null;
    }
    if (cameraSensorStream) {
        cameraSensorStream.getTracks().forEach(track => track.stop());
        cameraSensorStream = null;
    }
    prevFrameData = null;
    cameraConsecutiveDetections = 0;
}

function startCameraDetectionLoop() {
    if (cameraDetectionInterval) clearInterval(cameraDetectionInterval);

    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 48;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    let video = document.getElementById('cameraSensorVideo');
    const indicator = document.getElementById('cameraDetectionIndicator');

    const hasNativeFaceDetector = ('FaceDetector' in window);
    let nativeFaceDetector = null;
    if (hasNativeFaceDetector) {
        try {
            nativeFaceDetector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 2 });
        } catch (e) {}
    }

    cameraDetectionInterval = setInterval(async () => {
        if (!isCameraSensorActive || !video || video.readyState < 2) return;

        let personDetected = false;

        // 1. Native FaceDetector API (ถ้าเบราว์เซอร์รองรับ)
        if (nativeFaceDetector) {
            try {
                const faces = await nativeFaceDetector.detect(video);
                if (faces && faces.length > 0) {
                    personDetected = true;
                }
            } catch (err) {}
        }

        // 2. Fallback Computer Vision: Skin-tone & Central Region Presence
        // ตรวจจับทั้งการขยับเข้ามา และการหยุดยืนนิ่งสบตามองตรงหน้า
        if (!personDetected && ctx) {
            ctx.drawImage(video, 0, 0, 64, 48);
            const frame = ctx.getImageData(0, 0, 64, 48);
            const data = frame.data;

            let skinPixelCount = 0;
            let centerSkinCount = 0;
            let diffScore = 0;

            const total = 64 * 48;
            for (let i = 0; i < data.length; i += 4) {
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];

                const pixelIndex = i / 4;
                const px = pixelIndex % 64;
                const py = Math.floor(pixelIndex / 64);

                // ตรวจจับผิวหน้า/คน (Skin-Tone Presence)
                if (r > 60 && g > 40 && b > 20 && r > g && r > b && (Math.max(r, g, b) - Math.min(r, g, b) > 15) && Math.abs(r - g) > 12) {
                    skinPixelCount++;
                    // ถ้าอยู่ในโซนตรงกลางจอ (ยืนอยู่ตรงหน้าระบบ)
                    if (px >= 16 && px <= 48 && py <= 40) {
                        centerSkinCount++;
                    }
                }

                if (prevFrameData) {
                    const pr = prevFrameData[i];
                    const pg = prevFrameData[i + 1];
                    const pb = prevFrameData[i + 2];
                    diffScore += Math.abs(r - pr) + Math.abs(g - pg) + Math.abs(b - pb);
                }
            }

            prevFrameData = new Uint8ClampedArray(data);

            const skinRatio = skinPixelCount / total;
            const centerSkinRatio = centerSkinCount / (32 * 40);
            const avgDiff = diffScore / (total * 3);

            // เมื่อมีคนหยุดยืนมองตรงกลางหรือขยับเข้าใกล้ในเฟรม (ลดโอกาสทริกเกอร์ผิดพลาดจากฉากหลังโทนอุ่น)
            if (centerSkinRatio > 0.09 || (skinRatio > 0.12 && avgDiff > 4)) {
                personDetected = true;
            }
        }

        const nowMs = Date.now();
        const inCooldown = (nowMs - lastPresenceTriggerTime) < PRESENCE_TRIGGER_COOLDOWN_MS;

        if (personDetected) {
            cameraConsecutiveDetections++;
            if (indicator) {
                indicator.textContent = inCooldown ? '👀 กำลังรอคูลดาวน์...' : '👀 มีคนหยุดมองระบบ!';
                indicator.className = 'text-[9px] font-bold text-cyan-300 bg-cyan-950/90 px-2 py-0.5 rounded-full border border-cyan-500/50 animate-pulse';
            }

            // ต้องมีคนหยุดมองต่อเนื่อง 3 รอบ (~1.65 วินาที) และพ้นระยะคูลดาวน์ 30 วินาทีก่อนส่งทริกเกอร์ใหม่
            if (cameraConsecutiveDetections >= 3) {
                cameraConsecutiveDetections = 0;
                if (!inCooldown && !document.hidden) {
                    sendPresenceTrigger('camera_eye_contact', 45);
                }
            }
        } else {
            cameraConsecutiveDetections = Math.max(0, cameraConsecutiveDetections - 1);
            if (indicator) {
                indicator.textContent = 'สแกนหาคน...';
                indicator.className = 'text-[9px] font-medium text-slate-300 bg-slate-900/80 px-2 py-0.5 rounded-full border border-slate-700';
            }
        }
    }, 550);
}

function sendPresenceTrigger(source = 'manual_simulation', distance = 45, greetingText = null) {
    const nowMs = Date.now();
    // ป้องกันการยิง /api/iot/trigger รัวเกินไปสำหรับทริกเกอร์อัตโนมัติ (ยอมให้กดจำลองเองได้ตลอด)
    if (source !== 'manual_simulation' && (nowMs - lastPresenceTriggerTime) < PRESENCE_TRIGGER_COOLDOWN_MS) {
        return;
    }
    if (source !== 'manual_simulation') {
        lastPresenceTriggerTime = nowMs;
    }

    fetch('/api/iot/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            event: 'user_detected',
            distance: distance,
            source: source,
            greeting_text: greetingText
        })
    }).catch(err => console.log('Presence trigger error:', err));
}

// -----------------------------------------------------------------------------
// Real-time Server-Sent Events (SSE) Stream
// -----------------------------------------------------------------------------
function initIoTEventStream() {
    if (!!window.EventSource) {
        try {
            iotEventSource = new EventSource('/api/iot/events');

            iotEventSource.onopen = function() {
                const badge = document.getElementById('iotStatusBadge');
                if (badge) {
                    badge.textContent = 'ONLINE';
                    badge.className = 'px-2 py-0.5 rounded-full text-[9px] font-black bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
                }
            };

            iotEventSource.onmessage = function(e) {
                try {
                    const data = JSON.parse(e.data);
                    if (data.event === 'user_detected') {
                        const nowMs = Date.now();
                        if (data.source === 'manual_simulation' || (nowMs - lastPresenceToastTime) >= 15000) {
                            lastPresenceToastTime = nowMs;
                            showIoTToast(data.distance, data.timestamp, data.source, data.greeting_text);
                        }
                        triggerAutoGreeting(data.distance, data.source, data.greeting_text);
                    }
                } catch (err) {}
            };

            iotEventSource.onerror = function() {
                const badge = document.getElementById('iotStatusBadge');
                if (badge) {
                    badge.textContent = 'STANDBY';
                    badge.className = 'px-2 py-0.5 rounded-full text-[9px] font-black bg-amber-500/20 text-amber-300 border border-amber-500/40';
                }
            };
        } catch (e) {
            console.log('IoT SSE not available');
        }
    }
}

// เริ่มต้นการเชื่อมต่อ IoT SSE และระบบกล้องตรวจจับคนหยุดมองอัตโนมัติ
window.addEventListener('DOMContentLoaded', () => {
    initIoTEventStream();
    
    // เริ่มต้นตรวจจับคนหยุดมองในเบื้องหลังโดยอัตโนมัติ (หน่วงเวลา 1.2 วินาทีเพื่อให้ DOM พร้อม)
    setTimeout(() => {
        if (!isCameraSensorActive && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            toggleCameraSensor(true, true).catch(() => {});
        }
    }, 1200);
});

