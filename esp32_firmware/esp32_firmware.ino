/*
 * ==============================================================================
 * โครงการ: น้องเพชร AI Smart Guide (Nong Phet AI Assistant)
 * โมดูล: ระบบสมองกลฝังตัวและไอโอที (ESP32 Embedded IoT Controller)
 * มาตรฐาน: สอดคล้องเกณฑ์การประเมินสิ่งประดิษฐ์ สอศ. ข้อ 4.2 (GPIO Input/Output)
 * ------------------------------------------------------------------------------
 * คำอธิบายการทำงาน:
 * 1. Input: อ่านค่าระยะทางจากเซนเซอร์อัลตราโซนิก (HC-SR04) แบบ Non-blocking (millis)
 * 2. Output 1: ควบคุมไฟ LED แสดงสถานะ (GPIO 2) ปรับตามสถานะ (พร้อมใช้งาน/ตรวจพบคน/AI กำลังพูด)
 * 3. Output 2: ส่งข้อมูล JSON ผ่าน USB Serial (UART) ไปยัง Flask Server เมื่อตรวจพบคน (< 80 cm)
 * 4. Bidirectional UART: รองรับคำสั่ง JSON จาก Flask/Python เพื่อควบคุมไฟ LED จากระบบ AI
 * ==============================================================================
 * การต่อวงจร (Wiring Diagram):
 * ESP32 Pin        Component Pin           หมายเหตุ
 * ------------------------------------------------------------------------------
 * 5V (VIN)   --->  HC-SR04 VCC            (แหล่งจ่ายไฟเซนเซอร์)
 * GND        --->  HC-SR04 GND            (กราวด์ร่วม)
 * GPIO 5     --->  HC-SR04 TRIG           (ส่งสัญญาณพัลส์ Trigger)
 * GPIO 18    <---  HC-SR04 ECHO (ผ่าน R)   (รับสัญญาณพัลส์ Echo *ดูวงจรแบ่งแรงดันด้านล่าง*)
 * GPIO 2     --->  LED Anode (+) ผ่าน 220Ω (ไฟสถานะ Onboard หรือ External LED)
 * GND        --->  LED Cathode (-)        (ขาลบของ LED)
 * ------------------------------------------------------------------------------
 * *คำแนะนำความปลอดภัยแรงดันไฟฟ้า (Voltage Divider สำหรับขา ECHO):*
 * ขา ECHO ของ HC-SR04 จ่ายไฟ 5V แต่ขา GPIO ของ ESP32 รับได้ 3.3V
 * วงจรแบ่งแรงดัน: HC-SR04 ECHO ---> [ตัวต้านทาน 1kΩ] ---> GPIO 18 ---> [ตัวต้านทาน 2kΩ] ---> GND
 * (หรือหากใช้เซนเซอร์รุ่น HC-SR04P หรือ RCWL-9610 สามารถต่อไฟ 3.3V ได้โดยตรง)
 * ==============================================================================
 */

#include <Arduino.h>

// --- กำหนดหมายเลขขา GPIO ตามเกณฑ์ สอศ. ข้อ 4.2 ---
const int PIN_TRIG = 5;      // GPIO 5 : Output ส่งคลื่น Ultrasonic
const int PIN_ECHO = 18;     // GPIO 18: Input รับคลื่นสะท้อน Ultrasonic
const int PIN_LED  = 2;      // GPIO 2 : Output ไฟ LED แสดงสถานะ (Onboard LED ESP32)

// --- การตั้งค่าพารามิเตอร์การตรวจจับ ---
const float DISTANCE_THRESHOLD = 80.0;     // ระยะตรวจจับผู้ใช้: น้อยกว่า 80 ซม.
const unsigned long SENSOR_INTERVAL = 100;  // ความถี่ในการอ่านเซนเซอร์ (ms)
const unsigned long TRIGGER_COOLDOWN = 6000; // ระยะเวลาหน่วงป้องกันการส่งข้อความซ้ำ (Cooldown 6 วินาที)

