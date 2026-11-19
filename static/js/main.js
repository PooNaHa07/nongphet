// ===== QR Code ในเครื่อง (static/vendor/qrcode, qrcode-generator) ใช้ได้แม้ไม่มีอินเทอร์เน็ต =====
function makeQrDataUrl(text, cellSize = 6) {
    if (typeof qrcode === 'undefined') return '';
    const qr = qrcode(0, 'M');
    qr.addData(String(text || ''));
    qr.make();
    return qr.createDataURL(cellSize, 2);
}

function renderStaticQrCodes(root = document) {
    root.querySelectorAll('img[data-qr]').forEach(img => {
        if (!img.src) img.src = makeQrDataUrl(img.dataset.qr);
    });
}
document.addEventListener('DOMContentLoaded', () => renderStaticQrCodes());


const clientAudioCache = new Map();
let quickFeedbackAudioCtx = null;
let chimeAudioCtx = null;

// -----------------------------------------------------------------------------
// Procedural Sci-Fi Synthesizer Sound Engine (Web Audio API Chime Earcons)
// ปิ๊ง! สัญญาณเสียงเปิดรับฟัง (listen), ปิดรับฟัง (done), และแตะแทรก (barge_in)
// -----------------------------------------------------------------------------
function playEarconChime(type = 'listen') {
    try {
        if (!chimeAudioCtx) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) {
                chimeAudioCtx = new AudioContextClass();
            }
        }
        if (!chimeAudioCtx) return;
        if (chimeAudioCtx.state === 'suspended') {
            chimeAudioCtx.resume().catch(() => {});
        }
        const now = chimeAudioCtx.currentTime;
        const osc = chimeAudioCtx.createOscillator();
        const gain = chimeAudioCtx.createGain();

        if (type === 'listen') {
            // Soft rising chime: C6 (1046.50 Hz) -> E6 (1318.51 Hz) in 160ms (ปิ๊ง!)
            osc.type = 'sine';
            osc.frequency.setValueAtTime(1046.50, now);
            osc.frequency.exponentialRampToValueAtTime(1318.51, now + 0.08);
            gain.gain.setValueAtTime(0.001, now);
            gain.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.20);
            osc.connect(gain);
            gain.connect(chimeAudioCtx.destination);
            osc.start(now);
            osc.stop(now + 0.21);
        } else if (type === 'done') {
            // Soft falling chime: G5 (783.99 Hz) -> C5 (523.25 Hz) in 180ms
            osc.type = 'sine';
            osc.frequency.setValueAtTime(783.99, now);
            osc.frequency.exponentialRampToValueAtTime(523.25, now + 0.10);
            gain.gain.setValueAtTime(0.001, now);
            gain.gain.exponentialRampToValueAtTime(0.06, now + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
            osc.connect(gain);
            gain.connect(chimeAudioCtx.destination);
            osc.start(now);
            osc.stop(now + 0.23);
        } else if (type === 'barge_in') {
            // Crisp high-pitched tick / blip: 1200 Hz -> 800 Hz in 45ms
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(1200, now);
            osc.frequency.exponentialRampToValueAtTime(800, now + 0.04);
            gain.gain.setValueAtTime(0.09, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
            osc.connect(gain);
            gain.connect(chimeAudioCtx.destination);
            osc.start(now);
            osc.stop(now + 0.055);
        }
    } catch (e) {
        console.warn('playEarconChime error:', e);
    }
}
window.playEarconChime = playEarconChime;

function playQuickAudioFeedback() {
    playEarconChime('listen');
}

// -----------------------------------------------------------------------------
// Preloaded Instant Conversational Fillers (<100ms Reaction)
// -----------------------------------------------------------------------------
window.preloadedFillers = [];

async function preloadFillerAudios() {
    try {
        const fillers = [0, 1, 2, 3, 4];
        for (const idx of fillers) {
            fetch(`/api/tts/filler?index=${idx}`)
                .then(res => res.json())
                .then(data => {
                    if (data && data.audio_base64) {
                        const mime = (data.audio_format === 'wav') ? 'audio/wav' : 'audio/mp3';
                        window.preloadedFillers.push({
                            text: data.text,
                            uri: `data:${mime};base64,` + data.audio_base64
                        });
                    }
                })
                .catch(() => {});
        }
    } catch (e) {}
}
window.preloadFillerAudios = preloadFillerAudios;

function playInstantFiller(onEndedCallback) {
    try {
        let uri = null;
        if (window.preloadedFillers && window.preloadedFillers.length > 0) {
            const randomItem = window.preloadedFillers[Math.floor(Math.random() * window.preloadedFillers.length)];
            uri = randomItem.uri;
        }

        if (window.currentFillerAudio) {
            try { window.currentFillerAudio.pause(); } catch (e) {}
            window.currentFillerAudio = null;
        }

        const audio = new Audio();
        window.currentFillerAudio = audio;
        audio.volume = 1.0;

        let hasEnded = false;
        const finishFiller = () => {
            if (hasEnded) return;
            hasEnded = true;
            if (window.currentFillerAudio === audio) {
                window.currentFillerAudio = null;
            }
            if (typeof onEndedCallback === 'function') {
                onEndedCallback();
            }
        };

        audio.onended = finishFiller;
        audio.onerror = finishFiller;

        if (uri) {
            audio.src = uri;
            audio.play().then(() => {
                isSpeakingTTS = true;
                setEmotion('speaking');
                if (typeof startLipSyncAnalysis === 'function') startLipSyncAnalysis();
            }).catch(() => {
                finishFiller();
            });
        } else {
            fetch('/api/tts/filler')
                .then(res => res.json())
                .then(data => {
                    if (data && data.audio_base64 && isWaitingChatResponse) {
                        const mime = (data.audio_format === 'wav') ? 'audio/wav' : 'audio/mp3';
                        audio.src = `data:${mime};base64,` + data.audio_base64;
                        audio.play().then(() => {
                            isSpeakingTTS = true;
                            setEmotion('speaking');
                            if (typeof startLipSyncAnalysis === 'function') startLipSyncAnalysis();
                        }).catch(() => finishFiller());
                    } else {
                        finishFiller();
                    }
                })
                .catch(() => finishFiller());
        }
        return audio;
    } catch (e) {
        console.warn('playInstantFiller error:', e);
        if (typeof onEndedCallback === 'function') onEndedCallback();
        return null;
    }
}
window.playInstantFiller = playInstantFiller;

// -----------------------------------------------------------------------------
// Emergency Touch-to-Barge-In (ระบบแตะแทรกเพื่อสั่งให้บอทหยุดพูดทันที)
// -----------------------------------------------------------------------------
function handleBargeInAction() {
    if (isSpeakingTTS || isPlayingQueue || window.currentFillerAudio || isWaitingChatResponse) {
        console.log('🛑 [Touch Barge-In] ขัดจังหวะเสียงบอทสำเร็จ -> ตัดเสียงและเปิดไมค์รับฟังทันที');
        stopAllSpeech();
        if (typeof cancelProactiveAutoListenWindow === 'function') cancelProactiveAutoListenWindow();
        playEarconChime('barge_in');
        setEmotion('listening');
        if (typeof setRealtimeVoiceStatus === 'function') {
            setRealtimeVoiceStatus('listening', '🎙️ น้องเพชรหยุดฟังคุณแล้วค่ะ... พูดได้เลยนะคะ ✨');
        }
        setTimeout(() => {
            playEarconChime('listen');
            startRecognitionSafe();
        }, 220);
    }
}
window.handleBargeInAction = handleBargeInAction;

