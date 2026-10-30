/**
 * Nong Phet AI Smart Guide - Emotion & Vision Tracking Controller (JavaScript)
 * For Raspberry Pi 5 Secondary Head Screen (2.4" - 3.5" Display)
 * 
 * Features:
 * 1. Interactive Mouse & Touch Gaze Tracking (มองตามเมาส์/การสัมผัสแบบ 3D Parallax)
 * 2. Camera Motion & Person Tracking (มองตามคนเดินผ่านกล้องแบบอัตโนมัติ)
 * 3. Autonomous Greeting on Eye Contact (ทักทายอัตโนมัติเมื่อคนเดินมาสบตา 1.5 วินาที)
 * 4. Real-time Audio Analyser Lip-Sync (ปากขยับตามคลื่นเสียงจริง)
 * 5. Idle Sleep Mode & Wakeup Reaction (โหมดหลับพักผ่อนเมื่อไม่มีคนใช้งาน)
 * 6. Cross-screen Gaze & State Synchronization via SSE & BroadcastChannel
 */

let currentEmotion = 'idle';
let blinkInterval = null;
let eventSource = null;

// Gaze Tracking Variables
let currentGazeX = 0;
let currentGazeY = 0;
let targetGazeX = 0;
let targetGazeY = 0;
let lastInteractionTime = performance.now();
let isMouseActive = false;
let mouseTimeout = null;

// Camera Vision Tracking Variables
let isCameraTracking = false;
let cameraStream = null;
let trackingInterval = null;
let prevFrameData = null;
let showPipPreview = false;
let faceDetector = null;

// Sign Language (TSL) Detection Variables
let isSignLanguageMode = false;
let emotionSignHands = null;
let emotionSignHandsBusy = false;
let emotionSignLastDetectedGesture = null;
let emotionSignHoldStartTime = 0;
let emotionSignLastTriggeredGesture = null;
let emotionSignLastTriggerTime = 0;
const EMOTION_SIGN_HOLD_DURATION_MS = 600; // Hold steady for 600ms to trigger

// Autonomous Greeting & Eye Contact
let eyeContactStartTime = null;
let lastGreetingTriggerTime = 0;

// Idle Sleep Timer
let sleepCheckInterval = null;

// Theme Matrix Variables
const THEMES = ['cyan', 'emerald', 'rose', 'amber', 'purple'];
let currentTheme = localStorage.getItem('nongphet_face_theme') || 'cyan';

// Procedural Sci-Fi Synthesizer Sound Engine (Web Audio API)
let sfxEnabled = true;
let sfxAudioCtx = null;

function getSfxAudioContext() {
    if (!sfxAudioCtx) {
        const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
        if (AudioCtxClass) {
            sfxAudioCtx = new AudioCtxClass();
        }
    }
    if (sfxAudioCtx && sfxAudioCtx.state === 'suspended') {
        sfxAudioCtx.resume();
    }
    return sfxAudioCtx;
}

function playSfx(type) {
    if (!sfxEnabled) return;
    try {
        const ctx = getSfxAudioContext();
        if (!ctx) return;
        const now = ctx.currentTime;

        if (type === 'happy' || type === 'chime') {
            const freqs = [523.25, 659.25, 783.99, 1046.50];
            freqs.forEach((f, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(f, now + i * 0.07);
                gain.gain.setValueAtTime(0.08, now + i * 0.07);
                gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.07 + 0.25);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + i * 0.07);
                osc.stop(now + i * 0.07 + 0.26);
            });
        } else if (type === 'love' || type === 'blush') {
            const notes = [659.25, 830.61, 987.77, 1318.51, 1567.98];
            notes.forEach((f, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(f, now + i * 0.05);
                gain.gain.setValueAtTime(0.07, now + i * 0.05);
                gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.05 + 0.3);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + i * 0.05);
                osc.stop(now + i * 0.05 + 0.32);
            });
        } else if (type === 'scanner') {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(880, now);
            osc.frequency.exponentialRampToValueAtTime(220, now + 0.35);
            gain.gain.setValueAtTime(0.05, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.36);
        } else if (type === 'thinking') {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(440, now);
            osc.frequency.setValueAtTime(554.37, now + 0.08);
            osc.frequency.setValueAtTime(659.25, now + 0.16);
            gain.gain.setValueAtTime(0.04, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.3);
        } else if (type === 'wink' || type === 'pop') {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(400, now);
            osc.frequency.exponentialRampToValueAtTime(1200, now + 0.12);
            gain.gain.setValueAtTime(0.09, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.16);
        } else if (type === 'wake') {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(220, now);
            osc.frequency.exponentialRampToValueAtTime(880, now + 0.4);
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.46);
        } else if (type === 'click' || type === 'tap') {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(1400, now);
            gain.gain.setValueAtTime(0.03, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.05);
        } else if (type === 'purr') {
            const freqs = [330, 392, 440, 523.25, 659.25, 783.99];
            freqs.forEach((f, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(f, now + i * 0.07);
                gain.gain.setValueAtTime(0.07, now + i * 0.07);
                gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.07 + 0.22);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + i * 0.07);
                osc.stop(now + i * 0.07 + 0.24);
            });
        } else if (type === 'flutter') {
            const freqs = [659.25, 880, 1174.66, 880, 1318.51];
            freqs.forEach((f, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(f, now + i * 0.04);
                gain.gain.setValueAtTime(0.06, now + i * 0.04);
                gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.04 + 0.12);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + i * 0.04);
                osc.stop(now + i * 0.04 + 0.14);
            });
        } else if (type === 'surprised') {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(350, now);
            osc.frequency.exponentialRampToValueAtTime(1400, now + 0.18);
            gain.gain.setValueAtTime(0.09, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.24);
        }
    } catch (e) {}
}

function toggleSfx() {
    sfxEnabled = !sfxEnabled;
    const btn = document.getElementById('btnToggleSfx');
    if (btn) {
        btn.innerHTML = sfxEnabled ? '<i class="fa-solid fa-volume-high"></i>' : '<i class="fa-solid fa-volume-xmark"></i>';
        btn.className = sfxEnabled ? 'dock-btn text-cyan-300' : 'dock-btn text-slate-500 opacity-60';
        btn.title = sfxEnabled ? 'เสียงเอฟเฟกต์: เปิด (กด M เพื่อปิด)' : 'เสียงเอฟเฟกต์: ปิด (กด M เพื่อเปิด)';
    }
    if (sfxEnabled) playSfx('click');
    showVoiceSubtitle(sfxEnabled ? '🔊 เปิดเสียงเอฟเฟกต์หุ่นยนต์แล้ว' : '🔇 ปิดเสียงเอฟเฟกต์แล้ว', 2000);
}

function cycleTheme() {
    let idx = THEMES.indexOf(currentTheme);
    idx = (idx + 1) % THEMES.length;
    setTheme(THEMES[idx]);
}

function setTheme(themeName) {
    currentTheme = themeName;
    localStorage.setItem('nongphet_face_theme', themeName);
    if (STAGE) {
        THEMES.forEach(t => STAGE.classList.remove(`theme-${t}`));
        STAGE.classList.add(`theme-${themeName}`);
    }
    playSfx('click');
    showVoiceSubtitle(`🎨 สลับธีมสีไฟนีออน: ${themeName.toUpperCase()}`, 2000);
}

// Cross-window BroadcastChannel for zero-latency sync
const lipSyncBroadcast = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('nongphet_sync') : null;

const STAGE = document.querySelector('.robot-face-stage');
const STATUS_BADGE = document.getElementById('statusBadge');
const STATUS_TEXT = document.getElementById('statusText');
const TRACKING_VIDEO = document.getElementById('trackingVideo');
const TRACKING_CANVAS = document.getElementById('trackingCanvas');
const PIP_CANVAS = document.getElementById('pipCanvas');
const CAM_INDICATOR_DOT = document.getElementById('camIndicatorDot');
const CAM_STATUS_TEXT = document.getElementById('camStatusText');

const EMOTION_LABELS = {
    'smile': 'ยิ้มโค้งพิมพ์เขียว (⌒‿⌒)',
    'squint': 'ยิ้มตาหยี (>‿<)',
    'excited': 'ตื่นเต้น ประกายดาว (✦‿✦)',
    'surprised': 'ตกใจ/ตรวจพบ (O‿O)',
    'idle': 'น้องเพชรพร้อมให้บริการ',
    'listening': 'กำลังฟังเสียง...',
    'thinking': 'กำลังคิดคำตอบ...',
    'speaking': 'กำลังพูดคุย...',
    'happy': 'มีความสุข ยินดีต้อนรับ',
    'love': 'น้องเพชรเขินจังเลยครับ 💖',
    'scanner': 'กำลังสแกนวิเคราะห์ข้อมูล ⚡',
    'wink': 'สวัสดีครับ 😉',
    'sleeping': 'กำลังหลับพักผ่อน (Sleep Mode)'
};

document.addEventListener('DOMContentLoaded', () => {
    setTheme(currentTheme);
    applyEmotion('idle');
    startOrganicBlinking();
    initEventStream();
    setupKeyListeners();
    setupMouseGazeTracking();
    startGazeAnimationLoop();
    checkFaceDetectorAPI();
    initLipSyncReceiver();
    startIdleSleepWatcher();
    initDirectVoiceEngine();
    initHudClock();

    // ปลดล็อค AudioContext และ Audio Element เมื่อมีการสัมผัสหรือคลิกครั้งแรก
    function primeAudioPlayback() {
        getSfxAudioContext();
        const a = document.getElementById('emotionAudioPlayer');
        if (a) {
            if (!a.src) a.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            a.play().then(() => {
                a.pause();
                a.currentTime = 0;
            }).catch(() => {});
        }
    }
    window.addEventListener('pointerdown', primeAudioPlayback, { once: true });
    window.addEventListener('touchstart', primeAudioPlayback, { once: true });
    window.addEventListener('keydown', primeAudioPlayback, { once: true });
});

let emotionSafetyWatchdog = null;

/**
 * สลับสถานะอารมณ์บนใบหน้า
 */
