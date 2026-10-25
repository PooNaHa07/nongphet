/**
 * nongphet AI Smart Guide - Gemini 3.8 Live API Multimodal Engine
 * Low-latency real-time voice & camera interaction using WebSockets and PCM audio streaming
 */

let liveWs = null;
let liveMediaStream = null;
let liveAudioInputCtx = null;
let liveAudioOutputCtx = null;
let liveAudioSource = null;
let liveScriptProcessor = null;
let liveIsActive = false;
let liveIsMuted = false;
let liveCameraFacing = 'user';
let liveVideoInterval = null;
let liveActiveSources = [];
let liveNextPlayTime = 0;

function setLiveState(state, customMsg) {
    if (!liveIsActive && state !== 'offline') return;

    const liveStatusPulse = document.getElementById('liveStatusPulse');
    const liveStatusLabel = document.getElementById('liveStatusLabel');
    const liveStateBadge = document.getElementById('liveStateBadge');
    const liveVoiceWaves = document.getElementById('liveVoiceWaves');
    const liveScanningBeam = document.getElementById('liveScanningBeam');
    const liveMascotOrb = document.getElementById('liveMascotOrb');
    const btnToggleLiveSession = document.getElementById('btnToggleLiveSession');
    const btnToggleLiveIcon = document.getElementById('btnToggleLiveIcon');
    const btnToggleLiveLabel = document.getElementById('btnToggleLiveLabel');

    if (!liveStatusPulse) return;
    
    if (state === 'offline') {
        liveStatusPulse.className = 'w-2.5 h-2.5 rounded-full bg-slate-500';
        liveStatusLabel.textContent = 'OFFLINE';
        liveStateBadge.textContent = 'กดปุ่มด้านล่างเพื่อเริ่มคุยสด';
        liveVoiceWaves.classList.add('hidden');
        liveScanningBeam.classList.add('hidden');
        liveMascotOrb.className = 'w-20 h-20 rounded-3xl bg-blue-600/30 backdrop-blur-xl border border-blue-400/40 flex items-center justify-center shadow-[0_0_25px_rgba(37,99,235,0.4)] transition-all duration-300';
        btnToggleLiveSession.className = 'flex-1 py-4 bg-gradient-to-r from-rose-600 via-pink-600 to-rose-700 hover:from-rose-500 hover:to-pink-500 text-white font-black text-sm rounded-2xl shadow-[0_8px_25px_rgba(225,29,72,0.5)] border border-white/30 active:scale-95 transition flex items-center justify-center gap-2.5';
        btnToggleLiveIcon.className = 'fa-solid fa-play text-xs';
        btnToggleLiveLabel.textContent = 'เริ่มการสนทนาสด (Start Live Session)';
    } else if (state === 'connecting') {
        liveStatusPulse.className = 'w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping';
        liveStatusLabel.textContent = 'CONNECTING...';
        liveStateBadge.textContent = customMsg || 'กำลังเชื่อมต่อ Gemini 3.8 Live...';
        liveScanningBeam.classList.remove('hidden');
        btnToggleLiveSession.className = 'flex-1 py-4 bg-slate-800 text-slate-300 font-bold text-sm rounded-2xl border border-slate-700 flex items-center justify-center gap-2.5';
        btnToggleLiveIcon.className = 'fa-solid fa-spinner fa-spin text-xs';
        btnToggleLiveLabel.textContent = 'กำลังเชื่อมต่อ...';
    } else if (state === 'ready' || state === 'listening') {
        liveStatusPulse.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse';
        liveStatusLabel.textContent = 'LIVE ONLINE';
        liveStateBadge.textContent = '🎙️ กำลังฟังคุณพูด... (หรือส่องสิ่งของให้น้องเพชรดู)';
        liveVoiceWaves.classList.remove('hidden');
        liveScanningBeam.classList.remove('hidden');
        liveMascotOrb.className = 'w-20 h-20 rounded-3xl bg-emerald-600/30 backdrop-blur-xl border border-emerald-400/50 flex items-center justify-center shadow-[0_0_25px_rgba(16,185,129,0.5)] transition-all duration-300 scale-105';
        btnToggleLiveSession.className = 'flex-1 py-4 bg-gradient-to-r from-red-600 to-rose-700 hover:from-red-500 hover:to-rose-600 text-white font-black text-sm rounded-2xl shadow-[0_8px_25px_rgba(225,29,72,0.6)] border border-white/30 active:scale-95 transition flex items-center justify-center gap-2.5';
        btnToggleLiveIcon.className = 'fa-solid fa-stop text-xs';
        btnToggleLiveLabel.textContent = 'หยุดการสนทนา (Stop Live)';
    } else if (state === 'thinking') {
        liveStatusPulse.className = 'w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping';
        liveStatusLabel.textContent = 'THINKING...';
        liveStateBadge.textContent = '🤖 น้องเพชรกำลังคิดคำตอบ...';
        liveMascotOrb.className = 'w-20 h-20 rounded-3xl bg-cyan-600/40 backdrop-blur-xl border border-cyan-400/60 flex items-center justify-center shadow-[0_0_30px_rgba(6,182,212,0.6)] transition-all duration-300 scale-110';
    } else if (state === 'speaking') {
        liveStatusPulse.className = 'w-2.5 h-2.5 rounded-full bg-rose-500 animate-bounce';
        liveStatusLabel.textContent = 'SPEAKING...';
        liveStateBadge.textContent = '💬 น้องเพชรกำลังพูดตอบ...';
        liveVoiceWaves.classList.remove('hidden');
        liveMascotOrb.className = 'w-20 h-20 rounded-3xl bg-rose-600/40 backdrop-blur-xl border border-rose-400/60 flex items-center justify-center shadow-[0_0_35px_rgba(225,29,72,0.7)] transition-all duration-300 scale-110 animate-bounce';
    }
}

