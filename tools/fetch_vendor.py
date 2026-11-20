# -*- coding: utf-8 -*-
"""
tools/fetch_vendor.py — ดาวน์โหลดไลบรารีหน้าเว็บ (CDN) มาเก็บใน static/vendor/
ให้หน้าจอตู้ (kiosk / emotion / dashboard ฯลฯ) เปิดได้แม้ไม่มีอินเทอร์เน็ตในงานแข่ง

รันครั้งเดียวบนเครื่องที่มีเน็ต แล้ว commit โฟลเดอร์ static/vendor/ ไปกับโปรเจกต์:
    .venv\\Scripts\\python.exe tools\\fetch_vendor.py

เวอร์ชันถูกล็อกไว้ด้านล่าง เปลี่ยนเวอร์ชันแล้วรันใหม่ได้
"""
import os
import re
import sys
import httpx

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, 'static', 'vendor')

TAILWIND_VERSION = '3.4.17'
FONTAWESOME_VERSION = '6.5.1'
MP_HANDS_VERSION = '0.4.1675469240'
MP_CAMERA_VERSION = '0.3.1675466862'
CHARTJS_VERSION = '4.4.1'
QRCODE_VERSION = '1.4.4'   # qrcode-generator (MIT): สร้าง QR Code ในเบราว์เซอร์ ไม่ต้องพึ่ง api.qrserver.com
GOOGLE_FONTS_CSS = ('https://fonts.googleapis.com/css2?'
                    'family=JetBrains+Mono:wght@400;600;700;800'
                    '&family=Prompt:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,400'
                    '&display=swap')
# Google Fonts ส่ง woff2 เฉพาะเบราว์เซอร์รุ่นใหม่ จึงต้องระบุ User-Agent แบบ Chrome
CHROME_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

client = httpx.Client(follow_redirects=True, timeout=60, headers={'User-Agent': CHROME_UA})
total = {'files': 0, 'bytes': 0}


def save(url, rel_path):
    res = client.get(url)
    res.raise_for_status()
    path = os.path.join(VENDOR, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(res.content)
    total['files'] += 1
    total['bytes'] += len(res.content)
    return res


def fetch_tailwind():
    save(f'https://cdn.tailwindcss.com/{TAILWIND_VERSION}', 'tailwind/tailwind.js')


def fetch_chartjs():
    save(f'https://cdn.jsdelivr.net/npm/chart.js@{CHARTJS_VERSION}/dist/chart.umd.js', 'chartjs/chart.umd.js')


def fetch_qrcode():
    save(f'https://cdn.jsdelivr.net/npm/qrcode-generator@{QRCODE_VERSION}/qrcode.js', 'qrcode/qrcode.js')


def fetch_fontawesome():
    base = f'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/{FONTAWESOME_VERSION}'
    css = save(f'{base}/css/all.min.css', 'fontawesome/css/all.min.css').text
    for name in sorted(set(re.findall(r'\.\./webfonts/([\w.-]+)', css))):
        save(f'{base}/webfonts/{name}', f'fontawesome/webfonts/{name}')


def jsdelivr_files(package, version):
    meta = client.get(f'https://data.jsdelivr.com/v1/packages/npm/{package}@{version}?structure=flat')
    meta.raise_for_status()
    return [f['name'].lstrip('/') for f in meta.json()['files']]


def fetch_mediapipe():
    for package, version, folder in (('@mediapipe/hands', MP_HANDS_VERSION, 'mediapipe/hands'),
                                     ('@mediapipe/camera_utils', MP_CAMERA_VERSION, 'mediapipe/camera_utils')):
        for name in jsdelivr_files(package, version):
            if name.endswith(('.md', '.d.ts')):
                continue
            save(f'https://cdn.jsdelivr.net/npm/{package}@{version}/{name}', f'{folder}/{name}')


def fetch_google_fonts():
    css = client.get(GOOGLE_FONTS_CSS)
    css.raise_for_status()
    text = css.text
    for i, url in enumerate(dict.fromkeys(re.findall(r'url\((https://fonts\.gstatic\.com/[^)]+)\)', text))):
        name = f'{i:03d}_' + url.rsplit('/', 1)[-1]
        save(url, f'fonts/files/{name}')
        text = text.replace(url, f'files/{name}')
    path = os.path.join(VENDOR, 'fonts', 'fonts.css')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('/* Prompt + JetBrains Mono จาก Google Fonts (SIL Open Font License) — สร้างโดย tools/fetch_vendor.py */\n')
        f.write(text)


if __name__ == '__main__':
    for step in (fetch_tailwind, fetch_chartjs, fetch_qrcode, fetch_fontawesome, fetch_mediapipe, fetch_google_fonts):
        print(f'⬇️  {step.__name__} ...', flush=True)
        step()
    print(f"✅ ดาวน์โหลดครบ {total['files']} ไฟล์ รวม {total['bytes'] / 2**20:.1f} MB ใน {VENDOR}")