function applyEmotion(emotionName) {
    if (!STAGE) return;
    currentEmotion = emotionName;

    // Safety Watchdog: ป้องกันค้างหน้า thinking หรือ speaking นานเกินจริง
    clearTimeout(emotionSafetyWatchdog);
    if (emotionName === 'thinking') {
        emotionSafetyWatchdog = setTimeout(() => {
            if (currentEmotion === 'thinking') {
                console.warn('⚠️ [Watchdog] Thinking เกิน 7 วินาที -> รีเซ็ตกลับเป็น idle อัตโนมัติ');
                applyEmotion('idle');
            }
        }, 7000);
    } else if (emotionName === 'speaking') {
        emotionSafetyWatchdog = setTimeout(() => {
            if (currentEmotion === 'speaking') {
                console.warn('⚠️ [Watchdog] Speaking เกิน 20 วินาที -> รีเซ็ตกลับเป็น idle');
                applyEmotion('idle');
            }
        }, 20000);
    }

    // Reset old state classes while preserving active theme
    STAGE.className = `robot-face-stage theme-${currentTheme} relative w-full h-full flex flex-col items-center justify-center overflow-hidden`;
    STAGE.classList.add(`state-${emotionName}`);

    // Manage breathing class on face container
    const faceContainer = document.querySelector('.face-container');
    if (faceContainer) {
        if (emotionName === 'idle' || emotionName === 'smile') {
            faceContainer.classList.add('breathing');
        } else {
            faceContainer.classList.remove('breathing');
        }
    }

    // Play subtle reactive SFX
    if (emotionName === 'happy' || emotionName === 'smile' || emotionName === 'squint' || emotionName === 'excited') playSfx('happy');
    else if (emotionName === 'love') playSfx('love');
    else if (emotionName === 'scanner') playSfx('scanner');
    else if (emotionName === 'thinking') playSfx('thinking');
    else if (emotionName === 'surprised') playSfx('surprised');
    else if (emotionName === 'wink') playSfx('wink');

    // Update status text badge
    if (STATUS_TEXT) {
        STATUS_TEXT.textContent = EMOTION_LABELS[emotionName] || emotionName;
    }
    if (STATUS_BADGE) {
        STATUS_BADGE.classList.remove('opacity-0');
        clearTimeout(STATUS_BADGE._hideTimer);
        STATUS_BADGE._hideTimer = setTimeout(() => {
            if (currentEmotion === 'idle') {
                STATUS_BADGE.classList.add('opacity-0');
            }
        }, 3000);
    }

    // Highlight active emotion button in quick dock
    document.querySelectorAll('#quickEmotionDock .dock-btn').forEach(btn => {
        btn.classList.remove('ring-2', 'ring-cyan-400', 'bg-cyan-500/30', 'scale-110');
        const clickAttr = btn.getAttribute('onclick') || '';
        if (clickAttr.includes(`'${emotionName}'`)) {
            btn.classList.add('ring-2', 'ring-cyan-400', 'bg-cyan-500/30', 'scale-110');
        }
    });
}

/**
 * ปลุกน้องเพชรให้ตื่นจากโหมดหลับพักผ่อน
 */
function wakeUpFromSleep() {
    if (currentEmotion === 'sleeping') {
        playSfx('wake');
        applyEmotion('surprised');
        setTimeout(() => {
            applyEmotion('happy');
            setTimeout(() => {
                if (currentEmotion === 'happy') applyEmotion('idle');
            }, 2500);
        }, 600);
    }
}

/**
 * ตรวจจับความไม่มีการใช้งานเพื่อเข้าสู่โหมด Sleep (2.5 นาที)
 */
function startIdleSleepWatcher() {
    sleepCheckInterval = setInterval(() => {
        const now = performance.now();
        // ถ้าอยู่ในโหมด idle และไม่มีการโต้ตอบเกิน 2.5 นาที (150,000 ms)
        if (currentEmotion === 'idle' && !isMouseActive && (now - lastInteractionTime > 150000)) {
            console.log('💤 [Sleep Engine] เข้าสู่โหมดพักผ่อนประหยัดพลังงาน');
            applyEmotion('sleeping');
        }
    }, 2000);
}

/**
 * แอนิเมชันกะพริบตาเป็นระยะเมื่ออยู่ในโหมด Idle
 */
function startOrganicBlinking() {
    function scheduleNextBlink() {
        const nextDelay = Math.random() * 3500 + 2500; // 2.5 - 6 วินาที
        blinkInterval = setTimeout(() => {
            if (currentEmotion === 'idle') {
                triggerBlink();
            }
            scheduleNextBlink();
        }, nextDelay);
    }
    scheduleNextBlink();
}

function triggerBlink() {
    if (!STAGE || currentEmotion !== 'idle') return;
    STAGE.classList.add('blink');
    setTimeout(() => {
        STAGE.classList.remove('blink');
        if (Math.random() > 0.65) {
            setTimeout(() => {
                if (currentEmotion === 'idle') {
                    STAGE.classList.add('blink');
                    setTimeout(() => STAGE.classList.remove('blink'), 120);
                }
            }, 180);
        }
    }, 150);
}

// =============================================================================
// ระบบมองตามเมาส์และการสัมผัส (Interactive Mouse & Touch Gaze Tracking)
// =============================================================================
// =============================================================================
// ระบบมองตามเมาส์และการสัมผัส (Interactive Mouse, Touch, & 3D Parallax Tracking)
// =============================================================================
function spawnTouchRipple(x, y) {
    if (!x || !y) return;
    const ripple = document.createElement('div');
    ripple.className = 'touch-ripple';
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;
    document.body.appendChild(ripple);
    setTimeout(() => {
        if (ripple.parentElement) ripple.remove();
    }, 600);
}

function triggerHaptic(ms = 15) {
    if (typeof navigator !== 'undefined' && navigator.vibrate) {
        try { navigator.vibrate(ms); } catch (err) {}
    }
}

function setupMouseGazeTracking() {
    let touchStartX = 0;
    let touchStartY = 0;
    let touchStartTime = 0;

    function handlePointerMove(clientX, clientY) {
        wakeUpFromSleep();
        const width = window.innerWidth;
        const height = window.innerHeight;

        const normX = ((clientX - width / 2) / (width / 2));
        const normY = ((clientY - height / 2) / (height / 2));

        targetGazeX = Math.max(-1.0, Math.min(1.0, normX));
        targetGazeY = Math.max(-1.0, Math.min(1.0, normY));

        isMouseActive = true;
        lastInteractionTime = performance.now();

        document.body.classList.remove('cursor-none');
        clearTimeout(mouseTimeout);
        mouseTimeout = setTimeout(() => {
            isMouseActive = false;
            document.body.classList.add('cursor-none');
        }, 3200);
    }

    // Pointer move (works seamlessly across mouse, stylus, trackpad)
    window.addEventListener('pointermove', (e) => {
        handlePointerMove(e.clientX, e.clientY);
    }, { passive: true });

    // Tap/Click anywhere on screen to spawn ripple & look directly at touch point
    window.addEventListener('pointerdown', (e) => {
        wakeUpFromSleep();
        handlePointerMove(e.clientX, e.clientY);

        // Avoid triggering general ripple when clicking on buttons or dock
        if (!e.target.closest('button') && !e.target.closest('.cheek') && !e.target.closest('.cyber-eye') && !e.target.closest('.face-center-sensor') && !e.target.closest('.cyber-mouth')) {
            spawnTouchRipple(e.clientX, e.clientY);
            playSfx('tap');
            triggerHaptic(12);
        }
    });

    // Touch swipe gestures on touchscreen
    window.addEventListener('touchstart', (e) => {
        if (e.touches && e.touches.length > 0) {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchStartTime = performance.now();
            handlePointerMove(touchStartX, touchStartY);
        }
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
        if (e.touches && e.touches.length > 0) {
            handlePointerMove(e.touches[0].clientX, e.touches[0].clientY);
        }
    }, { passive: true });

    window.addEventListener('touchend', (e) => {
        if (!e.changedTouches || e.changedTouches.length === 0) return;
        const touchEndX = e.changedTouches[0].clientX;
        const touchEndY = e.changedTouches[0].clientY;
        const deltaX = touchEndX - touchStartX;
        const deltaY = touchEndY - touchStartY;
        const duration = performance.now() - touchStartTime;

        // Swipe threshold: > 45px within 450ms
        if (duration < 450 && (Math.abs(deltaX) > 45 || Math.abs(deltaY) > 45)) {
            triggerHaptic(20);
            if (Math.abs(deltaY) > Math.abs(deltaX)) {
                if (deltaY < -45) {
                    setEmotionLocally('happy');
                    showVoiceSubtitle('✨ น้องเพชรรู้สึกสดชื่นและมีความสุขมากครับ!', 2500);
                } else if (deltaY > 45) {
                    setEmotionLocally('sleeping');
                }
            } else {
                if (deltaX > 45) {
                    setEmotionLocally('love');
                    showVoiceSubtitle('💖 ส่งหัวใจให้น้องเพชร!', 2500);
                } else if (deltaX < -45) {
                    setEmotionLocally('wink');
                    showVoiceSubtitle('😉 ยิ้มทักทาย!', 2500);
                }
            }
        }
    }, { passive: true });

    window.addEventListener('mouseleave', () => {
        isMouseActive = false;
        targetGazeX = 0;
        targetGazeY = 0;
    });
}

/**
 * Animation Loop อัปเดตพิกัดลูกตา 3D Parallax และ Micro-Saccades (Silky-Smooth 60/120 FPS)
 */
let nextSaccadeTime = performance.now() + 2500;
let saccadeOffsetX = 0;
let saccadeOffsetY = 0;

