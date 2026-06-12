/*
 * ============================================================================
 * Smart Waste Management & Bin Level Detection System
 * File   : arduino_code/smart_bin.ino
 * Board  : ESP32 (NodeMCU-32S / Wemos D1 R32 / any ESP32 variant)
 * 
 * Hardware:
 *   - HC-SR04  Ultrasonic Distance Sensor  (TRIG: GPIO 5 / ECHO: GPIO 18)
 *   - Buzzer   (GPIO 25)
 *   - LED Red  (GPIO 26)   ← Full / Alert
 *   - LED Yellow (GPIO 27) ← Half Full
 *   - LED Green  (GPIO 14) ← OK / Empty
 *   - OLED 128×64 I²C      (SDA: GPIO 21 / SCL: GPIO 22)
 *   - Optional: DHT22 temperature/humidity (GPIO 4)
 * 
 * Libraries required (install via Arduino Library Manager):
 *   - Adafruit_SSD1306    (OLED display)
 *   - Adafruit_GFX        (graphics primitives)
 *   - PubSubClient        (MQTT)
 *   - WiFi.h              (built-in ESP32)
 *   - DHT sensor library  (optional, for DHT22)
 * ============================================================================
 */

// ── Includes ──────────────────────────────────────────────────────────────────
#include <WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>

// ── WiFi & MQTT Configuration ──────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";         // ← Change this
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";     // ← Change this
const char* MQTT_SERVER   = "broker.hivemq.com";      // Free public broker
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT_ID = "ESP32-SmartBin-001";    // Unique per device
const char* BIN_ID        = "BIN-A";                  // Change per bin

// MQTT Topics
const char* TOPIC_TELEMETRY = "smartwaste/BIN-A/telemetry";
const char* TOPIC_ALERT     = "smartwaste/BIN-A/alert";
const char* TOPIC_CMD       = "smartwaste/BIN-A/command";  // Subscribe for remote cmds

// ── Pin Definitions ───────────────────────────────────────────────────────────
#define TRIG_PIN      5
#define ECHO_PIN      18
#define LED_GREEN     14
#define LED_YELLOW    27
#define LED_RED       26
#define BUZZER_PIN    25
#define DHT_PIN       4    // Optional — comment out if no DHT sensor

// ── OLED Configuration ────────────────────────────────────────────────────────
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1   // Share reset with ESP32
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ── Bin Physical Parameters ───────────────────────────────────────────────────
const float BIN_HEIGHT_CM    = 60.0;   // Physical bin depth
const float SENSOR_OFFSET_CM = 2.0;   // Sensor sits 2cm above rim
const float USABLE_HEIGHT_CM = BIN_HEIGHT_CM - SENSOR_OFFSET_CM;  // 58 cm

// Alert threshold
const float ALERT_THRESHOLD_PCT = 80.0;

// ── Timing ────────────────────────────────────────────────────────────────────
const unsigned long READ_INTERVAL_MS   = 3000;   // Read sensor every 3s
const unsigned long PUBLISH_INTERVAL_MS= 5000;   // MQTT publish every 5s
const unsigned long DISPLAY_REFRESH_MS = 1000;   // OLED refresh every 1s
unsigned long lastReadTime    = 0;
unsigned long lastPublishTime = 0;
unsigned long lastDisplayTime = 0;

// ── Global State ──────────────────────────────────────────────────────────────
float   currentDistance  = 0.0;
float   currentFillPct   = 0.0;
String  currentStatus    = "UNKNOWN";
bool    alertActive      = false;
int     alertBeepCount   = 0;
bool    wifiConnected    = false;
bool    mqttConnected    = false;
float   temperature      = 25.0;   // Default if no DHT
float   humidity         = 60.0;

// ── Client Objects ────────────────────────────────────────────────────────────
WiFiClient   espClient;
PubSubClient mqttClient(espClient);

// ═════════════════════════════════════════════════════════════════════════════
// SETUP
// ═════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n\n  Smart Waste Management System — ESP32 Boot");
  Serial.println("  ─────────────────────────────────────────");

  // ── GPIO Init ──────────────────────────────────────────────────────────────
  pinMode(TRIG_PIN,   OUTPUT);
  pinMode(ECHO_PIN,   INPUT);
  pinMode(LED_GREEN,  OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_RED,    OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  // Boot indication — all LEDs on briefly
  setAllLEDs(HIGH);
  delay(500);
  setAllLEDs(LOW);

  // ── OLED Init ──────────────────────────────────────────────────────────────
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("  [OLED] SSD1306 not found. Check wiring.");
    // Continue without display — not critical
  } else {
    showSplashScreen();
  }

  // ── WiFi Connect ───────────────────────────────────────────────────────────
  connectWiFi();

  // ── MQTT Setup ─────────────────────────────────────────────────────────────
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setCallback(onMqttMessage);
  connectMQTT();

  Serial.println("\n  ✅  Setup complete — entering monitoring loop\n");
}

