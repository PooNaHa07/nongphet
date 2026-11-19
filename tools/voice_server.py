#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
เซิร์ฟเวอร์เสียงน้องเพชร (OmniVoice) — รันบนโน้ตบุ๊กที่มี GPU ภายในบูธ

Raspberry Pi ส่งข้อความมาที่ POST /synthesize แล้วได้ไฟล์ MP3 เสียงน้องเพชรกลับไป
(รูปแบบเดียวกับแคชเสียง: MP3 24kHz 48kbps mono) ทำงานผ่านวงแลนของบูธ ไม่ต้องใช้อินเทอร์เน็ต
(ยกเว้นครั้งแรกที่ดาวน์โหลดโมเดลจาก Hugging Face)

ติดตั้งบนโน้ตบุ๊ก (NVIDIA GPU):
    pip install torch==2.8.0+cu128 torchaudio==2.8.0+cu128 --extra-index-url https://download.pytorch.org/whl/cu128
    pip install omnivoice lameenc flask

เตรียมเสียงต้นแบบ (ดู voices/README.md):
    voices/nongphet_ref.wav หรือ .mp3   เสียงนักศึกษาที่ยินยอม 3-10 วินาที
    voices/nongphet_ref.txt   ข้อความที่อ่านในไฟล์เสียง (ต้องตรงทุกคำ, ถ้าไม่มี OmniVoice จะถอดเสียงเอง)

รัน:
    python tools/voice_server.py --port 8010
แล้วตั้งค่าบน Pi ใน .env:
    TTS_ENGINE=omnivoice
    VOICE_SERVER_URL=http://<IP โน้ตบุ๊ก>:8010
    VOICE_SERVER_TOKEN=<รหัสเดียวกับที่ตั้งบนโน้ตบุ๊ก>

ค่าที่ปรับได้ (environment):
    OMNIVOICE_MODEL   รุ่นโมเดล (ค่าเริ่มต้น k2-fsa/OmniVoice หรือรุ่นไทย hotdogs/omnivoice-thai)
    OMNIVOICE_DEVICE  อุปกรณ์ (ค่าเริ่มต้น cuda:0)
    OMNIVOICE_DTYPE   float32 (ค่าเริ่มต้น) หรือ float16
                      การ์ด GTX 16xx เช่น GTX 1650: float32 เร็วกว่า float16 ประมาณ 4 เท่า (วัดจริง)
                      การ์ด RTX รุ่นใหม่: ลอง float16 แล้วเทียบ
    OMNIVOICE_TOKENIZER_DEVICE  cpu (ค่าเริ่มต้น: ย้าย audio tokenizer ออกจาก GPU กัน VRAM 4 GB ล้น)
    OMNIVOICE_SEED    7 (ค่าเริ่มต้น: ล็อกการสุ่มให้โทนเสียงคงที่) หรือ random
                      เปลี่ยน seed แล้วต้องเปลี่ยน VOICE_ID บน Pi และอัดเสียงใหม่
    WHISPER_ENABLED   1 (ค่าเริ่มต้น: เปิดถอดเสียงพูด /transcribe ให้หน้า kiosk บน Pi) หรือ 0
    WHISPER_MODEL     biodatlab/distill-whisper-th-small (เร็ว) หรือ biodatlab/whisper-th-small-combined (แม่นกว่า)
    WHISPER_DEVICE    cpu (ค่าเริ่มต้น กัน VRAM 4 GB ล้น) หรือ cuda:0 สำหรับการ์ด 8 GB ขึ้นไป
    OMNIVOICE_FAST    1 (ค่าเริ่มต้น: ทางลัด CFG เร็วขึ้น ~25%) หรือ 0 ใช้โค้ดต้นฉบับ
    OMNIVOICE_STEPS_LIVE  จำนวนรอบสร้างเสียงตอนตอบสด (ค่าเริ่มต้น 32: เท่ากับตอนอัดเก็บ โทนเสียงจึงตรงกัน)
    OMNIVOICE_STEPS_BAKE  จำนวนรอบตอนอัดเสียงเก็บล่วงหน้า (ค่าเริ่มต้น 32: คุณภาพสูงสุด)
                      วัดบน GTX 1650 float32 (tokenizer บน CPU, ต้นแบบ 5 วินาที) ประโยค 6.7 วินาที: 8 รอบ ~6 วินาที, 32 รอบ ~20
    OMNIVOICE_SPEED   ความเร็วพูด (ค่าเริ่มต้น 1.0)
    VOICE_SERVER_TOKEN  รหัสป้องกันไม่ให้เครื่องอื่นในวงแลนเรียกใช้