function startGazeAnimationLoop() {
    const faceContainer = document.querySelector('.face-container');
    const ringOuter = document.querySelector('.ring-outer');
    const ringInner = document.querySelector('.ring-inner');

    function animate() {
        const now = performance.now();

        // 1. Natural Micro-Saccades (Eye Darts) when idle
        if (!isMouseActive && !isCameraTracking && (now - lastInteractionTime > 2500)) {
            if (now > nextSaccadeTime) {
                if (Math.random() > 0.4) {
                    saccadeOffsetX = (Math.random() - 0.5) * 0.45;
                    saccadeOffsetY = (Math.random() - 0.5) * 0.3;
                } else {
                    saccadeOffsetX = 0;
                    saccadeOffsetY = 0;
                }
                nextSaccadeTime = now + Math.random() * 2500 + 1500;
            }
            targetGazeX += (saccadeOffsetX - targetGazeX) * 0.08;
            targetGazeY += (saccadeOffsetY - targetGazeY) * 0.08;
        }

        // 2. Critically Damped Smoothing (0.18 for instant, natural reactivity)
        currentGazeX += (targetGazeX - currentGazeX) * 0.18;
        currentGazeY += (targetGazeY - currentGazeY) * 0.18;

        const eyeOffsetMax = Math.min(28, window.innerWidth * 0.04);
        const pupilOffsetMax = Math.min(18, window.innerWidth * 0.025);

        const gazePixelX = currentGazeX * eyeOffsetMax;
        const gazePixelY = currentGazeY * eyeOffsetMax;
        const pupilPixelX = currentGazeX * pupilOffsetMax;
        const pupilPixelY = currentGazeY * pupilOffsetMax;

        if (STAGE) {
            STAGE.style.setProperty('--gaze-x', `${gazePixelX.toFixed(2)}px`);
            STAGE.style.setProperty('--gaze-y', `${gazePixelY.toFixed(2)}px`);
            STAGE.style.setProperty('--pupil-x', `${pupilPixelX.toFixed(2)}px`);
            STAGE.style.setProperty('--pupil-y', `${pupilPixelY.toFixed(2)}px`);
        }

        // 3. 3D Head Tilt Parallax & Organic Curiosity Roll on Face Container
        if (faceContainer) {
            if (currentEmotion === 'sleeping') {
                faceContainer.style.transform = 'perspective(700px) translateY(16px) rotateX(12deg) scale(0.96)';
            } else if (faceContainer.classList.contains('is-petting')) {
                // Gentle purr/flutter wobble when head is being petted
                const purrWobble = Math.sin(now / 80) * 1.5;
                faceContainer.style.transform = `perspective(700px) translateY(-8px) scale(1.05) rotateZ(${purrWobble.toFixed(2)}deg)`;
            } else {
                const tiltY = (currentGazeX * 11).toFixed(2);
                const tiltX = (-currentGazeY * 9).toFixed(2);
                // Inquisitive head cant / roll (rotateZ) - tilts naturally sideways when gazing or thinking
                const baseTiltZ = (currentGazeX * 4.2);
                const thinkingRoll = (currentEmotion === 'thinking' ? 5.8 : 0);
                const tiltZ = (baseTiltZ + thinkingRoll).toFixed(2);
                faceContainer.style.transform = `perspective(700px) rotateY(${tiltY}deg) rotateX(${tiltX}deg) rotateZ(${tiltZ}deg)`;
            }
        }

        // 4. 2D Depth Parallax on Ambient Orbital Rings
        if (ringOuter) {
            ringOuter.style.transform = `translate(calc(-50% + ${(-currentGazeX * 14).toFixed(1)}px), calc(-50% + ${(-currentGazeY * 14).toFixed(1)}px))`;
        }
        if (ringInner) {
            ringInner.style.transform = `translate(calc(-50% + ${(-currentGazeX * 7).toFixed(1)}px), calc(-50% + ${(-currentGazeY * 7).toFixed(1)}px))`;
        }

        requestAnimationFrame(animate);
    }
    requestAnimationFrame(animate);
}

// =============================================================================
// ระบบกล้องมองตามคนเดินผ่าน & ทักทายอัตโนมัติเมื่อสบตา (Eye Contact Greeting)
// =============================================================================
function checkFaceDetectorAPI() {
    if ('FaceDetector' in window) {
        try {
            faceDetector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 1 });
            console.log('✨ [Vision Engine] ตรวจพบ Hardware FaceDetector API พร้อมใช้งาน');
        } catch (e) {
            faceDetector = null;
        }
    }
}

async function toggleCameraTracking() {
    if (isCameraTracking) {
        stopCameraTracking();
    } else {
        await startCameraTracking();
    }
}

async function startCameraTracking() {
    try {
        const constraints = {
            video: {
                width: { ideal: 320 },
                height: { ideal: 240 },
                facingMode: 'user'
            },
            audio: false
        };

        cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
        if (TRACKING_VIDEO) {
            TRACKING_VIDEO.srcObject = cameraStream;
            await TRACKING_VIDEO.play();
        }

        isCameraTracking = true;
        if (CAM_INDICATOR_DOT) {
            CAM_INDICATOR_DOT.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse';
        }
        if (CAM_STATUS_TEXT) {
            CAM_STATUS_TEXT.textContent = 'กล้องมองตามคน: เปิดทำงาน';
        }
        const btnToggleCam = document.getElementById('btnToggleCam');
        if (btnToggleCam) {
            btnToggleCam.className = 'px-2 py-1 bg-rose-700 hover:bg-rose-600 text-white rounded font-bold';
            btnToggleCam.innerHTML = '<i class="fa-solid fa-video-slash"></i> ปิดกล้องตามคน';
        }

        console.log('🎥 [Vision Engine] เริ่มต้นกล้องมองตามคนเรียบร้อยแล้ว');
        startVisionProcessing();
    } catch (err) {
        console.error('ไม่สามารถเปิดกล้องได้:', err);
        alert('ไม่สามารถเข้าถึงกล้องเว็บแคมได้ กรุณาตรวจสอบสิทธิ์การใช้งานกล้องในเบราว์เซอร์');
    }
}

function stopCameraTracking() {
    isCameraTracking = false;
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
    }
    if (trackingInterval) {
        clearInterval(trackingInterval);
        trackingInterval = null;
    }
    if (CAM_INDICATOR_DOT) {
        CAM_INDICATOR_DOT.className = 'w-2.5 h-2.5 rounded-full bg-slate-500';
    }
    if (CAM_STATUS_TEXT) {
        CAM_STATUS_TEXT.textContent = 'กล้องมองตามคน: ปิด';
    }
    const btnToggleCam = document.getElementById('btnToggleCam');
    if (btnToggleCam) {
        btnToggleCam.className = 'px-2 py-1 bg-emerald-800 hover:bg-emerald-700 text-white rounded font-bold';
        btnToggleCam.innerHTML = '<i class="fa-solid fa-video"></i> เปิดกล้องตามคน';
    }
    if (isSignLanguageMode) {
        isSignLanguageMode = false;
        const signDot = document.getElementById('signIndicatorDot');
        const signText = document.getElementById('signStatusText');
        const btnDock = document.getElementById('btnDockSign');
        const btnToggle = document.getElementById('btnToggleSign');
        if (signDot) signDot.className = 'w-2.5 h-2.5 rounded-full bg-slate-500';
        if (signText) signText.textContent = 'ตรวจจับภาษามือ: ปิด';
        if (btnDock) {
            btnDock.classList.remove('ring-2', 'ring-emerald-400', 'bg-emerald-500/30', 'scale-110');
            btnDock.title = 'เปิด/ปิด ตรวจจับภาษามือ (หรือกด S)';
        }
        if (btnToggle) {
            btnToggle.className = 'px-2 py-1 bg-cyan-700 hover:bg-cyan-600 text-white rounded font-bold';
            btnToggle.innerHTML = '<i class="fa-solid fa-hands-asl-interpreting"></i> ตรวจจับภาษามือ';
        }
    }
    prevFrameData = null;
}

let lastVisitorPingTime = 0;
function pingVisitorDetected() {
    const now = performance.now();
    if (now - lastVisitorPingTime > 45000) { // Throttle: 1 ping per 45 วินาที
        lastVisitorPingTime = now;
        fetch('/api/analytics/ping_visitor', { method: 'POST' }).catch(() => {});
    }
}

/**
 * ลูปประมวลผลการตรวจจับคน & ทักทายอัตโนมัติเมื่อสบตา
 */
function startVisionProcessing() {
    if (!TRACKING_CANVAS || !TRACKING_VIDEO) return;
    const ctx = TRACKING_CANVAS.getContext('2d', { willReadFrequently: true });
    const pipCtx = PIP_CANVAS ? PIP_CANVAS.getContext('2d') : null;

    const w = TRACKING_CANVAS.width;   // 160 px
    const h = TRACKING_CANVAS.height;  // 120 px

    trackingInterval = setInterval(async () => {
        if (!isCameraTracking || TRACKING_VIDEO.readyState < 2) return;

        ctx.drawImage(TRACKING_VIDEO, 0, 0, w, h);
        const currentFrame = ctx.getImageData(0, 0, w, h);

        if (showPipPreview && pipCtx && PIP_CANVAS) {
            PIP_CANVAS.width = w;
            PIP_CANVAS.height = h;
            pipCtx.drawImage(TRACKING_VIDEO, 0, 0, w, h);
        }

        // 0. ระบบตรวจจับภาษามือ TSL (MediaPipe Hands Frame Dispatch)
        if (isSignLanguageMode && emotionSignHands && !emotionSignHandsBusy && TRACKING_VIDEO.videoWidth > 0) {
            emotionSignHandsBusy = true;
            emotionSignHands.send({ image: TRACKING_VIDEO })
                .catch(() => {})
                .finally(() => { emotionSignHandsBusy = false; });
        }

        if (isMouseActive) return;

        let detectedPersonInCenter = false;

        // 1. ลองใช้ FaceDetector API
        if (faceDetector) {
            try {
                const faces = await faceDetector.detect(TRACKING_VIDEO);
                if (faces && faces.length > 0) {
                    wakeUpFromSleep();
                    pingVisitorDetected();
                    const face = faces[0].boundingBox;
                    const faceCenterX = (TRACKING_VIDEO.videoWidth - (face.x + face.width / 2)) / TRACKING_VIDEO.videoWidth;
                    const faceCenterY = (face.y + face.height / 2) / TRACKING_VIDEO.videoHeight;

                    targetGazeX = (faceCenterX - 0.5) * 2.2;
                    targetGazeY = (faceCenterY - 0.5) * 2.0;
                    lastInteractionTime = performance.now();

                    if (Math.abs(faceCenterX - 0.5) < 0.25) {
                        detectedPersonInCenter = true;
                    }

                    if (pipCtx) {
                        pipCtx.strokeStyle = '#00f0ff';
                        pipCtx.lineWidth = 2;
                        pipCtx.strokeRect(face.x, face.y, face.width, face.height);
                    }
                }
            } catch (e) {}
        }

        // 2. อัลกอริทึม Optical Motion Difference Centroid
        if (!detectedPersonInCenter && prevFrameData) {
            let motionPixels = 0;
            let sumX = 0;
            let sumY = 0;

            const curr = currentFrame.data;
            const prev = prevFrameData.data;
            const totalPixels = w * h;

            for (let i = 0; i < totalPixels; i++) {
                const idx = i * 4;
                const rDiff = Math.abs(curr[idx] - prev[idx]);
                const gDiff = Math.abs(curr[idx + 1] - prev[idx + 1]);
                const bDiff = Math.abs(curr[idx + 2] - prev[idx + 2]);
                const diff = (rDiff + gDiff + bDiff) / 3;

                if (diff > 30) {
                    const px = i % w;
                    const py = Math.floor(i / w);
                    sumX += px;
                    sumY += py;
                    motionPixels++;
                }
            }

            if (motionPixels > 250) {
                wakeUpFromSleep();
                const avgX = sumX / motionPixels;
                const avgY = sumY / motionPixels;

                const normX = ((w - avgX) - w / 2) / (w / 2);
                const normY = (avgY - h / 2) / (h / 2);

                targetGazeX = Math.max(-1.0, Math.min(1.0, normX * 1.5));
                targetGazeY = Math.max(-1.0, Math.min(1.0, normY * 1.3));
                lastInteractionTime = performance.now();

                if (Math.abs(normX) < 0.35 && motionPixels > 450) {
                    detectedPersonInCenter = true;
                }

                if (showPipPreview && pipCtx) {
                    pipCtx.strokeStyle = '#38bdf8';
                    pipCtx.fillStyle = '#00f0ff';
                    pipCtx.beginPath();
                    pipCtx.arc(avgX, avgY, 8, 0, Math.PI * 2);
                    pipCtx.fill();
                    pipCtx.stroke();
                }

                // ตรวจจับท่าทางมือไร้สัมผัส (Touchless Air Gestures: Wave 👋 & Swipe ↔️)
                detectAirGestures(avgX, avgY, motionPixels, w, h);
            }
        }

        // 3. ตรวจจับการสบตาต่อเนื่อง > 1.5 วินาที เพื่อทักทายอัตโนมัติ (Autonomous Greeting)
        const now = performance.now();
        if (detectedPersonInCenter) {
            if (eyeContactStartTime === null) {
                eyeContactStartTime = now;
            } else if (now - eyeContactStartTime > 1400) {
                // ยืนสบตาเกิน 1.4 วินาที และพ้นระยะ Cool-down (40 วินาที)
                if (now - lastGreetingTriggerTime > 40000) {
                    lastGreetingTriggerTime = now;
                    eyeContactStartTime = null;
                    console.log('👋 [Autonomous Greet] ตรวจพบการสบตาตรงหน้า! เริ่มต้นทักทายอัตโนมัติ');
                    triggerAutonomousGreeting();
                }
            }
        } else {
            eyeContactStartTime = null;
        }

        prevFrameData = currentFrame;
    }, 75); // ปรับจาก 45ms เป็น 75ms เพื่อลดภาระ CPU และทำให้เบราว์เซอร์ลื่นไหลขึ้น
}

