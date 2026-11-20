"""
==============================================================================
โครงการ: น้องเพชร AI Smart Guide (Nong Phet AI Assistant)
โมดูล: Python Serial Bridge สำหรับบอร์ดสมองกลฝังตัว ESP32 (esp32_listener.py)
มาตรฐาน: สอดคล้องเกณฑ์การประเมินสิ่งประดิษฐ์ สอศ. ข้อ 4.2 (GPIO Input/Output)
------------------------------------------------------------------------------
หน้าที่:
1. เชื่อมต่อพอร์ต Serial (UART) กับ ESP32 อัตโนมัติ (ตรวจจับชิป CP210x, CH340, USB Serial)
2. ดักฟัง Event จาก Ultrasonic Sensor (เช่น {"event": "user_detected", "distance": 45.2})
3. ส่งสัญญาณ Trigger ไปยัง Flask Web Server (http://127.0.0.1:5000/api/iot/trigger)
4. รองรับการส่งคำสั่งกลับไปควบคุมไฟ LED บน ESP32 (เช่น ให้กะพริบตอน AI กำลังพูด)
5. มีโหมดจำลอง (--simulate) เพื่อการทดสอบและสาธิตโดยไม่ต้องต่อฮาร์ดแวร์จริง
==============================================================================
"""

import sys
import time
import json
import argparse
import queue
import threading
import urllib.request
import urllib.error

# ป้องกันปัญหา Windows Console UTF-8 Encoding
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


FLASK_TRIGGER_URL = "http://127.0.0.1:5000/api/iot/trigger"
FLASK_STATUS_URL = "http://127.0.0.1:5000/api/iot/status"
FLASK_EVENTS_URL = "http://127.0.0.1:5000/api/iot/events"
FLASK_ARM_HARDWARE_URL = "http://127.0.0.1:5000/api/arm/hardware"
BAUD_RATE = 115200
STATUS_POLL_SEC = 10.0   # ถามสถานะบอร์ดเป็นระยะ (heartbeat) เพื่อให้แดชบอร์ดรู้ว่าบอร์ดยังอยู่
LED_STATES_ON_BOARD = ("idle", "speaking", "thinking", "off")


def event_to_serial_command(event):
    """
    แปลง SSE event จาก Flask เป็นคำสั่ง JSON สำหรับ ESP32 (คืน None ถ้าไม่เกี่ยวข้องกับฮาร์ดแวร์)
    โปรโตคอลต้องตรงกับ esp32_firmware.ino
    """
    kind = event.get("event")
    if kind == "arm_gesture" and event.get("gesture"):
        return {"cmd": "arm", "gesture": event["gesture"]}
    if kind == "arm_pose":
        return {"cmd": "arm", "side": event.get("side", "both"),
                "angle": event.get("angle"), "speed": event.get("speed", 90)}
    if kind == "led_state_changed" and event.get("state"):
        # firmware รู้จักเฉพาะ idle/speaking/thinking/off ส่วนสถานะอื่นของหน้าเว็บ (เช่น listening) ถือเป็น idle
        state = event["state"]
        if state in LED_STATES_ON_BOARD:
            return {"cmd": "set_led", "state": state}
        if state == "listening":
            return {"cmd": "set_led", "state": "idle"}
    return None


def report_to_flask(payload):
    """
    รายงานสถานะบอร์ด (เชื่อมต่อ/คำตอบจาก ESP32) กลับไปที่ Flask ให้แดชบอร์ดแสดงผล
    ทำในเธรดแยกเพื่อไม่ให้การรอ Flask ทำให้ลูป Serial สะดุด และไม่ล้มถ้า Flask ยังไม่เปิด
    """
    def _post():
        try:
            req = urllib.request.Request(
                FLASK_ARM_HARDWARE_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=2.0).close()
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()


def sse_command_listener(cmd_queue, stop_event):
    """
    สมัครรับ SSE /api/iot/events จาก Flask แล้วแปลงเป็นคำสั่งฮาร์ดแวร์ใส่คิว
    (เธรดนี้ไม่แตะพอร์ต Serial เพื่อให้มีเธรดเดียวที่เขียน Serial) เชื่อมต่อใหม่เองเมื่อหลุด
    """
    while not stop_event.is_set():
        try:
            with urllib.request.urlopen(FLASK_EVENTS_URL, timeout=30) as resp:
                for raw in resp:
                    if stop_event.is_set():
                        return
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    command = event_to_serial_command(event)
                    if command:
                        cmd_queue.put(command)
        except Exception:
            # Flask ยังไม่เปิด / ขาดการเชื่อมต่อ ลองใหม่
            stop_event.wait(3.0)


