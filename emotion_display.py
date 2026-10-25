#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
โครงการ: น้องเพชร AI Smart Guide (Nong Phet AI Assistant)
โมดูล: ไดรเวอร์ขับจอแสดงอารมณ์ส่วนหัวสำหรับ Raspberry Pi 5 (emotion_display.py)
ฮาร์ดแวร์เป้าหมาย: จอ LCD 2.4 - 3.5 นิ้ว (SPI Bus: ST7789 / ILI9341 หรือ Framebuffer /dev/fb1)
==============================================================================
หน้าที่:
1. ดักฟัง Realtime Event จาก Flask Server (http://127.0.0.1:5000/api/iot/events)
2. วาดแอนิเมชันใบหน้าน้องเพชรแบบเวกเตอร์ (กะพริบตา, ยิ้ม, ตั้งใจฟัง, กำลังคิด, ขยับปากพูด)
3. ส่งเฟรมภาพตรงเข้าจอ SPI LCD หรือ Framebuffer ด้วยความเร็ว 30-60 FPS
4. รองรับโหมดทดสอบ (--test) จำลองหน้าตาบนหน้าต่าง Desktop ได้ทันที
==============================================================================
"""

import sys
import time
import math
import json
import argparse
import threading
import urllib.request
import urllib.error
from PIL import Image, ImageDraw

# สีธีมประจำตัวน้องเพชร
COLOR_BG = (2, 6, 23)           # ดำอมน้ำเงินลึก (Visor Screen)
COLOR_CYAN = (56, 189, 248)      # ฟ้าสว่างนีออน
COLOR_BLUE = (2, 132, 199)       # น้ำเงินไซเบอร์
COLOR_WHITE = (255, 255, 255)    # ขาวไฮไลต์
COLOR_EMERALD = (16, 185, 129)   # เขียว (โหมดฟังเสียง)
COLOR_AMBER = (245, 158, 11)     # ส้มทอง (โหมดกำลังคิด)
COLOR_PINK = (244, 63, 94)       # ชมพู (แก้มและโหมดมีความสุข)

class EmotionDisplayRenderer:
    def __init__(self, width=320, height=240):
        self.width = width
        self.height = height
        self.current_state = 'idle'
        self.blink_progress = 0.0  # 0.0 = ลืมตาปกติ, 1.0 = ปิดตา
        self.is_blinking = False
        self.speaking_phase = 0.0
        self.thinking_angle = 0.0
        self.last_blink_time = time.time()
        self.next_blink_delay = 3.0
        self.gaze_x = 0.0
        self.gaze_y = 0.0
        self.target_gaze_x = 0.0
        self.target_gaze_y = 0.0

    def set_state(self, new_state):
        self.current_state = new_state

    def set_gaze(self, x, y):
        """กำหนดพิกัดเป้าหมายการมอง (-1.0 ถึง 1.0)"""
        self.target_gaze_x = max(-1.0, min(1.0, float(x)))
        self.target_gaze_y = max(-1.0, min(1.0, float(y)))

    def update_animation(self, dt):
        """คำนวณเฟรมถัดไปของแอนิเมชัน"""
        now = time.time()
        
        # ปรับพิกัดการมองตามอย่างนุ่มนวล (Smooth Lerp)
        self.gaze_x += (self.target_gaze_x - self.gaze_x) * 0.18
        self.gaze_y += (self.target_gaze_y - self.gaze_y) * 0.18
        
        # จัดการการกะพริบตาในโหมด Idle
        if self.current_state == 'idle':
            if not self.is_blinking and (now - self.last_blink_time > self.next_blink_delay):
                self.is_blinking = True
                self.blink_progress = 0.0

            if self.is_blinking:
                self.blink_progress += dt * 8.0  # ความเร็วกะพริบ
                if self.blink_progress >= 2.0:
                    self.is_blinking = False
                    self.blink_progress = 0.0
                    self.last_blink_time = now
                    self.next_blink_delay = 2.5 + (hash(str(now)) % 30) / 10.0

        # จัดการแอนิเมชันการพูด
        if self.current_state == 'speaking':
            self.speaking_phase += dt * 10.0
        else:
            self.speaking_phase = 0.0

        # จัดการแอนิเมชันตอนคิด
        if self.current_state == 'thinking':
            self.thinking_angle += dt * 4.0

    def render_frame(self):
        """วาดภาพใบหน้า 1 เฟรมลงบน Pillow Image"""
        img = Image.new("RGB", (self.width, self.height), COLOR_BG)
        draw = ImageDraw.Draw(img)

        cx, cy = self.width // 2, self.height // 2
        eye_spacing = int(self.width * 0.22)
        base_eye_w = int(self.width * 0.18)
        base_eye_h = int(self.height * 0.32)

        # คำนวณระยะการเลื่อนสายตามองตามเมาส์/กล้อง
        gaze_offset_x = int(self.gaze_x * (self.width * 0.06))
        gaze_offset_y = int(self.gaze_y * (self.height * 0.05))

        left_eye_center = (cx - eye_spacing + gaze_offset_x, cy - int(self.height * 0.08) + gaze_offset_y)
        right_eye_center = (cx + eye_spacing + gaze_offset_x, cy - int(self.height * 0.08) + gaze_offset_y)

        eye_color = COLOR_CYAN
        if self.current_state == 'listening':
            eye_color = COLOR_EMERALD
        elif self.current_state == 'thinking':
            eye_color = COLOR_AMBER
        elif self.current_state == 'happy':
            eye_color = COLOR_PINK

        # วาดแก้มอมชมพู
        cheek_r = int(self.width * 0.05)
        draw.ellipse([left_eye_center[0] - eye_spacing//2 - cheek_r, left_eye_center[1] + base_eye_h//2,
                      left_eye_center[0] - eye_spacing//2 + cheek_r, left_eye_center[1] + base_eye_h//2 + cheek_r],
                     fill=(80, 20, 35))
        draw.ellipse([right_eye_center[0] + eye_spacing//2 - cheek_r, right_eye_center[1] + base_eye_h//2,
                      right_eye_center[0] + eye_spacing//2 + cheek_r, right_eye_center[1] + base_eye_h//2 + cheek_r],
                     fill=(80, 20, 35))

        # -------------------------------------------------------------
        # วาดคิ้วไซเบอร์เรืองแสง (Cybernetic Eyebrows)
        # -------------------------------------------------------------
        brow_w = int(base_eye_w * 0.95)
        brow_y = left_eye_center[1] - base_eye_h // 2 - 10
        brow_color = eye_color

        if self.current_state == 'thinking':
            # คิ้วซ้ายยกสูง คิ้วขวาขมวดต่ำ (Curious Thinking)
            draw.line([left_eye_center[0] - brow_w//2, brow_y - 8, left_eye_center[0] + brow_w//2, brow_y - 2], fill=COLOR_AMBER, width=4)
            draw.line([right_eye_center[0] - brow_w//2, brow_y + 2, right_eye_center[0] + brow_w//2, brow_y + 6], fill=COLOR_AMBER, width=4)
        elif self.current_state == 'listening':
            # คิ้วเอียงตั้งใจฟัง (Attentive Listening)
            draw.line([left_eye_center[0] - brow_w//2, brow_y + 3, left_eye_center[0] + brow_w//2, brow_y - 2], fill=COLOR_EMERALD, width=4)
            draw.line([right_eye_center[0] - brow_w//2, brow_y - 2, right_eye_center[0] + brow_w//2, brow_y + 3], fill=COLOR_EMERALD, width=4)
        elif self.current_state in ['happy', 'speaking']:
            # คิ้วโค้งยกสูงอารมณ์ดี
            draw.line([left_eye_center[0] - brow_w//2, brow_y - 6, left_eye_center[0] + brow_w//2, brow_y - 6], fill=brow_color, width=4)
            draw.line([right_eye_center[0] - brow_w//2, brow_y - 6, right_eye_center[0] + brow_w//2, brow_y - 6], fill=brow_color, width=4)
        else:
            # คิ้วปกติ
            draw.line([left_eye_center[0] - brow_w//2, brow_y, left_eye_center[0] + brow_w//2, brow_y], fill=COLOR_CYAN, width=3)
            draw.line([right_eye_center[0] - brow_w//2, brow_y, right_eye_center[0] + brow_w//2, brow_y], fill=COLOR_CYAN, width=3)

        # -------------------------------------------------------------
        # วาดดวงตา (ซ้ายและขวา)
        # -------------------------------------------------------------
        if self.current_state == 'speaking':
            # ตารูปโค้งยิ้มมีความสุขตอนพูด (^ ^)
            for center in [left_eye_center, right_eye_center]:
                arc_w = base_eye_w
                arc_h = int(base_eye_h * 0.7)
                draw.arc([center[0] - arc_w//2, center[1] - arc_h//2,
                          center[0] + arc_w//2, center[1] + arc_h//2],
                         start=190, end=350, fill=eye_color, width=6)
        elif self.current_state == 'thinking':
            # ตากำลังคิด เหลือบไปมา
            offset_x = int(math.sin(self.thinking_angle) * 8)
            offset_y = int(math.cos(self.thinking_angle) * 4) - 6
            for center in [left_eye_center, right_eye_center]:
                bx = center[0] + offset_x
                by = center[1] + offset_y
                draw.ellipse([bx - base_eye_w//2, by - base_eye_h//2,
                              bx + base_eye_w//2, by + base_eye_h//2], fill=eye_color)
                draw.ellipse([bx - base_eye_w//4, by - base_eye_h//4,
                              bx + base_eye_w//4, by + base_eye_h//4], fill=COLOR_WHITE)
        elif self.current_state == 'listening':
            # ตาโต ตื่นตัว ตั้งใจฟัง
            for center in [left_eye_center, right_eye_center]:
                draw.ellipse([center[0] - int(base_eye_w*0.65), center[1] - int(base_eye_h*0.65),
                              center[0] + int(base_eye_w*0.65), center[1] + int(base_eye_h*0.65)],
                             outline=eye_color, width=4)
                draw.ellipse([center[0] - base_eye_w//2, center[1] - base_eye_h//2,
                              center[0] + base_eye_w//2, center[1] + base_eye_h//2], fill=eye_color)
                draw.ellipse([center[0] - base_eye_w//5, center[1] - base_eye_h//5,
                              center[0] + base_eye_w//5, center[1] + base_eye_h//5], fill=COLOR_WHITE)
        else:
            # โหมด Idle ปกติ พร้อมคำนวณการกะพริบตา
            current_h = base_eye_h
            if self.is_blinking:
                blink_factor = math.sin(self.blink_progress * math.pi)
                current_h = max(4, int(base_eye_h * (1.0 - blink_factor * 0.92)))

            for center in [left_eye_center, right_eye_center]:
                draw.rounded_rectangle([center[0] - base_eye_w//2, center[1] - current_h//2,
                                        center[0] + base_eye_w//2, center[1] + current_h//2],
                                       radius=int(base_eye_w*0.45), fill=eye_color)
                # แสงสะท้อนในตา
                if current_h > 12:
                    draw.ellipse([center[0] + base_eye_w//6, center[1] - current_h//4,
                                  center[0] + base_eye_w//3, center[1] - current_h//8], fill=COLOR_WHITE)

        # -------------------------------------------------------------
        # วาดปาก (Mouth)
        # -------------------------------------------------------------
        mouth_y = cy + int(self.height * 0.22)
        if self.current_state == 'speaking':
            # ปากขยับเปิดปิดตามจังหวะเสียงพูด
            m_open = int(abs(math.sin(self.speaking_phase)) * (self.height * 0.12)) + 6
            m_w = int(self.width * 0.12)
            draw.ellipse([cx - m_w//2, mouth_y - m_open//2,
                          cx + m_w//2, mouth_y + m_open//2], fill=COLOR_CYAN, outline=COLOR_WHITE, width=2)
        elif self.current_state == 'listening':
            # ปากกลมเล็กๆ รับเสียง
            draw.ellipse([cx - 8, mouth_y - 8, cx + 8, mouth_y + 8], outline=COLOR_EMERALD, width=3)
        elif self.current_state == 'thinking':
            # ปากเป็นเส้นตรงครุ่นคิด
            draw.line([cx - 15, mouth_y, cx + 15, mouth_y], fill=COLOR_AMBER, width=4)
        else:
            # รอยยิ้มน่ารักปกติ
            m_w = int(self.width * 0.16)
            m_h = int(self.height * 0.08)
            draw.arc([cx - m_w//2, mouth_y - m_h//2, cx + m_w//2, mouth_y + m_h//2],
                     start=10, end=170, fill=COLOR_CYAN, width=4)

        return img


def sse_event_listener(renderer, flask_url="http://127.0.0.1:5000/api/iot/events"):
    """เธรดสำหรับดักฟัง Event จาก Flask ผ่าน SSE"""
    while True:
        try:
            req = urllib.request.Request(flask_url, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=30) as response:
                print(f"📡 [Emotion Driver] เชื่อมต่อกับ Flask Server เรียบร้อยแล้ว: {flask_url}")
                for line in response:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("data:"):
                        payload = line_str[5:].strip()
                        try:
                            data = json.loads(payload)
                            if data.get('event') == 'emotion_changed':
                                new_st = data.get('state', 'idle')
                                renderer.set_state(new_st)
                                print(f"😊 [Emotion Changed] ==> {new_st}")
                            elif data.get('event') == 'gaze_changed':
                                renderer.set_gaze(data.get('x', 0.0), data.get('y', 0.0))
                            elif data.get('event') == 'led_state_changed':
                                st = data.get('state')
                                if st in ['speaking', 'thinking', 'listening']:
                                    renderer.set_state(st)
                                else:
                                    renderer.set_state('idle')
                        except Exception:
                            pass
        except Exception as e:
            time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description="น้องเพชร AI - ไดรเวอร์จอแสดงอารมณ์สำหรับ Raspberry Pi 5")
    parser.add_argument("--test", action="store_true", help="รันในโหมดทดสอบเปิดหน้าต่าง Preview บน Desktop")
    parser.add_argument("--spi", action="store_true", help="รันผ่านจอฮาร์ดแวร์ SPI (ST7789 / ILI9341)")
    parser.add_argument("--fb", default="/dev/fb1", help="เส้นทาง Framebuffer ของจอ SPI (ค่าเริ่มต้น /dev/fb1)")
    parser.add_argument("--width", type=int, default=320, help="ความกว้างของจอ (พิกเซล)")
    parser.add_argument("--height", type=int, default=240, help="ความสูงของจอ (พิกเซล)")
    args = parser.parse_args()

    renderer = EmotionDisplayRenderer(width=args.width, height=args.height)

    # เริ่มเธรดดักฟัง Event จาก Flask
    listener_thread = threading.Thread(target=sse_event_listener, args=(renderer,), daemon=True)
    listener_thread.start()

    print("=" * 60)
    print("🤖 น้องเพชร AI Smart Guide - Emotion Display Engine")
    print(f"📐 ความละเอียด: {args.width}x{args.height} px")
    print("=" * 60)

    # 1. โหมดทดสอบเปิดดูบน Desktop (ใช้ Pygame หรือ Pillow show)
    if args.test:
        try:
            import pygame
            pygame.init()
            screen = pygame.display.set_mode((args.width, args.height))
            pygame.display.set_caption("น้องเพชร AI - Emotion Display Preview")
            clock = pygame.time.Clock()

            print("💡 คำแนะนำ: กด 1:Idle | 2:Listening | 3:Thinking | 4:Speaking | 5:Happy")

            running = True
            last_time = time.time()
            while running:
                dt = clock.tick(30) / 1000.0
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_1: renderer.set_state('idle')
                        elif event.key == pygame.K_2: renderer.set_state('listening')
                        elif event.key == pygame.K_3: renderer.set_state('thinking')
                        elif event.key == pygame.K_4: renderer.set_state('speaking')
                        elif event.key == pygame.K_5: renderer.set_state('happy')

                renderer.update_animation(dt)
                pil_frame = renderer.render_frame()

                # แปลง Pillow Image -> Pygame Surface
                mode = pil_frame.mode
                size = pil_frame.size
                data = pil_frame.tobytes()
                py_image = pygame.image.fromstring(data, size, mode)

                screen.blit(py_image, (0, 0))
                pygame.display.flip()

            pygame.quit()
            return
        except ImportError:
            print("ℹ️ Pygame ไม่ได้ติดตั้ง สามารถทดสอบผ่านหน้าเว็บ http://127.0.0.1:5000/emotion ได้เช่นกัน")

    # 2. โหมดรันจริงบน Raspberry Pi 5 (Framebuffer /dev/fb1 หรือ SPI Driver)
    print(f"🚀 กำลังส่งสัญญาณภาพออก Framebuffer: {args.fb} ...")
    last_time = time.time()
    try:
        while True:
            now = time.time()
            dt = now - last_time
            last_time = now

            renderer.update_animation(dt)
            pil_frame = renderer.render_frame()

            # เขียนข้อมูล Raw RGB565 / RGB888 ลง Framebuffer ของจอ SPI
            try:
                raw_bytes = pil_frame.convert("RGB").tobytes()
                with open(args.fb, "wb") as f:
                    f.write(raw_bytes)
            except FileNotFoundError:
                # กรณีรันบนเครื่องทั่วไปที่ไม่มี /dev/fb1
                time.sleep(0.05)
            except Exception:
                pass

            time.sleep(0.033)  # ควบคุมอัตราเฟรมที่ ~30 FPS
    except KeyboardInterrupt:
        print("\nหยุดการทำงานเรียบร้อย")

if __name__ == '__main__':
    main()
