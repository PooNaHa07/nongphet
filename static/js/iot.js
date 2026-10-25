/**
 * nongphet AI Smart Guide - ESP32 Embedded IoT & Camera Smart Presence Integration
 * Implements Vocational Standard 4.2 (GPIO Control, Ultrasonic Sensor HC-SR04, Camera AI Presence)
 */

let iotEventSource = null;
let lastAutoGreetTime = 0;
let isCameraSensorActive = false;
let cameraSensorStream = null;
let cameraDetectionInterval = null;
let cameraConsecutiveDetections = 0;
let prevFrameData = null;

function showIoTToast(distance, timestamp, source = 'esp32_hardware') {
    const toast = document.getElementById('iotAlertToast');
    const timeEl = document.getElementById('iotToastTime');
    const msgEl = document.getElementById('iotToastMsg');
    const titleText = document.getElementById('iotToastTitleText');
    const iconEl = document.getElementById('iotToastIcon');
    const distDisp = document.getElementById('iotDistanceDisplay');

    if (timeEl) timeEl.textContent = timestamp || new Date().toLocaleTimeString();

    if (source === 'camera_ai') {
        if (titleText) titleText.textContent = 'กล้อง AI: ตรวจพบผู้ใช้!';
        if (msgEl) msgEl.textContent = 'ตรวจพบบุคคลยืนอยู่หน้ากล้อง (Smart Camera Presence)';
        if (iconEl) iconEl.innerHTML = '<i class="fa-solid fa-camera text-cyan-300"></i>';
        if (distDisp) distDisp.textContent = 'พบคนผ่านกล้อง 📷';
    } else if (source === 'manual_simulation') {
        if (titleText) titleText.textContent = 'จำลอง: ตรวจพบผู้ใช้!';
        if (msgEl) msgEl.textContent = `จำลองพบผู้ใช้ระยะ ${distance || 45} ซม. (Simulated Presence)`;
        if (iconEl) iconEl.innerHTML = '<i class="fa-solid fa-bolt text-amber-300"></i>';
        if (distDisp) distDisp.textContent = `${distance || 45} cm (จำลอง)`;
    } else {
        if (titleText) titleText.textContent = 'ESP32: ตรวจพบผู้ใช้!';
        if (msgEl) msgEl.textContent = `พบผู้ใช้ในระยะ ${distance} ซม. (Ultrasonic HC-SR04)`;
        if (iconEl) iconEl.innerHTML = '<i class="fa-solid fa-person-walking text-emerald-300"></i>';
        if (distDisp) distDisp.textContent = `${distance} cm (ตรวจพบ)`;
    }

    if (toast) {
        toast.classList.remove('translate-y-[-140%]', 'opacity-0', 'pointer-events-none');
        toast.classList.add('translate-y-0', 'opacity-100');

        setTimeout(() => {
            toast.classList.add('translate-y-[-140%]', 'opacity-0', 'pointer-events-none');
            toast.classList.remove('translate-y-0', 'opacity-100');
            if (distDisp && !isCameraSensorActive) distDisp.textContent = 'ปกติ (พร้อมใช้งาน)';
        }, 5000);
    }
}

// โหมดสลับเข้าสู่กล้องตอบโต้ Live ทันทีเมื่อตรวจพบคน (Default: true)
let autoLiveOnPresence = true;

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