def find_esp32_port(strict=False, quiet=False):
    """
    ค้นหาพอร์ต Serial ของบอร์ด ESP32 โดยอัตโนมัติจาก Vendor/Description
    strict=True: คืนเฉพาะพอร์ตที่ตรงกับชิป USB-Serial ที่รู้จัก (ไม่เดาพอร์ตแรก) ใช้ใน --wait
                 เพื่อไม่ให้ไปเปิดพอร์ตของอุปกรณ์อื่นโดยไม่ตั้งใจ
    quiet=True : ไม่พิมพ์รายการพอร์ต (ใช้ตอนสแกนซ้ำเป็นระยะ)
    """
    if not SERIAL_AVAILABLE:
        return None

    ports = serial.tools.list_ports.comports()
    keywords = ["cp210", "ch340", "ch341", "ftdi", "usb-serial", "esp32", "silicon labs", "uart"]

    if not quiet:
        print("\n[Hardware Scanner] รายการพอร์ต Serial ที่ตรวจพบบนเครื่อง:")
    for p in ports:
        if not quiet:
            print(f"  - {p.device}: {p.description} [{p.hwid}]")
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        for kw in keywords:
            if kw in desc or kw in hwid:
                if not quiet:
                    print(f"  ==> ตรวจพบอุปกรณ์ที่ตรงกัน: {p.device}")
                return p.device

    # หากมีพอร์ตอย่างน้อย 1 พอร์ต ให้คืนค่าพอร์ตแรก (ยกเว้นโหมด strict)
    if ports and not strict:
        return ports[0].device
    return None