สัญญาอนุญาต: โค้ด OmniVoice เป็น Apache-2.0 แต่ weights เป็น CC-BY-NC (ห้ามใช้เชิงพาณิชย์)
ห้ามโคลนเสียงบุคคลที่ไม่ได้ยินยอม
"""
import os
import sys
import hmac
import time
import io
import argparse
import threading

from flask import Flask, request, jsonify, Response

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICES_DIR = os.path.join(ROOT, 'voices')
REF_AUDIO_CANDIDATES = [os.path.join(VOICES_DIR, f'nongphet_ref.{ext}') for ext in ('wav', 'mp3', 'flac')]
REF_TEXT = os.path.join(VOICES_DIR, 'nongphet_ref.txt')
PROMPT_FILE = os.path.join(VOICES_DIR, 'nongphet_voice.pt')

SAMPLE_RATE = 24000          # OmniVoice ส่งเสียงออกที่ 24 kHz
MP3_BITRATE_KBPS = 48        # ต้องตรงกับรูปแบบแคชเสียงบน Pi (services/tts_service.py)
MAX_TEXT_CHARS = 2500
DEFAULT_SEED = 7             # เลือกจากการฟังเทียบ (tools/pick_seed.py) เปลี่ยนแล้วต้องเปลี่ยน VOICE_ID ด้วย


def encode_mp3(samples, sample_rate=SAMPLE_RATE, bitrate=MP3_BITRATE_KBPS):
    """แปลงเสียง float (-1..1) เป็น MP3 mono ด้วย lameenc (ไม่ต้องติดตั้ง ffmpeg)"""
    import numpy as np
    import lameenc
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).astype('<i2').tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate)
    enc.set_in_sample_rate(sample_rate)
    enc.set_channels(1)
    enc.set_quality(2)
    return bytes(enc.encode(pcm) + enc.flush())


class OmniVoiceBackend:
    """โหลดโมเดลครั้งเดียว และสร้างเสียงด้วยเสียงต้นแบบของน้องเพชร (ใช้ GPU ทีละคำขอ)"""

    def __init__(self, model_id, device, steps, speed, dtype='float32', bake_steps=None, seed=None):
        self.model_id = model_id
        self.device = device
        self.steps = steps                     # ตอบสด
        self.bake_steps = bake_steps or steps  # อัดเก็บล่วงหน้า
        self.speed = speed
        self.dtype = dtype
        self.seed = seed                       # ล็อกการสุ่ม: ข้อความเดิมได้เสียงเดิมทุกครั้ง (None = สุ่มใหม่ทุกครั้ง)
        self.model = None
        self.prompt = None
        self.lock = threading.Lock()

    def load(self):
        import torch
        from omnivoice import OmniVoice, VoiceClonePrompt
        if os.environ.get('OMNIVOICE_FAST', '1').strip() != '0':
            # แยก forward ของ CFG uncond ให้ยาวเท่าเสียงเป้าหมาย: เร็วขึ้น ~25% (tools/omnivoice_fast.py)
            import omnivoice_fast
            omnivoice_fast.install()
            print("⚡ เปิดทางลัดถอดรหัส OmniVoice (OMNIVOICE_FAST=0 เพื่อปิด)")
        print(f"📥 กำลังโหลด {self.model_id} บน {self.device} ({self.dtype}) ...")
        self.model = OmniVoice.from_pretrained(self.model_id, device_map=self.device,
                                               dtype=getattr(torch, self.dtype))
        if os.path.exists(PROMPT_FILE):
            self.prompt = VoiceClonePrompt.load(PROMPT_FILE)
        else:
            ref_audio = next((p for p in REF_AUDIO_CANDIDATES if os.path.exists(p)), None)
            if not ref_audio:
                raise SystemExit(f"ไม่พบเสียงต้นแบบใน {VOICES_DIR} (nongphet_ref.wav/.mp3) ดู voices/README.md")
            kwargs = {'ref_audio': ref_audio}
            if os.path.exists(REF_TEXT):
                with open(REF_TEXT, encoding='utf-8') as f:
                    kwargs['ref_text'] = f.read().strip()
            else:
                # ไม่มีข้อความ: OmniVoice ถอดเสียงเองด้วย Whisper (แม่นยำน้อยกว่าพิมพ์เอง)
                print(f"⚠️ ไม่พบ {REF_TEXT}: ให้ OmniVoice ถอดข้อความจากเสียงเอง แนะนำให้พิมพ์ข้อความที่อ่านจริงใส่ไฟล์นี้")
            self.prompt = self.model.create_voice_clone_prompt(**kwargs)
            self.prompt.save(PROMPT_FILE)
            print(f"💾 บันทึกเสียงต้นแบบที่เตรียมแล้ว: {PROMPT_FILE} (ลบไฟล์นี้เมื่อเปลี่ยนเสียงต้นแบบ)")
        # ตัวแปลงเสียง (audio tokenizer ~760 MiB) ใช้แค่ตอนเตรียมต้นแบบและถอดเสียงท้ายสุด
        # ย้ายไป CPU เพื่อให้ VRAM 4 GB ไม่ล้นไปใช้ RAM ระบบ (ล้นแล้วช้าลง 5-17 เท่า)
        tok_device = os.environ.get('OMNIVOICE_TOKENIZER_DEVICE', 'cpu').strip() or 'cpu'
        if tok_device != self.device:
            self.model.audio_tokenizer.to(tok_device)
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print(f"↪️ ย้าย audio tokenizer ไป {tok_device} (ประหยัด VRAM)")
        print("✅ พร้อมสร้างเสียงน้องเพชร")

    def synthesize(self, text, purpose='live', seed=None):
        import torch
        steps = self.bake_steps if purpose == 'bake' else self.steps
        seed = self.seed if seed is None else seed
        with self.lock:
            if seed is not None:
                torch.manual_seed(seed)        # ตั้งทั้ง CPU และ CUDA
            audio = self.model.generate(text=text, voice_clone_prompt=self.prompt,
                                        num_step=steps, speed=self.speed)
        return audio[0]


MAX_STT_SECONDS = 30            # Whisper ฟังได้ครั้งละไม่เกิน 30 วินาที
MAX_STT_BYTES = 2 * 1024 * 1024  # WAV 16 kHz 16-bit mono 30 วินาที ~ 1 MB
WHISPER_LANGS = {'th': 'th', 'en': 'en', 'zh': 'zh'}


class WhisperBackend:
    """
    ถอดเสียงพูดเป็นข้อความด้วย Whisper ที่ฝึกภาษาไทย (แทน Web Speech ของ Chromium บน Pi ที่ใช้ไม่ได้)
    ค่าเริ่มต้น biodatlab/distill-whisper-th-small บน CPU (i5-10300H): ประโยค 3 วินาที ~2-3 วินาที
    (บน GPU เร็วกว่า ~0.8 วินาที แต่การ์ด 4 GB ใส่คู่กับ OmniVoice แล้ว VRAM ล้น)
    แม่นกว่าแต่ช้ากว่า: WHISPER_MODEL=biodatlab/whisper-th-small-combined (~2.5 วินาที, ~1.1 GB)
    ต้องใช้ float32 บนการ์ด GTX 16xx (float16 ให้ผลเป็น !!!!)
    """

    def __init__(self, model_id, device):
        self.model_id = model_id
        self.device = device
        self.model = None
        self.processor = None
        self.lock = threading.Lock()

    def load(self):
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        print(f"🎧 กำลังโหลดตัวถอดเสียง {self.model_id} บน {self.device} ...")
        self.processor = WhisperProcessor.from_pretrained(self.model_id)
        self.model = WhisperForConditionalGeneration.from_pretrained(
            self.model_id, torch_dtype=torch.float32).to(self.device).eval()
        with torch.inference_mode():                       # อุ่นเครื่อง ครั้งแรกจะได้ไม่ช้า
            self._generate([0.0] * 16000, 'th', max_new_tokens=4)
        print("✅ พร้อมฟังเสียงพูด")

    def _generate(self, samples, lang, max_new_tokens=180):
        import torch
        feats = self.processor(samples, sampling_rate=16000, return_tensors='pt').input_features
        ids = self.model.generate(feats.to(self.device, torch.float32), language=WHISPER_LANGS.get(lang, 'th'),
                                  task='transcribe', max_new_tokens=max_new_tokens)
        return self.processor.batch_decode(ids, skip_special_tokens=True)[0]

    def transcribe(self, samples, lang='th'):
        import torch
        with self.lock, torch.inference_mode():
            text = self._generate(samples, lang).strip()
        if lang == 'th':
            # รุ่นไทยบางรุ่นเว้นวรรคทุกคำ: ตัดช่องว่างระหว่างอักษรไทยออก
            import re
            text = re.sub(r'(?<=[\u0e00-\u0e7f]) (?=[\u0e00-\u0e7f])', '', text)
        return text


def decode_wav(data):
    """WAV จากหน้าเว็บ -> float32 16 kHz mono (คืน (samples, วินาที))"""
    import wave
    import numpy as np
    with wave.open(io.BytesIO(data), 'rb') as w:
        if w.getsampwidth() != 2:
            raise ValueError('only 16-bit PCM WAV is supported')
        sr, channels = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float32) / 32768.0
    samples = pcm.reshape(-1, channels).mean(axis=1) if channels > 1 else pcm
    if sr != 16000 and len(samples):
        n_out = int(round(len(samples) * 16000 / sr))
        samples = np.interp(np.linspace(0, len(samples) - 1, n_out), np.arange(len(samples)), samples)
    return np.ascontiguousarray(samples, dtype=np.float32), len(samples) / 16000.0


def create_app(backend, token='', stt=None):
    app = Flask(__name__)
    stats = {'requests': 0, 'last_ms': None, 'stt_requests': 0, 'stt_last_ms': None}

    def authorized():
        if not token:
            return True
        supplied = request.headers.get('X-Voice-Token', '')
        return bool(supplied) and hmac.compare_digest(supplied, token)

    @app.get('/health')
    def health():
        return jsonify({'ok': backend.model is not None, 'model': backend.model_id,
                        'device': backend.device, 'steps': backend.steps,
                        'bake_steps': getattr(backend, 'bake_steps', backend.steps),
                        'seed': getattr(backend, 'seed', None),
                        'stt': bool(stt and stt.model is not None),
                        'stt_model': stt.model_id if stt else None, **stats})

    @app.post('/synthesize')
    def synthesize():
        if not authorized():
            return jsonify({'error': 'unauthorized'}), 403
        body = request.get_json(silent=True) or {}
        text = (body.get('text') or '').strip()
        purpose = 'bake' if body.get('purpose') == 'bake' else 'live'
        seed = body.get('seed')                # ใช้ตอนเลือก seed เท่านั้น (tools/pick_seed.py)
        if seed is not None and not isinstance(seed, int):
            return jsonify({'error': 'seed must be an integer'}), 400
        if not text:
            return jsonify({'error': 'text is required'}), 400
        if len(text) > MAX_TEXT_CHARS:
            return jsonify({'error': f'text longer than {MAX_TEXT_CHARS} characters'}), 413
        started = time.time()
        try:
            mp3 = encode_mp3(backend.synthesize(text, purpose, seed=seed) if seed is not None
                             else backend.synthesize(text, purpose))
        except Exception as e:
            return jsonify({'error': f'synthesis failed: {type(e).__name__}: {e}'}), 500
        stats['requests'] += 1
        stats['last_ms'] = int((time.time() - started) * 1000)
        return Response(mp3, mimetype='audio/mpeg', headers={'X-Synthesis-Ms': str(stats['last_ms'])})

    @app.post('/transcribe')
    def transcribe():
        """ถอดเสียง: body = WAV (audio/wav), ?lang=th|en|zh -> {text, ms, seconds}"""
        if not authorized():
            return jsonify({'error': 'unauthorized'}), 403
        if not stt or stt.model is None:
            return jsonify({'error': 'speech-to-text is not enabled on this server'}), 503
        data = request.get_data(cache=False)
        if not data:
            return jsonify({'error': 'audio is required'}), 400
        if len(data) > MAX_STT_BYTES:
            return jsonify({'error': 'audio too large'}), 413
        try:
            samples, seconds = decode_wav(data)
        except Exception as e:
            return jsonify({'error': f'bad audio: {type(e).__name__}'}), 400
        if seconds > MAX_STT_SECONDS:
            return jsonify({'error': f'audio longer than {MAX_STT_SECONDS} seconds'}), 413
        started = time.time()
        try:
            text = stt.transcribe(samples, request.args.get('lang', 'th'))
        except Exception as e:
            return jsonify({'error': f'transcription failed: {type(e).__name__}: {e}'}), 500
        stats['stt_requests'] += 1
        stats['stt_last_ms'] = int((time.time() - started) * 1000)
        return jsonify({'text': text, 'ms': stats['stt_last_ms'], 'seconds': round(seconds, 2)})

    return app


def _seed_from_env():
    raw = os.environ.get('OMNIVOICE_SEED', str(DEFAULT_SEED)).strip().lower()
    return None if raw in ('', 'none', 'random') else int(raw)


def _load_dotenv(path=os.path.join(ROOT, '.env')):
    """อ่าน .env ของโปรเจกต์ (ไม่ทับค่าที่ตั้งไว้แล้ว) ให้ VOICE_SERVER_TOKEN ฯลฯ ตรงกับแอปเมื่อรันจาก run.bat"""
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description='เซิร์ฟเวอร์เสียงน้องเพชร (OmniVoice)')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8010)
    args = parser.parse_args()

    backend = OmniVoiceBackend(
        model_id=os.environ.get('OMNIVOICE_MODEL', 'k2-fsa/OmniVoice'),
        device=os.environ.get('OMNIVOICE_DEVICE', 'cuda:0'),
        steps=int(os.environ.get('OMNIVOICE_STEPS_LIVE', os.environ.get('OMNIVOICE_STEPS', '32'))),
        bake_steps=int(os.environ.get('OMNIVOICE_STEPS_BAKE', '32')),
        dtype=os.environ.get('OMNIVOICE_DTYPE', 'float32'),
        speed=float(os.environ.get('OMNIVOICE_SPEED', '1.0')),
        seed=_seed_from_env(),
    )
    backend.load()
    stt = None
    if os.environ.get('WHISPER_ENABLED', '1').strip() != '0':
        stt = WhisperBackend(os.environ.get('WHISPER_MODEL', 'biodatlab/distill-whisper-th-small'),
                             # ค่าเริ่มต้น CPU: การ์ด 4 GB ใส่ OmniVoice + Whisper พร้อมกันแล้ว VRAM ล้น
                             # (สร้างเสียงช้าจนหมดเวลา) การ์ด 8 GB ขึ้นไปตั้ง WHISPER_DEVICE=cuda:0 ได้
                             os.environ.get('WHISPER_DEVICE', 'cpu'))
        try:
            stt.load()
        except Exception as e:                     # ถอดเสียงพัง ไม่ให้ลากเซิร์ฟเวอร์เสียงพังตาม
            print(f"⚠️ โหลดตัวถอดเสียงไม่สำเร็จ ({type(e).__name__}: {e}) ระบบจะใช้แค่สร้างเสียง")
            stt = None
    token = os.environ.get('VOICE_SERVER_TOKEN', '')
    if not token:
        print('⚠️ ไม่ได้ตั้ง VOICE_SERVER_TOKEN: เครื่องใดในวงแลนก็เรียกใช้ได้')
    create_app(backend, token, stt).run(host=args.host, port=args.port, threaded=True)


if __name__ == '__main__':
    main()
