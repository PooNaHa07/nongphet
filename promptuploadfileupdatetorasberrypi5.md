ช่วยซิงก์ไฟล์ที่อัปเดตจากเครื่องโลคอลขึ้นไปยัง Raspberry Pi ให้หน่อย:

- Remote Host: pi@raspberrypi.local (หรือ pi@192.168.1.162)
- Target Directory บน Pi: ~/nongphet/
- เงื่อนไขการส่งไฟล์:
  1. ซิงก์เฉพาะซอร์สโค้ดและไฟล์ที่จำเป็น (เช่น *.py, templates/, static/, *.json, *.pkl)
  2. ยกเว้น (Exclude) โฟลเดอร์ต่อไปนี้โดยเด็ดขาด: venv/, .venv/, __pycache__/, .git/
  3. สามารถใช้ rsync (ผ่าน Git Bash/WSL) หรือ scp คำสั่งที่เหมาะสมได้เลย
  4. หากมีการแก้ไข Service หรือโค้ดฝั่ง Flask ให้ช่วยรันคำสั่ง restart service หรือแจ้งคำสั่งที่ต้องสั่งรันบนบอร์ดต่อด้วย
password: nongphet999