def forward_to_flask(event_data):
    """ส่งข้อมูล Event ที่ได้รับจาก ESP32 ไปยัง Flask Backend API"""
    try:
        payload = json.dumps(event_data).encode('utf-8')
        req = urllib.request.Request(
            FLASK_TRIGGER_URL,
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            resp_data = json.loads(resp.read().decode('utf-8'))
            return resp_data
    except Exception as e:
        # Flask อาจยังไม่เปิด หรือเปิดช้า
        return {"status": "flask_unreachable", "error": str(e)}


def send_command_to_esp32(ser, command_dict):
    """ส่งคำสั่ง JSON ไปยังบอร์ด ESP32 ผ่าน Serial"""
    if ser and ser.is_open:
        try:
            # separators แบบกะทัดรัด: ไม่มีช่องว่างหลัง ':' และ ',' (ลดขนาดข้อความและตรงกับ parser ใน firmware)
            cmd_str = json.dumps(command_dict, separators=(",", ":")) + "\n"
            ser.write(cmd_str.encode('utf-8'))
            ser.flush()
            print(f"  [Tx -> ESP32] สั่งการ GPIO: {cmd_str.strip()}")
            return True
        except Exception as e:
            print(f"  [Tx Error] ไม่สามารถส่งคำสั่งได้: {e}")
            return False
    return False


def run_simulation_mode():
    """โหมดจำลองการทำงาน (Simulation Mode) สำหรับสาธิตเมื่อไม่มีบอร์ดจริง"""
    print("\n" + "="*65)
    print("  🚀 เข้าสู่โหมดจำลอง ESP32 IoT (Simulation Mode)")
    print("  เกณฑ์ สอศ. ข้อ 4.2: จำลองเซนเซอร์ Ultrasonic & GPIO LED")
    print("  กด Enter เพื่อจำลองเหตุการณ์ 'ตรวจพบคนเดินเข้ามาใกล้ (distance: 42 cm)'")
    print("  หรือพิมพ์ 'quit' เพื่อออก")
    print("="*65 + "\n")

    def auto_trigger_loop():
        # ส่งสัญญาณทดสอบอัตโนมัติทุกๆ 20 วินาที
        counter = 1
        while getattr(threading.current_thread(), "do_run", True):
            time.sleep(20)
            simulated_dist = 45.0 + (counter % 5) * 5
            sim_event = {
                "event": "user_detected",
                "distance": simulated_dist,
                "unit": "cm",
                "source": "esp32_simulator",
                "timestamp_ms": int(time.time() * 1000)
            }
            print(f"\n[Auto Sim] 🤖 จำลองพบคนเข้าใกล้ระยะ {simulated_dist} ซม. -> กำลังยิง Trigger ไปที่ Flask...")
            resp = forward_to_flask(sim_event)
            print(f"  [Flask Response] {resp}")
            counter += 1

    sim_thread = threading.Thread(target=auto_trigger_loop, daemon=True)
    sim_thread.do_run = True
    sim_thread.start()

    # จำลองฝั่งฮาร์ดแวร์: แสดงคำสั่งแขน/ไฟที่ Flask สั่งมา แทนการเขียนลง Serial จริง
    sim_queue = queue.Queue()
    sim_stop = threading.Event()
    threading.Thread(target=sse_command_listener, args=(sim_queue, sim_stop), daemon=True).start()

    def print_commands():
        while not sim_stop.is_set():
            try:
                command = sim_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            print(f"\n  [Sim Tx -> ESP32] {json.dumps(command, ensure_ascii=False, separators=(',', ':'))}")

    threading.Thread(target=print_commands, daemon=True).start()

    while True:
        try:
            user_input = input("กด [Enter] เพื่อยิง Event จำลองทันที: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            sim_event = {
                "event": "user_detected",
                "distance": 38.5,
                "unit": "cm",
                "source": "esp32_manual_simulation",
                "timestamp_ms": int(time.time() * 1000)
            }
            print(f"[Manual Trigger] ยิงสัญญาณตรวจพบคนระยะ 38.5 ซม. ไปยัง Flask...")
            resp = forward_to_flask(sim_event)
            print(f"  [Flask Response] {resp}")
        except (KeyboardInterrupt, EOFError):
            break

    sim_thread.do_run = False
    sim_stop.set()
    print("\nสิ้นสุดโหมดจำลอง")


def run_serial_listener(port_name):
    """เปิดพอร์ต Serial และรับข้อมูลจากบอร์ด ESP32 ตลอดเวลา"""
    print(f"\n[Serial Connector] กำลังเชื่อมต่อกับ {port_name} ที่ {BAUD_RATE} bps...")

    # คิวคำสั่งจาก Flask (แขน/ไฟ LED) -> เธรดนี้เป็นเธรดเดียวที่เขียนลง Serial
    cmd_queue = queue.Queue()
    stop_event = threading.Event()
    threading.Thread(target=sse_command_listener, args=(cmd_queue, stop_event), daemon=True).start()

    while True:
        try:
            with serial.Serial(port_name, BAUD_RATE, timeout=1.0) as ser:
                print(f"✅ เชื่อมต่อกับบอร์ด ESP32 สำเร็จบนพอร์ต {port_name}")
                print(f"   พร้อมรับสัญญาณ Trigger จาก Ultrasonic HC-SR04...")
                
                report_to_flask({"connected": True, "port": port_name})
                # ส่งคำสั่งทดสอบเบื้องต้น
                send_command_to_esp32(ser, {"cmd": "get_status"})
                next_status_poll = time.time() + STATUS_POLL_SEC

                while True:
                    # Heartbeat: ถามสถานะบอร์ดเป็นระยะ
                    if time.time() >= next_status_poll:
                        send_command_to_esp32(ser, {"cmd": "get_status"})
                        next_status_poll = time.time() + STATUS_POLL_SEC

                    # ส่งคำสั่งที่ค้างในคิว (ท่าทางแขน, สถานะไฟ LED) ไปยัง ESP32
                    try:
                        while True:
                            send_command_to_esp32(ser, cmd_queue.get_nowait())
                    except queue.Empty:
                        pass

                    if ser.in_waiting > 0:
                        try:
                            raw_line = ser.readline().decode('utf-8', errors='ignore').strip()
                            if not raw_line:
                                continue
                                
                            print(f"[Rx <- ESP32] {raw_line}")

                            # พยายามถอดรหัส JSON
                            if raw_line.startswith('{') and raw_line.endswith('}'):
                                try:
                                    event = json.loads(raw_line)
                                    if "response" in event or "device" in event:
                                        # คำตอบ/ข้อความระบุตัวตนจากบอร์ด -> รายงานให้ Flask (ack, เวอร์ชัน, มุมแขน, error)
                                        report_to_flask({"response": event})
                                    if event.get("event") == "user_detected":
                                        distance = event.get("distance", 0)
                                        print(f"🚨 [ALERT] ตรวจพบผู้ใช้! ระยะทาง: {distance} ซม. ส่งต่อไปยัง Web App...")
                                        flask_resp = forward_to_flask(event)
                                        print(f"   [Flask Web Hook Result] {flask_resp}")
                                        
                                        # ส่งคำสั่งให้ ESP32 สลับไฟ LED เป็นสถานะพูด/ต้อนรับ
                                        send_command_to_esp32(ser, {"cmd": "set_led", "state": "speaking"})
                                        
                                except json.JSONDecodeError:
                                    pass
                        except UnicodeDecodeError:
                            pass
                    time.sleep(0.01)

        except serial.SerialException as e:
            report_to_flask({"connected": False})
            print(f"⚠️ การเชื่อมต่อ Serial ขัดข้อง: {e}")
            print("   จะลองเชื่อมต่อใหม่อัตโนมัติในอีก 3 วินาที...")
            time.sleep(3)
        except KeyboardInterrupt:
            print("\nปิดโปรแกรมเชื่อมต่อ ESP32 เรียบร้อย")
            break


def main():
    parser = argparse.ArgumentParser(description="น้องเพชร AI - ESP32 Serial & IoT Controller")
    parser.add_argument("--port", type=str, help="พอร์ต Serial ของ ESP32 (เช่น COM3, /dev/ttyUSB0)")
    parser.add_argument("--simulate", action="store_true", help="รันในโหมดจำลอง (ไม่ต้องเชื่อมต่อบอร์ดจริง)")
    parser.add_argument("--wait", action="store_true",
                        help="โหมดบริการ (systemd): ถ้ายังไม่พบบอร์ดให้รอและสแกนซ้ำทุก 5 วินาทีโดยไม่ถามคำถาม")
    args = parser.parse_args()

    print("="*65)
    print("   🤖 น้องเพชร AI Smart Guide - ESP32 IoT Bridge Controller")
    print("   สอดคล้องเกณฑ์สิ่งประดิษฐ์คนรุ่นใหม่ สอศ. ข้อ 4.2 (GPIO I/O)")
    print("="*65)

    if args.simulate:
        run_simulation_mode()
        return

    if not SERIAL_AVAILABLE:
        print("\n❌ ยังไม่ได้ติดตั้ง pyserial (pip install pyserial) จึงเปิดพอร์ต Serial ไม่ได้")
        print("💡 ทดสอบโดยไม่ต้องมีบอร์ดได้ด้วย: python esp32_listener.py --simulate")
        sys.exit(1)

    port = args.port

    if args.wait and not port:
        # โหมดบริการ: ยังไม่ต่อบอร์ดก็ไม่เป็นไร รอจนกว่าจะเสียบ แล้วค่อยเชื่อมต่อเอง
        print("⏳ โหมดรอบอร์ด (--wait): สแกนหา ESP32 ทุก 5 วินาที (Ctrl+C เพื่อออก)")
        announced = False
        try:
            while not port:
                port = find_esp32_port(strict=True, quiet=True)
                if not port:
                    if not announced:
                        print("   ยังไม่พบบอร์ด ESP32 กำลังรอการเสียบสาย USB...")
                        announced = True
                    time.sleep(5)
        except KeyboardInterrupt:
            return
        print(f"✅ พบบอร์ดที่พอร์ต {port}")

    if not port:
        port = find_esp32_port()

    if not port:
        print("\n❌ ไม่พบพอร์ต Serial ของบอร์ด ESP32 ที่เชื่อมต่ออยู่")
        print("💡 คุณสามารถรันโหมดจำลองได้โดยพิมพ์: python esp32_listener.py --simulate")
        choice = input("\nต้องการเปิดโหมดจำลอง (Simulation) หรือไม่? [y/N]: ").strip().lower()
        if choice in ['y', 'yes']:
            run_simulation_mode()
        else:
            print("ยกเลิกการทำงาน")
        return

    run_serial_listener(port)


if __name__ == "__main__":
    main()
