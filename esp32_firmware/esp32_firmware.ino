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
 * 5. Output 3: แขนเซอร์โวที่ไหล่ซ้าย/ขวา (SG90/MG90S) ขยับแบบ non-blocking พร้อมท่าทางสำเร็จรูป
 * ==============================================================================
 * โปรโตคอลคำสั่ง (JSON 1 บรรทัดต่อคำสั่ง ลงท้ายด้วย \n):
 *   {"cmd":"arm","gesture":"wave"}                         เล่นท่าทาง (ดูรายชื่อใน GESTURES)
 *   {"cmd":"arm","side":"L","angle":90,"speed":60}         สั่งมุม side = L | R | both
 *   {"cmd":"set_led","state":"speaking"}                   ไฟ LED (idle|speaking|thinking|off)
 *   {"cmd":"get_status"} / ping                            ตรวจสอบสถานะบอร์ด
 * ต้องติดตั้งไลบรารี "ESP32Servo" ผ่าน Library Manager ของ Arduino IDE
 * ==============================================================================
 * การต่อแขนเซอร์โว (ห้ามจ่ายไฟเซอร์โวจาก 3.3V / ขา VIN ของ ESP32):
 *   Servo L (สีส้ม/เหลือง = สัญญาณ) ---> GPIO 13
 *   Servo R (สีส้ม/เหลือง = สัญญาณ) ---> GPIO 14
 *   สายแดง (VCC) ---> 5V แหล่งจ่ายแยก 2-3A (buck converter) + คาปาซิเตอร์ 470-1000uF
 *   สายน้ำตาล (GND) ---> GND ร่วมกับ ESP32 (ต้องต่อกราวด์ร่วมกันเสมอ)
 *   หมายเหตุ: หลีกเลี่ยง GPIO 12 เพราะเป็น strapping pin อาจทำให้บอร์ดบูตไม่ขึ้น
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
#include <ESP32Servo.h>

// --- แขนเซอร์โวไหล่ ---
const int PIN_ARM_L = 13;
const int PIN_ARM_R = 14;
const int ARM_MIN = 20;                         // มุมต่ำสุด (ลดแขน/ท่าพัก) ต้องตรงกับ services/arm_service.py
const int ARM_MAX = 120;                        // มุมสูงสุด (ยกแขน)
const int ARM_REST = 20;
const float ARM_DEFAULT_SPEED = 90.0;           // องศา/วินาที
const unsigned long ARM_UPDATE_INTERVAL = 15;   // ms ระหว่างการขยับแต่ละก้าว
const unsigned long ARM_DETACH_AFTER = 800;     // ms หลังถึงเป้าหมาย ให้ปล่อยสัญญาณ กันเซอร์โวสั่น/กินไฟ
const unsigned long ARM_POSE_TIMEOUT = 30000;   // ไม่มีคำสั่งนานเกินนี้ ให้กลับท่าพักเอง (Watchdog)

struct Arm {
  Servo servo;
  int pin;
  bool invert;          // แขนที่ติดตั้งกลับด้านกระจก ให้ใส่ true
  float current;        // มุมปัจจุบัน (องศาตรรกะ ARM_MIN..ARM_MAX)
  float target;
  float speed;          // องศา/วินาที
  bool attached;
  unsigned long settledAt;
};

Arm armL;
Arm armR;

void initArm(Arm& a, int pin, bool invert) {
  a.pin = pin;
  a.invert = invert;
  a.current = ARM_REST;
  a.target = ARM_REST;
  a.speed = ARM_DEFAULT_SPEED;
  a.attached = false;
  a.settledAt = 0;
}
unsigned long lastArmUpdate = 0;
unsigned long lastArmCommand = 0;

// --- ท่าทางสำเร็จรูป (keyframe) --- -1 = ไม่เปลี่ยนมุมแขนข้างนั้น
struct ArmStep { int l; int r; int speed; unsigned int holdMs; };

const ArmStep G_REST[]        = {{ARM_REST, ARM_REST, 120, 0}};
const ArmStep G_WAVE[]        = {{-1, 120, 240, 150}, {-1, 70, 300, 0}, {-1, 120, 300, 0}, {-1, 70, 300, 0}, {-1, 120, 300, 150}, {-1, ARM_REST, 120, 0}};
const ArmStep G_WAVE_LEFT[]   = {{120, -1, 240, 150}, {70, -1, 300, 0}, {120, -1, 300, 0}, {70, -1, 300, 0}, {120, -1, 300, 150}, {ARM_REST, -1, 120, 0}};
const ArmStep G_RAISE_LEFT[]  = {{120, -1, 150, 1200}, {ARM_REST, -1, 120, 0}};
const ArmStep G_RAISE_RIGHT[] = {{-1, 120, 150, 1200}, {-1, ARM_REST, 120, 0}};
const ArmStep G_RAISE_BOTH[]  = {{120, 120, 150, 1200}, {ARM_REST, ARM_REST, 120, 0}};
const ArmStep G_CHEER[]       = {{120, 60, 300, 0}, {60, 120, 300, 0}, {120, 60, 300, 0}, {60, 120, 300, 0}, {120, 120, 300, 300}, {ARM_REST, ARM_REST, 150, 0}};
const ArmStep G_SURPRISE[]    = {{120, 120, 360, 400}, {ARM_REST, ARM_REST, 90, 0}};
const ArmStep G_TALK[]        = {{-1, 45, 70, 250}, {45, 30, 70, 250}, {30, 45, 70, 250}, {-1, 30, 70, 250}};