// --- ตัวแปรจัดการเวลา (Non-blocking using millis) ---
unsigned long lastSensorReadTime = 0;
unsigned long lastTriggerTime = 0;
unsigned long lastBlinkTime = 0;

// --- สถานะไฟ LED (LED State Machine) ---
enum LedMode {
  LED_IDLE,       // สว่างค้าง: ระบบพร้อมทำงาน
  LED_SPEAKING,   // กะพริบเร็ว (100ms): กำลังโต้ตอบ/ส่งเสียงพูด
  LED_THINKING,   // กะพริบปานกลาง (250ms): กำลังประมวลผล AI
  LED_DETECTED,   // กะพริบเตือนระยะ (50ms): ตรวจพบคนเข้าใกล้
  LED_OFF         // ดับไฟ
};

LedMode currentLedMode = LED_IDLE;
bool ledState = false;
int blinkInterval = 200;

// บัฟเฟอร์สำหรับอ่านคำสั่ง Serial
String serialBuffer = "";

// ฟังก์ชันวัดระยะทางแบบปลอดภัย มี Timeout
float measureDistance() {
  // สร้างพัลส์ LOW 2us เพื่อให้สัญญาณนิ่ง
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  
  // ยิงพัลส์ HIGH 10us เพื่อกระตุ้นเซนเซอร์
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  
  // อ่านระยะเวลาที่พัลส์สะท้อนกลับ (Timeout 30,000 us = ~5 เมตร)
  unsigned long duration = pulseIn(PIN_ECHO, HIGH, 30000);
  
  if (duration == 0) {
    return -1.0; // ไม่พบสัญญาณสะท้อนหรืออยู่นอกระยะ
  }
  
  // คำนวณระยะทาง: ความเร็วเสียง 343 m/s = 0.0343 cm/us (หาร 2 ไป-กลับ)
  float distance = (duration * 0.0343) / 2.0;
  return distance;
}

// อัปเดตสถานะไฟ LED แบบ Non-blocking
void updateLedState() {
  unsigned long now = millis();
  
  switch (currentLedMode) {
    case LED_IDLE:
      digitalWrite(PIN_LED, HIGH); // ติดค้าง
      break;
      
    case LED_OFF:
      digitalWrite(PIN_LED, LOW); // ดับ
      break;
      
    case LED_SPEAKING:
      blinkInterval = 100; // กะพริบเร็วมากขณะ AI พูด
      if (now - lastBlinkTime >= blinkInterval) {
        lastBlinkTime = now;
        ledState = !ledState;
        digitalWrite(PIN_LED, ledState ? HIGH : LOW);
      }
      break;
      
    case LED_THINKING:
      blinkInterval = 250; // กะพริบเป็นจังหวะครุ่นคิด
      if (now - lastBlinkTime >= blinkInterval) {
        lastBlinkTime = now;
        ledState = !ledState;
        digitalWrite(PIN_LED, ledState ? HIGH : LOW);
      }
      break;
      
    case LED_DETECTED:
      blinkInterval = 60; // กะพริบเตือนถี่สั้นๆ
      if (now - lastBlinkTime >= blinkInterval) {
        lastBlinkTime = now;
        ledState = !ledState;
        digitalWrite(PIN_LED, ledState ? HIGH : LOW);
      }
      break;
  }
}

