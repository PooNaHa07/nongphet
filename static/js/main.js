const clientAudioCache = new Map();

function playQuickAudioFeedback() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.08);
        gain.gain.setValueAtTime(0.06, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.12);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.12);
    } catch (e) {}
}

function stripEmojiAndIcons(str) {
    if (!str) return '';
    return str
        .replace(/[\p{Extended_Pictographic}\u2600-\u27BF\uFE0E\uFE0F\u200D\u2300-\u23FF\u2B50\u2B55]/gu, '')
        .replace(/[*#_~>•\-=|]/g, ' ')
        .replace(/[^\w\s\u0E00-\u0E7F.,!?'"-]/g, ' ')
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
let currentVoiceGender = 'female'; // 'female' (Premwadee) or 'male' (Niwat)
let isSpeakingTTS = false;

// -----------------------------------------------------------------------------
// Cross-Screen BroadcastChannel for Zero-Latency Lip-Sync & Air Gestures
// -----------------------------------------------------------------------------
const lipSyncBroadcast = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('nongphet_sync') : null;
if (lipSyncBroadcast) {
    lipSyncBroadcast.onmessage = (e) => {
        if (!e.data) return;
        if (e.data.type === 'gesture') {
            if (e.data.gesture === 'wave') {
                console.log('👋 [Main Screen] Air Gesture Wave detected!');
                if (typeof showIotToast === 'function') {
                    showIotToast('👋 น้องเพชรตรวจพบการโบกมือทักทาย!', 'ยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีครับ');
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
        lipSyncBroadcast.postMessage({ type: 'lipsync', amp: normAmp });
        lipSyncAnimFrame = requestAnimationFrame(update);
    }
    update();
}

window.addEventListener('DOMContentLoaded', () => {
    // ปลดล็อก Browser Autoplay Policy ทันทีเมื่อผู้ใช้แตะหรือคลิกหน้าจอครั้งแรก
    const unlockAudio = () => {
        const p = document.getElementById('audioPlayer');
        if (p && !p.src) {
            p.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            p.play().then(() => p.pause()).catch(() => {});
        }
    };
    window.addEventListener('pointerdown', unlockAudio, { once: true });
    window.addEventListener('touchstart', unlockAudio, { once: true });

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
        sendQuickMessage('สวัสดีครับ แนะนำตัวเองและบริการทั้งหมดให้ฟังหน่อยครับ');
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
    sendQuickMessage(`อยากทราบว่าสาขา "${courseName}" ของวิทยาลัยอาชีวศึกษาเพชรบุรี เรียนเกี่ยวกับอะไรบ้าง ทักษะที่จะได้รับ และโอกาสในการทำงานในอนาคตครับ`);
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
        fetch('/api/emotion/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: state })
        }).catch(() => {});
    } catch (e) {}
}


// -----------------------------------------------------------------------------
// Neural TTS Audio Engine
// -----------------------------------------------------------------------------
async function playTTS(text, btnElement = null, onEndedCallback = null) {
    const speechText = stripEmojiAndIcons(text);
    if (!speechText) return;
    try {
        const audioPlayer = document.getElementById('audioPlayer');
        if (isSpeakingTTS && audioPlayer && !audioPlayer.paused) {
            audioPlayer.pause();
            audioPlayer.currentTime = 0;
            isSpeakingTTS = false;
            setEmotion('idle');
            if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
            if (typeof onEndedCallback === 'function') onEndedCallback();
            return;
        }

                const cacheKey = (currentLang || 'th') + '_' + text;
        if (clientAudioCache.has(cacheKey)) {
            const cachedBase64 = clientAudioCache.get(cacheKey);
            audioPlayer.src = cachedBase64;
            audioPlayer.volume = 1.0;
            audioPlayer.muted = false;
            audioPlayer.play().then(() => {
                isSpeakingTTS = true;
                setEmotion('speaking');
                if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-circle-stop text-rose-500 animate-pulse"></i> หยุดเสียง';
                startLipSyncAnalysis();
            }).catch(() => {});
            audioPlayer.onended = () => {
                isSpeakingTTS = false;
                setEmotion('idle');
                if (lipSyncBroadcast) lipSyncBroadcast.postMessage({ type: 'lipsync', amp: 0 });
                if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
                if (typeof onEndedCallback === 'function') onEndedCallback();
            };
            return;
        }

        if (btnElement) {
            btnElement.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-blue-500"></i> กำลังโหลดเสียง...';
        }
        setEmotion('thinking');

        const response = await fetch('/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: speechText,
                lang: currentLang,
                gender: currentVoiceGender
            })
        });
        const data = await response.json();
        
                if (data.audio_base64) {
            const audioDataUri = 'data:audio/mp3;base64,' + data.audio_base64;
            if (clientAudioCache.size < 64) {
                clientAudioCache.set(cacheKey, audioDataUri);
            }
            audioPlayer.src = audioDataUri;
            audioPlayer.volume = 1.0;
            audioPlayer.muted = false;

            audioPlayer.play().then(() => {
                isSpeakingTTS = true;
                setEmotion('speaking');
                if (btnElement) {
                    btnElement.innerHTML = '<i class="fa-solid fa-circle-stop text-rose-500 animate-pulse"></i> หยุดเสียง';
                }
                startLipSyncAnalysis();
            }).catch((err) => {
                console.warn('Audio play prevented or blocked by browser autoplay:', err);
                if ('speechSynthesis' in window) {
                    const u = new SpeechSynthesisUtterance(speechText);
                    u.lang = currentLang === 'en' ? 'en-US' : 'th-TH';
                    u.onstart = () => {
                        isSpeakingTTS = true;
                        setEmotion('speaking');
                    };
                    u.onend = () => {
                        isSpeakingTTS = false;
                        setEmotion('idle');
                        if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
                        if (typeof onEndedCallback === 'function') onEndedCallback();
                    };
                    u.onerror = () => {
                        isSpeakingTTS = false;
                        setEmotion('idle');
                        if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
                        if (typeof onEndedCallback === 'function') onEndedCallback();
                    };
                    window.speechSynthesis.speak(u);
                } else {
                    isSpeakingTTS = false;
                    setEmotion('idle');
                    if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
                    if (typeof onEndedCallback === 'function') onEndedCallback();
                }
            });
            audioPlayer.onended = () => {
                isSpeakingTTS = false;
                setEmotion('idle');
                if (lipSyncBroadcast) lipSyncBroadcast.postMessage({ type: 'lipsync', amp: 0 });
                if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
                if (typeof onEndedCallback === 'function') onEndedCallback();
            };
            audioPlayer.onerror = () => {
                isSpeakingTTS = false;
                setEmotion('idle');
                if (lipSyncBroadcast) lipSyncBroadcast.postMessage({ type: 'lipsync', amp: 0 });
                if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
                if (typeof onEndedCallback === 'function') onEndedCallback();
            };
        } else {
            isSpeakingTTS = false;
            setEmotion('idle');
            if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
            if (typeof onEndedCallback === 'function') onEndedCallback();
        }
    } catch (e) {
        console.error('TTS error:', e);
        isSpeakingTTS = false;
        setEmotion('idle');
        if (btnElement) btnElement.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
        if (typeof onEndedCallback === 'function') onEndedCallback();
    }
}

// -----------------------------------------------------------------------------
// Real-time Voice Recognition Engine (Hands-free Continuous Conversation)
// -----------------------------------------------------------------------------
let recognition = null;
let isRecording = false;
let isRealtimeVoiceActive = false;
let isWaitingChatResponse = false;
let speechSilenceTimer = null;

function getRecognitionLang() {
    if (currentLang === 'en') return 'en-US';
    if (currentLang === 'zh') return 'zh-CN';
    if (currentLang === 'ja') return 'ja-JP';
    if (currentLang === 'ko') return 'ko-KR';
    return 'th-TH';
}

if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
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
            setRealtimeVoiceStatus('listening', '🎙️ กำลังฟังเสียงคุณ... (พูดได้เลยไม่ต้องกดปุ่ม)');
        } else if (chatInput) {
            chatInput.placeholder = 'กำลังฟังเสียงพูดของคุณ...';
        }
    };

    recognition.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }

        const chatInput = document.getElementById('chatInput');
        
        if (interimTranscript) {
            if (chatInput) chatInput.value = interimTranscript;
            if (isRealtimeVoiceActive) {
                setRealtimeVoiceStatus('listening', `🎙️ กำลังได้ยิน: "${interimTranscript}"`);
            }
        }

                if (finalTranscript && finalTranscript.trim().length > 0) {
            if (chatInput) chatInput.value = finalTranscript.trim();
            if (speechSilenceTimer) clearTimeout(speechSilenceTimer);
            if (isRealtimeVoiceActive) {
                setRealtimeVoiceStatus('thinking', '⚡ น้องเพชรกำลังประมวลผลคำตอบ...');
            }
            stopRecognitionSafe();
            playQuickAudioFeedback();
            sendChatMessage();
            return;
        }

        // Automatic silence debounce (auto-submit if speaker pauses for ~750ms for ultra-fast response)
        if (interimTranscript && interimTranscript.trim().length > 1) {
            if (speechSilenceTimer) clearTimeout(speechSilenceTimer);
            speechSilenceTimer = setTimeout(() => {
                const currentVal = chatInput ? chatInput.value.trim() : '';
                if (currentVal && !isSpeakingTTS && !isWaitingChatResponse) {
                    if (isRealtimeVoiceActive) {
                        setRealtimeVoiceStatus('thinking', '⚡ น้องเพชรกำลังประมวลผลคำตอบ...');
                    }
                    stopRecognitionSafe();
                    playQuickAudioFeedback();
                    sendChatMessage();
                }
            }, 750);
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
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
            showAppToast('กรุณาอนุญาตการเข้าถึงไมโครโฟนในเบราว์เซอร์เพื่อใช้งานระบบเสียงครับ', 'warning');
            toggleRealtimeVoiceMode(false);
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
    try {
        recognition.lang = getRecognitionLang();
        recognition.start();
    } catch (e) {
        // Recognition might already be running
    }
}

function stopRecognitionSafe() {
    if (!recognition) return;
    if (speechSilenceTimer) clearTimeout(speechSilenceTimer);
    try {
        recognition.stop();
    } catch (e) {}
}


function toggleSpeechRecognition() {
    if (!recognition) {
        showAppToast('เบราว์เซอร์ของคุณไม่รองรับการสั่งการด้วยเสียง (แนะนำ Chrome หรือ Edge)', 'warning');
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
        autoSpeak = true;
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