struct Gesture { const char* name; const ArmStep* steps; uint8_t count; bool loop; };
const Gesture GESTURES[] = {
  {"rest",        G_REST,        sizeof(G_REST)/sizeof(ArmStep),        false},
  {"wave",        G_WAVE,        sizeof(G_WAVE)/sizeof(ArmStep),        false},
  {"wave_left",   G_WAVE_LEFT,   sizeof(G_WAVE_LEFT)/sizeof(ArmStep),   false},
  {"raise_left",  G_RAISE_LEFT,  sizeof(G_RAISE_LEFT)/sizeof(ArmStep),  false},
  {"raise_right", G_RAISE_RIGHT, sizeof(G_RAISE_RIGHT)/sizeof(ArmStep), false},
  {"raise_both",  G_RAISE_BOTH,  sizeof(G_RAISE_BOTH)/sizeof(ArmStep),  false},
  {"cheer",       G_CHEER,       sizeof(G_CHEER)/sizeof(ArmStep),       false},
  {"surprise",    G_SURPRISE,    sizeof(G_SURPRISE)/sizeof(ArmStep),    false},
  {"talk",        G_TALK,        sizeof(G_TALK)/sizeof(ArmStep),        true},
};
const int GESTURE_COUNT = sizeof(GESTURES) / sizeof(Gesture);

const Gesture* activeGesture = nullptr;
int gestureStep = 0;
unsigned long stepReachedAt = 0;   // เวลาที่แขนถึงเป้าหมายของ step นี้ (0 = ยังไม่ถึง)

// ท่าประกอบการพูด (talk): ถ้าสั่งตอนที่ท่าอื่นกำลังเล่นอยู่ จะรอให้ท่านั้นจบก่อนแล้วค่อยเริ่มขยับเบาๆ
// เมื่อได้รับ rest หรือครบเวลา TALK_MAX_MS (กันค้างถ้าสัญญาณ "หยุดพูด" ไม่มาถึง) จะหยุดเอง
const unsigned long TALK_MAX_MS = 60000;
bool speakingFlag = false;
unsigned long speakingSince = 0;
const Gesture* talkGesture = nullptr;
const Gesture* restGesture = nullptr;

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

// ==============================================================================
// ตัวช่วยอ่านค่าจาก JSON แบบเบา (ไม่ต้องใช้ไลบรารีเพิ่ม และไม่สนใจช่องว่างหลัง : หรือ ,)
// ==============================================================================
// คืนตำแหน่งเริ่มต้นของค่า (หลัง ':' และช่องว่าง) หรือ -1 หากไม่พบคีย์
int jsonValueStart(const String& s, const char* key) {
  String needle = String("\"") + key + "\"";
  int k = s.indexOf(needle);
  if (k < 0) return -1;
  int i = k + needle.length();
  while (i < (int)s.length() && s[i] == ' ') i++;
  if (i >= (int)s.length() || s[i] != ':') return -1;
  i++;
  while (i < (int)s.length() && s[i] == ' ') i++;
  return i < (int)s.length() ? i : -1;
}

String jsonString(const String& s, const char* key) {
  int i = jsonValueStart(s, key);
  if (i < 0 || s[i] != '"') return "";
  int end = s.indexOf('"', i + 1);
  if (end < 0) return "";
  return s.substring(i + 1, end);
}

float jsonNumber(const String& s, const char* key, float def) {
  int i = jsonValueStart(s, key);
  if (i < 0) return def;
  return s.substring(i).toFloat();
}

// ==============================================================================
// ควบคุมแขนเซอร์โว (Non-blocking)
// ==============================================================================
int toServoAngle(const Arm& a, float logical) {
  // แขนที่ติดตั้งกลับด้านให้สะท้อนมุมภายในช่วง ARM_MIN..ARM_MAX
  float v = a.invert ? (ARM_MIN + ARM_MAX - logical) : logical;
  return (int)constrain(v, 0.0f, 180.0f);
}

