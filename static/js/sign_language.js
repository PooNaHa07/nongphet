/**
 * nongphet AI Smart Guide - Thai Sign Language (TSL) & Accessibility Engine
 * MediaPipe Hands 21-Points Skeleton Tracker + Edge Gesture Recognition + Gemini Vision TSL
 */

let signCameraStream = null;
let signHands = null;
let signCameraFacing = 'user';
let signIsCameraActive = false;
let signAnimFrameId = null;
let signLastFrameTime = performance.now();
let signFps = 0;

// Gesture stability & hold tracking
let signCurrentDetectedGesture = null;
let signGestureHoldStartTime = 0;
const SIGN_HOLD_DURATION_MS = 1000; // Hold steady for 1s to auto-trigger
let signLastTriggeredGesture = null;
let signLastTriggerTime = 0;

// Current recognized state
let currentSignResult = {
    gesture_name: 'ฉันรักเธอ (I Love You)',
    gesture_emoji: '🤟',
    meaning: 'ภาษามือสากลและไทย แสดงความรัก มิตรภาพ และความยินดีที่ได้พบกัน',
    reply: 'น้องเพชรยินดีต้อนรับทุกท่านสู่วิทยาลัยอาชีวศึกษาเพชรบุรีครับ! พร้อมดูแลอำนวยความสะดวกให้ทุกท่านตลอดการท่องเที่ยวในเมืองเพชรบุรีครับ ❤️',
    emotion: 'love',
    quick_options: ['แนะนำที่เที่ยวไฮไลท์', 'ดูหลักสูตรเรียนต่อ', 'ของฝากเมืองเพชร']
};

window.addEventListener('DOMContentLoaded', () => {
    initMediaPipeHands();
});

/**
 * Initialize MediaPipe Hands Detector
 */
function initMediaPipeHands() {
    if (typeof Hands === 'undefined') {
        console.warn('MediaPipe Hands library not loaded yet, will retry on camera start');
        return;
    }

    try {
        signHands = new Hands({
            locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
        });

        signHands.setOptions({
            maxNumHands: 2,
            modelComplexity: 1,
            minDetectionConfidence: 0.65,
            minTrackingConfidence: 0.65
        });

        signHands.onResults(onSignLanguageResults);
        console.log('✅ MediaPipe Hands initialized successfully for Nong Phet TSL');
    } catch (e) {
        console.error('Failed to init MediaPipe Hands:', e);
    }
}

/**
 * Toggle Camera On / Off
 */
function toggleSignLanguageCamera() {
    if (signIsCameraActive) {
        stopSignLanguageCamera();
    } else {
        startSignLanguageCamera();
    }
}

/**
 * Start Camera Stream & MediaPipe Loop
 */
async function startSignLanguageCamera() {
    const video = document.getElementById('signVideo');
    const standbyOverlay = document.getElementById('signCameraStandby');
    const hudBar = document.getElementById('signHudBar');
    const btnCam = document.getElementById('btnToggleSignCam');
    const btnLabel = document.getElementById('btnToggleSignCamLabel');

    if (!signHands) {
        initMediaPipeHands();
    }

    try {
        const constraints = {
            video: {
                facingMode: signCameraFacing,
                width: { ideal: 640 },
                height: { ideal: 480 }
            },
            audio: false
        };

        signCameraStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = signCameraStream;
        await video.play();

        signIsCameraActive = true;
        if (standbyOverlay) standbyOverlay.classList.add('hidden');
        if (hudBar) hudBar.classList.remove('hidden');
        if (btnCam) btnCam.className = 'flex-1 py-2.5 px-4 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-xs font-bold border border-rose-400/40 transition flex items-center justify-center gap-2 active:scale-95 shadow';
        if (btnLabel) btnLabel.textContent = 'ปิดกล้อง (Stop Camera)';

        processSignVideoFrames();
    } catch (err) {
        console.error('Sign camera error:', err);
        alert('ไม่สามารถเปิดกล้องได้: ' + (err.message || 'โปรดตรวจสอบการอนุญาตใช้งานกล้องบนอุปกรณ์'));
    }
}

