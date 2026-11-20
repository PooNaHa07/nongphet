/**
 * static/js/local_stt.js — ตัวฟังเสียงพูดของน้องเพชร (แทน Web Speech API)
 *
 * Chromium บน Raspberry Pi ใช้ webkitSpeechRecognition ไม่ได้ (error: network เพราะไม่มีคีย์ Google)
 * ไฟล์นี้ให้คลาส NongPhetSpeechRecognition ที่ใช้งานเหมือน SpeechRecognition ทุกอย่าง
 * (start/stop/abort, lang, onstart/onresult/onerror/onend ...) ให้ main.js ใช้ได้โดยไม่ต้องแก้ตรรกะเดิม:
 *
 *   - เซิร์ฟเวอร์เสียงในบูธมีตัวถอดเสียง (Whisper ภาษาไทย) -> อัดเสียงเอง ตรวจจับช่วงพูด/ช่วงเงียบ
 *     แล้วส่ง WAV 16 kHz ไป /api/stt บน Pi (Pi ส่งต่อให้โน้ตบุ๊ก)
 *   - ไม่มี -> ใช้ Web Speech ของเบราว์เซอร์ตามเดิม (เช่น เปิดบน Chrome ของคอมพิวเตอร์)
 */
(function () {
    const NativeSR = window.SpeechRecognition || window.webkitSpeechRecognition || null;

    // ค่าที่วัดจริงจากไมค์เว็บแคมบน Pi (ผ่าน noise suppression + auto gain ของเบราว์เซอร์):
    //   เสียงรบกวนรอบข้าง RMS ~0.015, เสียงพูด ~0.03-0.09, ช่วง ~0.5-2 วินาทีแรกหลังเปิดไมค์มีเสียงกระชาก ~0.2-0.3
    const VAD = {
        minSpeechMs: 200,         // เสียงดังสะสมเท่านี้ถึงนับว่าเริ่มพูด (ช่องว่างระหว่างพยางค์ไม่รีเซ็ต)
        endSilenceMs: 900,        // เงียบต่อเนื่องเท่านี้หลังพูด = พูดจบ
        noSpeechMs: 8000,         // ไม่พูดเลยภายในเวลานี้ = no-speech (เหมือน Web Speech)
        maxUtteranceMs: 10000,    // พูดยาวสุดต่อครั้ง (คำถามที่ตู้สั้นกว่านี้ ถ้าห้องเสียงดังจนจับเงียบไม่ได้ จะตัดที่นี่)
        endRelPeak: 0.2,          // หลังเริ่มพูด: เสียงเบากว่า 20% ของเสียงพูดที่ดังสุด นับเป็น "เงียบ" (ห้องที่มีเสียงคนคุย)
        endRelCap: 0.025,         // ...แต่เกณฑ์นี้ไม่เกินระดับนี้ (เสียงกระแทกครั้งเดียวจะได้ไม่ตัดคำพูดปกติ ~0.03-0.09)
        minLevel: 0.008,          // ความดังขั้นต่ำ (RMS) ที่นับว่าเป็นเสียงพูด
        noiseFactor: 1.8,         // ต้องดังกว่าเสียงรบกวนรอบข้างกี่เท่า (+ noiseMargin)
        noiseMargin: 0.006,
        sustainFactor: 1.3,       // หลังเริ่มพูดแล้ว: เกณฑ์ "ยังพูดอยู่" ต่ำลง (hysteresis)
        sustainMargin: 0.003,
        minVoicedMs: 450,         // เสียงพูดจริงสั้นกว่านี้ไม่ส่งถอดความ (กัน Whisper แต่งคำจากเสียงรบกวน)
        initialFloor: 0.015,      // ระดับเสียงรบกวนเริ่มต้น ก่อนเรียนรู้จากห้องจริง
        preRollMs: 300,           // เก็บเสียงก่อนเริ่มพูดไว้ด้วย กันคำแรกขาด
    };

    // แจ้งสถานะเสียงพูดของผู้ใช้ให้จอใบหน้าแสดง (กำลังฟัง / กำลังแปลงเสียง / ข้อความที่พูด)
    function reportUserSpeech(state, text = '') {
        try {
            fetch('/api/user-speech', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state, text }), keepalive: true
            }).catch(() => {});
        } catch (e) {}
    }

    let localAvailable = null;     // null = ยังไม่รู้, true/false = ผลจาก /api/stt/status
    let statusPromise = null;

    function checkLocalStt(force = false) {
        if (!force && statusPromise) return statusPromise;
        statusPromise = fetch('/api/stt/status' + (force ? '?refresh=1' : ''))
            .then(r => r.json())
            .then(d => { localAvailable = !!d.available; return localAvailable; })
            .catch(() => { localAvailable = false; return false; });
        return statusPromise;
    }

    function encodeWav16k(chunks, inputRate) {
        // รวมเสียง -> ลดอัตราสุ่มเป็น 16 kHz (เฉลี่ยช่วง) -> PCM 16-bit WAV
        let total = 0;
        chunks.forEach(c => { total += c.length; });
        const ratio = inputRate / 16000;
        const outLen = Math.floor(total / ratio);
        const out = new Int16Array(outLen);
        let ci = 0, offset = 0;
        const sampleAt = (globalIdx) => {
            while (ci < chunks.length && globalIdx >= offset + chunks[ci].length) { offset += chunks[ci].length; ci++; }
            return ci < chunks.length ? chunks[ci][globalIdx - offset] : 0;
        };
        for (let i = 0; i < outLen; i++) {
            const start = Math.floor(i * ratio), end = Math.min(total, Math.floor((i + 1) * ratio));
            let sum = 0, n = 0;
            for (let j = start; j < end; j++) { sum += sampleAt(j); n++; }
            const v = Math.max(-1, Math.min(1, n ? sum / n : 0));
            out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
        }
        const buf = new ArrayBuffer(44 + out.length * 2);
        const dv = new DataView(buf);
        const w = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
        w(0, 'RIFF'); dv.setUint32(4, 36 + out.length * 2, true); w(8, 'WAVE');
        w(12, 'fmt '); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
        dv.setUint32(24, 16000, true); dv.setUint32(28, 32000, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
        w(36, 'data'); dv.setUint32(40, out.length * 2, true);
        new Int16Array(buf, 44).set(out);
        return new Blob([buf], { type: 'audio/wav' });
    }

    // ไมค์เปิดค้างไว้ตลอด (เปิดครั้งเดียวตอนฟังครั้งแรก): ทุกครั้งที่เปิดไมค์ใหม่ auto gain ของเบราว์เซอร์
    // จะกระชากเสียงดังอยู่ราว 2 วินาที ทำให้จับผิดว่าเป็นเสียงพูด และต้องรอทุกรอบ
    const Mic = { ready: null, stream: null, ctx: null, proc: null, handler: null,
                  sampleRate: 48000, frameMs: 2048 / 48000 * 1000, warmUntil: 0, noiseFloor: VAD.initialFloor };
    const MIC_WARMUP_MS = 2000;

    function ensureMic() {
        if (Mic.ready) {
            return Mic.ready.then(() => {
                if (Mic.ctx && Mic.ctx.state === 'suspended') Mic.ctx.resume().catch(() => {});
                const live = Mic.stream && Mic.stream.getAudioTracks().some(t => t.readyState === 'live');
                if (!live) { Mic.ready = null; return ensureMic(); }   // ไมค์หลุด (ถอดสาย) เปิดใหม่
            });
        }
        Mic.ready = (async () => {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 }
            });
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const source = ctx.createMediaStreamSource(stream);
            const proc = ctx.createScriptProcessor(2048, 1, 1);
            Mic.stream = stream; Mic.ctx = ctx; Mic.proc = proc;
            Mic.sampleRate = ctx.sampleRate;
            Mic.frameMs = 2048 / ctx.sampleRate * 1000;
            Mic.warmUntil = performance.now() + MIC_WARMUP_MS;
            proc.onaudioprocess = (e) => {
                const h = Mic.handler;
                if (!h || performance.now() < Mic.warmUntil) return;
                const input = e.inputBuffer.getChannelData(0);
                const copy = new Float32Array(input);
                let sum = 0;
                for (let i = 0; i < copy.length; i++) sum += copy[i] * copy[i];
                h(copy, Math.sqrt(sum / copy.length));
            };
            source.connect(proc);
            proc.connect(ctx.destination);   // ScriptProcessor ต้องต่อออกปลายทางถึงจะทำงาน (ไม่เขียน output = ไม่มีเสียงออก)
            if (ctx.state === 'suspended') await ctx.resume().catch(() => {});
            // รอให้พ้นช่วงกระชากก่อนเริ่มฟังครั้งแรก
            await new Promise(r => setTimeout(r, MIC_WARMUP_MS));
        })().catch(err => { Mic.ready = null; throw err; });
        return Mic.ready;
    }

    class NongPhetSpeechRecognition {
        constructor() {
            this.lang = 'th-TH';
            this.continuous = false;
            this.interimResults = false;
            this.maxAlternatives = 1;
            this.onstart = this.onaudiostart = this.onspeechstart = this.onspeechend = null;
            this.onresult = this.onerror = this.onend = this.onaudioend = this.onnomatch = null;
            this._mode = null;          // 'local' | 'native'
            this._native = null;
            this._active = false;
            this._session = 0;
        }

        _emit(name, ev = {}) {
            const fn = this['on' + name];
            if (typeof fn === 'function') {
                try { fn.call(this, ev); } catch (e) { console.error('[STT] handler error', e); }
            }
        }

        _langCode() {
            const l = (this.lang || 'th').toLowerCase();
            return l.startsWith('en') ? 'en' : (l.startsWith('zh') ? 'zh' : 'th');
        }

        start() {
            if (this._active) {
                const err = new Error('recognition has already started');
                err.name = 'InvalidStateError';
                throw err;          // เหมือน Web Speech: main.js จับ error นี้อยู่แล้ว
            }
            this._active = true;
            const session = ++this._session;
            checkLocalStt().then(ok => {
                if (session !== this._session || !this._active) return;
                if (ok) { this._mode = 'local'; this._startLocal(session); }
                else if (NativeSR) { this._mode = 'native'; this._startNative(); }
                else { this._active = false; this._emit('error', { error: 'not-allowed', message: 'no speech recognizer' }); this._emit('end'); }
            });
        }

        stop() { this._finish(true); }
        abort() { this._finish(false); }

        _finish(sendAudio) {
            if (!this._active) return;
            if (this._mode === 'native' && this._native) {
                try { sendAudio ? this._native.stop() : this._native.abort(); } catch (e) {}
                return;
            }
            if (this._mode === 'local' && this._local) {
                this._local.stopRequested = sendAudio ? 'stop' : 'abort';
                return;
            }
            // ยังไม่ทันเริ่มจริง
            this._active = false;
            this._session++;
            this._emit('end');
        }

        // ---------------- Web Speech ของเบราว์เซอร์ (สำรอง) ----------------
        _startNative() {
            if (!this._native) {
                this._native = new NativeSR();
                ['start', 'audiostart', 'speechstart', 'speechend', 'audioend', 'result', 'nomatch'].forEach(n => {
                    this._native['on' + n] = (ev) => this._emit(n, ev);
                });
                this._native.onerror = (ev) => {
                    // Chromium บน Pi: network = ไม่มีบริการของ Google -> ลองถามหาตัวถอดเสียงในบูธใหม่
                    if (ev && ev.error === 'network') checkLocalStt(true);
                    this._emit('error', ev);
                };
                this._native.onend = (ev) => { this._active = false; this._emit('end', ev); };
            }
            this._native.lang = this.lang;
            this._native.continuous = this.continuous;
            this._native.interimResults = this.interimResults;
            try { this._native.start(); } catch (e) { this._active = false; this._emit('error', { error: 'aborted' }); this._emit('end'); }
        }

        // ---------------- ตัวถอดเสียงในบูธ (Whisper) ----------------
        async _startLocal(session) {
            const st = { stopRequested: null, chunks: [], preRoll: [], speaking: false, speechMs: 0, silenceMs: 0,
                         elapsedMs: 0, peak: 0, done: false, voicedMs: 0, speechPeak: 0, endReason: '' };
            this._local = st;
            let handler = null;
            const detach = () => { if (Mic.handler === handler) Mic.handler = null; };
            const end = (error) => {
                st.done = true;
                detach();
                if (session !== this._session) return;
                this._active = false;
                this._local = null;
                if (error) this._emit('error', { error });
                this._emit('end');
            };
            try {
                await ensureMic();
            } catch (e) {
                return end('not-allowed');
            }
            if (session !== this._session || st.stopRequested === 'abort') return end(null);

            const frameMs = Mic.frameMs;
            const preRollFrames = Math.ceil(VAD.preRollMs / frameMs);
            this._emit('start');
            this._emit('audiostart');

            const finishUtterance = async () => {
                if (st.done) return;
                st.done = true;
                detach();
                this._emit('speechend');
                this._emit('audioend');
                if (st.stopRequested === 'abort') return end(null);
                if (!st.speaking || !st.chunks.length || st.voicedMs < VAD.minVoicedMs) {
                    if (st.speaking) reportUserSpeech('clear');
                    return end('no-speech');
                }
                const wav = encodeWav16k(st.chunks, Mic.sampleRate);
                const audioSec = st.chunks.length * frameMs / 1000;
                const t0 = performance.now();
                reportUserSpeech('transcribing');
                try {
                    const res = await fetch('/api/stt?lang=' + this._langCode(), {
                        method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: wav
                    });
                    const data = await res.json();
                    const sttMs = Math.round(performance.now() - t0);
                    // จับเวลาไว้ดูใน console: พูดจบเพราะเงียบ (silence) หรือยาวจนถูกตัด (max-length = ห้องเสียงดัง)
                    console.info(`🎧 [STT] จบเพราะ ${st.endReason}, เสียง ${audioSec.toFixed(1)} วิ, ถอดความ ${sttMs} ms: "${(data.text || '').trim()}"`);
                    if (session !== this._session) return;
                    if (!res.ok) { reportUserSpeech('clear'); checkLocalStt(true); return end('network'); }
                    const text = (data.text || '').trim();
                    if (!text) { reportUserSpeech('clear'); return end('no-speech'); }
                    reportUserSpeech('final', text);
                    const result = [{ transcript: text, confidence: 0.9 }];
                    result.isFinal = true;
                    this._emit('result', { resultIndex: 0, results: [result] });
                    end(null);
                } catch (e) {
                    reportUserSpeech('clear');
                    checkLocalStt(true);
                    end('network');
                }
            };

            handler = (copy, rms) => {
                if (st.done) return;
                st.elapsedMs += frameMs;
                if (st.stopRequested === 'abort') return end(null);
                if (st.stopRequested === 'stop') { st.endReason = 'stop'; return finishUtterance(); }

                const threshold = Math.max(VAD.minLevel, Mic.noiseFloor * VAD.noiseFactor + VAD.noiseMargin);
                const loud = rms > threshold;
                st.peak = Math.max(st.peak, rms);
                window.nongphetSttLevel = { rms, threshold, noiseFloor: Mic.noiseFloor, peak: st.peak, speaking: st.speaking };

                if (!st.speaking) {
                    // เรียนรู้เสียงรบกวนจากเฟรมที่เงียบเท่านั้น (ลดเร็ว เพิ่มช้า) ใช้ต่อเนื่องข้ามรอบการฟัง
                    if (!loud) Mic.noiseFloor = rms < Mic.noiseFloor ? Mic.noiseFloor * 0.8 + rms * 0.2 : Mic.noiseFloor * 0.97 + rms * 0.03;
                    st.preRoll.push(copy);
                    if (st.preRoll.length > preRollFrames) st.preRoll.shift();
                    // ดังสะสม: เงียบสั้นๆ ระหว่างพยางค์ลดลงครึ่งเดียว ไม่รีเซ็ตเป็นศูนย์
                    st.speechMs = loud ? st.speechMs + frameMs : Math.max(0, st.speechMs - frameMs / 2);
                    if (st.speechMs >= VAD.minSpeechMs) {
                        st.speaking = true;
                        st.chunks = st.preRoll.slice();
                        st.silenceMs = 0;
                        this._emit('speechstart');
                        reportUserSpeech('listening');
                    } else if (st.elapsedMs >= VAD.noSpeechMs) {
                        return end('no-speech');
                    }
                    return;
                }
                st.chunks.push(copy);
                // พูดอยู่แล้ว: ใช้เกณฑ์ "ยังพูดอยู่" ต่ำกว่าเกณฑ์เริ่มพูด (hysteresis) เสียงเบาลงช่วงท้ายคำจะไม่ถูกตัด
                st.speechPeak = Math.max(st.speechPeak, rms);
                // ห้องที่มีเสียงคนคุย เสียงรบกวนดังกว่าเกณฑ์ "ยังพูดอยู่" ตลอด จึงเทียบกับเสียงพูดที่ดังสุดด้วย
                const sustain = Math.max(VAD.minLevel * 0.75, Mic.noiseFloor * VAD.sustainFactor + VAD.sustainMargin,
                                         Math.min(st.speechPeak * VAD.endRelPeak, VAD.endRelCap));
                const voiced = rms > sustain;
                if (voiced) st.voicedMs += frameMs;
                st.silenceMs = voiced ? 0 : st.silenceMs + frameMs;
                if (st.silenceMs >= VAD.endSilenceMs) { st.endReason = 'silence'; finishUtterance(); }
                else if (st.chunks.length * frameMs >= VAD.maxUtteranceMs) { st.endReason = 'max-length'; finishUtterance(); }
            };
            Mic.handler = handler;
        }
    }

    window.NongPhetSpeechRecognition = NongPhetSpeechRecognition;
    window.nongphetCheckLocalStt = checkLocalStt;
    checkLocalStt();
})();
