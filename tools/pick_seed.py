# -*- coding: utf-8 -*-
"""
tools/pick_seed.py — ฟังเทียบเพื่อเลือก seed ของเสียงน้องเพชร (รันบนโน้ตบุ๊ก GPU ใน .venv-voice)

OmniVoice สุ่มทุกครั้งที่สร้างเสียง: ข้อความเดียวกันอาจออกมาดีหรือเพี้ยน
ล็อก seed แล้วข้อความเดิมได้เสียงเดิมเสมอ สคริปต์นี้สร้างประโยคทดสอบด้วยหลาย seed
ให้ฟังแล้วเลือก seed ที่ชัดและน่ารักที่สุด จากนั้นตั้ง OMNIVOICE_SEED=<seed> (หรือแก้ DEFAULT_SEED)

    .venv-voice\\Scripts\\python.exe tools\\pick_seed.py --seeds 7,11,23,42,99
    .venv-voice\\Scripts\\python.exe tools\\pick_seed.py --check 7     (ตรวจว่า seed เดิมได้เสียงเดิม)

ผลลัพธ์: voice_samples/seeds/seed<N>_<ประโยค>.wav
"""
import os
import sys
import time
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
OUT = os.path.join(ROOT, 'voice_samples', 'seeds')

SENTENCES = [
    ('1_greet', 'สวัสดีค่ะ น้องเพชรยินดีต้อนรับสู่วิทยาลัยอาชีวศึกษาเพชรบุรีนะคะ วันนี้อยากรู้เรื่องอะไร ถามน้องเพชรได้เลยค่ะ'),
    ('2_info', 'วิทยาลัยของเราเปิดรับสมัครนักเรียนใหม่ทุกปีนะคะ ช่วงเวลารับสมัครและเอกสารที่ต้องใช้ โปรดตรวจสอบกับวิทยาลัยอีกครั้งนะคะ'),
    ('3_tour', 'ถ้ามาเพชรบุรี แนะนำให้ไปเที่ยวพระนครคีรี หรือที่คนเพชรเรียกว่าเขาวังนะคะ ขึ้นไปแล้วเห็นวิวเมืองสวยมากเลยค่ะ'),
]


def make_backend():
    import voice_server as vs
    b = vs.OmniVoiceBackend(
        model_id=os.environ.get('OMNIVOICE_MODEL', 'k2-fsa/OmniVoice'),
        device=os.environ.get('OMNIVOICE_DEVICE', 'cuda:0'),
        steps=int(os.environ.get('OMNIVOICE_STEPS_BAKE', '32')),
        speed=float(os.environ.get('OMNIVOICE_SPEED', '1.0')),
        dtype=os.environ.get('OMNIVOICE_DTYPE', 'float32'))
    b.load()
    return b, vs.SAMPLE_RATE


def main():
    parser = argparse.ArgumentParser(description='ฟังเทียบ seed เสียงน้องเพชร')
    parser.add_argument('--seeds', default='7,11,23,42,99', help='รายการ seed คั่นด้วยจุลภาค')
    parser.add_argument('--check', type=int, help='สร้าง seed นี้ 2 รอบแล้วเทียบว่าได้เสียงเดิมหรือไม่')
    args = parser.parse_args()

    import numpy as np
    import soundfile as sf
    backend, sr = make_backend()
    os.makedirs(OUT, exist_ok=True)

    if args.check is not None:
        name, text = SENTENCES[0]
        a = backend.synthesize(text, 'bake', seed=args.check)
        b = backend.synthesize(text, 'bake', seed=args.check)
        same = len(a) == len(b) and float(np.abs(a - b).max()) < 1e-3
        print(f"seed {args.check}: {'✅ ได้เสียงเดิมทุกครั้ง' if same else '⚠️ เสียงต่างกัน'} "
              f"(ยาว {len(a)} / {len(b)} samples)")
        return

    for seed in [int(x) for x in args.seeds.split(',') if x.strip()]:
        for name, text in SENTENCES:
            t = time.time()
            audio = backend.synthesize(text, 'bake', seed=seed)
            path = os.path.join(OUT, f'seed{seed}_{name}.wav')
            sf.write(path, audio, sr)
            print(f'seed {seed} {name}: เสียง {len(audio) / sr:.1f}s สร้าง {time.time() - t:.1f}s')
    print(f'🎧 ฟังเทียบได้ที่ {OUT}')


if __name__ == '__main__':
    main()
