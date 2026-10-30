
function fallbackCopy(text) {
    try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
    } catch (e) {}
}
/**
 * nongphet AI Smart Guide - Chat System
 * Handles chat messaging, Local ML Intent Classifier badges, markdown rendering, and audio integration
 */

window.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }
});

function sendQuickMessage(text) {
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
        chatInput.value = text;
        sendChatMessage();
    }
}

async function sendChatMessage() {
    const chatInput = document.getElementById('chatInput');
    const chatBox = document.getElementById('chatBox');
    const typingIndicator = document.getElementById('typingIndicator');
    
    if (!chatInput) return;
    const text = chatInput.value.trim();
    if (!text) return;

    appendChatBubble('user', text);
    chatInput.value = '';

    isWaitingChatResponse = true;
    if (typeof setEmotion === 'function') setEmotion('thinking');
    if (typeof stopRecognitionSafe === 'function') {
        stopRecognitionSafe();
    }
    if (typeof isRealtimeVoiceActive !== 'undefined' && isRealtimeVoiceActive) {
        if (typeof setRealtimeVoiceStatus === 'function') {
            setRealtimeVoiceStatus('thinking', '⚡ น้องเพชรกำลังประมวลผลคำตอบ...');
        }
    }

    if (typingIndicator) typingIndicator.classList.remove('hidden');
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;

    // บริหารจัดการ Session ID สำหรับ Multi-turn Context Memory
    let sessionId = localStorage.getItem('nongphet_session_id');
    if (!sessionId) {
        sessionId = 'user_' + Math.random().toString(36).substring(2, 10);
        localStorage.setItem('nongphet_session_id', sessionId);
    }

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                language: currentLang,
                session_id: sessionId
            })
        });
        const data = await response.json();
        isWaitingChatResponse = false;
        if (typingIndicator) typingIndicator.classList.add('hidden');

        if (data.reply) {
            appendChatBubble('ai', data.reply, data);
            
            const targetEmotion = data.emotion || 'happy';
            const shouldSpeak = (typeof isRealtimeVoiceActive !== 'undefined' && isRealtimeVoiceActive) || (typeof autoSpeak !== 'undefined' && autoSpeak);
            
            if (shouldSpeak && typeof playTTS === 'function') {
                if (typeof isRealtimeVoiceActive !== 'undefined' && isRealtimeVoiceActive && typeof setRealtimeVoiceStatus === 'function') {
                    setRealtimeVoiceStatus('speaking', '🔊 น้องเพชรกำลังตอบกลับ...');
                }
                
                playTTS(data.reply, null, () => {
                    // When speech playback finishes
                    if (typeof setEmotion === 'function') {
                        setEmotion(targetEmotion);
                        setTimeout(() => {
                            if (!isSpeakingTTS && !isWaitingChatResponse && !isRecording) {
                                setEmotion('idle');
                            }
                        }, 3500);
                    }
                    if (typeof isRealtimeVoiceActive !== 'undefined' && isRealtimeVoiceActive) {
                        if (typeof setRealtimeVoiceStatus === 'function') {
                            setRealtimeVoiceStatus('listening', '🎙️ กำลังฟังเสียงคุณ... (พูดต่อได้เลยไม่ต้องกดปุ่ม)');
                        }
                        if (typeof startRecognitionSafe === 'function') {
                            setTimeout(() => {
                                startRecognitionSafe();
                            }, 300);
                        }
                    }
                });
            } else {
                if (typeof setEmotion === 'function') {
                    setEmotion(targetEmotion);
                    setTimeout(() => {
                        if (!isSpeakingTTS && !isWaitingChatResponse && !isRecording) {
                            setEmotion('idle');
                        }
                    }, 3500);
                }
                if (typeof isRealtimeVoiceActive !== 'undefined' && isRealtimeVoiceActive) {
                    if (typeof setRealtimeVoiceStatus === 'function') {
                        setRealtimeVoiceStatus('listening', '🎙️ กำลังฟังเสียงคุณ... (พูดต่อได้เลยไม่ต้องกดปุ่ม)');
                    }
                    if (typeof startRecognitionSafe === 'function') {
                        setTimeout(() => startRecognitionSafe(), 300);
                    }
                }
            }
        } else {
            if (typeof setEmotion === 'function') setEmotion('idle');
            appendChatBubble('ai', data.error || 'ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผล');
            if (typeof isRealtimeVoiceActive !== 'undefined' && isRealtimeVoiceActive && typeof startRecognitionSafe === 'function') {
                setTimeout(() => startRecognitionSafe(), 1000);
            }
        }
    } catch (err) {
        if (typeof setEmotion === 'function') setEmotion('idle');
        isWaitingChatResponse = false;
        if (typingIndicator) typingIndicator.classList.add('hidden');
        appendChatBubble('ai', 'ไม่สามารถเชื่อมต่อระบบ AI ได้ในขณะนี้');
        if (typeof isRealtimeVoiceActive !== 'undefined' && isRealtimeVoiceActive && typeof startRecognitionSafe === 'function') {
            setTimeout(() => startRecognitionSafe(), 1000);
        }
    }
}