function isEchoOfBotSpeech(spokenText, botText) {
    if (!botText || !spokenText) return false;
    const cleanSpoken = spokenText.replace(/[\s\-_,.!?~*#]/g, '').toLowerCase();
    const cleanBot = botText.replace(/[\s\-_,.!?~*#]/g, '').toLowerCase();
    if (cleanSpoken.length >= 3 && cleanBot.includes(cleanSpoken)) {
        return true;
    }
    return false;
}
window.isEchoOfBotSpeech = isEchoOfBotSpeech;

function stripEmojiAndIcons(str) {
    if (!str) return '';
    let t = str;
    for (const delim of ['---', '💡 ถามต่อยอด', 'ถามต่อยอดกับน้องเพชร', '💡 แนะนำคำถาม', 'คำถามที่น่าสนใจ', '💡 Follow-up', '💡 推荐问题', '❓ คำถาม']) {
        if (t.includes(delim)) {
            t = t.split(delim)[0].trim();
        }
    }
    return t
        .replace(/[\p{Extended_Pictographic}\u2600-\u27BF\uFE0E\uFE0F\u200D\u2300-\u23FF\u2B50\u2B55]/gu, '')
        .replace(/[*#_~>•\-=|`]/g, ' ')
        .replace(/[^\w\s\u0E00-\u0E7F\u4E00-\u9FA5.,!?'"-]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}
// -----------------------------------------------------------------------------
// Universal Kiosk Toast Notification System (Replaces disruptive window.alert)
// -----------------------------------------------------------------------------
function showAppToast(message, type = 'info', duration = 3500) {
    if (typeof window === 'undefined') return;
    let container = document.getElementById('appToastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'appToastContainer';
        container.className = 'fixed top-5 left-1/2 -translate-x-1/2 z-[99999] flex flex-col items-center gap-2 pointer-events-none transition-all duration-300';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    const bgColors = {
        info: 'bg-slate-900/95 border-blue-500/50 text-blue-100',
        success: 'bg-emerald-950/95 border-emerald-500/50 text-emerald-100',
        warning: 'bg-amber-950/95 border-amber-500/50 text-amber-100',
        error: 'bg-rose-950/95 border-rose-500/50 text-rose-100'
    };
    const icons = {
        info: '<i class=\"fa-solid fa-circle-info text-blue-400\"></i>',
        success: '<i class=\"fa-solid fa-circle-check text-emerald-400\"></i>',
        warning: '<i class=\"fa-solid fa-triangle-exclamation text-amber-400\"></i>',
        error: '<i class=\"fa-solid fa-circle-exclamation text-rose-400\"></i>'
    };
    toast.className = 'flex items-center gap-2.5 px-4 py-2.5 rounded-2xl border shadow-2xl backdrop-blur-md text-sm font-medium pointer-events-auto transition-all duration-300 transform translate-y-0 opacity-100 ' + (bgColors[type] || bgColors.info);
    toast.innerHTML = '<span>' + (icons[type] || icons.info) + '</span><span>' + message + '</span>';
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}
window.showAppToast = showAppToast;
/**
 * nongphet AI Smart Guide - Main Core JS
 * Handles View modes, Routing, Clock, Weather, Voice Gender & Neural TTS, Speech-to-Text
 */

let currentVisionIndex = 0;
let uploadedVisionFile = null;
let autoSpeak = true;
let currentLang = 'th';
let currentVoiceGender = 'female'; // 'female' (Premwadee - Default Female Voice)
let isSpeakingTTS = false;

// -----------------------------------------------------------------------------
// Cross-Screen BroadcastChannel for Zero-Latency Lip-Sync & Air Gestures
// -----------------------------------------------------------------------------
const lipSyncBroadcast = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('nongphet_sync') : null;

// ประกาศตนเองเป็น Audio Master (จอสัมผัสหลัก 10.1 นิ้ว เป็นผู้คุมเสียงและไมโครโฟนเพียงผู้เดียว)
function announceKioskMaster() {
    if (lipSyncBroadcast) {
        lipSyncBroadcast.postMessage({
            type: 'kiosk_master_presence',
            role: 'master',
            timestamp: Date.now()
        });
    }
}
announceKioskMaster();
setInterval(announceKioskMaster, 2500);

if (lipSyncBroadcast) {
    lipSyncBroadcast.onmessage = (e) => {
        if (!e.data) return;
        if (e.data.type === 'barge_in') {
            console.log('🛑 [Broadcast Barge-In] ได้รับสัญญาณแตะแทรกจากจอใบหน้า');
            if (typeof handleBargeInAction === 'function') {
                handleBargeInAction();
            }
            return;
        }
        if (e.data.type === 'person_detected') {
            console.log('👀 [Broadcast] ได้รับสัญญาณตรวจพบคนจากจอใบหน้า -> เริ่มการต้อนรับอัตโนมัติ');
            if (typeof triggerAutoGreeting === 'function') {
                triggerAutoGreeting(e.data.distance || 85, e.data.source || 'emotion_screen');
            }
            return;
        }
        if (e.data.type === 'delegate_tts' && e.data.text) {
            console.log('🗣️ [Master Audio Bus] เล่นเสียงตอบรับที่ส่งมาจากจอใบหน้า:', e.data.text);
            playTTS(e.data.text, null, null, e.data.lang || null);
            return;
        }
        if (e.data.type === 'gesture') {
            if (e.data.gesture === 'wave') {
                console.log('👋 [Main Screen] Air Gesture Wave detected!');
                if (typeof showIotToast === 'function') {
                    showIotToast('👋 น้องเพชรตรวจพบการโบกมือทักทาย!', 'ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีค่ะ');
                }
            } else if (e.data.gesture === 'swipe') {
                console.log('↔️ [Main Screen] Air Gesture Swipe:', e.data.dir);
                if (e.data.dir === 'right' && typeof nextVisionLocation === 'function') {
                    nextVisionLocation();
                } else if (e.data.dir === 'left' && typeof prevVisionLocation === 'function') {
                    prevVisionLocation();
                }
            }
        }
    };
}

let lipSyncAnimFrame = null;
function startLipSyncAnalysis() {
    if (!lipSyncBroadcast) return;
    cancelAnimationFrame(lipSyncAnimFrame);
    function update() {
        if (!isSpeakingTTS) {
            lipSyncBroadcast.postMessage({ type: 'lipsync', amp: 0 });
            return;
        }
        const t = performance.now() / 140;
        const normAmp = 0.35 + 0.45 * Math.abs(Math.sin(t) * Math.cos(t * 1.6));
        // ช่วงรอเสียงประโยคถัดไป: ปิดปากไว้ แต่ยังถือว่ากำลังพูด (ไมค์ยังปิด กันเสียงสะท้อน)
        lipSyncBroadcast.postMessage({ type: 'lipsync', amp: ttsGapActive ? 0 : normAmp });
        lipSyncAnimFrame = requestAnimationFrame(update);
    }
    update();
}

// -----------------------------------------------------------------------------
// ระบบปลดล็อก Browser Autoplay Policy & Microphone Permission อัตโนมัติ
// -----------------------------------------------------------------------------
let isBrowserAudioUnlocked = false;
let pendingAutoplayTTS = null;

function showAudioUnlockPrompt(message = '👆 แตะหน้าจอ 1 ครั้ง เพื่อเปิดระบบเสียงและไมโครโฟนอัตโนมัติ') {
    let el = document.getElementById('audioUnlockPrompt');
    if (!el) {
        el = document.createElement('div');
        el.id = 'audioUnlockPrompt';
        el.className = 'fixed bottom-6 left-1/2 -translate-x-1/2 z-[99999] px-5 py-3 rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white font-bold text-sm shadow-2xl border border-white/20 flex items-center gap-3 cursor-pointer animate-bounce hover:scale-105 transition-transform backdrop-blur-md select-none';
        el.onclick = () => {
            unlockBrowserAudioAndMic(true);
        };
        document.body.appendChild(el);
    }
    el.innerHTML = '<i class="fa-solid fa-hand-pointer text-amber-300 animate-pulse text-lg"></i><span>' + message + '</span>';
    el.style.display = 'flex';
}
window.showAudioUnlockPrompt = showAudioUnlockPrompt;

function hideAudioUnlockPrompt() {
    const el = document.getElementById('audioUnlockPrompt');
    if (el) {
        el.style.opacity = '0';
        el.style.transform = 'translate(-50%, 20px)';
        el.style.transition = 'all 0.3s ease';
        setTimeout(() => {
            if (el.parentNode) el.parentNode.removeChild(el);
        }, 320);
    }
}
window.hideAudioUnlockPrompt = hideAudioUnlockPrompt;

function getAudioPlayer() {
    let p = document.getElementById('audioPlayer');
    if (!p) {
        p = document.createElement('audio');
        p.id = 'audioPlayer';
        p.className = 'hidden';
        p.preload = 'auto';
        document.body.appendChild(p);
    }
    return p;
}
window.getAudioPlayer = getAudioPlayer;

async function unlockBrowserAudioAndMic(userInitiated = false) {
    if (isBrowserAudioUnlocked && !userInitiated) return;
    isBrowserAudioUnlocked = true;

    // 1. ปลดล็อก AudioContext
    try {
        if (typeof getChimeAudioContext === 'function') {
            const ctx = getChimeAudioContext();
            if (ctx && ctx.state === 'suspended') {
                await ctx.resume();
            }
        }
    } catch (e) {}

    // 2. ปลดล็อก <audio id="audioPlayer">
    const p = getAudioPlayer();
    if (p) {
        p.muted = false;
        p.volume = 1.0;
        try {
            p.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            await p.play();
            p.pause();
        } catch (e) {}
    }

    // 3. Pre-flight Mic Permission
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach(t => t.stop());
            console.log('🎙️ [Mic Permission] ได้รับสิทธิ์ใช้งานไมโครโฟนสมบูรณ์');
        } catch (err) {
            console.warn('🎙️ [Mic Permission Warning]:', err.name);
        }
    }

    hideAudioUnlockPrompt();

    // 4. หากมีเสียงทักทายต้อนรับค้างอยู่จากการตรวจพบคนก่อนหน้านี้ -> เล่นเสียงนั้นทันที
    if (pendingAutoplayTTS) {
        const item = pendingAutoplayTTS;
        pendingAutoplayTTS = null;
        console.log('🔊 [Autoplay Recovery] เล่นเสียงต้อนรับที่ค้างอยู่ทันที:', item.text);
        if (typeof playTTS === 'function') {
            playTTS(item.text, item.btnElement, item.onEndedCallback, item.forcedLang);
        }
    }
}
window.unlockBrowserAudioAndMic = unlockBrowserAudioAndMic;

window.addEventListener('DOMContentLoaded', () => {
    // ปลดล็อก Browser Autoplay Policy & Mic ทันทีเมื่อผู้ใช้แตะหรือคลิกหน้าจอครั้งแรก
    ['click', 'touchstart', 'pointerdown', 'mousedown', 'keydown'].forEach(evt => {
        window.addEventListener(evt, () => unlockBrowserAudioAndMic(false), { once: true, passive: true });
    });

    fetchLiveWeather();
    startClock();
    // Auto-detect mode from URL parameters (e.g. ?mode=kiosk on Raspberry Pi)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'kiosk' || urlParams.get('kiosk') === '1') {
        switchViewMode('kiosk');
    } else {
        switchViewMode('desktop');
    }
    updateSidebarActive('screen-welcome');
    updateMobileNavActive('screen-welcome');
    initCrossScreenGazeTracking();

    // Touch-to-Barge-In บนจอหลัก: หากแตะจอขณะที่บอทกำลังส่งเสียงพูด ให้ตัดเสียงและเปิดไมค์ทันที
    document.addEventListener('pointerdown', (e) => {
        if (!isSpeakingTTS && !isPlayingQueue && !window.currentFillerAudio) return;
        const target = e.target;
        if (target && (target.closest('input') || target.closest('textarea') || target.closest('button') || target.closest('select') || target.closest('a'))) {
            // แตะปุ่มหรือช่องพิมพ์: ตัดเสียงพูดเพื่อไม่ให้รบกวน
            stopAllSpeech();
            return;
        }
        if (typeof handleBargeInAction === 'function') {
            handleBargeInAction();
        }
    }, { passive: true });

    // Preload Conversational Fillers (<100ms Reaction)
    setTimeout(() => {
        if (typeof preloadFillerAudios === 'function') {
            preloadFillerAudios();
        }
    }, 1500);
});

function startClock() {
    function updateTime() {
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const timeString = `${hours}:${minutes} น.`;
        const clockHeader = document.getElementById('liveClockDisplay');
        const clockPhone = document.getElementById('phoneClock');
        if (clockHeader) clockHeader.textContent = timeString;
        if (clockPhone) clockPhone.textContent = `${hours}:${minutes}`;
    }
    updateTime();
    setInterval(updateTime, 1000);
}

async function fetchLiveWeather() {
    try {
        const res = await fetch('/weather');
        const data = await res.json();
        if (data.weather) {
            const cleanWeather = data.weather.replace(/\*\*/g, '').replace(/\*/g, '').trim();
            const wt = document.getElementById('weatherText');
            const wth = document.getElementById('weatherTextHeader');
            if (wt) wt.textContent = cleanWeather;
            if (wth) wth.textContent = cleanWeather.length > 55 ? cleanWeather.substring(0, 55) + '...' : cleanWeather;
        }
    } catch (e) {
        // Default fallback
    }
}

function changeLanguage(lang) {
    currentLang = lang;
    const sel = document.getElementById('appLanguageSelect');
    if (sel) sel.value = lang;
    if (recognition) {
        recognition.lang = lang === 'en' ? 'en-US' : (lang === 'zh' ? 'zh-CN' : (lang === 'ja' ? 'ja-JP' : (lang === 'ko' ? 'ko-KR' : 'th-TH')));
    }
}

function setLangAndNotify(lang) {
    changeLanguage(lang);
    if (lang === 'en') {
        sendQuickMessage('Hello! Please introduce yourself and show what you can do in English');
    } else {
        sendQuickMessage('สวัสดีค่ะ แนะนำตัวเองและบริการทั้งหมดให้ฟังหน่อยนะคะ');
    }
    navigateTo('screen-chat');
}

function switchViewMode(mode) {
    const appStage = document.getElementById('app-stage');
    const phoneContainer = document.getElementById('interactive-phone-container');
    const posterContainer = document.getElementById('poster-container');
    const desktopSidebar = document.getElementById('desktop-sidebar');
    const phoneDecors = document.querySelectorAll('.phone-decor');
    const mobileBottomNav = document.getElementById('mobile-bottom-nav');
    
    const btnKiosk = document.getElementById('btn-mode-kiosk');
    const btnDesktop = document.getElementById('btn-mode-desktop');
    const btnPhone = document.getElementById('btn-mode-phone');
    const btnPoster = document.getElementById('btn-mode-poster');

    // Reset buttons style
    [btnKiosk, btnDesktop, btnPhone, btnPoster].forEach(btn => {
        if (btn) btn.className = 'px-2.5 sm:px-3 py-1 rounded-lg font-medium text-xs text-slate-400 hover:text-white transition';
    });

    if (mode === 'kiosk') {
        // True 10.1" Hardware Blueprint Fullscreen Kiosk Mode
        posterContainer.classList.add('hidden');
        phoneContainer.classList.remove('hidden');
        if (desktopSidebar) desktopSidebar.classList.add('hidden');
        if (mobileBottomNav) mobileBottomNav.classList.add('hidden');
        phoneDecors.forEach(el => el.classList.add('hidden'));

        // Maximize app stage to occupy full viewport
        appStage.className = 'w-full h-full max-w-none max-h-none rounded-none border-none shadow-none flex flex-col overflow-hidden relative m-0 p-0 transition-all duration-300';
        if (btnKiosk) btnKiosk.className = 'px-2.5 sm:px-3 py-1 rounded-lg font-bold text-xs transition bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500 text-white shadow-md';
    } else if (mode === 'poster') {
        phoneContainer.classList.add('hidden');
        posterContainer.classList.remove('hidden');
        if (mobileBottomNav) mobileBottomNav.classList.add('hidden');
        if (btnPoster) btnPoster.className = 'px-2.5 sm:px-3 py-1 rounded-lg font-bold text-xs transition bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md';
    } else if (mode === 'phone') {
        posterContainer.classList.add('hidden');
        phoneContainer.classList.remove('hidden');
        
        // Switch to phone frame mode (simulator on desktop, natural on mobile)
        appStage.className = 'phone-frame flex flex-col my-auto transition-all duration-300';
        if (desktopSidebar) desktopSidebar.classList.add('hidden');
        if (window.innerWidth >= 640) {
            phoneDecors.forEach(el => el.classList.remove('hidden'));
        } else {
            phoneDecors.forEach(el => el.classList.add('hidden'));
        }
        if (mobileBottomNav) mobileBottomNav.classList.remove('hidden');
        
        if (btnPhone) btnPhone.className = 'px-2.5 sm:px-3 py-1 rounded-lg font-bold text-xs transition bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md';
    } else {
        // Desktop / Responsive Adaptive mode (Default for all devices)
        posterContainer.classList.add('hidden');
        phoneContainer.classList.remove('hidden');

        // Switch to fluid adaptive workspace
        appStage.className = 'w-full max-w-7xl h-full rounded-2xl md:rounded-3xl border border-white/10 glass-base shadow-2xl flex flex-col lg:flex-row overflow-hidden relative transition-all duration-300';
        
        if (desktopSidebar) {
            if (window.innerWidth >= 1024) {
                desktopSidebar.classList.remove('hidden');
            } else {
                desktopSidebar.classList.add('hidden');
            }
        }
        phoneDecors.forEach(el => el.classList.add('hidden'));

        if (mobileBottomNav) {
            if (window.innerWidth < 1024) {
                mobileBottomNav.classList.remove('hidden');
            } else {
                mobileBottomNav.classList.add('hidden');
            }
        }

        if (btnDesktop) btnDesktop.className = 'px-2.5 sm:px-3 py-1 rounded-lg font-bold text-xs transition bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md';
    }
}

function toggleKioskFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
        switchViewMode('kiosk');
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen().catch(() => {});
        }
        switchViewMode('desktop');
    }
}

// Keep layout in sync on device orientation change or window resize
window.addEventListener('resize', () => {
    const desktopSidebar = document.getElementById('desktop-sidebar');
    const mobileBottomNav = document.getElementById('mobile-bottom-nav');
    const appStage = document.getElementById('app-stage');
    
    if (appStage && !appStage.classList.contains('phone-frame')) {
        if (window.innerWidth >= 1024) {
            if (desktopSidebar) desktopSidebar.classList.remove('hidden');
            if (mobileBottomNav) mobileBottomNav.classList.add('hidden');
        } else {
            if (desktopSidebar) desktopSidebar.classList.add('hidden');
            if (mobileBottomNav) mobileBottomNav.classList.remove('hidden');
        }
    }
});

function selectScreenFromPoster(screenId) {
    switchViewMode('desktop');
    navigateTo(screenId);
}

function updateSidebarActive(screenId) {
    document.querySelectorAll('.sidebar-nav-item').forEach(item => {
        if (item.getAttribute('data-screen') === screenId) {
            item.classList.add('bg-blue-600/30', 'text-white', 'border-blue-500/50', 'shadow-md');
            item.classList.remove('text-slate-300', 'border-transparent');
        } else {
            item.classList.remove('bg-blue-600/30', 'text-white', 'border-blue-500/50', 'shadow-md');
            item.classList.add('text-slate-300', 'border-transparent');
        }
    });
}

function updateMobileNavActive(screenId) {
    document.querySelectorAll('.mobile-nav-btn').forEach(btn => {
        if (btn.getAttribute('data-mobile-nav') === screenId) {
            btn.classList.add('text-blue-400', 'font-black');
            btn.classList.remove('text-slate-400');
        } else {
            btn.classList.remove('text-blue-400', 'font-black');
            btn.classList.add('text-slate-400');
        }
    });
}

function navigateTo(screenId) {
    if (screenId !== 'screen-sign-language' && typeof stopSignLanguageCamera === 'function' && typeof signIsCameraActive !== 'undefined' && signIsCameraActive) {
        stopSignLanguageCamera();
    }
    document.querySelectorAll('.screen-view').forEach(screen => {
        screen.classList.remove('active');
    });
    const target = document.getElementById(screenId);
    if (target) {
        target.classList.add('active');
        target.scrollTop = 0;
    }
    updateSidebarActive(screenId);
    updateMobileNavActive(screenId);
}

function selectPlace(placeName) {
    navigateTo('screen-chat');
    sendQuickMessage(`ช่วยแนะนำข้อมูลการท่องเที่ยว จุดถ่ายรูปสวยๆ และร้านอาหารแนะนำของ "${placeName}" อย่างละเอียดหน่อยครับ`);
}

function selectCourse(courseName) {
    navigateTo('screen-chat');
    sendQuickMessage(`สาขาวิชา${courseName} เรียนอะไร`);
}

function openGoogleMapsSearch(query) {
    window.open(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`, '_blank');
}

function toggleAutoSpeak() {
    autoSpeak = !autoSpeak;
    const icon = document.getElementById('autoSpeakIcon');
    const btn = document.getElementById('toggleAutoSpeakBtn');
    if (autoSpeak) {
        icon.className = 'fa-solid fa-volume-high text-emerald-400';
        btn.title = 'ปิดเสียงอ่านอัตโนมัติ';
    } else {
        icon.className = 'fa-solid fa-volume-xmark text-slate-400';
        btn.title = 'เปิดเสียงอ่านอัตโนมัติ';
    }
}

function toggleVoiceGender() {
    currentVoiceGender = 'female';
    if (typeof showAppToast === 'function') {
        showAppToast('น้องเพชรใช้เสียงทางการ: เปรมวดี Neural (สดใส นุ่มนวล)', 'info');
    }
}

function formatMarkdown(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

// -----------------------------------------------------------------------------
// Robot Emotion Display Sync Helper
// -----------------------------------------------------------------------------
function setEmotion(state) {
    if (!state) return;
    try {
        // 1. ส่งสัญญาณข้ามหน้าจอทันทีแบบ 0ms ด้วย BroadcastChannel (Dual-Screen Sync)
        if (lipSyncBroadcast) {
            lipSyncBroadcast.postMessage({ type: 'emotion', state: state });
        }
        // 2. ซิงค์สถานะเข้าสู่ Flask Backend และกระจายผ่าน SSE
        fetch('/api/emotion/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: state }),
            keepalive: true
        }).catch(() => {});
    } catch (e) {}
}


// -----------------------------------------------------------------------------
// Neural TTS Audio Engine (รองรับ 3 ภาษา th, en, zh)
// -----------------------------------------------------------------------------
// Voice Synthesis Engine (Edge Neural TTS & Browser Fallback)
// -----------------------------------------------------------------------------
function fallbackBrowserSpeechMain(text, lang, btnElement, onEndedCallback) {
    // นโยบายเสียงเดียวทั้งระบบ: ไม่ใช้เสียงของเบราว์เซอร์ (speechSynthesis) เพราะเป็นคนละเสียงกับน้องเพชร
    // แสดงข้อความอย่างเดียว แล้วจบรอบการพูดตามปกติ
    setTimeout(() => {
        isSpeakingTTS = false;
        setEmotion('idle');
        if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
        if (typeof onEndedCallback === 'function') onEndedCallback();
    }, 350);
}

// -----------------------------------------------------------------------------
// Sentence Splitting & Pipeline Streaming TTS Engine
// -----------------------------------------------------------------------------
let ttsQueue = [];
let ttsQueueIndex = 0;
let ttsQueueAbortController = null;
let isPlayingQueue = false;
let ttsGapActive = false;       // กำลังรอเสียงประโยคถัดไป (ปากหยุดขยับ)

function splitTextIntoSentences(text, maxSentenceLen = 140) {
    if (!text) return [];
    let cleaned = stripEmojiAndIcons(text)
        .replace(/[*#_~`>]/g, ' ')
        .replace(/https?:\/\/\S+/g, '')
        .trim();
    if (!cleaned) return [];

    const rawParagraphs = cleaned.split(/\n+/).map(p => p.trim()).filter(Boolean);
    const rawSentences = [];
    for (const para of rawParagraphs) {
        // แยกประโยคตามหางเสียงลงท้ายภาษาไทย หรือเครื่องหมายวรรคตอน (รองรับทั้งที่มีและไม่มี space)
        const parts = para.split(/(?<=ค่ะ|นะคะ|นะค้า|ค่า|จ้า|จ้ะ|[!?;\.:])(?:\s+|(?=[ก-ฮA-Za-z]))/);
        for (const part of parts) {
            const p = part.trim();
            if (p) rawSentences.push(p);
        }
    }
    // รวมท่อนสั้น (< 22 ตัวอักษร) เข้ากับท่อนถัดไป เพื่อให้จังหวะพูดธรรมชาติ ไม่ห้วนสั้นเกินไป
    const merged = [];
    let buffer = '';
    for (let i = 0; i < rawSentences.length; i++) {
        const s = rawSentences[i];
        if (buffer) {
            buffer = buffer + ' ' + s;
            if (buffer.length >= 26 || i === rawSentences.length - 1) {
                merged.push(buffer.trim());
                buffer = '';
            }
        } else if (s.length < 22 && i < rawSentences.length - 1) {
            buffer = s;
        } else {
            merged.push(s);
        }
    }
    if (buffer) merged.push(buffer.trim());
    return merged.length > 0 ? merged : [cleaned];
}

// ขอเสียงจาก /tts คืน JSON (หรือ null) — cacheOnly=true ถามแค่ว่ามีเสียงที่อัดเก็บไว้หรือไม่
async function requestTTS(text, lang, signal, cacheOnly = false) {
    try {
        const response = await fetch('/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, lang: lang, gender: 'female', fast_mode: false, cache_only: cacheOnly }),
            signal: signal
        });
        return await response.json();
    } catch (e) {
        if (e.name !== 'AbortError') console.warn('TTS fetch error:', e);
        return null;
    }
}

function ttsDataToUri(data) {
    const mime = (data.audio_format === 'wav' || data.audio_base64.startsWith('UklGR')) ? 'audio/wav' : 'audio/mp3';
    return `data:${mime};base64,` + data.audio_base64;
}

// ความยาวเสียง (วินาที) จาก metadata ถ้าอ่านไม่ได้ ประมาณจากจำนวนตัวอักษร (~12 ตัว/วินาที)
function audioDurationSec(uri, fallbackSec) {
    return new Promise(resolve => {
        const probe = new Audio();
        let settled = false;
        const done = (v) => { if (settled) return; settled = true; resolve(v); };
        setTimeout(() => done(fallbackSec), 1500);
        probe.preload = 'metadata';
        probe.onloadedmetadata = () => done(isFinite(probe.duration) ? probe.duration : fallbackSec);
        probe.onerror = () => done(fallbackSec);
        probe.src = uri;
    });
}

function stopAllSpeech() {
    lastBotSpeechEndTime = Date.now();
    isPlayingQueue = false;
    ttsGapActive = false;
    ttsQueue = [];
    ttsQueueIndex = 0;
    if (ttsQueueAbortController) {
        try { ttsQueueAbortController.abort(); } catch (e) {}
        ttsQueueAbortController = null;
    }
    if (window.currentFillerAudio) {
        try {
            window.currentFillerAudio.pause();
            window.currentFillerAudio.currentTime = 0;
        } catch (e) {}
        window.currentFillerAudio = null;
    }
    const audioPlayer = getAudioPlayer();
    if (audioPlayer) {
        audioPlayer.pause();
        audioPlayer.currentTime = 0;
    }
    if ('speechSynthesis' in window) {
        try { window.speechSynthesis.cancel(); } catch (e) {}
    }
    isSpeakingTTS = false;
    isWaitingChatResponse = false;
    setEmotion('idle');
    if (lipSyncBroadcast) lipSyncBroadcast.postMessage({ type: 'lipsync', amp: 0 });
}

async function playTTS(text, btnElement = null, onEndedCallback = null, forcedLang = null) {
    const speechText = stripEmojiAndIcons(text);
    if (!speechText) return;
    lastBotSpokenText = speechText;
    const activeLang = forcedLang || currentLang || 'th';

    // 1. ตัดไมค์ทันทีและหยุดคิวเสียงเดิม (Half-duplex Control ป้องกันเสียงสะท้อน)
    stopRecognitionSafe();
    stopAllSpeech();
    isSpeakingTTS = true;

    const audioPlayer = getAudioPlayer();

    const handlePlaybackFinished = () => {
        lastBotSpeechEndTime = Date.now();
        isPlayingQueue = false;
        if (lipSyncBroadcast) lipSyncBroadcast.postMessage({ type: 'lipsync', amp: 0 });
        if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
        fetch('/api/iot/led', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: 'idle' })
        }).catch(() => {});
        setTimeout(() => {
            isSpeakingTTS = false;
            setEmotion('idle');
            if (typeof onEndedCallback === 'function') onEndedCallback();
        }, 350);
    };

    const cacheKey = activeLang + '_' + speechText;

    // ถ้ามีในแคช RAM ของเบราว์เซอร์แล้ว เล่นได้ทันที (0ms Latency)
    if (clientAudioCache.has(cacheKey)) {
        const cachedUri = clientAudioCache.get(cacheKey);
        audioPlayer.src = cachedUri;
        audioPlayer.volume = 1.0;
        audioPlayer.muted = false;
        audioPlayer.onended = handlePlaybackFinished;
        audioPlayer.onerror = handlePlaybackFinished;
        audioPlayer.play().then(() => {
            isSpeakingTTS = true;
            setEmotion('speaking');
            fetch('/api/iot/led', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: 'speaking' })
            }).catch(() => {});
            if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-circle-stop text-rose-500 animate-pulse"></i> หยุดเสียง';
            startLipSyncAnalysis();
        }).catch((playErr) => {
            if (playErr && (playErr.name === 'NotAllowedError' || playErr.name === 'NotSupportedError')) {
                console.warn('🔇 [Autoplay Shield] เบราว์เซอร์บล็อกการเล่นเสียงอัตโนมัติ รอการแตะหน้าจอ 1 ครั้ง');
                pendingAutoplayTTS = {
                    text: speechText,
                    btnElement: btnElement,
                    onEndedCallback: onEndedCallback,
                    forcedLang: activeLang
                };
                showAudioUnlockPrompt('👆 แตะหน้าจอ 1 ครั้ง เพื่อเปิดระบบเสียงและไมโครโฟนอัตโนมัติ');
            }
            handlePlaybackFinished();
        });
        return;
    }

    if (btnElement) {
        btnElement.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-blue-500"></i> กำลังโหลดเสียง...';
    }
    setEmotion('thinking');

    ttsQueueAbortController = new AbortController();
    const signal = ttsQueueAbortController.signal;

    const markSpeaking = () => {
        isSpeakingTTS = true;
        ttsGapActive = false;
        setEmotion('speaking');
        fetch('/api/iot/led', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: 'speaking' })
        }).catch(() => {});
        if (btnElement) {
            btnElement.innerHTML = '<i class="fa-solid fa-circle-stop text-rose-500 animate-pulse"></i> หยุดเสียง';
        }
        startLipSyncAnalysis();
    };

    const handleAutoplayBlock = (playErr) => {
        if (playErr && (playErr.name === 'NotAllowedError' || playErr.name === 'NotSupportedError')) {
            console.warn('🔇 [Autoplay Shield] เบราว์เซอร์บล็อกเสียง รอการแตะหน้าจอเพื่อปลดล็อก');
            pendingAutoplayTTS = {
                text: speechText,
                btnElement: btnElement,
                onEndedCallback: onEndedCallback,
                forcedLang: activeLang
            };
            showAudioUnlockPrompt('👆 แตะหน้าจอ 1 ครั้ง เพื่อเปิดระบบเสียงและไมโครโฟนอัตโนมัติ');
        }
    };

    // เล่นเสียงหนึ่งท่อนจนจบ: true = เล่นจบ/ถูกหยุด, false = เบราว์เซอร์บล็อกเสียง
    const playUriToEnd = (uri) => new Promise(resolve => {
        if (signal.aborted) return resolve(true);
        const onAbort = () => finish(true);
        const finish = (v) => { signal.removeEventListener('abort', onAbort); resolve(v); };
        signal.addEventListener('abort', onAbort);
        audioPlayer.src = uri;
        audioPlayer.volume = 1.0;
        audioPlayer.muted = false;
        audioPlayer.onended = () => finish(true);
        audioPlayer.onerror = () => finish(true);
        audioPlayer.play().then(markSpeaking).catch((playErr) => {
            handleAutoplayBlock(playErr);
            finish(false);
        });
    });

    // คำตอบที่ไม่มีเสียงอัดไว้: ขอเสียงทีละประโยค แล้วเริ่มพูดเมื่อเสียงที่ได้มาพอให้พูดต่อเนื่อง
    // (เซิร์ฟเวอร์เสียงในบูธสร้างเสียงช้ากว่าเวลาพูดจริง ~2 เท่า จึงสะสมก่อนเล็กน้อย)
    const MAX_PREBUFFER_MS = 6000;   // หลังได้ประโยคแรก รอสะสมเสียงเพิ่มไม่เกินนี้
    const playSentenceQueue = async (sentences) => {
        const queue = [];
        let producing = true;
        let producedChars = 0, genMs = 0, genChars = 0;
        const totalChars = sentences.reduce((n, x) => n + x.length, 0);
        let wake = null;
        const notify = () => { if (wake) { const w = wake; wake = null; w(); } };
        const waitChange = (ms) => new Promise(r => {
            wake = r;
            setTimeout(() => { if (wake === r) wake = null; r(); }, ms);
        });

        (async () => {
            for (const sentence of sentences) {
                if (signal.aborted) break;
                const t0 = performance.now();
                const d = await requestTTS(sentence, activeLang, signal);
                if (signal.aborted) break;
                producedChars += sentence.length;
                // สร้างเสียงไม่ได้เลย (ไม่มีประโยคกลางอัดไว้): หยุด ไม่ต้องรอประโยคถัดไปอีก
                if (d && d.status === 'no_voice') break;
                if (!d || !d.audio_base64) continue;
                if (!String(d.engine || '').startsWith('cache')) {
                    genMs += performance.now() - t0;
                    genChars += sentence.length;
                }
                const uri = ttsDataToUri(d);
                queue.push({ uri, dur: await audioDurationSec(uri, sentence.length / 12) });
                notify();
                // เซิร์ฟเวอร์เสียงใช้ไม่ได้: พูดประโยคกลางครั้งเดียวพอ ไม่ต้องขอประโยคถัดไป
                if (d.fallback) break;
            }
            producing = false;
            notify();
        })();

        // รอจนเสียงที่สะสมไว้ยาวพอให้พูดต่อเนื่องจนจบ หรือรอครบ MAX_PREBUFFER_MS
        let firstReadyAt = null;
        while (!signal.aborted && producing) {
            if (queue.length) {
                if (firstReadyAt === null) firstReadyAt = performance.now();
                const bufferedSec = queue.reduce((n, q) => n + q.dur, 0);
                const remainingGenSec = genChars ? (totalChars - producedChars) * (genMs / genChars) / 1000 : 0;
                if (bufferedSec >= remainingGenSec || performance.now() - firstReadyAt >= MAX_PREBUFFER_MS) break;
            }
            await waitChange(400);
        }

        isPlayingQueue = true;
        while (!signal.aborted) {
            if (!queue.length) {
                if (!producing) break;
                ttsGapActive = true;          // ยังสร้างเสียงประโยคถัดไปไม่เสร็จ
                setEmotion('thinking');
                await waitChange(400);
                continue;
            }
            const ok = await playUriToEnd(queue.shift().uri);
            if (!ok) break;
        }
        if (!signal.aborted) {
            ttsGapActive = false;
            handlePlaybackFinished();
        }
    };

    try {
        // 1) เสียงคำตอบเต็มที่อัดเก็บไว้แล้ว (prebake) เล่นได้ทันที
        let data = await requestTTS(speechText, activeLang, signal, true);
        if (signal.aborted) return;
        const sentences = splitTextIntoSentences(speechText);
        // 2) ไม่มีเสียงอัดไว้ และเป็นข้อความประโยคเดียว: ขอทั้งก้อน
        if (!(data && data.audio_base64) && sentences.length <= 1) {
            data = await requestTTS(speechText, activeLang, signal);
            if (signal.aborted) return;
        }
        if (data && data.audio_base64) {
            const uri = ttsDataToUri(data);
            if (!data.fallback && clientAudioCache.size < 128) {
                clientAudioCache.set(cacheKey, uri);
            }
            await playUriToEnd(uri);
            if (!signal.aborted) handlePlaybackFinished();   // ถูกขัดจังหวะ: คำตอบใหม่จัดการสถานะเอง
            return;
        }
        // 3) ไม่มีเสียงอัดไว้ และมีหลายประโยค: สร้างทีละประโยคแล้วพูดต่อกัน
        if (sentences.length > 1) {
            await playSentenceQueue(sentences);
            return;
        }
        handlePlaybackFinished();
    } catch (err) {
        if (err.name !== 'AbortError') {
            console.warn('⚠️ [Audio Playback] TTS error:', err);
        }
        handlePlaybackFinished();
    }
}