/**
 * Stop Camera Stream
 */
function stopSignLanguageCamera() {
    if (signCameraStream) {
        signCameraStream.getTracks().forEach(track => track.stop());
        signCameraStream = null;
    }

    if (signAnimFrameId) {
        cancelAnimationFrame(signAnimFrameId);
        signAnimFrameId = null;
    }

    const video = document.getElementById('signVideo');
    if (video) video.srcObject = null;

    const canvas = document.getElementById('signCanvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    signIsCameraActive = false;
    const standbyOverlay = document.getElementById('signCameraStandby');
    const hudBar = document.getElementById('signHudBar');
    const liveBanner = document.getElementById('signLiveBanner');
    const btnCam = document.getElementById('btnToggleSignCam');
    const btnLabel = document.getElementById('btnToggleSignCamLabel');

    if (standbyOverlay) standbyOverlay.classList.remove('hidden');
    if (hudBar) hudBar.classList.add('hidden');
    if (liveBanner) liveBanner.classList.add('hidden');
    if (btnCam) btnCam.className = 'flex-1 py-2.5 px-4 bg-slate-800/90 hover:bg-slate-700 text-slate-200 hover:text-white rounded-xl text-xs font-bold border border-slate-700 transition flex items-center justify-center gap-2 active:scale-95 shadow';
    if (btnLabel) btnLabel.textContent = 'เปิดกล้อง (Start Camera)';
}

/**
 * Switch Front/Back Camera
 */
async function switchSignCameraFacing() {
    signCameraFacing = signCameraFacing === 'user' ? 'environment' : 'user';
    if (signIsCameraActive) {
        stopSignLanguageCamera();
        await startSignLanguageCamera();
    }
}

/**
 * Continuous Video Processing Loop
 */
async function processSignVideoFrames() {
    if (!signIsCameraActive) return;

    const video = document.getElementById('signVideo');
    if (video && video.readyState >= 2 && signHands) {
        try {
            await signHands.send({ image: video });
        } catch (e) {
            // Frame processing catch
        }
    }

    // Measure FPS
    const now = performance.now();
    signFps = Math.round(1000 / (now - signLastFrameTime));
    signLastFrameTime = now;
    const fpsBadge = document.getElementById('signFpsCounter');
    if (fpsBadge) fpsBadge.textContent = `${signFps} FPS`;

    signAnimFrameId = requestAnimationFrame(processSignVideoFrames);
}

/**
 * MediaPipe Results Callback: Draw skeleton & classify gesture
 */
function onSignLanguageResults(results) {
    const canvas = document.getElementById('signCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const video = document.getElementById('signVideo');
    if (video && (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight)) {
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const handBadge = document.getElementById('signHandCountBadge');
    const liveBanner = document.getElementById('signLiveBanner');

    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
        if (handBadge) handBadge.innerHTML = '<i class="fa-solid fa-hand"></i> ไม่พบมือในจอ';
        if (liveBanner) liveBanner.classList.add('hidden');
        signCurrentDetectedGesture = null;
        updateHoldProgressBar(0);
        return;
    }

    const handCount = results.multiHandLandmarks.length;
    if (handBadge) {
        handBadge.innerHTML = `<i class="fa-solid fa-hand text-cyan-400"></i> ตรวจพบ ${handCount} มือ (กำลังวิเคราะห์)`;
    }

    // Process primary hand landmarks
    for (let i = 0; i < results.multiHandLandmarks.length; i++) {
        const landmarks = results.multiHandLandmarks[i];
        drawNongPhetHandSkeleton(ctx, landmarks, canvas.width, canvas.height);
        
        // Analyze gesture from primary hand (first hand detected)
        if (i === 0) {
            const detected = classifyHandLandmarkGesture(landmarks);
            handleDetectedGesture(detected);
        }
    }
}

/**
 * Draw Futuristic Gold-Cyan Hand Skeleton matching Nong Phet Branding
 */
function drawNongPhetHandSkeleton(ctx, landmarks, width, height) {
    // 21 Joint connections in MediaPipe Hand
    const connections = [
        [0, 1], [1, 2], [2, 3], [3, 4],       // Thumb
        [0, 5], [5, 6], [6, 7], [7, 8],       // Index
        [0, 9], [9, 10], [10, 11], [11, 12],  // Middle
        [0, 13], [13, 14], [14, 15], [15, 16],// Ring
        [0, 17], [17, 18], [18, 19], [19, 20],// Pinky
        [5, 9], [9, 13], [13, 17], [0, 17]    // Palm base
    ];

    // Draw connecting neon cyan/blue lines
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#38bdf8'; // Cyan-neon
    ctx.shadowColor = '#06b6d4';
    ctx.shadowBlur = 8;

    for (const [start, end] of connections) {
        const p1 = landmarks[start];
        const p2 = landmarks[end];
        ctx.beginPath();
        ctx.moveTo(p1.x * width, p1.y * height);
        ctx.lineTo(p2.x * width, p2.y * height);
        ctx.stroke();
    }

    // Draw glowing gold joint nodes
    for (let idx = 0; idx < landmarks.length; idx++) {
        const lm = landmarks[idx];
        const x = lm.x * width;
        const y = lm.y * height;

        ctx.beginPath();
        // Fingertips (4, 8, 12, 16, 20) are bigger
        const isTip = [4, 8, 12, 16, 20].includes(idx);
        const radius = isTip ? 6 : 4;

        ctx.arc(x, y, radius, 0, 2 * Math.PI);
        ctx.fillStyle = isTip ? '#f59e0b' : '#fde047'; // Golden Yellow
        ctx.shadowColor = '#f59e0b';
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = '#ffffff';
        ctx.stroke();
    }
}

/**
 * Geometric Rule-Based Classifier for 21 Hand Landmarks
 * Classifies: love, peace, pointing, open_palm, fist, thumbs_up, shaka
 */
function classifyHandLandmarkGesture(lm) {
    const wrist = lm[0];

    // Distance helper
    const dist = (p1, p2) => Math.hypot(p1.x - p2.x, p1.y - p2.y);

    // Finger tips & pip joints
    const thumbTip = lm[4], thumbIp = lm[3], thumbMcp = lm[2];
    const indexTip = lm[8], indexPip = lm[6], indexMcp = lm[5];
    const middleTip = lm[12], middlePip = lm[10], middleMcp = lm[9];
    const ringTip = lm[16], ringPip = lm[14], ringMcp = lm[13];
    const pinkyTip = lm[20], pinkyPip = lm[18], pinkyMcp = lm[17];

    // Hand bounding size for normalization
    const palmSize = dist(wrist, middleMcp) || 0.1;

    // Check if each finger is extended (Tip is farther from wrist than PIP)
    const isIndexExtended = dist(indexTip, wrist) > dist(indexPip, wrist) * 1.15;
    const isMiddleExtended = dist(middleTip, wrist) > dist(middlePip, wrist) * 1.15;
    const isRingExtended = dist(ringTip, wrist) > dist(ringPip, wrist) * 1.15;
    const isPinkyExtended = dist(pinkyTip, wrist) > dist(pinkyPip, wrist) * 1.15;

    // Thumb extension check
    const isThumbExtended = dist(thumbTip, indexMcp) > palmSize * 0.7;

    // Thumb Up direction check: Thumb tip is higher than all other fingers
    const isThumbPointingUp = (thumbTip.y < indexMcp.y) && (!isIndexExtended && !isMiddleExtended && !isRingExtended && !isPinkyExtended);

    // 1. I Love You (🤟): Thumb, Index, Pinky extended; Middle, Ring folded
    if (isThumbExtended && isIndexExtended && isPinkyExtended && !isMiddleExtended && !isRingExtended) {
        return 'love';
    }

    // 2. Thumbs Up (👍): Thumb up, others folded
    if (isThumbPointingUp || (isThumbExtended && !isIndexExtended && !isMiddleExtended && !isRingExtended && !isPinkyExtended && thumbTip.y < wrist.y)) {
        return 'thumbs_up';
    }

    // 3. Peace / V-Sign (✌️): Index, Middle extended; Ring, Pinky folded
    if (isIndexExtended && isMiddleExtended && !isRingExtended && !isPinkyExtended) {
        return 'peace';
    }

    // 4. Pointing Up (☝️): Index extended; Middle, Ring, Pinky folded
    if (isIndexExtended && !isMiddleExtended && !isRingExtended && !isPinkyExtended && !isThumbExtended) {
        return 'pointing';
    }

    // 5. Open Palm / Hello (🖐️): All fingers extended
    if (isIndexExtended && isMiddleExtended && isRingExtended && isPinkyExtended && isThumbExtended) {
        return 'open_palm';
    }

    // 6. Fist (✊): All fingers folded
    if (!isIndexExtended && !isMiddleExtended && !isRingExtended && !isPinkyExtended && !isThumbExtended) {
        return 'fist';
    }

    // 7. Shaka / Call (🤙): Thumb and Pinky extended; Index, Middle, Ring folded
    if (isThumbExtended && isPinkyExtended && !isIndexExtended && !isMiddleExtended && !isRingExtended) {
        return 'shaka';
    }

    return null;
}

/**
 * Handle gesture stability debounce & HUD display
 */
function handleDetectedGesture(gestureKey) {
    const liveBanner = document.getElementById('signLiveBanner');
    const floatingEmoji = document.getElementById('signFloatingEmoji');
    const floatingName = document.getElementById('signFloatingName');

    if (!gestureKey) {
        if (liveBanner) liveBanner.classList.add('hidden');
        signCurrentDetectedGesture = null;
        updateHoldProgressBar(0);
        return;
    }

    const gestureNames = {
        'love': { name: 'ฉันรักเธอ (I Love You)', emoji: '🤟' },
        'thumbs_up': { name: 'ยอดเยี่ยม / ขอบคุณ (Thumbs Up)', emoji: '👍' },
        'peace': { name: 'เที่ยวเมืองเพชรบุรี (Peace)', emoji: '✌️' },
        'pointing': { name: 'แนะแนวเรียนต่ออาชีวะ (Pointing Up)', emoji: '☝️' },
        'open_palm': { name: 'สวัสดี / ทักทาย (Open Palm)', emoji: '🖐️' },
        'fist': { name: 'ของกิน & ขนมหวาน (Fist)', emoji: '✊' },
        'shaka': { name: 'ขอความช่วยเหลือฉุกเฉิน (Help / Call)', emoji: '🤙' }
    };

    const gInfo = gestureNames[gestureKey] || { name: gestureKey, emoji: '✋' };

    if (liveBanner) liveBanner.classList.remove('hidden');
    if (floatingEmoji) floatingEmoji.textContent = gInfo.emoji;
    if (floatingName) floatingName.textContent = gInfo.name;

    const now = performance.now();

    if (gestureKey !== signCurrentDetectedGesture) {
        signCurrentDetectedGesture = gestureKey;
        signGestureHoldStartTime = now;
        updateHoldProgressBar(0);
    } else {
        const elapsed = now - signGestureHoldStartTime;
        const progress = Math.min(100, Math.round((elapsed / SIGN_HOLD_DURATION_MS) * 100));
        updateHoldProgressBar(progress);

        // Auto trigger when held steady
        if (elapsed >= SIGN_HOLD_DURATION_MS && (now - signLastTriggerTime > 2500 || signLastTriggeredGesture !== gestureKey)) {
            signLastTriggeredGesture = gestureKey;
            signLastTriggerTime = now;
            simulateGesture(gestureKey);
        }
    }
}

function updateHoldProgressBar(percent) {
    const bar = document.getElementById('signHoldProgressBar');
    const label = document.getElementById('signHoldPercent');
    if (bar) bar.style.width = `${percent}%`;
    if (label) label.textContent = `${percent}%`;
}

/**
 * Simulate or Apply Gesture Result (Local Rule Engine or Backend)
 */
async function simulateGesture(gestureKey) {
    const engineBadge = document.getElementById('signEngineBadge');
    if (engineBadge) {
        engineBadge.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-amber-400"></i> กำลังแปลความหมาย...';
    }

    try {
        const res = await fetch('/api/sign_language', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                gesture_hint: gestureKey,
                language: currentLang || 'th'
            })
        });

        const json = await res.json();
        if (json.status === 'success' || json.status === 'fallback') {
            displaySignLanguageResult(json.data, json.engine || 'local_rules');
        }
    } catch (e) {
        console.warn('API error, using client fallback:', e);
        // Client-side instant fallback
        displaySignLanguageResult(getClientGestureData(gestureKey), 'client_offline');
    }
}