void setArmTarget(Arm& a, int angle, float speed) {
  angle = constrain(angle, ARM_MIN, ARM_MAX);
  a.target = angle;
  a.speed = constrain(speed, 5.0f, 360.0f);
  a.settledAt = 0;
  if (!a.attached) {
    a.servo.attach(a.pin, 500, 2400);
    a.servo.write(toServoAngle(a, a.current));  // เริ่มจากมุมเดิม ป้องกันกระชากตอน attach
    a.attached = true;
  }
}

// คืน true เมื่อแขนอยู่ที่เป้าหมายแล้ว
bool stepArm(Arm& a, float dtSec, unsigned long now) {
  if (!a.attached) return true;
  float diff = a.target - a.current;
  float maxMove = a.speed * dtSec;
  if (fabsf(diff) <= maxMove) {
    a.current = a.target;
  } else {
    a.current += (diff > 0 ? maxMove : -maxMove);
  }
  a.servo.write(toServoAngle(a, a.current));

  if (a.current == a.target) {
    if (a.settledAt == 0) a.settledAt = now;
    // ปล่อยสัญญาณเฉพาะตอนแขนห้อยอยู่ท่าพัก (กันสั่ง/กินกระแส) ถ้ายกแขนค้างต้องคงแรงบิดไว้ ไม่งั้นแขนจะตก
    if (a.target <= ARM_REST && now - a.settledAt > ARM_DETACH_AFTER) {
      a.servo.detach();
      a.attached = false;
    }
    return true;
  }
  return false;
}

void startGesture(const Gesture* g) {
  activeGesture = g;
  gestureStep = 0;
  stepReachedAt = 0;
  lastArmCommand = millis();
  const ArmStep& s = g->steps[0];
  if (s.l >= 0) setArmTarget(armL, s.l, s.speed);
  if (s.r >= 0) setArmTarget(armR, s.r, s.speed);
}

void updateArms() {
  unsigned long now = millis();
  if (now - lastArmUpdate < ARM_UPDATE_INTERVAL) return;
  float dt = (now - lastArmUpdate) / 1000.0f;
  lastArmUpdate = now;

  bool lDone = stepArm(armL, dt, now);
  bool rDone = stepArm(armR, dt, now);

  // หมดเวลาท่าพูด -> หยุดขยับและกลับท่าพัก
  if (speakingFlag && now - speakingSince > TALK_MAX_MS) {
    speakingFlag = false;
    if (activeGesture == talkGesture && restGesture) startGesture(restGesture);
    return;
  }

  if (activeGesture) {
    if (lDone && rDone) {
      if (stepReachedAt == 0) stepReachedAt = now;
      const ArmStep& cur = activeGesture->steps[gestureStep];
      if (now - stepReachedAt >= cur.holdMs) {
        gestureStep++;
        stepReachedAt = 0;
        if (gestureStep >= activeGesture->count) {
          if (activeGesture->loop) {
            gestureStep = 0;
          } else {
            activeGesture = nullptr;
            // ท่าที่เล่นจบแล้ว ถ้ายังอยู่ระหว่างพูด ให้กลับมาขยับเบาๆ ต่อ
            if (speakingFlag && talkGesture) startGesture(talkGesture);
            return;
          }
        }
        const ArmStep& nxt = activeGesture->steps[gestureStep];
        if (nxt.l >= 0) setArmTarget(armL, nxt.l, nxt.speed);
        if (nxt.r >= 0) setArmTarget(armR, nxt.r, nxt.speed);
      }
    }
  } else if ((armL.target != ARM_REST || armR.target != ARM_REST) &&
             now - lastArmCommand > ARM_POSE_TIMEOUT) {
    // Watchdog: ไม่มีคำสั่งนาน ให้ลดแขนกลับท่าพักเอง
    setArmTarget(armL, ARM_REST, ARM_DEFAULT_SPEED);
    setArmTarget(armR, ARM_REST, ARM_DEFAULT_SPEED);
  }
}