// -----------------------------------------------------------------------------
// Real-time Voice Recognition & Intelligent Acoustic Noise Filter Engine
// -----------------------------------------------------------------------------
let recognition = null;
let isRecording = false;
let isRealtimeVoiceActive = false;
let isRealtimeDialogueActive = false;
let realtimeDialogueTimer = null;
let isWaitingChatResponse = false;
let speechSilenceTimer = null;
let realtimeVoiceInactivityTimer = null;
const REALTIME_VOICE_TIMEOUT_MS = 45000; // 45 วินาที ไม่มีการสนทนา -> ปิดโหมดคุยสด

// ข้อมูลสถานะสำหรับการกรองเสียงสะท้อนจากลำโพง (Acoustic Echo Guard)
const ACOUSTIC_COOLDOWN_MS = 400; // ชดเชย Bluetooth buffer delay ป้องกันไมค์ดูดเสียงตัวเอง
let lastBotSpeechEndTime = 0;
let lastBotSpokenText = '';

/**
 * รีเฟรชหน้าต่างเปิดรับคำถามต่อเนื่อง (Active Dialogue Window) นาน 12 วินาที
 * ช่วยให้คุยต่อเนื่องได้โดยไม่ต้องพูด "น้องเพชร" ซ้ำ และเมื่อหมดเวลาจะกลับสู่โหมด Standby เพื่อกันเสียงรอบข้าง
 */