/**
 * Capture High-Res Snapshot from Video and send to Gemini 2.5 Flash Vision
 */
async function analyzeSignWithGemini() {
    const video = document.getElementById('signVideo');
    if (!video || !signIsCameraActive || video.videoWidth === 0) {
        alert('กรุณาเปิดกล้องก่อนทำการวิเคราะห์ด้วย Gemini Vision ครับ');
        return;
    }

    const btn = document.getElementById('btnTriggerGeminiSign');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-amber-300"></i> Gemini กำลังวิเคราะห์ภาพ...';
    btn.disabled = true;

    try {
        // Capture frame to canvas
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = video.videoWidth;
        tempCanvas.height = video.videoHeight;
        const ctx = tempCanvas.getContext('2d');
        ctx.drawImage(video, 0, 0, tempCanvas.width, tempCanvas.height);
        const dataUrl = tempCanvas.toDataURL('image/jpeg', 0.85);

        const res = await fetch('/api/sign_language', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image: dataUrl,
                gesture_hint: signCurrentDetectedGesture || '',
                language: currentLang || 'th'
            })
        });

        const json = await res.json();
        if (json.data) {
            displaySignLanguageResult(json.data, json.engine || 'gemini_vision_tsl');
        } else {
            alert('ไม่สามารถวิเคราะห์ภาษามือจากภาพได้ กรุณาลองใหม่อีกครั้ง');
        }
    } catch (err) {
        console.error('Gemini sign analysis error:', err);
        alert('เกิดข้อผิดพลาดในการเชื่อมต่อ Gemini Vision: ' + err.message);
    } finally {
        btn.innerHTML = origHtml;
        btn.disabled = false;
    }
}