// ═════════════════════════════════════════════════════════════════════════════
// LOOP
// ═════════════════════════════════════════════════════════════════════════════
void loop() {
  unsigned long now = millis();

  // ── MQTT Keepalive ─────────────────────────────────────────────────────────
  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();

  // ── Sensor Read ────────────────────────────────────────────────────────────
  if (now - lastReadTime >= READ_INTERVAL_MS) {
    lastReadTime = now;
    takeSensorReading();
    updateLEDs();
    updateBuzzer();
    printSerialReading();
  }

  // ── MQTT Publish ───────────────────────────────────────────────────────────
  if (now - lastPublishTime >= PUBLISH_INTERVAL_MS) {
    lastPublishTime = now;
    publishTelemetry();
  }

  // ── OLED Update ────────────────────────────────────────────────────────────
  if (now - lastDisplayTime >= DISPLAY_REFRESH_MS) {
    lastDisplayTime = now;
    updateDisplay();
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// SENSOR FUNCTIONS
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Take an HC-SR04 reading and update global state.
 * Takes 5 samples and uses the median for noise reduction.
 */
void takeSensorReading() {
  float samples[5];
  for (int i = 0; i < 5; i++) {
    samples[i] = readHCSR04();
    delay(60);
  }

  // Median of 5 samples
  bubbleSort(samples, 5);
  currentDistance = samples[2];   // Median

  // Convert to fill percentage
  currentFillPct  = distanceToFillPct(currentDistance);
  currentStatus   = classifyBinStatus(currentFillPct);
  alertActive     = (currentFillPct >= ALERT_THRESHOLD_PCT);
}

/**
 * Single HC-SR04 pulse.
 * Returns distance in centimetres.
 */
float readHCSR04() {
  // Clear TRIG
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  // 10µs pulse
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  // Measure echo duration (timeout 30ms)
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);

  // If no echo (object too far or absent)
  if (duration == 0) return BIN_HEIGHT_CM;

  // Speed of sound: 0.0343 cm/µs → distance = duration / 58.0
  float distance_cm = (float)duration / 58.0;
  return constrain(distance_cm, 2.0, BIN_HEIGHT_CM);
}

/**
 * Convert raw distance to fill percentage.
 * fill% = (1 - (distance - offset) / usable_height) × 100
 */
float distanceToFillPct(float distance_cm) {
  float fill = (1.0 - (distance_cm - SENSOR_OFFSET_CM) / USABLE_HEIGHT_CM) * 100.0;
  return constrain(fill, 0.0, 100.0);
}

/**
 * Classify fill percentage into human-readable status.
 */
String classifyBinStatus(float fill_pct) {
  if (fill_pct <= 20.0)  return "EMPTY";
  if (fill_pct <= 40.0)  return "QUARTER FULL";
  if (fill_pct <= 60.0)  return "HALF FULL";
  if (fill_pct <= 80.0)  return "THREE QUARTERS";
  return "FULL";
}

// ═════════════════════════════════════════════════════════════════════════════
// ACTUATOR CONTROL
// ═════════════════════════════════════════════════════════════════════════════
void updateLEDs() {
  // All off first
  setAllLEDs(LOW);

  if (currentFillPct >= 80.0) {
    digitalWrite(LED_RED, HIGH);
  } else if (currentFillPct >= 50.0) {
    digitalWrite(LED_YELLOW, HIGH);
  } else {
    digitalWrite(LED_GREEN, HIGH);
  }
}

void updateBuzzer() {
  if (alertActive) {
    // Three short beeps when full
    for (int i = 0; i < 3; i++) {
      tone(BUZZER_PIN, 2000, 200);
      delay(300);
    }
  } else {
    noTone(BUZZER_PIN);
  }
}

void setAllLEDs(int state) {
  digitalWrite(LED_GREEN,  state);
  digitalWrite(LED_YELLOW, state);
  digitalWrite(LED_RED,    state);
}

// ═════════════════════════════════════════════════════════════════════════════
// DISPLAY
// ═════════════════════════════════════════════════════════════════════════════
void showSplashScreen() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Smart Waste Mgmt");
  display.println("IoT Monitor v1.0");
  display.println("");
  display.println("Initialising...");
  display.display();
  delay(1500);
}

void updateDisplay() {
  display.clearDisplay();

  // ── Row 0: Bin ID + WiFi/MQTT indicators ──────────────────────────────────
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.print(BIN_ID);
  display.setCursor(80, 0);
  display.print(wifiConnected ? "W:OK" : "W:--");
  display.setCursor(104, 0);
  display.print(mqttConnected ? "M:OK" : "M:--");

  // ── Row 1: Divider ─────────────────────────────────────────────────────────
  display.drawLine(0, 9, 127, 9, SSD1306_WHITE);

  // ── Row 2: Distance ────────────────────────────────────────────────────────
  display.setCursor(0, 12);
  display.print("Dist: ");
  display.print(currentDistance, 1);
  display.print(" cm");

  // ── Row 3: Fill % ─────────────────────────────────────────────────────────
  display.setCursor(0, 22);
  display.print("Fill: ");
  display.print(currentFillPct, 1);
  display.print("%");

  // ── Row 4: Progress Bar ────────────────────────────────────────────────────
  int barWidth = (int)(currentFillPct / 100.0 * 118);
  display.drawRect(5, 33, 118, 8, SSD1306_WHITE);
  display.fillRect(5, 33, barWidth, 8, SSD1306_WHITE);

  // ── Row 5: Status ─────────────────────────────────────────────────────────
  display.setCursor(0, 44);
  display.setTextSize(1);
  display.print(currentStatus);

  // ── Row 6: Alert (if active) ──────────────────────────────────────────────
  if (alertActive) {
    display.setTextSize(1);
    display.setCursor(0, 55);
    display.setTextColor(SSD1306_WHITE);
    display.print("!! COLLECT NOW !!");
  }

  display.display();
}