// -----------------------------------------------------------------------------
// ระบบตรวจจับท่าทางมือไร้สัมผัส (Touchless Air Gesture Engine)
// -----------------------------------------------------------------------------
let gestureHistory = [];
let lastGestureTriggerTime = 0;

function detectAirGestures(x, y, pixels, w, h) {
    const now = performance.now();
    if (now - lastGestureTriggerTime < 1800) return; // Cool-down 1.8s

    gestureHistory.push({ x: x, y: y, time: now });
    if (gestureHistory.length > 10) gestureHistory.shift();

    if (gestureHistory.length >= 6) {
        // ตรวจสอบการโบกมือ (Wave 👋) ในช่วงบนของจอ
        if (y < h * 0.75) {
            let reversals = 0;
            let lastDir = 0;
            for (let i = 1; i < gestureHistory.length; i++) {
                const dx = gestureHistory[i].x - gestureHistory[i - 1].x;
                if (Math.abs(dx) > 4) {
                    const dir = dx > 0 ? 1 : -1;
                    if (lastDir !== 0 && dir !== lastDir) {
                        reversals++;
                    }
                    lastDir = dir;
                }
            }

            if (reversals >= 2) {
                lastGestureTriggerTime = now;
                gestureHistory = [];
                onAirGestureDetected('wave');
                return;
            }
        }

        // ตรวจสอบการปัดมือซ้าย/ขวา (Swipe ↔️)
        const first = gestureHistory[0];
        const last = gestureHistory[gestureHistory.length - 1];
        const totalDx = last.x - first.x;
        const totalDt = last.time - first.time;

        if (totalDt < 400 && Math.abs(totalDx) > w * 0.35) {
            lastGestureTriggerTime = now;
            const swipeDir = totalDx > 0 ? 'left' : 'right';
            gestureHistory = [];
            onAirGestureDetected('swipe', swipeDir);
            return;
        }
    }
}

function onAirGestureDetected(gesture, param = null) {
    console.log(`✨ [Air Gesture] ตรวจพบท่าทาง: ${gesture} ${param || ''}`);
    wakeUpFromSleep();

    if (gesture === 'wave') {
        applyEmotion('wink');
        setTimeout(() => applyEmotion('happy'), 600);
        setTimeout(() => { if (currentEmotion === 'happy') applyEmotion('idle'); }, 2500);

        if (STATUS_TEXT) STATUS_TEXT.textContent = '👋 สวัสดีครับ! (ตรวจพบการโบกมือ)';
        if (STATUS_BADGE) STATUS_BADGE.classList.remove('opacity-0');

        if (lipSyncBroadcast) {
            lipSyncBroadcast.postMessage({ type: 'gesture', gesture: 'wave' });
        }
    } else if (gesture === 'swipe') {
        applyEmotion('surprised');
        setTimeout(() => applyEmotion('idle'), 800);

        if (STATUS_TEXT) STATUS_TEXT.textContent = `↔️ ปัดมือ: ${param === 'left' ? 'ย้อนกลับ' : 'ถัดไป'}`;
        if (STATUS_BADGE) STATUS_BADGE.classList.remove('opacity-0');

        if (lipSyncBroadcast) {
            lipSyncBroadcast.postMessage({ type: 'gesture', gesture: 'swipe', dir: param });
        }
    }
}

/**
 * สั่งทักทายอัตโนมัติเมื่อคนเดินมาหยุดหน้ากล้อง
 */
function triggerAutonomousGreeting() {
    wakeUpFromSleep();
    applyEmotion('happy');

    // ส่งสัญญาณไปยัง Flask Backend เพื่อกระจายเสียงทักทายไปยังจอสัมผัสหลัก
    fetch('/api/iot/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            event: 'user_detected',
            distance: 40.0,
            source: 'camera_eye_contact'
        })
    }).catch(() => {});
}

function togglePipPreview() {
    showPipPreview = !showPipPreview;
    const box = document.getElementById('camPreviewBox');
    if (box) {
        if (showPipPreview) box.classList.remove('hidden');
        else box.classList.add('hidden');
    }
}

// =============================================================================
// ระบบตรวจจับภาษามือไทย (Thai Sign Language TSL) ด้วย MediaPipe Hands บนหน้าจออารมณ์
// =============================================================================

const EMOTION_SIGN_RESPONSES = {
    'love': {
        name: 'ฉันรักเธอ (I Love You)',
        emoji: '🤟',
        emotion: 'love',
        sfx: 'love',
        speech: 'น้องเพชรก็รักคุณครับ! ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีครับ ❤️'
    },
    'thumbs_up': {
        name: 'ยอดเยี่ยม / ขอบคุณ (Thumbs Up)',
        emoji: '👍',
        emotion: 'wink',
        sfx: 'happy',
        speech: 'ขอบคุณมากครับ! ขอให้มีความสุขกับการท่องเที่ยวในเมืองเพชรบุรีนะครับ 👍'
    },
    'peace': {
        name: 'เที่ยวเมืองเพชรบุรี (Peace)',
        emoji: '✌️',
        emotion: 'happy',
        sfx: 'happy',
        speech: 'พร้อมพาเที่ยวเมืองเพชรบุรีแล้วครับ! แนะนำหาดเจ้าสำราญ หาดชะอำ และเขาวังครับ 🌊'
    },
    'open_palm': {
        name: 'สวัสดี / ยินดีต้อนรับ (Open Palm)',
        emoji: '🖐️',
        emotion: 'happy',
        sfx: 'chime',
        speech: 'สวัสดีครับ! ผมคือน้องเพชร AI Smart Guide ยินดีต้อนรับสู่เพชรบุรีครับ 😊'
    },
    'pointing': {
        name: 'แนะแนวเรียนต่ออาชีวะ (Pointing)',
        emoji: '☝️',
        emotion: 'thinking',
        sfx: 'thinking',
        speech: 'แนะนำศึกษาต่อ 9 สาขาวิชาชั้นนำ ณ วิทยาลัยอาชีวศึกษาเพชรบุรีครับ 🎓'
    },
    'fist': {
        name: 'ของกิน & ขนมหวาน (Fist)',
        emoji: '✊',
        emotion: 'happy',
        sfx: 'happy',
        speech: 'ห้ามพลาดขนมหม้อแกงเตาฟืนและก๋วยเตี๋ยวน้ำแดงสูตรเพชรบุรีแท้ๆ นะครับ 🍧'
    },
    'shaka': {
        name: 'ขอความช่วยเหลือฉุกเฉิน (Help / Call)',
        emoji: '🤙',
        emotion: 'surprised',
        sfx: 'wake',
        speech: 'หากต้องการความช่วยเหลือฉุกเฉินหรือติดต่อเจ้าหน้าที่ น้องเพชรพร้อมดูแลทันทีครับ 🚨'
    }
};

/**
 * สลับโหมดตรวจจับภาษามือ (เปิด/ปิด)
 */
