# Gunicorn Configuration for Nong Phet AI Smart Guide
import os

bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"

# ต้องใช้ worker เดียวเท่านั้น: สถานะทั้งหมดอยู่ในหน่วยความจำของโปรเซส
# (ผู้ฟัง SSE, อารมณ์ใบหน้า, สถานะแขน, หัวข้อสนทนาล่าสุด) ถ้ามีหลาย worker
# อีเวนต์จาก worker หนึ่งจะไปไม่ถึงหน้าจอที่ต่อกับอีก worker ทำให้จอไม่ซิงก์กัน
workers = 1
worker_class = 'gthread'
# การเชื่อมต่อ SSE (/api/iot/events) แต่ละตัวจองเธรดค้างไว้ตลอด
# (kiosk, จอหน้า, แดชบอร์ด, บริดจ์ ESP32 ...) จึงต้องมีเธรดเหลือพอสำหรับคำขอปกติ
threads = int(os.environ.get('GUNICORN_THREADS', 32))
timeout = 120
keepalive = 5

accesslog = None   # ไม่เขียน access log ทุกคำขอ (ลดการเขียน SD card); เปิดได้ด้วย --access-logfile -
errorlog = '-'
loglevel = 'info'