function refreshRealtimeDialogueWindow(durationMs = 12000) {
    isRealtimeDialogueActive = true;
    if (realtimeDialogueTimer) clearTimeout(realtimeDialogueTimer);
    realtimeDialogueTimer = setTimeout(() => {
        isRealtimeDialogueActive = false;
        console.log('💤 [Voice Standby] หมดเวลาหน้าต่างสนทนาต่อเนื่อง -> กลับสู่โหมดรอคำปลุกเรียก (Wake-word Standby)');
        if (isRealtimeVoiceActive && !isSpeakingTTS && !isWaitingChatResponse) {
            setRealtimeVoiceStatus('idle', '💤 พร้อมคุยเสมอ... เรียก "น้องเพชร" เพื่อถามได้เลยนะคะ ✨');
        }
    }, durationMs);
}

let proactiveAutoListenTimer = null;

/**
 * หน้าต่างรอรับคำถามอัตโนมัติแบบ Proactive Hands-Free (8 วินาที)
 * เมื่อน้องเพชรกล่าวทักทายเสร็จ จะเปิดไมค์และสลับจอเป็น listening อัตโนมัติ
 * หากผู้ใช้ไม่พูดภายในเวลาที่กำหนด จะเล่นเสียง earcon 'done' และกลับสู่ Standby อย่างนุ่มนวล
 */