async function toggleSignLanguageMode() {
    isSignLanguageMode = !isSignLanguageMode;
    const dot = document.getElementById('signIndicatorDot');
    const text = document.getElementById('signStatusText');
    const btnDock = document.getElementById('btnDockSign');
    const btnToggle = document.getElementById('btnToggleSign');
    const pipBox = document.getElementById('camPreviewBox');
    const pipLabel = document.getElementById('pipLabel');

    if (isSignLanguageMode) {
        wakeUpFromSleep();
        playSfx('happy');
        if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse';
        if (text) text.textContent = 'ตรวจจับภาษามือ: เปิดทำงาน';
        if (btnDock) {
            btnDock.classList.add('ring-2', 'ring-emerald-400', 'bg-emerald-500/30', 'scale-110');
            btnDock.title = 'ตรวจจับภาษามือ: กำลังทำงาน (คลิกเพื่อปิด หรือกด S)';
        }
        if (btnToggle) {
            btnToggle.className = 'px-2 py-1 bg-rose-700 hover:bg-rose-600 text-white rounded font-bold';
            btnToggle.innerHTML = '<i class="fa-solid fa-hands-asl-interpreting"></i> ปิดตรวจจับภาษามือ';
        }
        if (pipLabel) pipLabel.textContent = 'TSL 🤟';

        // 1. ถ้ากล้องยังไม่เปิด ให้เปิดกล้องอัตโนมัติ
        if (!isCameraTracking) {
            await startCameraTracking();
        }

        // 2. แสดงจอเล็ก PIP เพื่อให้ผู้ใช้จัดท่าทางมือได้สะดวก
        showPipPreview = true;
        if (pipBox) pipBox.classList.remove('hidden');

        // 3. เริ่มต้นระบบ MediaPipe Hands
        initEmotionSignHands();

        showVoiceSubtitle('🤟 เปิดโหมดตรวจจับภาษามือแล้วครับ แสดงท่าทางภาษามือหน้ากล้องได้เลย!', 4500);
    } else {
        playSfx('click');
        if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-slate-500';
        if (text) text.textContent = 'ตรวจจับภาษามือ: ปิด';
        if (btnDock) {
            btnDock.classList.remove('ring-2', 'ring-emerald-400', 'bg-emerald-500/30', 'scale-110');
            btnDock.title = 'เปิด/ปิด ตรวจจับภาษามือ (หรือกด S)';
        }
        if (btnToggle) {
            btnToggle.className = 'px-2 py-1 bg-cyan-700 hover:bg-cyan-600 text-white rounded font-bold';
            btnToggle.innerHTML = '<i class="fa-solid fa-hands-asl-interpreting"></i> ตรวจจับภาษามือ';
        }
        if (pipLabel) pipLabel.textContent = 'VISION';

        showVoiceSubtitle('ปิดโหมดตรวจจับภาษามือแล้วครับ', 2500);
    }
}

/**
 * เริ่มต้น MediaPipe Hands Engine
 */
function initEmotionSignHands() {
    if (emotionSignHands) return true;
    if (typeof Hands === 'undefined') {
        console.warn('⚠️ MediaPipe Hands library not loaded yet');
        return false;
    }

    try {
        emotionSignHands = new Hands({
            locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
        });

        emotionSignHands.setOptions({
            maxNumHands: 1,
            modelComplexity: 1,
            minDetectionConfidence: 0.60,
            minTrackingConfidence: 0.60
        });

        emotionSignHands.onResults(onEmotionSignResults);
        console.log('✅ [TSL Engine] MediaPipe Hands พร้อมทำงานบนหน้าจออารมณ์');
        return true;
    } catch (e) {
        console.error('Failed to init MediaPipe Hands on emotion screen:', e);
        return false;
    }
}

/**
 * ประมวลผลผลลัพธ์ MediaPipe Hands: วาดโครงกระดูกนีออน และจำแนกท่าทาง
 */
function onEmotionSignResults(results) {
    if (!isSignLanguageMode) return;

    const pipCanvas = document.getElementById('pipCanvas');
    const pipBox = document.getElementById('camPreviewBox');
    const pipLabel = document.getElementById('pipLabel');

    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
        emotionSignLastDetectedGesture = null;
        if (pipLabel) pipLabel.textContent = 'TSL 🤟';
        return;
    }

    const landmarks = results.multiHandLandmarks[0];

    // วาดโครงกระดูกมือบนจอเล็ก PIP
    if (pipCanvas && pipBox && !pipBox.classList.contains('hidden')) {
        const pipCtx = pipCanvas.getContext('2d');
        if (TRACKING_VIDEO && TRACKING_VIDEO.videoWidth > 0) {
            if (pipCanvas.width !== TRACKING_VIDEO.videoWidth) {
                pipCanvas.width = TRACKING_VIDEO.videoWidth;
                pipCanvas.height = TRACKING_VIDEO.videoHeight;
            }
        }
        pipCtx.drawImage(TRACKING_VIDEO, 0, 0, pipCanvas.width, pipCanvas.height);
        drawEmotionSignSkeleton(pipCtx, landmarks, pipCanvas.width, pipCanvas.height);
    }

    // จำแนกท่าทางด้วยอัลกอริทึมเรขาคณิตความเร็วสูง
    const detected = classifyHandLandmarkGesture(landmarks);
    if (detected) {
        const now = performance.now();
        if (pipLabel) {
            const info = EMOTION_SIGN_RESPONSES[detected];
            if (info) pipLabel.textContent = `${info.emoji} ${detected.toUpperCase()}`;
        }

        if (detected !== emotionSignLastDetectedGesture) {
            emotionSignLastDetectedGesture = detected;
            emotionSignHoldStartTime = now;
        } else {
            const holdElapsed = now - emotionSignHoldStartTime;
            // ถือท่าค้างนิ่งๆ เกิน 600ms และพ้นระยะ Cool-down (3.5 วินาที)
            if (holdElapsed >= EMOTION_SIGN_HOLD_DURATION_MS && (now - emotionSignLastTriggerTime > 3500 || emotionSignLastTriggeredGesture !== detected)) {
                emotionSignLastTriggeredGesture = detected;
                emotionSignLastTriggerTime = now;
                handleEmotionSignTrigger(detected);
            }
        }
    } else {
        emotionSignLastDetectedGesture = null;
    }
}

/**
 * วาดโครงกระดูกมือนีออนสุดล้ำบนจอเล็ก (Futuristic Neon Hand Skeleton)
 */
function drawEmotionSignSkeleton(ctx, lm, width, height) {
    const connections = [
        [0, 1], [1, 2], [2, 3], [3, 4],        // นิ้วโป้ง
        [0, 5], [5, 6], [6, 7], [7, 8],        // นิ้วชี้
        [0, 9], [9, 10], [10, 11], [11, 12],   // นิ้วกลาง
        [0, 13], [13, 14], [14, 15], [15, 16], // นิ้วนาง
        [0, 17], [17, 18], [18, 19], [19, 20], // นิ้วก้อย
        [5, 9], [9, 13], [13, 17], [0, 17]     // ฐานฝ่ามือ
    ];

    ctx.save();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = '#00f0ff';
    ctx.shadowColor = '#00f0ff';
    ctx.shadowBlur = 8;

    // วาดเส้นกระดูก
    for (const [startIdx, endIdx] of connections) {
        const p1 = lm[startIdx];
        const p2 = lm[endIdx];
        ctx.beginPath();
        ctx.moveTo(p1.x * width, p1.y * height);
        ctx.lineTo(p2.x * width, p2.y * height);
        ctx.stroke();
    }

    // วาดข้อต่อเรืองแสง (สีทอง-เหลือง)
    for (let idx = 0; idx < lm.length; idx++) {
        const p = lm[idx];
        const x = p.x * width;
        const y = p.y * height;
        const isTip = [4, 8, 12, 16, 20].includes(idx);
        const radius = isTip ? 4.5 : 3;

        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fillStyle = isTip ? '#f59e0b' : '#38bdf8';
        ctx.shadowColor = isTip ? '#f59e0b' : '#06b6d4';
        ctx.shadowBlur = 6;
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.stroke();
    }
    ctx.restore();
}

/**
 * อัลกอริทึมจำแนกท่าทางภาษามือจากตำแหน่งพิกัด 21 จุด (Geometric Rule Engine)
 */
function classifyHandLandmarkGesture(lm) {
    const wrist = lm[0];
    const dist = (p1, p2) => Math.hypot(p1.x - p2.x, p1.y - p2.y);

    const thumbTip = lm[4], thumbIp = lm[3], thumbMcp = lm[2];
    const indexTip = lm[8], indexPip = lm[6], indexMcp = lm[5];
    const middleTip = lm[12], middlePip = lm[10], middleMcp = lm[9];
    const ringTip = lm[16], ringPip = lm[14], ringMcp = lm[13];
    const pinkyTip = lm[20], pinkyPip = lm[18], pinkyMcp = lm[17];

    const palmSize = dist(wrist, middleMcp) || 0.1;

    // ตรวจสอบว่าแต่ละนิ้วเหยียดตรงหรือไม่ (ปลายนิ้วอยู่ไกลจากข้อมือมากกว่าข้อกลาง)
    const isIndexExtended = dist(indexTip, wrist) > dist(indexPip, wrist) * 1.15;
    const isMiddleExtended = dist(middleTip, wrist) > dist(middlePip, wrist) * 1.15;
    const isRingExtended = dist(ringTip, wrist) > dist(ringPip, wrist) * 1.15;
    const isPinkyExtended = dist(pinkyTip, wrist) > dist(pinkyPip, wrist) * 1.15;
    const isThumbExtended = dist(thumbTip, indexMcp) > palmSize * 0.7;

    // ท่าชูนิ้วโป้งขึ้นด้านบน
    const isThumbPointingUp = (thumbTip.y < indexMcp.y) && (!isIndexExtended && !isMiddleExtended && !isRingExtended && !isPinkyExtended);

    // 1. ท่าบอกรัก (🤟 I Love You): โป้ง, ชี้, ก้อย เหยียดตรง / กลาง, นาง พับ
    if (isThumbExtended && isIndexExtended && isPinkyExtended && !isMiddleExtended && !isRingExtended) {
        return 'love';
    }

    // 2. ท่ายอดเยี่ยม (👍 Thumbs Up): นิ้วโป้งชี้ขึ้น นิ้วอื่นพับหมด
    if (isThumbPointingUp || (isThumbExtended && !isIndexExtended && !isMiddleExtended && !isRingExtended && !isPinkyExtended && thumbTip.y < wrist.y)) {
        return 'thumbs_up';
    }

    // 3. ท่าชูสองนิ้ว (✌️ Peace / V-Sign): นิ้วชี้ และ นิ้วกลาง เหยียด / นาง, ก้อย พับ
    if (isIndexExtended && isMiddleExtended && !isRingExtended && !isPinkyExtended) {
        return 'peace';
    }

    // 4. ท่าชี้นิ้วขึ้น (☝️ Pointing Up): นิ้วชี้ เหยียดเดียว / นิ้วอื่นพับหมด
    if (isIndexExtended && !isMiddleExtended && !isRingExtended && !isPinkyExtended && !isThumbExtended) {
        return 'pointing';
    }

    // 5. ท่าแบมือ (🖐️ Open Palm / Hello): เหยียดครบทั้ง 5 นิ้ว
    if (isIndexExtended && isMiddleExtended && isRingExtended && isPinkyExtended && isThumbExtended) {
        return 'open_palm';
    }

    // 6. ท่ากำหมัด (✊ Fist): พับนิ้วทั้งหมด
    if (!isIndexExtended && !isMiddleExtended && !isRingExtended && !isPinkyExtended && !isThumbExtended) {
        return 'fist';
    }

    // 7. ท่าสัญลักษณ์สายเรียกเข้า (🤙 Shaka / Call): โป้ง และ ก้อย เหยียด / ชี้, กลาง, นาง พับ
    if (isThumbExtended && isPinkyExtended && !isIndexExtended && !isMiddleExtended && !isRingExtended) {
        return 'shaka';
    }

    return null;
}