/**
 * Render Translated Result on Visual Accessibility Card
 */
function displaySignLanguageResult(data, engine) {
    if (!data) return;
    currentSignResult = data;

    const emojiEl = document.getElementById('signResultEmoji');
    const nameEl = document.getElementById('signResultName');
    const meaningEl = document.getElementById('signResultMeaning');
    const responseEl = document.getElementById('signResponseText');
    const emotionEmoji = document.getElementById('signEmotionEmoji');
    const emotionText = document.getElementById('signEmotionText');
    const engineBadge = document.getElementById('signEngineBadge');
    const optionsContainer = document.getElementById('signQuickOptions');

    if (emojiEl) emojiEl.textContent = data.gesture_emoji || '🤟';
    if (nameEl) nameEl.textContent = data.gesture_name || 'ภาษามือไทย';
    if (meaningEl) meaningEl.textContent = data.meaning || 'ความหมายของท่าทาง';
    if (responseEl) {
        responseEl.textContent = data.reply || 'น้องเพชรพร้อมให้บริการครับ';
        responseEl.parentElement.classList.add('ring-2', 'ring-cyan-400/50');
        setTimeout(() => responseEl.parentElement.classList.remove('ring-2', 'ring-cyan-400/50'), 1000);
    }

    // Emotion sync
    const emotionMap = {
        'love': { emoji: '❤️', label: 'ส่งมอบความรัก' },
        'happy': { emoji: '😊', label: 'มีความสุข' },
        'wink': { emoji: '😉', label: 'ยินดีรับใช้' },
        'excited': { emoji: '🤩', label: 'ตื่นเต้นพาเที่ยว' },
        'thinking': { emoji: '🤔', label: 'กำลังคิดวิเคราะห์' },
        'smile': { emoji: '😄', label: 'ยิ้มสดใส' },
        'surprised': { emoji: '😲', label: 'พร้อมช่วยเหลือ' }
    };
    const emoInfo = emotionMap[data.emotion] || emotionMap['happy'];
    if (emotionEmoji) emotionEmoji.textContent = emoInfo.emoji;
    if (emotionText) emotionText.textContent = emoInfo.label;

    if (engineBadge) {
        const engineLabel = engine.includes('gemini') ? 'Gemini 2.5 Flash TSL' : 'Edge AI Real-time';
        engineBadge.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-400"></i> ${engineLabel}`;
    }

    // Render Quick Options
    if (optionsContainer && data.quick_options && Array.isArray(data.quick_options)) {
        optionsContainer.innerHTML = '';
        data.quick_options.forEach(opt => {
            const btn = document.createElement('button');
            btn.className = 'px-3 py-1.5 rounded-xl bg-cyan-600/30 hover:bg-cyan-600 text-cyan-200 hover:text-white border border-cyan-500/40 text-xs font-bold transition active:scale-95 shadow';
            btn.textContent = opt;
            btn.onclick = () => {
                navigateTo('screen-chat');
                if (typeof sendQuickMessage === 'function') {
                    sendQuickMessage(opt);
                }
            };
            optionsContainer.appendChild(btn);
        });
    }

    // Sync with Robot Head Display if endpoint exists
    try {
        fetch('/api/emotion/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: data.emotion || 'happy' })
        }).catch(() => {});
    } catch (e) {}
}