// ฟังก์ชันประมวลผลคำสั่ง Serial ขาเข้าจากคอมพิวเตอร์ (JSON/Plain Command)
void processIncomingCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  // รองรับทั้งคำสั่งแบบง่าย และ JSON string
  if (cmd.indexOf("\"state\":\"speaking\"") != -1 || cmd.equalsIgnoreCase("speaking")) {
    currentLedMode = LED_SPEAKING;
    Serial.println("{\"response\":\"ok\",\"led_mode\":\"speaking\"}");
  } 
  else if (cmd.indexOf("\"state\":\"thinking\"") != -1 || cmd.equalsIgnoreCase("thinking")) {
    currentLedMode = LED_THINKING;
    Serial.println("{\"response\":\"ok\",\"led_mode\":\"thinking\"}");
  } 
  else if (cmd.indexOf("\"state\":\"idle\"") != -1 || cmd.equalsIgnoreCase("idle")) {
    currentLedMode = LED_IDLE;
    Serial.println("{\"response\":\"ok\",\"led_mode\":\"idle\"}");
  } 
  else if (cmd.indexOf("\"state\":\"off\"") != -1 || cmd.equalsIgnoreCase("off")) {
    currentLedMode = LED_OFF;
    Serial.println("{\"response\":\"ok\",\"led_mode\":\"off\"}");
  } 
  else if (cmd.indexOf("ping") != -1) {
    Serial.println("{\"response\":\"pong\",\"device\":\"ESP32_NONGPHET_IOT\",\"uptime_ms\":" + String(millis()) + "}");
  }
}

void setup() {
  // เริ่มต้น Serial UART ความเร็วสูง 115200 bps
  Serial.begin(115200);
  delay(100);

  // กำหนดโหมดการทำงานของขา GPIO ตามเกณฑ์ สอศ.
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_LED, OUTPUT);

  // เริ่มต้นสถานะเริ่มต้น
  digitalWrite(PIN_TRIG, LOW);
  digitalWrite(PIN_LED, HIGH); // ติดค้างแสดงความพร้อม

  // ส่งข้อมูลระบุตัวตนของบอร์ด ESP32 เมื่อบูตเสร็จ
  Serial.println();
  Serial.println("=================================================");
  Serial.println("{\"device\":\"ESP32_NONGPHET_IOT\",\"version\":\"1.0.0\",\"status\":\"ready\"}");
  Serial.println("=================================================");
}

void loop() {
  unsigned long currentMillis = millis();

  // 1. อ่านคำสั่งที่ส่งมาจากคอมพิวเตอร์ผ่าน Serial (UART)
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        processIncomingCommand(serialBuffer);
        serialBuffer = "";
      }
    } else {
      if (serialBuffer.length() < 128) {
        serialBuffer += c;
      }
    }
  }

  // 2. ตรวจสอบระยะทางจากเซนเซอร์ Ultrasonic แบบตามรอบเวลา (Non-blocking)
  if (currentMillis - lastSensorReadTime >= SENSOR_INTERVAL) {
    lastSensorReadTime = currentMillis;

    float distance = measureDistance();

    // หากพบระยะทางที่ถูกต้องและอยู่ในเกณฑ์ตรวจจับ (< 80 ซม.)
    if (distance > 0 && distance < DISTANCE_THRESHOLD) {
      // ตรวจสอบว่าพ้นระยะ Cooldown หรือยัง เพื่อไม่ให้ส่งสัญญาณรัวเกินไป
      if (currentMillis - lastTriggerTime >= TRIGGER_COOLDOWN) {
        lastTriggerTime = currentMillis;
        currentLedMode = LED_DETECTED;

        // ส่งข้อความ JSON Output ไปยังเครื่องคอมพิวเตอร์ผ่าน Serial
        Serial.print("{\"event\":\"user_detected\",\"distance\":");
        Serial.print(distance, 1);
        Serial.print(",\"unit\":\"cm\",\"timestamp_ms\":");
        Serial.print(currentMillis);
        Serial.println("}");
      }
    } else {
      // เมื่อไม่มีคนหรือคนเดินออกห่าง และไม่ได้อยู่ในโหมด AI Speaking ให้กลับเป็น IDLE
      if (currentLedMode == LED_DETECTED && (currentMillis - lastTriggerTime > 1500)) {
        currentLedMode = LED_IDLE;
      }
    }
  }

  // 3. ควบคุมไฟ LED ตาม State Machine (Non-blocking)
  updateLedState();
}