function updateLiveUserSubtitle(text) {
    if (!text) return;
    const liveUserSubWrapper = document.getElementById('liveUserSubWrapper');
    const liveUserSubText = document.getElementById('liveUserSubText');
    if (liveUserSubWrapper) liveUserSubWrapper.classList.remove('hidden');
    if (liveUserSubText) liveUserSubText.textContent = text;
    const box = document.getElementById('liveSubtitleBox');
    if (box) box.scrollTop = box.scrollHeight;
}

function updateLiveAISubtitle(text) {
    if (!text) return;
    const liveAISubText = document.getElementById('liveAISubText');
    if (liveAISubText) liveAISubText.textContent = text;
    const box = document.getElementById('liveSubtitleBox');
    if (box) box.scrollTop = box.scrollHeight;
}

function floatTo16BitPCM(float32Array) {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    let offset = 0;
    for (let i = 0; i < float32Array.length; i++, offset += 2) {
        let s = Math.max(-1, Math.min(1, float32Array[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buffer;
}

function downsampleTo16k(inputBuffer, inputSampleRate) {
    if (inputSampleRate === 16000) return inputBuffer;
    const ratio = inputSampleRate / 16000;
    const newLength = Math.round(inputBuffer.length / ratio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
        const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
        let accum = 0, count = 0;
        for (let i = offsetBuffer; i < nextOffsetBuffer && i < inputBuffer.length; i++) {
            accum += inputBuffer[i];
            count++;
        }
        result[offsetResult] = count > 0 ? accum / count : 0;
        offsetResult++;
        offsetBuffer = nextOffsetBuffer;
    }
    return result;
}

function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
}

function base64ToFloat32Array24k(base64) {
    const binaryString = window.atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    const dataView = new DataView(bytes.buffer);
    const numSamples = Math.floor(len / 2);
    const float32 = new Float32Array(numSamples);
    for (let i = 0; i < numSamples; i++) {
        const int16 = dataView.getInt16(i * 2, true);
        float32[i] = int16 / 32768.0;
    }
    return float32;
}

function playLiveAudioChunk(float32Data) {
    if (!liveAudioOutputCtx) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        liveAudioOutputCtx = new AudioContext({ sampleRate: 24000 });
    }
    if (liveAudioOutputCtx.state === 'suspended') {
        liveAudioOutputCtx.resume();
    }
    
    const audioBuffer = liveAudioOutputCtx.createBuffer(1, float32Data.length, 24000);
    audioBuffer.getChannelData(0).set(float32Data);
    
    const source = liveAudioOutputCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(liveAudioOutputCtx.destination);
    
    const currentTime = liveAudioOutputCtx.currentTime;
    if (liveNextPlayTime < currentTime) {
        liveNextPlayTime = currentTime + 0.05;
    }
    
    source.start(liveNextPlayTime);
    liveNextPlayTime += audioBuffer.duration;
    
    liveActiveSources.push(source);
    source.onended = () => {
        const idx = liveActiveSources.indexOf(source);
        if (idx > -1) liveActiveSources.splice(idx, 1);
        if (liveActiveSources.length === 0) {
            setLiveState('listening');
        }
    };
}

function stopLiveAudioPlayback() {
    for (const src of liveActiveSources) {
        try { src.stop(); } catch (e) {}
    }
    liveActiveSources = [];
    if (liveAudioOutputCtx) {
        liveNextPlayTime = liveAudioOutputCtx.currentTime;
    }
}

async function toggleLiveSession() {
    if (liveIsActive) {
        stopLiveSession();
    } else {
        await startLiveSession();
    }
}

async function startLiveSession() {
    try {
        setLiveState('connecting', 'กำลังขอสิทธิ์เปิดกล้องและไมโครโฟน...');
        
        // หากเซนเซอร์กล้องตรวจจับพื้นหลังเปิดอยู่ ให้ปิดก่อนเพื่อให้กล้องหลักใช้งานได้
        if (typeof isCameraSensorActive !== 'undefined' && isCameraSensorActive) {
            if (typeof stopCameraSensor === 'function') {
                stopCameraSensor();
                const btn = document.getElementById('btnToggleCameraSensor');
                if (btn) {
                    btn.className = 'w-full py-1.5 px-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 rounded-lg text-[10px] font-medium flex items-center justify-center gap-1.5 transition active:scale-95';
                    btn.innerHTML = '<i class="fa-solid fa-camera"></i> <span>เปิดสแกนคนผ่านกล้องหน้า (Webcam)</span>';
                }
            }
        }
        
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!liveAudioOutputCtx) {
            liveAudioOutputCtx = new AudioContext({ sampleRate: 24000 });
        }
        if (liveAudioOutputCtx.state === 'suspended') {
            await liveAudioOutputCtx.resume();
        }

        const constraints = {
            video: {
                facingMode: liveCameraFacing,
                width: { ideal: 640 },
                height: { ideal: 480 }
            },
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        };

        liveMediaStream = await navigator.mediaDevices.getUserMedia(constraints);
        const liveVideoFeed = document.getElementById('liveVideoFeed');
        if (liveVideoFeed) {
            liveVideoFeed.srcObject = liveMediaStream;
            liveVideoFeed.play();
        }

        setLiveState('connecting', 'กำลังขอรหัส Ephemeral Token...');
        const tokenRes = await fetch('/api/live-token');
        const tokenData = await tokenRes.json();
        
        if (!tokenData.token) {
            throw new Error(tokenData.error || 'ไม่สามารถขอ Ephemeral Token ได้');
        }

        setLiveState('connecting', 'กำลังเชื่อมต่อ WebSocket กับ Gemini 3.8 Live...');
        const wsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained?access_token=${tokenData.token}`;
        liveWs = new WebSocket(wsUrl);

        liveWs.onopen = () => {
            console.log('Gemini Live WebSocket Connected!');
            liveIsActive = true;
            
            const setupMessage = {
                setup: {
                    model: "models/gemini-3.8-live",
                    generationConfig: {
                        responseModalities: ["AUDIO"],
                        speechConfig: {
                            voiceConfig: {
                                prebuiltVoiceConfig: {
                                    voiceName: "Aoede"
                                }
                            }
                        }
                    },
                    systemInstruction: {
                        parts: [
                            {
                                text: `คุณคือ "น้องเพชร" AI ผู้ช่วยอัจฉริยะแบบเรียลไทม์ (Live Multimodal Assistant) ประจำจังหวัดเพชรบุรี และวิทยาลัยอาชีวศึกษาเพชรบุรี
- คุณกำลังมองเห็นผู้ใช้และสิ่งแวดล้อมผ่านกล้อง Webcam และฟังเสียงผ่านไมค์แบบสดๆ
- บุคลิกภาพ: สุภาพ สดใส เป็นมิตร กระตือรือร้น น้ำเสียงเป็นธรรมชาติ กระชับ ไม่เยิ่นเย้อ
- เมื่อผู้ใช้ยกสิ่งของ สถานที่ หรือภาพถ่ายขึ้นมา ให้บรรยายและคุยอย่างชาญฉลาด
- ตอบเป็นภาษาไทยเป็นหลัก หรือตอบภาษาที่ผู้ใช้สื่อสารด้วย`
                            }
                        ]
                    },
                    inputAudioTranscription: {},
                    outputAudioTranscription: {}
                }
            };
            liveWs.send(JSON.stringify(setupMessage));
        };

        liveWs.onmessage = async (event) => {
            try {
                let textData = '';
                if (event.data instanceof Blob) {
                    textData = await event.data.text();
                } else if (typeof event.data === 'string') {
                    textData = event.data;
                } else if (event.data instanceof ArrayBuffer) {
                    textData = new TextDecoder().decode(event.data);
                } else {
                    textData = event.data.toString();
                }

                const msg = JSON.parse(textData);
                
                if (msg.setupComplete) {
                    setLiveState('ready');
                    startAudioStreaming();
                    startVideoStreaming();
                    updateLiveAISubtitle('สวัสดีครับ! ผมเห็นคุณผ่านกล้องแล้ว เริ่มคุยหรือโชว์สิ่งของได้เลยครับ 😊');
                    const liveSensorHudText = document.getElementById('liveSensorHudText');
                    if (liveSensorHudText) {
                        liveSensorHudText.textContent = '📡 Sensor & AI: ตรวจพบคน • โต้ตอบสดเรียลไทม์';
                    }
                }

                if (msg.serverContent) {
                    const sc = msg.serverContent;
                    
                    if (sc.interrupted) {
                        stopLiveAudioPlayback();
                        setLiveState('listening');
                    }

                    if (sc.inputTranscription && sc.inputTranscription.text) {
                        updateLiveUserSubtitle(sc.inputTranscription.text);
                        setLiveState('thinking');
                    }

                    if (sc.outputTranscription && sc.outputTranscription.text) {
                        updateLiveAISubtitle(sc.outputTranscription.text);
                        setLiveState('speaking');
                    }

                    if (sc.modelTurn && sc.modelTurn.parts) {
                        setLiveState('speaking');
                        for (const part of sc.modelTurn.parts) {
                            if (part.inlineData && part.inlineData.data) {
                                const float32 = base64ToFloat32Array24k(part.inlineData.data);
                                playLiveAudioChunk(float32);
                            }
                        }
                    }
                }
            } catch (e) {
                console.error('Error parsing live WS message:', e);
            }
        };

        liveWs.onerror = (err) => {
            console.error('Live WS Error:', err);
            updateLiveAISubtitle('เกิดข้อผิดพลาดในการเชื่อมต่อ Live API กรุณากดเริ่มใหม่อีกครั้ง');
            stopLiveSession();
        };

        liveWs.onclose = () => {
            console.log('Live WS Closed');
            stopLiveSession();
        };

    } catch (err) {
        console.error('Start Live Session Failed:', err);
        alert(`ไม่สามารถเริ่มคุยสดได้: ${err.message}`);
        setLiveState('offline');
        stopLiveSession();
    }
}

function startAudioStreaming() {
    if (!liveMediaStream) return;
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    liveAudioInputCtx = new AudioContext();
    liveAudioSource = liveAudioInputCtx.createMediaStreamSource(liveMediaStream);
    liveScriptProcessor = liveAudioInputCtx.createScriptProcessor(4096, 1, 1);

    liveScriptProcessor.onaudioprocess = (e) => {
        if (!liveIsActive || !liveWs || liveWs.readyState !== WebSocket.OPEN || liveIsMuted) return;
        
        const inputData = e.inputBuffer.getChannelData(0);
        const downsampled = downsampleTo16k(inputData, liveAudioInputCtx.sampleRate);
        const pcm16 = floatTo16BitPCM(downsampled);
        const b64 = arrayBufferToBase64(pcm16);

        const realtimeInputMsg = {
            realtimeInput: {
                mediaChunks: [
                    {
                        mimeType: "audio/pcm;rate=16000",
                        data: b64
                    }
                ]
            }
        };
        liveWs.send(JSON.stringify(realtimeInputMsg));
    };

    liveAudioSource.connect(liveScriptProcessor);
    liveScriptProcessor.connect(liveAudioInputCtx.destination);
}

function startVideoStreaming() {
    if (liveVideoInterval) clearInterval(liveVideoInterval);
    
    liveVideoInterval = setInterval(() => {
        if (!liveIsActive || !liveWs || liveWs.readyState !== WebSocket.OPEN) return;
        const liveVideoFeed = document.getElementById('liveVideoFeed');
        const liveCanvasCapture = document.getElementById('liveCanvasCapture');
        if (!liveVideoFeed || liveVideoFeed.readyState < 2 || !liveCanvasCapture) return;

        const width = 480;
        const height = 360;
        liveCanvasCapture.width = width;
        liveCanvasCapture.height = height;
        const ctx = liveCanvasCapture.getContext('2d');
        ctx.drawImage(liveVideoFeed, 0, 0, width, height);
        
        const dataUrl = liveCanvasCapture.toDataURL('image/jpeg', 0.6);
        const b64 = dataUrl.split(',')[1];

        const videoMsg = {
            realtimeInput: {
                mediaChunks: [
                    {
                        mimeType: "image/jpeg",
                        data: b64
                    }
                ]
            }
        };
        liveWs.send(JSON.stringify(videoMsg));
    }, 1000);
}

function stopLiveSession() {
    liveIsActive = false;
    
    if (liveVideoInterval) {
        clearInterval(liveVideoInterval);
        liveVideoInterval = null;
    }

    if (liveWs) {
        try { liveWs.close(); } catch (e) {}
        liveWs = null;
    }

    if (liveScriptProcessor) {
        try {
            liveScriptProcessor.disconnect();
            if (liveAudioSource) liveAudioSource.disconnect();
        } catch (e) {}
        liveScriptProcessor = null;
        liveAudioSource = null;
    }

    if (liveAudioInputCtx) {
        try { liveAudioInputCtx.close(); } catch (e) {}
        liveAudioInputCtx = null;
    }

    stopLiveAudioPlayback();

    if (liveMediaStream) {
        liveMediaStream.getTracks().forEach(track => track.stop());
        liveMediaStream = null;
    }

    const liveVideoFeed = document.getElementById('liveVideoFeed');
    if (liveVideoFeed) {
        liveVideoFeed.srcObject = null;
    }

    setLiveState('offline');
}

function flipLiveCamera() {
    liveCameraFacing = liveCameraFacing === 'user' ? 'environment' : 'user';
    if (liveIsActive) {
        if (liveMediaStream) {
            liveMediaStream.getTracks().forEach(track => track.stop());
        }
        navigator.mediaDevices.getUserMedia({
            video: { facingMode: liveCameraFacing, width: { ideal: 640 }, height: { ideal: 480 } },
            audio: true
        }).then(stream => {
            liveMediaStream = stream;
            const liveVideoFeed = document.getElementById('liveVideoFeed');
            if (liveVideoFeed) {
                liveVideoFeed.srcObject = stream;
                liveVideoFeed.play();
            }
        }).catch(e => console.error('Error flipping camera:', e));
    }
}

function toggleLiveMicMute() {
    liveIsMuted = !liveIsMuted;
    const liveMuteIcon = document.getElementById('liveMuteIcon');
    if (liveMuteIcon) {
        if (liveIsMuted) {
            liveMuteIcon.className = 'fa-solid fa-microphone-slash text-sm text-red-400';
        } else {
            liveMuteIcon.className = 'fa-solid fa-microphone text-sm text-emerald-400';
        }
    }
}