/**
 * Speak the Current Sign Response (TTS for companions)
 */
function speakCurrentSignResponse() {
    const text = currentSignResult.reply || 'น้องเพชรพร้อมให้บริการครับ';
    if (typeof playNeuralTTS === 'function') {
        playNeuralTTS(text);
    } else if ('speechSynthesis' in window) {
        const u = new SpeechSynthesisUtterance(text);
        u.lang = currentLang === 'en' ? 'en-US' : 'th-TH';
        window.speechSynthesis.speak(u);
    }
}

/**
 * Local Fallback Data
 */
function getClientGestureData(key) {
    const dict = {
        'love': {
            gesture_name: 'ฉันรักเธอ (I Love You)',
            gesture_emoji: '🤟',
            meaning: 'ภาษามือสากลและไทย แสดงความรัก มิตรภาพ และความยินดีที่ได้พบกัน',
            reply: 'น้องเพชรยินดีต้อนรับทุกท่านสู่วิทยาลัยอาชีวศึกษาเพชรบุรีครับ! ขอส่งมอบความรักและพร้อมดูแลอำนวยความสะดวกให้ทุกท่านตลอดการท่องเที่ยวในเมืองเพชรบุรีครับ ❤️',
            emotion: 'love',
            quick_options: ['แนะนำที่เที่ยวไฮไลท์', 'ดูหลักสูตรเรียนต่อ', 'ของฝากเมืองเพชร']
        },
        'thumbs_up': {
            gesture_name: 'ยอดเยี่ยม / ขอบคุณ (Thumbs Up)',
            gesture_emoji: '👍',
            meaning: 'แสดงความชื่นชม พอใจ หรือขอบคุณ',
            reply: 'ขอบคุณมากครับน้องเพชรดีใจมากที่ได้ช่วยเหลือคุณ ขอให้มีความสุขและเพลิดเพลินกับการท่องเที่ยวเมืองเพชรบุรีนะครับ!',
            emotion: 'happy',
            quick_options: ['วางแผนทริปท่องเที่ยว', 'ดูร้านอาหารแนะนำ']
        },
        'peace': {
            gesture_name: 'ท่องเที่ยวเพชรบุรี / สองนิ้ว (Peace)',
            gesture_emoji: '✌️',
            meaning: 'สัญลักษณ์แห่งความสุข การถ่ายรูป และการท่องเที่ยวสำรวจสถานที่',
            reply: 'พร้อมลุยเที่ยวเมืองเพชรบุรีแล้วครับ! แนะนำ 3 แลนด์มาร์กห้ามพลาด: พระนครคีรี (เขาวัง), ถ้ำเขาหลวง (แสงสวรรค์), และหาดชะอำครับ 🌊',
            emotion: 'excited',
            quick_options: ['แผนที่เขาวัง', 'เวลาแสงสวรรค์ถ้ำเขาหลวง']
        },
        'open_palm': {
            gesture_name: 'สวัสดี / ทักทาย (Open Palm)',
            gesture_emoji: '🖐️',
            meaning: 'การทักทายสวัสดี และเปิดรับการสื่อสาร',
            reply: 'สวัสดีครับ! ผมคือน้องเพชร AI Smart Guide ยินดีต้อนรับผู้มีความบกพร่องทางการได้ยินทุกท่าน มีอะไรให้ผมช่วยเหลือเลือกหรือทำภาษามือได้เลยครับ 😊',
            emotion: 'smile',
            quick_options: ['แนะนำสถานที่เที่ยว', 'แนะนำหลักสูตรอาชีวะ', 'จุดถ่ายรูปสวย']
        },
        'pointing': {
            gesture_name: 'แนะแนวเรียนต่ออาชีวะ (Pointing Up)',
            gesture_emoji: '☝️',
            meaning: 'การชี้เป้าหมาย มุ่งสู่อนาคต และการศึกษาพัฒนาตนเอง',
            reply: 'วิทยาลัยอาชีวศึกษาเพชรบุรี มุ่งมั่นพัฒนาผู้เรียนด้วยนวัตกรรมและเทคโนโลยีดิจิทัล มี 9 แผนกวิชายอดนิยม พร้อมสนับสนุนการเรียนรู้ที่เท่าเทียมสำหรับทุกคนครับ 🎓',
            emotion: 'thinking',
            quick_options: ['สาขาเทคโนโลยีธุรกิจดิจิทัล', 'สาขาอาหารและโภชนาการ']
        },
        'fist': {
            gesture_name: 'อาหารและขนมหวานเมืองเพชร (Fist)',
            gesture_emoji: '✊',
            meaning: 'พลัง ความอิ่มอร่อย และของกินขึ้นชื่อ',
            reply: 'เพชรบุรีเมืองสร้างสรรค์ด้านอาหารของยูเนสโก (City of Gastronomy)! อย่าลืมชิมขนมหม้อแกงเตาฟืน ก๋วยเตี๋ยวน้ำแดง และข้าวแช่ชาววังนะครับ 🍧',
            emotion: 'happy',
            quick_options: ['ร้านขนมหม้อแกงเจ้าดัง', 'ก๋วยเตี๋ยวน้ำแดงสูตรโบราณ']
        },
        'shaka': {
            gesture_name: 'ขอความช่วยเหลือฉุกเฉิน (Help / Call)',
            gesture_emoji: '🤙',
            meaning: 'ต้องการความช่วยเหลือ ติดต่อเจ้าหน้าที่ หรือบริการพิเศษ',
            reply: 'รับทราบครับ! หากต้องการความช่วยเหลือเร่งด่วน เจ้าหน้าที่วิทยาลัยอาชีวศึกษาเพชรบุรีและฝ่ายประชาสัมพันธ์พร้อมอำนวยความสะดวกให้ท่านทันทีครับ 🚨',
            emotion: 'surprised',
            quick_options: ['ติดต่อห้องประชาสัมพันธ์', 'ตำแหน่งห้องพยาบาล', 'ห้องน้ำสำหรับผู้พิการ']
        }
    };
    return dict[key] || dict['open_palm'];
}
