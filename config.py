import os

# โหลดค่าตัวแปรจากไฟล์ .env โดยอัตโนมัติหากมีไฟล์อยู่ในโฟลเดอร์เครื่อง
_env_file = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(_env_file):
    try:
        with open(_env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

class Config:
    # อ่านจาก Environment Variable ถ้ามี หรือกำหนดผ่านไฟล์ .env
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'YOUR_GEMINI_API_KEY_HERE')
