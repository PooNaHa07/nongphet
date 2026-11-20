# -*- coding: utf-8 -*-
"""
tools/voice_style_ab.py — ฟังเทียบการปรับน้ำเสียงน้องเพชร (OmniVoice) เพื่อเลือกค่าที่ "เหมือนต้นแบบ + น่ารัก"

ทุกแบบใช้เสียงต้นแบบเดิม seed เดิม และประโยคเดิม ต่างกันแค่ค่าที่ปรับ:
    guidance  ยิ่งสูงยิ่งยึดเสียงต้นแบบ (ค่าเริ่มต้นของโมเดล 2.0)
    instruct  คำกำกับสไตล์ของ OmniVoice เช่น "female, young adult, high pitch"
    speed     ความเร็วพูด

    .venv-voice\\Scripts\\python.exe tools\\voice_style_ab.py

ผลลัพธ์: voice_samples/style/<ชื่อแบบ>.wav (ปิดโปรแกรมที่ใช้ GPU อื่นก่อน เช่น Steam)
"""
import os
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
OUT = os.path.join(ROOT, 'voice_samples', 'style')

TEXT = 'สวัสดีค่ะ น้องเพชรยินดีต้อนรับนะคะ ถ้ามาเพชรบุรี อย่าลืมชิมขนมหม้อแกงด้วยนะคะ อร่อยมากเลยค่ะ'

VARIANTS = [
    ('A_now',              {}),
    ('B_guidance3',        {'guidance_scale': 3.0}),
    ('C_young_high',       {'instruct': 'female, young adult, high pitch'}),
    ('D_teen_high',        {'instruct': 'female, teenager, high pitch'}),
    ('E_young_high_g3',    {'instruct': 'female, young adult, high pitch', 'guidance_scale': 3.0}),
    ('F_young_high_fast',  {'instruct': 'female, young adult, high pitch', 'speed': 1.08}),
]


def main():
    import torch
    import soundfile as sf
    import voice_server as vs

    backend = vs.OmniVoiceBackend('k2-fsa/OmniVoice', os.environ.get('OMNIVOICE_DEVICE', 'cuda:0'),
                                  steps=32, speed=1.0, seed=vs.DEFAULT_SEED)
    backend.load()
    os.makedirs(OUT, exist_ok=True)
    for name, opts in VARIANTS:
        opts = dict(opts)
        speed = opts.pop('speed', backend.speed)
        t = time.time()
        with backend.lock:
            torch.manual_seed(backend.seed)
            audio = backend.model.generate(text=TEXT, voice_clone_prompt=backend.prompt,
                                           num_step=32, speed=speed, **opts)[0]
        sf.write(os.path.join(OUT, f'{name}.wav'), audio, vs.SAMPLE_RATE)
        print(f'{name}: {opts or "-"} speed={speed} เสียง {len(audio) / vs.SAMPLE_RATE:.1f}s สร้าง {time.time() - t:.1f}s')
    print(f'🎧 ฟังเทียบได้ที่ {OUT}')


if __name__ == '__main__':
    main()