/**
 * ตอบสนองเมื่อตรวจพบภาษามือ: ปรับอารมณ์ใบหน้า, ส่งเสียงเอฟเฟกต์, แสดงคำบรรยาย และพูดตอบสด
 */
function handleEmotionSignTrigger(gestureKey) {
    const data = EMOTION_SIGN_RESPONSES[gestureKey];
    if (!data) return;

    console.log(`🤟 [TSL Detected] ตรวจพบภาษามือ: ${gestureKey} -> ${data.name}`);

    wakeUpFromSleep();
    playSfx(data.sfx || 'happy');
    triggerHaptic(30);

    // ปรับอารมณ์บนใบหน้าน้องเพชรทันที
    applyEmotion(data.emotion);

    // แสดงคำบรรยายสดใต้ใบหน้า
    const subtitle = `${data.emoji} ภาษามือ: ${data.name} — ${data.speech}`;
    showVoiceSubtitle(subtitle, 6500);

    // สังเคราะห์เสียงพูดตอบรับทันที
    playDirectVoiceTTS(data.speech);

    // ส่งสัญญาณซิงก์ข้ามจอ (BroadcastChannel) เผื่อจอหลักเปิดอยู่
    if (lipSyncBroadcast) {
        lipSyncBroadcast.postMessage({
            type: 'sign_language_detected',
            gesture: gestureKey,
            data: data
        });
    }

    // ส่งบันทึกสถิติไปยัง Backend
    fetch('/api/sign_language', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gesture_hint: gestureKey, language: 'th' })
    }).catch(() => {});
}

// =============================================================================
// ระบบ Lip-Sync & Dual-Screen Synchronization (BroadcastChannel Receiver)
// =============================================================================
function initLipSyncReceiver() {
    if (lipSyncBroadcast) {
        lipSyncBroadcast.onmessage = (event) => {
            if (!event.data) return;
            const msg = event.data;
            if (msg.type === 'lipsync') {
                setLipSyncAmplitude(msg.amp || 0);
            } else if (msg.type === 'emotion' && msg.state) {
                if (msg.state !== 'sleeping') wakeUpFromSleep();
                applyEmotion(msg.state);
            } else if (msg.type === 'gaze') {
                if (!isMouseActive) {
                    targetGazeX = msg.x;
                    targetGazeY = msg.y;
                    lastInteractionTime = performance.now();
                    wakeUpFromSleep();
                }
            }
        };
    }
}

function setLipSyncAmplitude(amp) {
    if (!STAGE) return;
    if (amp > 0.05) {
        STAGE.classList.add('audio-active');
        STAGE.style.setProperty('--audio-amp', amp.toFixed(2));

        // ขยับแท่ง Audio Wave Equalizer ใต้ปากแบบไดนามิก
        const bars = document.querySelectorAll('.wave-bar');
        if (bars.length > 0) {
            bars.forEach((bar, idx) => {
                const factor = 1 - Math.abs(idx - 4) * 0.18;
                const h = Math.max(4, Math.min(28, 4 + amp * 26 * factor));
                bar.style.height = `${h.toFixed(1)}px`;
            });
        }
    } else {
        STAGE.classList.remove('audio-active');
        const bars = document.querySelectorAll('.wave-bar');
        bars.forEach((bar) => {
            bar.style.height = '';
        });
    }
}

// =============================================================================
// ระบบสื่อสาร Realtime ผ่าน Server-Sent Events (SSE)
// =============================================================================
function initEventStream() {
    if (eventSource) {
        eventSource.close();
    }

    try {
        eventSource = new EventSource('/api/iot/events');

        eventSource.onopen = () => {
            console.log('📡 [Emotion Display] Connected to Flask Event Stream');
        };

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'emotion_changed' && data.state) {
                    if (data.state !== 'sleeping') wakeUpFromSleep();
                    applyEmotion(data.state);
                } else if (data.event === 'gaze_changed') {
                    if (!isMouseActive) {
                        targetGazeX = data.x;
                        targetGazeY = data.y;
                        lastInteractionTime = performance.now();
                        wakeUpFromSleep();
                    }
                } else if (data.event === 'led_state_changed' && data.state) {
                    wakeUpFromSleep();
                    mapLedToEmotion(data.state);
                } else if (data.event === 'user_detected') {
                    wakeUpFromSleep();
                    applyEmotion('happy');
                    setTimeout(() => {
                        if (currentEmotion === 'happy') applyEmotion('idle');
                    }, 4000);
                }
            } catch (e) {}
        };

        eventSource.onerror = () => {
            console.warn('⚠️ [Emotion Display] SSE Disconnected, reconnecting in 3s...');
            eventSource.close();
            setTimeout(initEventStream, 3000);
        };
    } catch (err) {
        console.error('Failed to init SSE:', err);
        setInterval(pollEmotionState, 2000);
    }
}

function mapLedToEmotion(ledState) {
    switch (ledState) {
        case 'speaking':
            applyEmotion('speaking');
            break;
        case 'thinking':
            applyEmotion('thinking');
            break;
        case 'listening':
            applyEmotion('listening');
            break;
        default:
            applyEmotion('idle');
            break;
    }
}

async function pollEmotionState() {
    try {
        const res = await fetch('/api/emotion/state');
        const data = await res.json();
        if (data.current_state && data.current_state !== currentEmotion) {
            applyEmotion(data.current_state);
        }
    } catch (e) {}
}

function setEmotionLocally(state) {
    playSfx('click');
    applyEmotion(state);
    if (lipSyncBroadcast) {
        lipSyncBroadcast.postMessage({ type: 'emotion', state: state });
    }
    fetch('/api/emotion/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: state })
    }).catch(() => {});
}

function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen().catch(() => {});
        }
    }
}

function setupKeyListeners() {
    window.addEventListener('keydown', (e) => {
        if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            toggleDirectVoice();
        } else if (e.key === 't' || e.key === 'T') {
            cycleTheme();
        } else if (e.key === 'm' || e.key === 'M') {
            toggleSfx();
        } else if (e.key === 'e' || e.key === 'E') {
            toggleEmotionDock();
        } else if (e.key === 'f' || e.key === 'F') {
            toggleFullscreen();
        } else if (e.key === 'c' || e.key === 'C') {
            toggleCameraTracking();
        } else if (e.key === 'p' || e.key === 'P') {
            togglePipPreview();
        } else if (e.key === 's' || e.key === 'S') {
            toggleSignLanguageMode();
        } else if (e.key === 'z' || e.key === 'Z' || e.key === '0') {
            setEmotionLocally('sleeping');
        } else if (e.key === '1') setEmotionLocally('smile');
        else if (e.key === '2') setEmotionLocally('squint');
        else if (e.key === '3') setEmotionLocally('excited');
        else if (e.key === '4') setEmotionLocally('surprised');
        else if (e.key === '5') setEmotionLocally('idle');
        else if (e.key === '6') setEmotionLocally('listening');
        else if (e.key === '7') setEmotionLocally('thinking');
        else if (e.key === '8') setEmotionLocally('speaking');
        else if (e.key === '9') setEmotionLocally('love');
    });

    // ดับเบิลคลิกที่หน้าจอเพื่อขยายเต็มจอ
    window.addEventListener('dblclick', toggleFullscreen);
}

/**
 * ฟังก์ชันปฏิกิริยาสัมผัสหน้าจอสุดคูล (Interactive Tactile Reactions)
 */
const NONGPHET_SPOKEN_GREETINGS = [
    'สวัสดีครับ! ผมคือน้องเพชร AI Smart Guide ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีครับ 😊',
    'วันนี้อากาศเมืองเพชรบุรีแจ่มใสมากครับ อยากให้ผมแนะนำที่เที่ยวหรือร้านของหวานดีครับ',
    'แวะมาชิมขนมหม้อแกงเตาฟืนและก๋วยเตี๋ยวน้ำแดงสูตรเพชรบุรีแท้ๆ นะครับ อร่อยติดใจแน่นอน 🍧',
    'วิทยาลัยอาชีวศึกษาเพชรบุรีมี 9 สาขาวิชาแห่งอนาคต พร้อมต้อนรับน้องๆ ทุกคนครับ 🎓',
    'แตะปากแบบนี้ อยากคุยกับน้องเพชรใช่ไหมครับ กดปุ่มไมค์ด้านขวาล่างคุยสดกับผมได้เลยนะ!'
];

function triggerMouthReaction(e) {
    if (e) {
        e.stopPropagation();
        if (e.clientX && e.clientY) spawnTouchRipple(e.clientX, e.clientY);
    }
    wakeUpFromSleep();
    playSfx('happy');
    triggerHaptic(20);
    setEmotionLocally('happy');
    const quote = NONGPHET_SPOKEN_GREETINGS[Math.floor(Math.random() * NONGPHET_SPOKEN_GREETINGS.length)];
    showVoiceSubtitle(quote);
    playDirectVoiceTTS(quote);
}

function triggerShyReaction(e) {
    if (e) {
        e.stopPropagation();
        if (e.clientX && e.clientY) spawnTouchRipple(e.clientX, e.clientY);
    }
    wakeUpFromSleep();
    playSfx('love');
    triggerHaptic(20);
    setEmotionLocally('love');
    showVoiceSubtitle('ฮั่นแน่! แตะแก้มน้องเพชรทำไม... เขินนะเนี่ย 💖', 3500);
    setTimeout(() => {
        if (currentEmotion === 'love') setEmotionLocally('happy');
    }, 3500);
    setTimeout(() => {
        if (currentEmotion === 'happy') setEmotionLocally('idle');
    }, 6000);
}

function triggerScannerMode(e) {
    if (e) {
        e.stopPropagation();
        if (e.clientX && e.clientY) spawnTouchRipple(e.clientX, e.clientY);
    }
    wakeUpFromSleep();
    playSfx('scanner');
    triggerHaptic(25);
    setEmotionLocally('scanner');
    showVoiceSubtitle('⚡ เปิดระบบสแกนเนอร์เรดาร์วิเคราะห์เป้าหมาย...', 3000);
    setTimeout(() => {
        if (currentEmotion === 'scanner') setEmotionLocally('happy');
    }, 3200);
    setTimeout(() => {
        if (currentEmotion === 'happy') setEmotionLocally('idle');
    }, 5500);
}