function startProactiveAutoListenWindow(durationMs = 8000) {
    if (proactiveAutoListenTimer) {
        clearTimeout(proactiveAutoListenTimer);
        proactiveAutoListenTimer = null;
    }
    isRealtimeDialogueActive = true;
    console.log(`⏱️ [Auto Listen Window] เปิดหน้าต่างรอรับคำถามอัตโนมัติ ${durationMs/1000} วินาที (Hands-Free)`);

    proactiveAutoListenTimer = setTimeout(() => {
        proactiveAutoListenTimer = null;
        if (!isSpeakingTTS && !isWaitingChatResponse && !isRecording) {
            console.log('⏱️ [Auto Listen Window] ครบ 8 วินาที ผู้ใช้ยังไม่ได้ถามคำถาม -> สลับสู่ Standby อย่างนุ่มนวล');
            isRealtimeDialogueActive = false;
            playEarconChime('done');
            setEmotion('idle');
            if (typeof setRealtimeVoiceStatus === 'function') {
                setRealtimeVoiceStatus('idle', '💤 พร้อมคุยเสมอ... เรียก "น้องเพชร" เพื่อถามได้เลยนะคะ ✨');
            }
        }
    }, durationMs);
}

function cancelProactiveAutoListenWindow() {
    if (proactiveAutoListenTimer) {
        clearTimeout(proactiveAutoListenTimer);
        proactiveAutoListenTimer = null;
    }
}
window.startProactiveAutoListenWindow = startProactiveAutoListenWindow;
window.cancelProactiveAutoListenWindow = cancelProactiveAutoListenWindow;

