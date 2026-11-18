# 🔑 การตั้งค่า SSH Key สำหรับ Deploy ไปยัง Raspberry Pi

> ทำเพียงครั้งเดียว หลังจากนั้น `deploy.bat` และ `deploy.ps1` จะทำงานได้โดยไม่ต้องใส่รหัสผ่านอีก

---

## ขั้นตอนที่ 1: สร้าง SSH Key บนเครื่อง Windows

เปิด **PowerShell** หรือ **Git Bash** แล้วรัน:

```bash
ssh-keygen -t ed25519 -C "nongphet-deploy"
```

- กด Enter เพื่อใช้ตำแหน่งที่ไฟล์เริ่มต้น (`~/.ssh/id_ed25519`)
- ตั้ง passphrase หรือกด Enter เพื่อข้าม (แนะนำให้ข้ามเพื่อให้ deploy อัตโนมัติได้)

---

## ขั้นตอนที่ 2: คัดลอก Public Key ไปยัง Raspberry Pi

```bash
ssh-copy-id pi@raspberrypi.local
```

- ระบบจะถามรหัสผ่านของ Pi **เพียงครั้งสุดท้าย** ให้ใส่รหัสผ่านที่นี่
- ถ้าใช้ Git Bash บน Windows และ `ssh-copy-id` ไม่มี ให้ใช้คำสั่งนี้แทน:

```bash
cat ~/.ssh/id_ed25519.pub | ssh pi@raspberrypi.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

---

## ขั้นตอนที่ 3: ทดสอบการเชื่อมต่อ

```bash
ssh pi@raspberrypi.local "echo OK"
```

ถ้าเห็น `OK` โดยไม่ถามรหัสผ่าน แปลว่าตั้งค่าสำเร็จ ✅

---

## ขั้นตอนที่ 4: Deploy โดยไม่ต้องใส่รหัสผ่าน

ตอนนี้สามารถรันได้เลย:

```bat
deploy.bat
```

หรือ:

```bat
deploy_rsync.bat
```

ระบบจะ sync ไฟล์และ restart service อัตโนมัติ **โดยไม่ถามรหัสผ่าน**

---

## หมายเหตุ

- SSH key จะเก็บอยู่ที่ `~/.ssh/id_ed25519` (private) และ `~/.ssh/id_ed25519.pub` (public)
- **ห้ามแชร์ private key** (`id_ed25519`) ให้ใครเด็ดขาด
- ถ้า Pi เปลี่ยน IP หรือ hostname ให้ทำซ้ำขั้นตอนที่ 2
- ถ้าต้องการ deploy จากเครื่องอื่น ให้ทำขั้นตอน 1–3 ใหม่บนเครื่องนั้น