function triggerWinkReaction(e) {
    if (e) {
        e.stopPropagation();
        if (e.clientX && e.clientY) spawnTouchRipple(e.clientX, e.clientY);
    }
    wakeUpFromSleep();
    playSfx('wink');
    triggerHaptic(15);
    setEmotionLocally('wink');
    showVoiceSubtitle('😉 สวัสดีครับ มีอะไรให้น้องเพชรช่วยเหลือไหมครับ!', 2500);
    setTimeout(() => {
        if (currentEmotion === 'wink') setEmotionLocally('happy');
    }, 1800);
    setTimeout(() => {
        if (currentEmotion === 'happy') setEmotionLocally('idle');
    }, 4000);
}

function toggleEmotionDock() {
    const dock = document.getElementById('quickEmotionDock');
    if (!dock) return;
    dock.classList.toggle('translate-y-0');
    dock.classList.toggle('opacity-100');
    dock.classList.toggle('translate-y-16');
    dock.classList.toggle('opacity-0');
}

function initHudClock() {
    const clockEl = document.getElementById('hudClock');
    if (!clockEl) return;
    function updateClock() {
        const now = new Date();
        const timeStr = now.toTimeString().split(' ')[0];
        clockEl.textContent = `${timeStr} ◥`;
    }
    updateClock();
    setInterval(updateClock, 1000);
}

// =============================================================================
// ระบบคุยด้วยเสียงกับน้องเพชรโดยตรงบนหน้าจอแสดงอารมณ์ (Direct Voice Interaction)
// =============================================================================
let emotionRecognition = null;
let isEmotionListening = false;
let isEmotionSpeaking = false;
let voiceSubtitleTimer = null;

function initDirectVoiceEngine() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        emotionRecognition = new SpeechRec();
        emotionRecognition.lang = 'th-TH';
        emotionRecognition.interimResults = true;
        emotionRecognition.continuous = false;

        emotionRecognition.onstart = () => {
            isEmotionListening = true;
            wakeUpFromSleep();
            applyEmotion('listening');
            showVoiceSubtitle('🎙️ กำลังฟังเสียงคุณ... พูดได้เลยครับ');
            const micBtn = document.getElementById('btnEmotionVoice');
            if (micBtn) {
                micBtn.className = 'absolute bottom-4 right-4 sm:bottom-6 sm:right-6 w-12 h-12 rounded-2xl bg-rose-500/30 border border-rose-400 text-rose-300 text-lg shadow-2xl animate-pulse z-40 flex items-center justify-center';
            }
        };

        emotionRecognition.onresult = (event) => {
            let transcript = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                transcript += event.results[i][0].transcript;
            }
            if (transcript) {
                showVoiceSubtitle(`🎙️ ได้ยิน: "${transcript}"`);
            }
            if (event.results[0] && event.results[0].isFinal) {
                const finalQuery = event.results[0][0].transcript.trim();
                if (finalQuery) {
                    processDirectVoiceQuery(finalQuery);
                }
            }
        };

        emotionRecognition.onerror = () => {
            isEmotionListening = false;
            resetMicButton();
            if (currentEmotion === 'listening') applyEmotion('idle');
        };

        emotionRecognition.onend = () => {
            isEmotionListening = false;
            resetMicButton();
        };
    }
}

function toggleDirectVoice() {
    // ปลดล็อก Audio Element ทันทีในจังหวะที่ผู้ใช้กดปุ่ม (User Gesture Activation)
    getSfxAudioContext();
    const a = document.getElementById('emotionAudioPlayer');
    if (a) {
        if (!a.src) a.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
        a.play().then(() => { a.pause(); }).catch(() => {});
    }

    if (!emotionRecognition) {
        initDirectVoiceEngine();
        if (!emotionRecognition) {
            alert('เบราว์เซอร์นี้ไม่รองรับ Web Speech API กรุณาใช้งานผ่าน Chrome/Chromium หรือ Edge');
            return;
        }
    }

    if (isEmotionListening) {
        emotionRecognition.stop();
        isEmotionListening = false;
        resetMicButton();
        if (currentEmotion === 'listening') applyEmotion('idle');
    } else {
        try {
            emotionRecognition.start();
        } catch (e) {
            emotionRecognition.stop();
            setTimeout(() => emotionRecognition.start(), 200);
        }
    }
}

function resetMicButton() {
    const micBtn = document.getElementById('btnEmotionVoice');
    if (micBtn) {
        micBtn.className = 'absolute bottom-4 right-4 sm:bottom-6 sm:right-6 w-12 h-12 rounded-2xl bg-cyan-500/20 hover:bg-cyan-500/40 border border-cyan-400/50 flex items-center justify-center text-cyan-300 text-lg shadow-2xl shadow-cyan-500/30 backdrop-blur-md transition-all active:scale-95 z-40';
    }
}

function showVoiceSubtitle(text, autoHideMs = 0) {
    const box = document.getElementById('voiceSubtitleBox');
    const txt = document.getElementById('voiceSubtitleText');
    if (!box || !txt) return;

    txt.textContent = text;
    box.classList.remove('opacity-0', 'translate-y-3');

    if (voiceSubtitleTimer) clearTimeout(voiceSubtitleTimer);
    if (autoHideMs > 0) {
        voiceSubtitleTimer = setTimeout(() => {
            box.classList.add('opacity-0', 'translate-y-3');
        }, autoHideMs);
    }
}

async function processDirectVoiceQuery(queryText) {
    applyEmotion('thinking');
    showVoiceSubtitle(`⚡ น้องเพชรกำลังคิด: "${queryText}"`);

    let sessionId = localStorage.getItem('nongphet_session_id');
    if (!sessionId) {
        sessionId = 'user_' + Math.random().toString(36).substring(2, 10);
        localStorage.setItem('nongphet_session_id', sessionId);
    }

    try {
        const chatRes = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: queryText, language: 'th', session_id: sessionId })
        });
        const chatData = await chatRes.json();
        const reply = chatData.reply || 'น้องเพชรพร้อมให้บริการครับ';

        showVoiceSubtitle(reply);
        playDirectVoiceTTS(reply);
    } catch (e) {
        showVoiceSubtitle('ขออภัยครับ เกิดข้อผิดพลาดในการเชื่อมต่อ AI', 3000);
        applyEmotion('idle');
    }
}