/**
 * ตัวกรองเสียงพื้นฐาน ป้องกันการรับเสียงระหว่างที่บอทกำลังพูดตอบกลับ
 */
function evaluateSpeechQuality(transcript, confidence = 1.0) {
    if (!transcript) return { isValid: false, reason: 'empty' };
    const raw = transcript.trim();
    if (raw.length === 0) return { isValid: false, reason: 'empty' };

    // 1. ตรวจสอบว่าบอทกำลังส่งเสียงพูดอยู่หรือไม่ (Acoustic Echo Guard)
    const now = Date.now();
    if (isSpeakingTTS || (now - lastBotSpeechEndTime < ACOUSTIC_COOLDOWN_MS)) {
        return { isValid: false, reason: 'acoustic_cooldown', text: raw };
    }

    return { isValid: true, cleanedText: raw };
}

function resetRealtimeVoiceInactivityTimer() {
    if (!isRealtimeVoiceActive) return;
    clearTimeout(realtimeVoiceInactivityTimer);
    realtimeVoiceInactivityTimer = setTimeout(() => {
        console.log('⏱️ [Kiosk Voice] ไม่มีการสนทนานาน 45 วินาที -> ปิดโหมดคุยสดอัตโนมัติ');
        toggleRealtimeVoiceMode(false);
    }, REALTIME_VOICE_TIMEOUT_MS);
}

function getRecognitionLang() {
    if (currentLang === 'en') return 'en-US';
    if (currentLang === 'zh') return 'zh-CN';
    if (currentLang === 'ja') return 'ja-JP';
    if (currentLang === 'ko') return 'ko-KR';
    return 'th-TH';
}

/**
 * ตรวจจับและสกัดคำปลุกเรียก (Wake Word) อัจฉริยะ 3 ภาษา (ไทย, อังกฤษ, จีน)
 */
function parseWakeWord(transcript) {
    if (!transcript) return { isWakeWord: false, isWakeOnly: false, query: '', detectedLang: 'th' };

    const raw = transcript.trim();
    const lower = raw.toLowerCase();

    // 1. ตรวจจับภาษาของเสียงพูดเบื้องต้น
    let detectedLang = 'th';
    if (/[\u4e00-\u9fa5]/.test(raw)) {
        detectedLang = 'zh';
    } else if (/[a-zA-Z]/.test(raw) && !/[\u0e00-\u0e7f]/.test(raw)) {
        detectedLang = 'en';
    }

    // 2. Regular Expressions สำหรับ Wake Words
    const thaiWakeRegex = /^(?:เฮ้|เฮ้ย|สวัสดี|ฮัลโหล|ดีครับ|ดีค่ะ)?\s*(?:น้องเพชร|น้องเพ็ด|น้องเพชรครับ|น้องเพชรคะ|น้องเพชรจ๋า|น้องเพชรจ๊ะ)\s*[,.!?~]*\s*(.*)$/i;
    const engWakeRegex = /^(?:hey|hello|hi|ok)?\s*(?:nong\s*phet|nongphet|phet)\s*[,.!?~]*\s*(.*)$/i;
    const zhWakeRegex = /^(?:你好|嗨)?\s*(?:小佩特|小碧|佩特)\s*[,.!?~]*\s*(.*)$/i;

    let match = raw.match(thaiWakeRegex);
    if (match) {
        const query = match[1] ? match[1].trim() : '';
        return { isWakeWord: true, isWakeOnly: query.length === 0, query: query, detectedLang: 'th' };
    }

    match = raw.match(engWakeRegex);
    if (match) {
        const query = match[1] ? match[1].trim() : '';
        return { isWakeWord: true, isWakeOnly: query.length === 0, query: query, detectedLang: 'en' };
    }

    match = raw.match(zhWakeRegex);
    if (match) {
        const query = match[1] ? match[1].trim() : '';
        return { isWakeWord: true, isWakeOnly: query.length === 0, query: query, detectedLang: 'zh' };
    }

    return { isWakeWord: false, isWakeOnly: false, query: raw, detectedLang: detectedLang };
}