void handleArmCommand(const String& cmd) {
  String gesture = jsonString(cmd, "gesture");
  if (gesture.length() > 0) {
    for (int i = 0; i < GESTURE_COUNT; i++) {
      if (gesture.equals(GESTURES[i].name)) {
        const Gesture* g = &GESTURES[i];
        if (g == talkGesture) {
          speakingFlag = true;
          speakingSince = millis();
          // ถ้ามีท่าอื่นที่ไม่วนลูปกำลังเล่นอยู่ ปล่อยให้เล่นจนจบก่อน (จะกลับมาขยับเบาๆ เองตอนจบ)
          if (!activeGesture || activeGesture->loop) startGesture(g);
        } else {
          if (g == restGesture) speakingFlag = false;
          startGesture(g);
        }
        Serial.println(String("{\"response\":\"ok\",\"arm\":\"gesture\",\"gesture\":\"") + gesture + "\"}");
        return;
      }
    }
    Serial.println(String("{\"response\":\"error\",\"reason\":\"unknown_gesture\",\"gesture\":\"") + gesture + "\"}");
    return;
  }

  String side = jsonString(cmd, "side");
  if (side.length() == 0) side = "both";
  if (!(side == "L" || side == "R" || side == "both")) {
    Serial.println("{\"response\":\"error\",\"reason\":\"bad_side\"}");
    return;
  }
  int angle = (int)jsonNumber(cmd, "angle", ARM_REST);
  float speed = jsonNumber(cmd, "speed", ARM_DEFAULT_SPEED);
  activeGesture = nullptr;  // คำสั่งมุมโดยตรงยกเลิกท่าที่กำลังเล่น
  speakingFlag = false;
  lastArmCommand = millis();
  if (side == "L" || side == "both") setArmTarget(armL, angle, speed);
  if (side == "R" || side == "both") setArmTarget(armR, angle, speed);
  Serial.println(String("{\"response\":\"ok\",\"arm\":\"pose\",\"side\":\"") + side + "\",\"angle\":" + String(constrain(angle, ARM_MIN, ARM_MAX)) + "}");
}

void applyLedState(const String& state) {
  if (state == "speaking") currentLedMode = LED_SPEAKING;
  else if (state == "thinking") currentLedMode = LED_THINKING;
  else if (state == "idle") currentLedMode = LED_IDLE;
  else if (state == "off") currentLedMode = LED_OFF;
  else {
    Serial.println("{\"response\":\"error\",\"reason\":\"bad_led_state\"}");
    return;
  }
  Serial.println(String("{\"response\":\"ok\",\"led_mode\":\"") + state + "\"}");
}

// ฟังก์ชันประมวลผลคำสั่ง Serial ขาเข้าจากคอมพิวเตอร์ (JSON/Plain Command)
void processIncomingCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  // คำสั่งแบบข้อความเดี่ยว (เข้ากันได้กับเวอร์ชันเก่า)
  if (cmd.equalsIgnoreCase("speaking") || cmd.equalsIgnoreCase("thinking") ||
      cmd.equalsIgnoreCase("idle") || cmd.equalsIgnoreCase("off")) {
    String s = cmd;
    s.toLowerCase();
    applyLedState(s);
    return;
  }
  if (cmd.equalsIgnoreCase("ping")) {
    Serial.println("{\"response\":\"pong\",\"device\":\"ESP32_NONGPHET_IOT\",\"uptime_ms\":" + String(millis()) + "}");
    return;
  }

  String name = jsonString(cmd, "cmd");
  if (name.length() == 0) name = jsonString(cmd, "command");

  if (name == "arm") {
    handleArmCommand(cmd);
  } else if (name == "set_led" || (name.length() == 0 && jsonString(cmd, "state").length() > 0)) {
    applyLedState(jsonString(cmd, "state"));
  } else if (name == "get_status") {
    Serial.println(String("{\"response\":\"status\",\"device\":\"ESP32_NONGPHET_IOT\",\"version\":\"1.1.0\",\"uptime_ms\":") + String(millis()) +
                   ",\"arm_l\":" + String((int)armL.current) + ",\"arm_r\":" + String((int)armR.current) +
                   ",\"gesture\":\"" + (activeGesture ? activeGesture->name : "none") + "\"}");
  } else if (cmd.indexOf("ping") != -1) {
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

  // หาตัวชี้ท่า talk / rest ไว้ใช้ตอนสลับท่า
  for (int i = 0; i < GESTURE_COUNT; i++) {
    if (strcmp(GESTURES[i].name, "talk") == 0) talkGesture = &GESTURES[i];
    if (strcmp(GESTURES[i].name, "rest") == 0) restGesture = &GESTURES[i];
  }

  // เตรียมแขนเซอร์โว (จองไทเมอร์ PWM แล้วตั้งต้นที่ท่าพัก)
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  armL.servo.setPeriodHertz(50);
  armR.servo.setPeriodHertz(50);
  initArm(armL, PIN_ARM_L, false);
  initArm(armR, PIN_ARM_R, true);
  setArmTarget(armL, ARM_REST, ARM_DEFAULT_SPEED);
  setArmTarget(armR, ARM_REST, ARM_DEFAULT_SPEED);
  lastArmUpdate = millis();
  lastArmCommand = millis();

  // ส่งข้อมูลระบุตัวตนของบอร์ด ESP32 เมื่อบูตเสร็จ
  Serial.println();
  Serial.println("=================================================");
  Serial.println("{\"device\":\"ESP32_NONGPHET_IOT\",\"version\":\"1.1.0\",\"status\":\"ready\",\"arm\":true}");
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

  // 4. ขยับแขนเซอร์โวตาม State Machine (Non-blocking)
  updateArms();
}