function appendChatBubble(sender, text, meta = null) {
    const chatBox = document.getElementById('chatBox');
    if (!chatBox) return;

    const wrapper = document.createElement('div');
    wrapper.className = sender === 'user' ? 'flex items-end justify-end gap-3' : 'flex items-end gap-3';

    if (sender === 'ai') {
        const avatar = document.createElement('div');
        avatar.className = 'w-10 h-10 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-xl shrink-0 shadow-lg ring-2 ring-white/20';
        avatar.textContent = '🤖';
        wrapper.appendChild(avatar);
    }

    const bubble = document.createElement('div');
    bubble.className = sender === 'user' ? 'chat-bubble-user p-4 shadow-md max-w-[85%] md:max-w-[75%]' : 'chat-bubble-ai p-4 shadow-lg max-w-[85%] md:max-w-[75%] relative group';
    
    bubble.innerHTML = formatMarkdown(text);

    if (sender === 'ai') {
        // แสดง Debug Badge ยืนยันการประมวลผลผ่าน Local Machine Learning Model และ Cloud Engine
        if (meta && (meta.detected_intent || meta.intent)) {
            const intentName = meta.detected_intent || meta.intent;
            const confVal = meta.confidence ? (meta.confidence * 100).toFixed(1) : '99.0';
            const isLocal = ['local_model', 'semantic_rag', 'offline_fallback', 'local_slm'].includes(meta.engine);
            let engineLabel = '🤖 Gemini 2.5 Flash';
            let iconClass = 'fa-solid fa-wand-magic-sparkles';
            if (meta.engine === 'semantic_rag') {
                const ragScore = meta.rag_score ? ` (${(meta.rag_score * 100).toFixed(0)}%)` : '';
                engineLabel = `⚡ Local Semantic RAG${ragScore}`;
                iconClass = 'fa-solid fa-bolt text-emerald-600';
            } else if (meta.engine === 'local_model') {
                engineLabel = '⚡ Local Knowledge Base';
                iconClass = 'fa-solid fa-bolt text-emerald-600';
            } else if (meta.engine === 'offline_fallback') {
                engineLabel = '🛡️ Local Smart Fallback';
                iconClass = 'fa-solid fa-shield text-amber-600';
            } else if (meta.engine === 'local_slm') {
                engineLabel = '🦙 Local SLM (Qwen 2.5)';
                iconClass = 'fa-solid fa-brain text-teal-600';
            } else if (meta.engine === 'gemini_fallback') {
                engineLabel = '🔄 Gemini Flash-Lite';
                iconClass = 'fa-solid fa-arrows-rotate text-purple-600';
            }
            
            const badge = document.createElement('div');
            badge.className = 'mt-3 mb-1 flex flex-wrap items-center gap-1.5 text-[10px] font-mono-code';
            
            let badgesHtml = `
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200 font-bold shadow-xs">
                    <i class="fa-solid fa-microchip text-blue-500"></i> Local ML: <strong>${intentName}</strong> (${confVal}%)
                </span>
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md ${isLocal ? 'bg-emerald-50 text-emerald-800 border border-emerald-300' : 'bg-purple-50 text-purple-700 border border-purple-200'} font-semibold shadow-xs">
                    <i class="${iconClass}"></i> ${engineLabel}
                </span>
            `;

            // แสดง Badge หากมีการ Grounding ข้อมูลสดจาก Google Search
            if (meta.web_search && meta.web_search.length > 0) {
                const searchQueries = meta.web_search.join(', ');
                badgesHtml += `
                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 font-semibold shadow-xs">
                        <i class="fa-solid fa-globe text-amber-600"></i> Live Search: <strong>${searchQueries}</strong>
                    </span>
                `;
            }

            badge.innerHTML = badgesHtml;
            bubble.appendChild(badge);
        }

        // แสดง Interactive Suggestion Chips (ปุ่มคำถามต่อยอดที่คลิกได้ทันที)
        if (meta && meta.suggestions && meta.suggestions.length > 0) {
            const suggestContainer = document.createElement('div');
            suggestContainer.className = 'mt-3 pt-2.5 border-t border-slate-200/70 flex flex-wrap items-center gap-2';
            
            const label = document.createElement('span');
            label.className = 'text-[11px] font-bold text-slate-500 flex items-center gap-1 w-full';
            label.innerHTML = '<i class="fa-solid fa-lightbulb text-amber-500"></i> แนะนำคำถามต่อยอด (กดเพื่อถามทันที):';
            suggestContainer.appendChild(label);
            
            meta.suggestions.forEach(suggestText => {
                const chip = document.createElement('button');
                chip.className = 'text-xs bg-blue-50/90 hover:bg-blue-600 hover:text-white text-blue-700 px-3 py-1.5 rounded-xl border border-blue-200 transition-all font-medium flex items-center gap-1.5 shadow-2xs hover:shadow active:scale-95 cursor-pointer';
                chip.innerHTML = `<span>${suggestText}</span> <i class="fa-solid fa-arrow-turn-down text-[10px] opacity-60"></i>`;
                chip.onclick = () => {
                    sendQuickMessage(suggestText);
                };
                suggestContainer.appendChild(chip);
            });
            
            bubble.appendChild(suggestContainer);
        }

        const actionGroup = document.createElement('div');
        actionGroup.className = 'mt-2.5 pt-2 border-t border-slate-200/60 flex items-center justify-end gap-3 text-xs text-slate-500 font-semibold';
        
        const ttsBtn = document.createElement('button');
        ttsBtn.className = 'hover:text-blue-600 flex items-center gap-1 transition';
        ttsBtn.innerHTML = '<i class="fa-solid fa-volume-high text-blue-500"></i> ฟังเสียง';
        ttsBtn.onclick = () => playTTS(text, ttsBtn);
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'hover:text-blue-600 flex items-center gap-1 transition';
        copyBtn.innerHTML = '<i class="fa-solid fa-copy"></i> คัดลอก';
        copyBtn.onclick = () => {
            navigator.clipboard.writeText(text);
            copyBtn.innerHTML = '<i class="fa-solid fa-check text-emerald-500"></i> คัดลอกแล้ว';
            setTimeout(() => copyBtn.innerHTML = '<i class="fa-solid fa-copy"></i> คัดลอก', 2000);
        };

        const qrBtn = document.createElement('button');
        qrBtn.className = 'hover:text-cyan-600 flex items-center gap-1 transition text-cyan-600 font-bold';
        qrBtn.innerHTML = '<i class="fa-solid fa-qrcode text-cyan-500"></i> สแกนเข้ามือถือ';
        qrBtn.onclick = () => openMobileHandoffQR(text, meta ? (meta.detected_intent || meta.intent) : 'travel');

        actionGroup.appendChild(ttsBtn);
        actionGroup.appendChild(copyBtn);
        actionGroup.appendChild(qrBtn);
        bubble.appendChild(actionGroup);
    }

    wrapper.appendChild(bubble);
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// -----------------------------------------------------------------------------
// Mobile Handoff: สร้างและแสดงผล QR Code สำหรับส่งข้อมูลเข้าสมาร์ตโฟน
// -----------------------------------------------------------------------------
async function openMobileHandoffQR(content, intent = 'travel') {
    let modal = document.getElementById('qrHandoffModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'qrHandoffModal';
        modal.className = 'fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 transition-opacity';
        document.body.appendChild(modal);
    }
    
    modal.innerHTML = `
        <div class="bg-slate-900 border border-cyan-500/40 rounded-3xl p-6 max-w-sm w-full text-center shadow-2xl relative animate-scale-up">
            <button onclick="document.getElementById('qrHandoffModal').classList.add('hidden')" class="absolute top-4 right-4 text-slate-400 hover:text-white text-lg">
                <i class="fa-solid fa-xmark"></i>
            </button>
            <div class="w-12 h-12 rounded-2xl bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-2xl mx-auto mb-3 text-cyan-300">
                <i class="fa-solid fa-qrcode"></i>
            </div>
            <h3 class="text-base font-extrabold text-white">ส่งข้อมูลเข้าสมาร์ตโฟน</h3>
            <p class="text-xs text-slate-400 mt-1 mb-4">เปิดกล้องมือถือสแกน QR Code เพื่อนำข้อมูลและแผนที่ Google Maps กลับบ้านได้ทันที</p>
            
            <div id="qrLoadingBox" class="py-12 flex flex-col items-center justify-center text-cyan-400 text-sm">
                <i class="fa-solid fa-spinner fa-spin text-3xl mb-2"></i>
                <span>กำลังสร้าง QR Code...</span>
            </div>
            
            <div id="qrContentBox" class="hidden">
                <div class="p-3 bg-white rounded-2xl inline-block shadow-lg mx-auto">
                    <img id="qrImg" class="w-52 h-52 object-contain" alt="QR Code">
                </div>
                <div class="mt-4 flex flex-col gap-2">
                    <a id="qrDirectLink" href="#" target="_blank" class="py-2.5 px-4 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-bold text-xs flex items-center justify-center gap-1.5 shadow-md hover:from-blue-500 hover:to-indigo-500 transition">
                        <i class="fa-solid fa-arrow-up-right-from-square"></i> เปิดดูบนเบราว์เซอร์หน้านี้
                    </a>
                </div>
            </div>
        </div>
    `;
    modal.classList.remove('hidden');

    try {
        const res = await fetch('/api/share', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: 'คำแนะนำจากน้องเพชร AI Smart Guide',
                content: content,
                intent: intent,
                maps_query: 'วิทยาลัยอาชีวศึกษาเพชรบุรี'
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            document.getElementById('qrLoadingBox').classList.add('hidden');
            const qrBox = document.getElementById('qrContentBox');
            qrBox.classList.remove('hidden');
            const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(data.share_url)}`;
            document.getElementById('qrImg').src = qrUrl;
            document.getElementById('qrDirectLink').href = data.share_url;
        }
    } catch (e) {
        document.getElementById('qrLoadingBox').innerHTML = '<span class="text-rose-400">เกิดข้อผิดพลาดในการสร้าง QR Code</span>';
    }
}