// ใช้ตัวฟังเสียงของน้องเพชร (local_stt.js): Whisper ในบูธถ้ามี ไม่งั้นใช้ Web Speech ของเบราว์เซอร์
// (Chromium บน Raspberry Pi ใช้ Web Speech ไม่ได้ -> error: network)
if (window.NongPhetSpeechRecognition || 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.NongPhetSpeechRecognition || window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.lang = getRecognitionLang();
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        isRecording = true;
        setEmotion('listening');
        const micBtn = document.getElementById('micBtn');
        const chatInput = document.getElementById('chatInput');
        if (micBtn) {
            micBtn.classList.add('text-emerald-400', 'bg-emerald-500/20', 'border-emerald-500', 'animate-pulse');
            micBtn.classList.remove('text-slate-300', 'border-slate-700');
        }
        if (isRealtimeVoiceActive) {
            setRealtimeVoiceStatus('listening', '🎙️ กำลังฟังเสียงคุณ... (พูดต่อได้เลย หรือพูด "น้องเพชร")');
        } else if (chatInput) {
            chatInput.placeholder = 'กำลังฟังเสียงพูดของคุณ...';
        }
    };

    recognition.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';
        let finalConfidence = 1.0;

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            const res = event.results[i];
            if (res.isFinal) {
                finalTranscript += res[0].transcript;
                if (res[0].confidence !== undefined && res[0].confidence > 0) {
                    finalConfidence = res[0].confidence;
                }
            } else {
                interimTranscript += res[0].transcript;
            }
        }

        const chatInput = document.getElementById('chatInput');
        const now = Date.now();

        // 0. Voice Barge-In: ตรวจจับเสียงพูดแทรกขณะบอทกำลังส่งเสียงพูด (Gemini Live style)
        if (isSpeakingTTS) {
            const checkText = (finalTranscript || interimTranscript).trim();
            if (checkText.length >= 2) {
                const isEcho = isEchoOfBotSpeech(checkText, lastBotSpokenText);
                if (!isEcho) {
                    console.log('⚡ [Voice Barge-In] ขัดจังหวะเสียงบอทด้วยคำพูดผู้ใช้:', checkText);
                    handleBargeInAction();
                }
            }
            return;
        }

        // 1. จัดการเสียงชั่วคราว (Interim Stream) พร้อมกรองเสียงสะท้อนลำโพง
        if (interimTranscript && !isSpeakingTTS && (now - lastBotSpeechEndTime > ACOUSTIC_COOLDOWN_MS)) {
            const trimmedInterim = interimTranscript.trim();
            if (trimmedInterim.length >= 3) {
                cancelProactiveAutoListenWindow();
                resetRealtimeVoiceInactivityTimer();
                if (chatInput) chatInput.value = trimmedInterim;
                if (isRealtimeVoiceActive) {
                    setRealtimeVoiceStatus('listening', `🎙️ กำลังได้ยิน: "${trimmedInterim}"`);
                }
            }
        }

        // 2. จัดการเสียงประโยคสมบูรณ์ (Final Transcript) พร้อมระบบคัดกรองเสียงรบกวนอัจฉริยะ
        if (finalTranscript && finalTranscript.trim().length > 0) {
            cancelProactiveAutoListenWindow();
            resetRealtimeVoiceInactivityTimer();
            if (speechSilenceTimer) clearTimeout(speechSilenceTimer);

            // ผ่านตัวกรองขยะ คำอุทานเดี่ยว ระดับพลังงานเสียง และเสียงสะท้อน
            const quality = evaluateSpeechQuality(finalTranscript, finalConfidence);
            if (!quality.isValid) {
                console.log(`🔇 [Voice Filter] ปฏิเสธเสียงรบกวน (${quality.reason}): "${finalTranscript}"`);
                if (chatInput && chatInput.value === finalTranscript.trim()) {
                    chatInput.value = '';
                }
                if (isRealtimeVoiceActive && !isRealtimeDialogueActive) {
                    setRealtimeVoiceStatus('idle', '💤 พร้อมคุยเสมอ... เรียก "น้องเพชร" เพื่อถามได้เลยนะคะ ✨');
                }
                return;
            }

            // ตรวจจับคำตอบเลือกโหมดเมื่อหน้าต่างต้อนรับเปิดอยู่ (Voice Command for Greeting Choice)
            const greetingModal = document.getElementById('greetingModal');
            if (greetingModal && !greetingModal.classList.contains('hidden')) {
                const normSpeech = finalTranscript.trim().toLowerCase();
                if (normSpeech.includes('คุย') || normSpeech.includes('พูด') || normSpeech.includes('เสียง')) {
                    if (typeof chooseInteractionChoice === 'function') {
                        chooseInteractionChoice('voice');
                        if (chatInput) chatInput.value = '';
                        return;
                    }
                } else if (normSpeech.includes('แชท') || normSpeech.includes('พิมพ์') || normSpeech.includes('ข้อความ')) {
                    if (typeof chooseInteractionChoice === 'function') {
                        chooseInteractionChoice('chat');
                        if (chatInput) chatInput.value = '';
                        return;
                    }
                }
            }

            const parsed = parseWakeWord(finalTranscript);
            if (parsed.isWakeWord) {
                refreshRealtimeDialogueWindow();
                playQuickAudioFeedback();
                if (parsed.isWakeOnly) {
                    // เรียกเฉพาะชื่อ "น้องเพชร"
                    toggleRealtimeVoiceMode(true);
                    const wakeReplies = {
                        th: 'ค่ะ! น้องเพชรพร้อมแล้วค่ะ สอบถามได้เลยนะคะ ✨',
                        en: "Hello! I'm Nong Phet. How can I help you? ✨",
                        zh: '在呢！请问有什么我可以帮您的吗？ ✨'
                    };
                    const reply = wakeReplies[parsed.detectedLang] || wakeReplies.th;
                    stopRecognitionSafe();
                    playTTS(reply, null, () => {
                        startRecognitionSafe();
                    }, parsed.detectedLang);
                    return;
                } else {
                    // พูดคำสั่งพร้อมคำปลุกเรียก เช่น "น้องเพชร มีแผนกอะไรบ้าง"
                    if (chatInput) chatInput.value = parsed.query;
                    if (!isRealtimeVoiceActive) toggleRealtimeVoiceMode(true);
                    stopRecognitionSafe();
                    playQuickAudioFeedback();
                    sendChatMessage(parsed.detectedLang);
                    return;
                }
            } else {
                // ไม่มี Wake word:
                // เมื่อไมค์เปิดทำงานอยู่ รับฟังและประมวลผลคำถามได้ทันที 100% ไม่ต้องบังคับเรียกชื่อ!
                refreshRealtimeDialogueWindow();
                if (chatInput) chatInput.value = finalTranscript.trim();
                setRealtimeVoiceStatus('thinking', '⚡ น้องเพชรกำลังประมวลผลคำตอบ...');
                stopRecognitionSafe();
                playQuickAudioFeedback();
                sendChatMessage(parsed.detectedLang);
                return;
            }
        }

        // 3. ปรับปรุง Automatic silence debounce:
        // - ปรับจาก 750ms เป็น 1400ms เพื่อให้ผู้ใช้พูดต่อเนื่องได้ ไม่ตัดคำกลางคัน
        // - ต้องมีความยาวอย่างน้อย 8 ตัวอักษร และผ่านตัวกรองคุณภาพเสียง
        if (interimTranscript && interimTranscript.trim().length >= 8) {
            const interimQuality = evaluateSpeechQuality(interimTranscript);
            if (interimQuality.isValid) {
                if (speechSilenceTimer) clearTimeout(speechSilenceTimer);
                speechSilenceTimer = setTimeout(() => {
                    const currentVal = chatInput ? chatInput.value.trim() : '';
                    if (currentVal && !isSpeakingTTS && !isWaitingChatResponse) {
                        const checkAgain = evaluateSpeechQuality(currentVal);
                        if (checkAgain.isValid) {
                            if (isRealtimeVoiceActive) {
                                refreshRealtimeDialogueWindow();
                                setRealtimeVoiceStatus('thinking', '⚡ น้องเพชรกำลังประมวลผลคำตอบ...');
                            }
                            stopRecognitionSafe();
                            playQuickAudioFeedback();
                            sendChatMessage();
                        }
                    }
                }, 1400); // หน่วงเวลา 1.4 วินาที ป้องกันการตัดส่งเร็วเกินไป
            }
        }
    };

    recognition.onend = () => {
        isRecording = false;
        const micBtn = document.getElementById('micBtn');
        const chatInput = document.getElementById('chatInput');

        if (!isRealtimeVoiceActive) {
            if (micBtn) {
                micBtn.classList.remove('text-emerald-400', 'bg-emerald-500/20', 'border-emerald-500', 'animate-pulse');
                micBtn.classList.add('text-slate-300', 'border-slate-700');
            }
            if (chatInput) chatInput.placeholder = 'พิมพ์คำถาม หรือกดไมโครโฟนเพื่อพูดคุย...';
            if (!isWaitingChatResponse && !isSpeakingTTS) {
                setEmotion('idle');
            }
        } else {
            // In Real-time Hands-free mode, auto restart listening when idle
            if (!isSpeakingTTS && !isWaitingChatResponse) {
                setTimeout(() => {
                    if (isRealtimeVoiceActive && !isSpeakingTTS && !isWaitingChatResponse) {
                        startRecognitionSafe();
                    }
                }, 200);
            }
        }
    };

    recognition.onerror = (e) => {
        isRecording = false;
        console.warn('Speech recognition event:', e.error);
        if (!isWaitingChatResponse && !isSpeakingTTS) {
            setEmotion('idle');
        }
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
            console.warn('🎙️ [Mic Permission Required] เบราว์เซอร์ต้องการการอนุญาตไมโครโฟนจากผู้ใช้');
            showAudioUnlockPrompt('🎙️ แตะที่นี่เพื่ออนุญาตการใช้ไมโครโฟนค่ะ');
            // ไม่ปิดโหมด Realtime เพื่อให้เมื่อผู้ใช้แตะปุ่มแล้ว ไมค์จะเปิดทำงานต่อเนื่องทันที
            return;
        }
        if (isRealtimeVoiceActive && !isSpeakingTTS && !isWaitingChatResponse) {
            setTimeout(() => {
                if (isRealtimeVoiceActive && !isSpeakingTTS && !isWaitingChatResponse) {
                    startRecognitionSafe();
                }
            }, 500);
        }
    };
}

