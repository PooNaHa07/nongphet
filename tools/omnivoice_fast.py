# -*- coding: utf-8 -*-
"""
tools/omnivoice_fast.py — เร่งความเร็ว OmniVoice ตอนโคลนเสียง (ใช้กับ tools/voice_server.py)

ต้นฉบับ (omnivoice _generate_iterative) รวมแถว cond และ uncond (classifier-free guidance)
ไว้ใน batch เดียวยาวเท่า c_len = เสียงต้นแบบ + ข้อความ + เสียงเป้าหมาย
แต่แถว uncond ใช้จริงแค่ส่วนเสียงเป้าหมาย (u_len) ที่เหลือเป็น padding ที่ยังต้องคำนวณทุกรอบ

ที่นี่แยกเป็น 2 forward: cond ยาว c_len และ uncond ยาวแค่ u_len
ผลลัพธ์เท่าเดิมทางคณิตศาสตร์ (uncond เห็นเฉพาะตำแหน่ง 0..u_len อยู่แล้วในต้นฉบับ)
ใช้เฉพาะ batch ขนาด 1 (การเรียกจากเซิร์ฟเวอร์เสียง) ขนาดอื่นใช้ฟังก์ชันเดิม
"""
import math

import torch

from omnivoice.models import omnivoice as ov

_original = ov.OmniVoice._generate_iterative


def _fast_generate_iterative(self, task, gen_config):
    if task.batch_size != 1:
        return _original(self, task, gen_config)

    inp = self._prepare_inference_inputs(
        task.texts[0], task.target_lens[0], task.ref_texts[0], task.ref_audio_tokens[0],
        task.langs[0], task.instructs[0], gen_config.denoise,
    )
    t_len = task.target_lens[0]
    cond_ids = inp["input_ids"].to(self.device).clone()          # [1, C, c_len]
    cond_audio = inp["audio_mask"].to(self.device)
    c_len = cond_ids.size(2)
    cond_attn = torch.ones((1, 1, c_len, c_len), dtype=torch.bool, device=self.device)

    use_cfg = gen_config.guidance_scale != 0
    if use_cfg:
        unc_ids = cond_ids[..., -t_len:].clone()                   # [1, C, u_len]
        unc_audio = cond_audio[..., -t_len:]
        unc_attn = torch.ones((1, 1, t_len, t_len), dtype=torch.bool, device=self.device)

    C = self.config.num_audio_codebook
    mask_id = self.config.audio_mask_id
    tokens = torch.full((1, C, t_len), mask_id, dtype=torch.long, device=self.device)

    timesteps = ov._get_time_steps(t_start=0.0, t_end=1.0, num_step=gen_config.num_step,
                                   t_shift=gen_config.t_shift).tolist()
    total_mask = t_len * C
    rem, sched = total_mask, []
    for step in range(gen_config.num_step):
        num = rem if step == gen_config.num_step - 1 else min(
            math.ceil(total_mask * (timesteps[step + 1] - timesteps[step])), rem)
        sched.append(int(num))
        rem -= int(num)

    layer_ids = torch.arange(C, device=self.device).view(1, -1, 1)

    for step in range(gen_config.num_step):
        k = sched[step]
        if k <= 0:
            continue
        c_logits = self(input_ids=cond_ids, audio_mask=cond_audio,
                        attention_mask=cond_attn).logits[:, :, c_len - t_len:c_len, :].to(torch.float32)
        if use_cfg:
            u_logits = self(input_ids=unc_ids, audio_mask=unc_audio,
                            attention_mask=unc_attn).logits.to(torch.float32)
        else:
            u_logits = c_logits

        pred_tokens, scores = self._predict_tokens_with_scoring(c_logits, u_logits, gen_config)
        scores = scores - (layer_ids * gen_config.layer_penalty_factor)
        if gen_config.position_temperature > 0.0:
            scores = ov._gumbel_sample(scores, gen_config.position_temperature)
        scores.masked_fill_(tokens != mask_id, -float("inf"))

        _, topk_idx = torch.topk(scores.flatten(), k)
        flat = tokens.flatten()
        flat[topk_idx] = pred_tokens.flatten()[topk_idx]
        tokens.copy_(flat.view_as(tokens))
        cond_ids[..., c_len - t_len:c_len] = tokens
        if use_cfg:
            unc_ids[...] = tokens

    return [tokens[0]]


def install():
    """เปิดใช้ทางลัด (เรียกครั้งเดียวหลัง import omnivoice)"""
    ov.OmniVoice._generate_iterative = _fast_generate_iterative


def uninstall():
    ov.OmniVoice._generate_iterative = _original