function fallbackBrowserSpeech(text) {
    clearTimeout(emotionSafetyWatchdog);
    if ('speechSynthesis' in window) {
        try {
            window.speechSynthesis.cancel();
            // ตัดส่วนแนะนำคำถามต่อยอดเพื่อให้ออกเสียงกระชับสดใส ไม่เกิน 150 ตัวอักษร
            let clean = text.split(/\n|---|💡|❓/)[0].replace(/[*#_~`>•\-=|]/g, ' ').replace(/\s+/g, ' ').trim();
            if (clean.length > 150) clean = clean.substring(0, 150) + '...';
            const u = new SpeechSynthesisUtterance(clean);
            u.lang = 'th-TH';
            u.rate = 1.05;
            u.pitch = 1.25;
            u.onstart = () => applyEmotion('speaking');
            u.onend = () => { applyEmotion('idle'); };
            u.onerror = () => { applyEmotion('idle'); };
            window.speechSynthesis.speak(u);
            return;
        } catch (e) {
            console.warn('SpeechSynthesis error:', e);
        }
    }
    applyEmotion('idle');
}

function playBase64ViaWebAudio(base64Data, onEndedCallback) {
    try {
        const ctx = getSfxAudioContext();
        if (!ctx) return false;
        if (ctx.state === 'suspended') ctx.resume();

        const binary = atob(base64Data);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }

        ctx.decodeAudioData(bytes.buffer, (audioBuffer) => {
            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            applyEmotion('speaking');
            startLocalLipSyncPulse();
            source.onended = () => {
                clearTimeout(emotionSafetyWatchdog);
                applyEmotion('idle');
                setLipSyncAmplitude(0);
                if (typeof onEndedCallback === 'function') onEndedCallback();
            };
            source.start(0);
        }, (err) => {
            console.warn('Web Audio decode failed:', err);
            applyEmotion('idle');
        });
        return true;
    } catch (e) {
        console.warn('Web Audio playback error:', e);
        applyEmotion('idle');
        return false;
    }
}

async function playDirectVoiceTTS(text) {
    // ตัดข้อความให้กระชับก่อนพูด: เอาแค่ประโยคแรก ไม่เกิน 150 ตัวอักษร
    let speakText = text
        .split(/\n|---|💡|❓/)[0]          // เอาแค่ย่อหน้าแรก
        .replace(/[*#_~`>•\-=|🌟💬🏛️]/g, '') // ลบ markdown symbols และ emoji ที่ออกเสียงไม่ได้
        .replace(/\s+/g, ' ')
        .trim();
    if (speakText.length > 150) speakText = speakText.substring(0, 150) + '...';

    try {
        const audioEl = document.getElementById('emotionAudioPlayer');
        if (!audioEl) {
            fallbackBrowserSpeech(speakText);
            return;
        }

        // ใช้ AbortController จำกัดเวลาเชื่อมต่อไม่ให้ค้างนาน
        const abortCtrl = new AbortController();
        const timeoutId = setTimeout(() => abortCtrl.abort(), 9500);

        const ttsRes = await fetch('/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: speakText, lang: 'th', gender: 'female' }),
            signal: abortCtrl.signal
        });
        clearTimeout(timeoutId);
        const ttsData = await ttsRes.json();

        if (ttsData.audio_base64) {
            audioEl.src = 'data:audio/mp3;base64,' + ttsData.audio_base64;
            audioEl.volume = 1.0;
            audioEl.muted = false;

            audioEl.onended = () => {
                clearTimeout(emotionSafetyWatchdog);
                applyEmotion('idle');
                setLipSyncAmplitude(0);
            };

            audioEl.onerror = () => {
                console.warn('audioEl error, falling back to Web Audio');
                playBase64ViaWebAudio(ttsData.audio_base64);
            };

            // เริ่มเล่นเสียง: เมื่อเสียงดังจริงค่อยเริ่มขยับปากพูด!
            try {
                await audioEl.play();
                applyEmotion('speaking');
                startLocalLipSyncPulse();
            } catch (playErr) {
                console.warn('Audio play blocked by browser, attempting Web Audio API:', playErr);
                const webAudioPlayed = playBase64ViaWebAudio(ttsData.audio_base64);
                if (!webAudioPlayed) {
                    fallbackBrowserSpeech(speakText);
                }
            }
        } else {
            fallbackBrowserSpeech(speakText);
        }
    } catch (e) {
        console.warn('TTS request failed/aborted:', e);
        fallbackBrowserSpeech(speakText);
    }
}

let localLipSyncFrame = null;
function startLocalLipSyncPulse() {
    cancelAnimationFrame(localLipSyncFrame);
    function loop() {
        if (currentEmotion === 'speaking') {
            const t = performance.now() / 150;
            const normAmp = 0.35 + 0.45 * Math.abs(Math.sin(t) * Math.sin(t * 2.1));
            setLipSyncAmplitude(normAmp);
            localLipSyncFrame = requestAnimationFrame(loop);
        } else {
            setLipSyncAmplitude(0);
        }
    }
    loop();
}

// =============================================================================
// Living Robot Particle System & Kawaii Emitter (หัวใจ, ประกายดาว, คอนเฟตตีลอย)
// =============================================================================
function spawnEmotionParticle(x, y, icon = '💖') {
    const layer = document.getElementById('emotionParticleLayer');
    if (!layer) return;

    const p = document.createElement('div');
    p.className = 'floating-particle';
    p.textContent = icon;

    // Spread coordinates slightly
    const posX = (x !== undefined && x !== null) ? x : (window.innerWidth / 2 + (Math.random() - 0.5) * 200);
    const posY = (y !== undefined && y !== null) ? y : (window.innerHeight / 2 + (Math.random() - 0.5) * 80);

    const driftX = (Math.random() - 0.5) * 120;
    const rotAngle = (Math.random() - 0.5) * 60;
    const size = Math.floor(Math.random() * 14 + 18); // 18px - 32px

    p.style.left = `${posX}px`;
    p.style.top = `${posY}px`;
    p.style.fontSize = `${size}px`;
    p.style.setProperty('--drift-x', `${driftX}px`);
    p.style.setProperty('--rot-angle', `${rotAngle}deg`);

    layer.appendChild(p);
    setTimeout(() => {
        if (p.parentElement) p.remove();
    }, 2300);
}

function spawnParticleBurst(x, y, count = 6, icons = ['💖', '✨', '✦', '🌸', '⭐']) {
    for (let i = 0; i < count; i++) {
        setTimeout(() => {
            const icon = icons[Math.floor(Math.random() * icons.length)];
            const offsetX = (Math.random() - 0.5) * 70;
            const offsetY = (Math.random() - 0.5) * 40;
            spawnEmotionParticle(x + offsetX, y + offsetY, icon);
        }, i * 65);
    }
}

// =============================================================================
// Interactive Touch & Living Pet Reactions (ระบบสัมผัสและปฏิกิริยาโต้ตอบเสมือนมีชีวิต)
// =============================================================================

// 1. Head Petting / Forehead Rub (ลูบหัวน้องเพชร -> เคลิ้มยิ้มตาหยี >‿< ปล่อยหัวใจฟุ้ง)
let headPetTimeout = null;
function triggerHeadPet(e) {
    if (e) e.stopPropagation();
    wakeUpFromSleep();
    playSfx('purr');
    triggerHaptic(35);

    const faceContainer = document.querySelector('.face-container');
    if (faceContainer) {
        faceContainer.classList.add('is-petting');
    }

    // Wiggle both ears happily
    document.querySelectorAll('.cyber-ear').forEach(ear => {
        ear.classList.remove('ear-wiggle');
        void ear.offsetWidth;
        ear.classList.add('ear-wiggle');
        setTimeout(() => ear.classList.remove('ear-wiggle'), 650);
    });

    // Switch to squint blissful face (>‿<)
    applyEmotion('squint');

    // Spawn floating hearts & sparkles burst at top center
    const rect = e && e.target ? e.target.getBoundingClientRect() : null;
    const px = rect ? (rect.left + rect.width / 2) : (window.innerWidth / 2);
    const py = rect ? rect.top : (window.innerHeight * 0.35);
    spawnParticleBurst(px, py, 9, ['💖', '✨', '💕', '✦', '🌸']);

    const cuteLines = [
        'งื้อออ... ขอบคุณที่ลูบหัวผมนะครับ อบอุ่นจัง (⌒‿⌒)💖',
        'น้องเพชรชอบให้ลูบหัวที่สุดเลยครับ งึมๆ~ ✨',
        'รู้สึกมีความสุขจังเลยครับ ขอบคุณนะครับที่เอ็นดูผม! 🥰',
        'แฮปปี้สุดๆ ไปเลยครับ! พร้อมช่วยเหลือทุกเรื่องเลยค้าบ 💖'
    ];
    const pickedLine = cuteLines[Math.floor(Math.random() * cuteLines.length)];
    showVoiceSubtitle(pickedLine, 3500);

    clearTimeout(headPetTimeout);
    headPetTimeout = setTimeout(() => {
        if (faceContainer) faceContainer.classList.remove('is-petting');
        if (currentEmotion === 'squint') {
            applyEmotion('happy');
            setTimeout(() => {
                if (currentEmotion === 'happy') applyEmotion('idle');
            }, 2500);
        }
    }, 3200);
}

// 2. Ear Tickle / Perk (เกาหูดุ๊กดิ๊ก)
function triggerEarReaction(side, e) {
    if (e) e.stopPropagation();
    wakeUpFromSleep();
    playSfx('flutter');
    triggerHaptic(20);

    const earEl = document.querySelector(`.ear-${side}`);
    if (earEl) {
        earEl.classList.remove('ear-wiggle');
        void earEl.offsetWidth; // force reflow
        earEl.classList.add('ear-wiggle');
        setTimeout(() => earEl.classList.remove('ear-wiggle'), 600);
    }

    // Look slightly towards the tickled ear with cute head tilt
    targetGazeX = side === 'left' ? -0.45 : 0.45;
    targetGazeY = -0.15;
    isMouseActive = true;
    setTimeout(() => { isMouseActive = false; }, 1800);

    const rect = earEl ? earEl.getBoundingClientRect() : null;
    const px = rect ? (rect.left + rect.width / 2) : (side === 'left' ? 40 : window.innerWidth - 40);
    const py = rect ? (rect.top + rect.height / 2) : (window.innerHeight / 2);
    spawnParticleBurst(px, py, 4, ['✨', '🎵', '✦', '⚡']);

    const subtitleText = side === 'left' 
        ? 'ฮั่นแน่! เกาหูซ้ายผมเหรอครับ จักจี้ดุ๊กดิ๊ก~ 🐾' 
        : 'เกาหูขวาน้องเพชร กระดิกหูดุ๊กดิ๊กๆ น่ารักจัง! 📡';
    showVoiceSubtitle(subtitleText, 2500);
}

// 3. Cheek Poke / Blush Reaction (จิ้มแก้มเขิน)
let shyTimeout = null;
function triggerShyReaction(e) {
    if (e) e.stopPropagation();
    wakeUpFromSleep();
    playSfx('love');
    triggerHaptic(25);

    applyEmotion('love');

    const rect = e && e.target ? e.target.getBoundingClientRect() : null;
    const px = rect ? (rect.left + rect.width / 2) : (window.innerWidth / 2);
    const py = rect ? (rect.top + rect.height / 2) : (window.innerHeight / 2);
    spawnParticleBurst(px, py, 8, ['💖', '💕', '🌸', '✨', '💗']);

    const cuteShyLines = [
        'งื้อออ... จิ้มแก้มผมทำไมครับ เขินจังเลยนะ (>///<)💖',
        'แก้มผมมีเซนเซอร์นะ! จิ้มแล้วหัวใจฟูฟ่องเลยค้าบ 🌸',
        'เขินนะเนี่ย! หน้าแดงหมดแล้วครับ (>‿<)✨'
    ];
    const picked = cuteShyLines[Math.floor(Math.random() * cuteShyLines.length)];
    showVoiceSubtitle(picked, 3200);

    clearTimeout(shyTimeout);
    shyTimeout = setTimeout(() => {
        if (currentEmotion === 'love') {
            applyEmotion('smile');
            setTimeout(() => {
                if (currentEmotion === 'smile') applyEmotion('idle');
            }, 2000);
        }
    }, 3200);
}

// 4. Wink Reaction (จิ้มดวงตา -> สบตาปิ๊งๆ 😉)
function triggerWinkReaction(e) {
    if (e) e.stopPropagation();
    wakeUpFromSleep();
    playSfx('wink');
    triggerHaptic(20);

    applyEmotion('wink');

    const rect = e && e.target ? e.target.getBoundingClientRect() : null;
    const px = rect ? (rect.left + rect.width / 2) : (window.innerWidth / 2);
    const py = rect ? (rect.top + rect.height / 2) : (window.innerHeight * 0.45);
    spawnParticleBurst(px, py, 5, ['✦', '✨', '⭐', '😉']);

    showVoiceSubtitle('ปิ๊งๆ! ยิ้มให้กันแบบนี้ สดชื่นทั้งวันแน่นอนครับ 😉✨', 2500);

    setTimeout(() => {
        if (currentEmotion === 'wink') {
            applyEmotion('smile');
            setTimeout(() => {
                if (currentEmotion === 'smile') applyEmotion('idle');
            }, 2000);
        }
    }, 2200);
}

// 5. Mouth Tap Reaction (จิ้มปาก -> คุยตอบรับ)
function triggerMouthReaction(e) {
    if (e) e.stopPropagation();
    wakeUpFromSleep();
    playSfx('happy');
    triggerHaptic(25);

    applyEmotion('speaking');
    startLocalLipSyncPulse();

    const greetings = [
        'สวัสดีครับ! น้องเพชรพร้อมแนะนำข้อมูลวิทยาลัยและนำทางครับ 💬',
        'มีอะไรให้ผมรับใช้สอบถามได้ตลอดเวลาเลยนะครับ! ยินดีต้อนรับครับ ✨',
        'กดเลือกดูหลักสูตร หรือคุยกับผมได้เลยนะครับ ผมรอคุยอยู่น้า! 🤖'
    ];
    const greeting = greetings[Math.floor(Math.random() * greetings.length)];
    showVoiceSubtitle(greeting, 4000);
    playDirectVoiceTTS(greeting);
}

// Attach explicitly to window for inline onclick reliability
window.triggerHeadPet = triggerHeadPet;
window.triggerEarReaction = triggerEarReaction;
window.triggerShyReaction = triggerShyReaction;
window.triggerWinkReaction = triggerWinkReaction;
window.triggerMouthReaction = triggerMouthReaction;
window.spawnEmotionParticle = spawnEmotionParticle;
window.spawnParticleBurst = spawnParticleBurst;