function startRecognitionSafe() {
    if (!recognition) return;
    if (isSpeakingTTS || isWaitingChatResponse) return;
    if (isRecording) return; // หลีกเลี่ยง InvalidStateError เมื่อกำลังบันทึกอยู่แล้ว
    try {
        recognition.lang = getRecognitionLang();
        recognition.start();
    } catch (e) {
        // Recognition might already be running or awaiting gesture
    }
}

function stopRecognitionSafe() {
    if (speechSilenceTimer) clearTimeout(speechSilenceTimer);
    if (!recognition) return;
    try {
        // ตัดไมโครโฟนทันที (Cut mic immediately เหมือน Gemini Live)
        recognition.abort();
    } catch (e) {
        try { recognition.stop(); } catch (e2) {}
    }
    isRecording = false;
}

function toggleSpeechRecognition() {
    if (!recognition) {
        showAppToast('เบราว์เซอร์ของคุณไม่รองรับการสั่งการด้วยเสียง (แนะนำ Chrome หรือ Edge)', 'warning');
        return;
    }
    // หากบอทกำลังคิดหรือกำลังพูดอยู่ -> แตะไมค์เพื่อขัดจังหวะทันที แล้วสลับไปฟังทันที
    if (isSpeakingTTS || isWaitingChatResponse) {
        stopAllSpeech();
        if (typeof setRealtimeVoiceStatus === 'function') {
            setRealtimeVoiceStatus('listening', '🎙️ กำลังฟังเสียงคุณ... พูดได้เลยค่ะ');
        }
        setTimeout(() => {
            startRecognitionSafe();
        }, 150);
        return;
    }

    if (isRecording) {
        stopRecognitionSafe();
    } else {
        startRecognitionSafe();
    }
}

function toggleRealtimeVoiceMode(forcedState) {
    if (!recognition) {
        showAppToast('เบราว์เซอร์ของคุณไม่รองรับการสนทนาด้วยเสียง (แนะนำ Chrome หรือ Edge)', 'warning');
        return;
    }

    if (forcedState !== undefined) {
        isRealtimeVoiceActive = forcedState;
    } else {
        isRealtimeVoiceActive = !isRealtimeVoiceActive;
    }

    const headerBtn = document.getElementById('realtimeVoiceHeaderBtn');
    const headerIcon = document.getElementById('realtimeVoiceHeaderIcon');
    const headerLabel = document.getElementById('realtimeVoiceHeaderLabel');
    const banner = document.getElementById('realtimeVoiceBanner');
    const micBtn = document.getElementById('micBtn');
    const chatInput = document.getElementById('chatInput');

    if (isRealtimeVoiceActive) {
        refreshRealtimeDialogueWindow(15000);
        autoSpeak = true;
        resetRealtimeVoiceInactivityTimer();
        const autoSpeakIcon = document.getElementById('autoSpeakIcon');
        if (autoSpeakIcon) autoSpeakIcon.className = 'fa-solid fa-volume-high text-emerald-400';

        if (banner) banner.classList.remove('hidden');
        if (headerBtn) {
            headerBtn.className = 'px-3 py-1.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 text-white text-xs font-bold border border-emerald-400/50 shadow-lg shadow-emerald-950/60 transition flex items-center gap-1.5';
        }
        if (headerIcon) {
            headerIcon.className = 'fa-solid fa-wave-square animate-pulse text-white';
        }
        if (headerLabel) {
            headerLabel.textContent = 'คุยสดอยู่ (เปิด)';
        }
        if (micBtn) {
            micBtn.classList.add('ring-2', 'ring-emerald-400', 'bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
        }
        if (chatInput) {
            chatInput.placeholder = '🎙️ โหมดคุยสดเปิดอยู่... พูดได้ทันทีโดยไม่ต้องกดปุ่ม';
        }

        setRealtimeVoiceStatus('listening', '🎙️ โหมดคุยสดเปิดอยู่: กำลังฟังเสียงคุณ... (พูดได้เลยไม่ต้องกดปุ่ม)');
        startRecognitionSafe();
    } else {
        if (speechSilenceTimer) clearTimeout(speechSilenceTimer);
        if (realtimeVoiceInactivityTimer) clearTimeout(realtimeVoiceInactivityTimer);
        if (banner) banner.classList.add('hidden');
        if (headerBtn) {
            headerBtn.className = 'px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-emerald-600/30 text-slate-300 hover:text-emerald-300 text-xs font-bold border border-slate-700 hover:border-emerald-500/50 transition flex items-center gap-1.5 shadow';
        }
        if (headerIcon) {
            headerIcon.className = 'fa-solid fa-microphone-lines text-slate-400';
        }
        if (headerLabel) {
            headerLabel.textContent = 'คุยสด Real-time';
        }
        if (micBtn) {
            micBtn.classList.remove('ring-2', 'ring-emerald-400', 'bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500', 'animate-pulse');
        }
        if (chatInput) {
            chatInput.placeholder = 'พิมพ์คำถาม หรือกดไมโครโฟนเพื่อพูดคุย...';
        }
        stopRecognitionSafe();
    }
}

function setRealtimeVoiceStatus(state, msg) {
    const statusText = document.getElementById('realtimeVoiceStatusText');
    const waveBars = document.getElementById('voiceWaveBars');
    if (statusText) statusText.textContent = msg;

    if (waveBars) {
        if (state === 'listening' || state === 'speaking') {
            waveBars.style.visibility = 'visible';
        } else {
            waveBars.style.visibility = 'hidden';
        }
    }
}

// -----------------------------------------------------------------------------
// Cross-screen Gaze Follow: ส่งพิกัดสัมผัส/เมาส์จากจอหลักไปยังจอแสดงอารมณ์ส่วนหัว
// -----------------------------------------------------------------------------
let lastGazeSentTime = 0;
let lastSentNormX = 0;
let lastSentNormY = 0;

function initCrossScreenGazeTracking() {
    let lastHttpGazeSentTime = 0;

    function sendGaze(clientX, clientY, isTouch = false) {
        const now = performance.now();
        const minInterval = isTouch ? 800 : 350;
        if (now - lastGazeSentTime < 150) return;

        const normX = Math.max(-1.0, Math.min(1.0, (clientX - window.innerWidth / 2) / (window.innerWidth / 2)));
        const normY = Math.max(-1.0, Math.min(1.0, (clientY - window.innerHeight / 2) / (window.innerHeight / 2)));

        if (Math.abs(normX - lastSentNormX) < 0.08 && Math.abs(normY - lastSentNormY) < 0.08) return;

        lastGazeSentTime = now;
        lastSentNormX = normX;
        lastSentNormY = normY;

        // Zero-overhead BroadcastChannel for dual-screen tabs
        if (lipSyncBroadcast) {
            lipSyncBroadcast.postMessage({ type: 'gaze', x: normX, y: normY });
        }

        // Throttle HTTP POST to prevent flooding Flask and choking Pi CPU
        if (now - lastHttpGazeSentTime > minInterval) {
            lastHttpGazeSentTime = now;
            fetch('/api/emotion/gaze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ x: normX, y: normY }),
                keepalive: true
            }).catch(() => {});
        }
    }

    window.addEventListener('mousemove', (e) => {
        sendGaze(e.clientX, e.clientY, false);
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
        if (e.touches && e.touches[0]) {
            sendGaze(e.touches[0].clientX, e.touches[0].clientY, true);
        }
    }, { passive: true });
}