// ═════════════════════════════════════════════════════════════════════════════
// NETWORK FUNCTIONS
// ═════════════════════════════════════════════════════════════════════════════
void connectWiFi() {
  Serial.printf("  [WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.printf("\n  [WiFi] ✅ Connected. IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    wifiConnected = false;
    Serial.println("\n  [WiFi] ❌ Failed. Operating in offline mode.");
  }
}

void connectMQTT() {
  if (!wifiConnected) return;

  int attempts = 0;
  while (!mqttClient.connected() && attempts < 5) {
    Serial.printf("  [MQTT] Connecting to %s...", MQTT_SERVER);
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      mqttConnected = true;
      mqttClient.subscribe(TOPIC_CMD);
      Serial.println(" ✅ Connected");

      // Announce online
      char online_msg[64];
      snprintf(online_msg, sizeof(online_msg),
               "{\"bin_id\":\"%s\",\"status\":\"online\"}", BIN_ID);
      mqttClient.publish("smartwaste/fleet/devices", online_msg);
      return;
    } else {
      Serial.printf(" ❌ Failed (state=%d). Retry %d/5\n", mqttClient.state(), ++attempts);
      delay(2000);
    }
  }
  mqttConnected = false;
}

void publishTelemetry() {
  if (!mqttClient.connected()) return;

  // Build JSON payload (ArduinoJson 6)
  StaticJsonDocument<256> doc;
  doc["bin_id"]          = BIN_ID;
  doc["distance_cm"]     = serialized(String(currentDistance, 2));
  doc["fill_percentage"] = serialized(String(currentFillPct, 1));
  doc["bin_status"]      = currentStatus;
  doc["alert"]           = alertActive;
  doc["temperature_c"]   = serialized(String(temperature, 1));
  doc["humidity_pct"]    = serialized(String(humidity, 1));
  doc["rssi_dbm"]        = WiFi.RSSI();

  char payload[256];
  serializeJson(doc, payload);

  mqttClient.publish(TOPIC_TELEMETRY, payload);
  mqttClient.publish(TOPIC_ALERT, alertActive ? "COLLECT NOW" : "OK");

  Serial.printf("  [MQTT] Published → fill=%.1f%% alert=%s\n",
                currentFillPct, alertActive ? "YES" : "NO");
}

// ── Callback for incoming MQTT commands ──────────────────────────────────────
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  Serial.printf("  [MQTT] Command received on %s : %s\n", topic, msg.c_str());

  // Handle remote commands
  if (msg == "RESET")   {
    // Simulate bin emptied
    Serial.println("  [CMD] Remote reset received — bin marked as emptied.");
    currentFillPct = 2.0;
    currentStatus  = "EMPTY";
    alertActive    = false;
  }
  else if (msg == "STATUS") {
    publishTelemetry();
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// UTILITY
// ═════════════════════════════════════════════════════════════════════════════
void printSerialReading() {
  Serial.printf("  [BIN] Dist=%.1fcm  Fill=%.1f%%  Status=%-14s  Alert=%s\n",
                currentDistance, currentFillPct,
                currentStatus.c_str(), alertActive ? "⚠ YES" : "No");
}

void bubbleSort(float arr[], int n) {
  for (int i = 0; i < n - 1; i++) {
    for (int j = 0; j < n - i - 1; j++) {
      if (arr[j] > arr[j + 1]) {
        float tmp  = arr[j];
        arr[j]     = arr[j + 1];
        arr[j + 1] = tmp;
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// EXPECTED SERIAL MONITOR OUTPUT (115200 baud):
//
//   Smart Waste Management System — ESP32 Boot
//   ─────────────────────────────────────────
//   [WiFi] Connecting to MyWiFi..........
//   [WiFi] ✅ Connected. IP: 192.168.1.105
//   [MQTT] Connecting to broker.hivemq.com... ✅ Connected
//   ✅  Setup complete — entering monitoring loop
//
//   [BIN] Dist=45.3cm  Fill=22.0%  Status=QUARTER FULL   Alert=No
//   [BIN] Dist=32.1cm  Fill=41.2%  Status=HALF FULL      Alert=No
//   [BIN] Dist=12.4cm  Fill=78.6%  Status=THREE QUARTERS Alert=No
//   [BIN] Dist= 4.2cm  Fill=96.5%  Status=FULL           Alert=⚠ YES
// ─────────────────────────────────────────────────────────────────────────────
