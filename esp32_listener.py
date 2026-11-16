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
BAUD_RATE = 115200


def find_esp32_port():
    """ค้นหาพอร์ต Serial ของบอร์ด ESP32 โดยอัตโนมัติจาก Vendor/Description"""
    if not SERIAL_AVAILABLE:
        return None
    
    ports = serial.tools.list_ports.comports()
    keywords = ["cp210", "ch340", "ch341", "ftdi", "usb-serial", "esp32", "silicon labs", "uart"]
    
    print("\n[Hardware Scanner] รายการพอร์ต Serial ที่ตรวจพบบนเครื่อง:")
    for p in ports:
        print(f"  - {p.device}: {p.description} [{p.hwid}]")
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        for kw in keywords:
            if kw in desc or kw in hwid:
                print(f"  ==> ตรวจพบอุปกรณ์ที่ตรงกัน: {p.device}")
                return p.device
                
    # หากมีพอร์ตอย่างน้อย 1 พอร์ต ให้คืนค่าพอร์ตแรก
    if ports:
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
            cmd_str = json.dumps(command_dict) + "\n"
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
    print("\nสิ้นสุดโหมดจำลอง")


def run_serial_listener(port_name):
    """เปิดพอร์ต Serial และรับข้อมูลจากบอร์ด ESP32 ตลอดเวลา"""
    print(f"\n[Serial Connector] กำลังเชื่อมต่อกับ {port_name} ที่ {BAUD_RATE} bps...")
    
    while True:
        try:
            with serial.Serial(port_name, BAUD_RATE, timeout=1.0) as ser:
                print(f"✅ เชื่อมต่อกับบอร์ด ESP32 สำเร็จบนพอร์ต {port_name}")
                print(f"   พร้อมรับสัญญาณ Trigger จาก Ultrasonic HC-SR04...")
                
                # ส่งคำสั่งทดสอบเบื้องต้น
                send_command_to_esp32(ser, {"command": "get_status"})

                while True:
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
                                    if event.get("event") == "user_detected":
                                        distance = event.get("distance", 0)
                                        print(f"🚨 [ALERT] ตรวจพบผู้ใช้! ระยะทาง: {distance} ซม. ส่งต่อไปยัง Web App...")
                                        flask_resp = forward_to_flask(event)
                                        print(f"   [Flask Web Hook Result] {flask_resp}")
                                        
                                        # ส่งคำสั่งให้ ESP32 สลับไฟ LED เป็นสถานะพูด/ต้อนรับ
                                        send_command_to_esp32(ser, {"command": "set_led", "state": "speaking"})
                                        
                                except json.JSONDecodeError:
                                    pass
                        except UnicodeDecodeError:
                            pass
                    time.sleep(0.01)

        except serial.SerialException as e:
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
    args = parser.parse_args()

    print("="*65)
    print("   🤖 น้องเพชร AI Smart Guide - ESP32 IoT Bridge Controller")
    print("   สอดคล้องเกณฑ์สิ่งประดิษฐ์คนรุ่นใหม่ สอศ. ข้อ 4.2 (GPIO I/O)")
    print("="*65)

    if args.simulate:
        run_simulation_mode()
        return

    port = args.port
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