function triggerAutoGreeting(distance, source = 'esp32_hardware') {
    const now = Date.now();
    // ป้องกันการกล่าวทักทายซ้ำซ้อนภายใน 10 วินาที
    if (now - lastAutoGreetTime < 10000) return;
    lastAutoGreetTime = now;

    // อัปเดตสถานะเซนเซอร์บนหน้าจอ Live HUD
    updateLiveSensorHud(distance, source);

    // สั่งให้ ESP32 สลับไฟ LED เป็นสถานะพูดโต้ตอบ (Speaking - GPIO 2 กะพริบเร็ว)
    fetch('/api/iot/led', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: 'speaking' })
    }).catch(() => {});

    // หากเปิดโหมด Auto Live (สลับเข้ากล้องตอบโต้ Real-time ทันที)
    if (autoLiveOnPresence) {
        // 1. นำทางไปยังหน้าจอกล้องคุยสด
        if (typeof navigateTo === 'function') {
            navigateTo('screen-live');
        }

        // 2. เริ่มต้น Live Session อัตโนมัติ (เปิดกล้องและไมค์คุยทันที)
        setTimeout(async () => {
            if (typeof liveIsActive !== 'undefined' && !liveIsActive) {
                if (typeof startLiveSession === 'function') {
                    try {
                        // ปิดกล้องตรวจจับพื้นหลังก่อนเพื่อให้กล้องหลักใช้งานได้
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
        // โหมดธรรมดา: เล่นเสียงทักทายผ่าน Neural TTS
        const welcomeText = "สวัสดีครับ ยินดีต้อนรับสู่น้องเพชร AI ผู้ช่วยอัจฉริยะประจำจังหวัดเพชรบุรีและวิทยาลัยอาชีวศึกษาเพชรบุรี มีอะไรให้น้องเพชรช่วยแนะนำไหมครับ";
        if (typeof playTTS === 'function') {
            playTTS(welcomeText);
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
// Real-time Camera AI Human Presence Detection
// -----------------------------------------------------------------------------
async function toggleCameraSensor(forcedState) {
    if (forcedState !== undefined) {
        isCameraSensorActive = forcedState;
    } else {
        isCameraSensorActive = !isCameraSensorActive;
    }

    const btn = document.getElementById('btnToggleCameraSensor');
    const video = document.getElementById('cameraSensorVideo');
    const previewContainer = document.getElementById('cameraSensorPreview');
    const statusText = document.getElementById('cameraSensorStatus');

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

            startCameraDetectionLoop();
        } catch (e) {
            console.error('Camera Sensor error:', e);
            alert('ไม่สามารถเปิดกล้องเพื่อตรวจจับคนได้ กรุณาอนุญาตสิทธิ์การเข้าถึงกล้องในเบราว์เซอร์ครับ');
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
    const video = document.getElementById('cameraSensorVideo');
    const indicator = document.getElementById('cameraDetectionIndicator');

    const hasNativeFaceDetector = ('FaceDetector' in window);
    let nativeFaceDetector = null;
    if (hasNativeFaceDetector) {
        try {
            nativeFaceDetector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 3 });
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

        // 2. Fallback Computer Vision: Skin-tone & Motion presence in Central Region
        if (!personDetected && ctx) {
            ctx.drawImage(video, 0, 0, 64, 48);
            const frame = ctx.getImageData(0, 0, 64, 48);
            const data = frame.data;

            let skinPixelCount = 0;
            let diffScore = 0;

            for (let i = 0; i < data.length; i += 4) {
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];

                // Rule-based Skin tone detection
                if (r > 60 && g > 40 && b > 20 && r > g && r > b && (Math.max(r, g, b) - Math.min(r, g, b) > 15) && Math.abs(r - g) > 15) {
                    skinPixelCount++;
                }

                if (prevFrameData) {
                    const pr = prevFrameData[i];
                    const pg = prevFrameData[i + 1];
                    const pb = prevFrameData[i + 2];
                    diffScore += Math.abs(r - pr) + Math.abs(g - pg) + Math.abs(b - pb);
                }
            }

            prevFrameData = new Uint8ClampedArray(data);

            const skinRatio = skinPixelCount / (64 * 48);
            const avgDiff = diffScore / (64 * 48 * 3);

            if (skinRatio > 0.05 || (avgDiff > 10 && skinRatio > 0.025)) {
                personDetected = true;
            }
        }

        if (personDetected) {
            cameraConsecutiveDetections++;
            if (indicator) {
                indicator.textContent = '👤 ตรวจพบคนหน้ากล้อง!';
                indicator.className = 'text-[9px] font-bold text-emerald-300 bg-emerald-950/90 px-2 py-0.5 rounded-full border border-emerald-500/50 animate-pulse';
            }

            // ถ้าตรวจพบต่อเนื่อง 2 รอบ (~1.2 วินาที)
            if (cameraConsecutiveDetections >= 2) {
                cameraConsecutiveDetections = 0;
                sendPresenceTrigger('camera_ai', 50);
            }
        } else {
            cameraConsecutiveDetections = Math.max(0, cameraConsecutiveDetections - 1);
            if (indicator) {
                indicator.textContent = 'สแกนหาคน...';
                indicator.className = 'text-[9px] font-medium text-slate-300 bg-slate-900/80 px-2 py-0.5 rounded-full border border-slate-700';
            }
        }
    }, 600);
}

function sendPresenceTrigger(source = 'manual_simulation', distance = 45) {
    fetch('/api/iot/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            event: 'user_detected',
            distance: distance,
            source: source
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
                        showIoTToast(data.distance, data.timestamp, data.source);
                        triggerAutoGreeting(data.distance, data.source);
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

// เริ่มต้นการเชื่อมต่อ IoT SSE ทันทีที่โหลดหน้าเว็บ
window.addEventListener('DOMContentLoaded', initIoTEventStream);

