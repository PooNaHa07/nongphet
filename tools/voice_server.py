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

    def __init__(self, model_id, device, steps, speed, dtype='float32', bake_steps=None):
        self.model_id = model_id
        self.device = device
        self.steps = steps                     # ตอบสด
        self.bake_steps = bake_steps or steps  # อัดเก็บล่วงหน้า
        self.speed = speed
        self.dtype = dtype
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

    def synthesize(self, text, purpose='live'):
        steps = self.bake_steps if purpose == 'bake' else self.steps
        with self.lock:
            audio = self.model.generate(text=text, voice_clone_prompt=self.prompt,
                                        num_step=steps, speed=self.speed)
        return audio[0]


def create_app(backend, token=''):
    app = Flask(__name__)
    stats = {'requests': 0, 'last_ms': None}

    def authorized():
        if not token:
            return True
        supplied = request.headers.get('X-Voice-Token', '')
        return bool(supplied) and hmac.compare_digest(supplied, token)

    @app.get('/health')
    def health():
        return jsonify({'ok': backend.model is not None, 'model': backend.model_id,
                        'device': backend.device, 'steps': backend.steps,
                        'bake_steps': getattr(backend, 'bake_steps', backend.steps), **stats})

    @app.post('/synthesize')
    def synthesize():
        if not authorized():
            return jsonify({'error': 'unauthorized'}), 403
        body = request.get_json(silent=True) or {}
        text = (body.get('text') or '').strip()
        purpose = 'bake' if body.get('purpose') == 'bake' else 'live'
        if not text:
            return jsonify({'error': 'text is required'}), 400
        if len(text) > MAX_TEXT_CHARS:
            return jsonify({'error': f'text longer than {MAX_TEXT_CHARS} characters'}), 413
        started = time.time()
        try:
            mp3 = encode_mp3(backend.synthesize(text, purpose))
        except Exception as e:
            return jsonify({'error': f'synthesis failed: {type(e).__name__}: {e}'}), 500
        stats['requests'] += 1
        stats['last_ms'] = int((time.time() - started) * 1000)
        return Response(mp3, mimetype='audio/mpeg', headers={'X-Synthesis-Ms': str(stats['last_ms'])})

    return app


def main():
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
    )
    backend.load()
    token = os.environ.get('VOICE_SERVER_TOKEN', '')
    if not token:
        print('⚠️ ไม่ได้ตั้ง VOICE_SERVER_TOKEN: เครื่องใดในวงแลนก็เรียกใช้ได้')
    create_app(backend, token).run(host=args.host, port=args.port, threaded=True)


if __name__ == '__main__':
    main()
