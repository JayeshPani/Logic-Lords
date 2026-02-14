#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <time.h>

// -----------------------------
// User configuration
// -----------------------------
static const char* WIFI_SSID = "YOUR_WIFI_SSID";
static const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

static const char* FIREBASE_DB_URL = "https://infraguard-8cb5b-default-rtdb.asia-southeast1.firebasedatabase.app";
static const char* FIREBASE_AUTH_TOKEN = ""; // optional, leave empty if rules allow writes
static const char* FIREBASE_PREFIX = "infraguard";
static const char* ASSET_ID = "asset_w12_bridge_0042";
static const char* DEVICE_ID = "esp32-node-01";
static const char* FIRMWARE_VERSION = "1.1.0-adxl335";

static const int DHT_PIN = 15;
static const int DHT_TYPE = DHT11;
static const int X_PIN = 34;
static const int Y_PIN = 35;
static const int Z_PIN = 32;
static const unsigned long PUSH_INTERVAL_MS = 5000;

// ADXL335 defaults at 3.3V.
// Keep board still and tune these if values drift heavily.
static const float ADXL_SENSITIVITY_V_PER_G = 0.330f;
static const float ADXL_ZERO_G_X_V = 1.65f;
static const float ADXL_ZERO_G_Y_V = 1.65f;
static const float ADXL_ZERO_G_Z_V = 1.65f;
static const int ADXL_SAMPLE_COUNT = 10;

// -----------------------------
// Globals
// -----------------------------
DHT dht(DHT_PIN, DHT_TYPE);
unsigned long lastPushAt = 0;

static String iso8601NowUtc() {
  time_t now = time(nullptr);
  if (now < 1700000000) {
    return String("1970-01-01T00:00:00Z");
  }
  struct tm tmNow;
  gmtime_r(&now, &tmNow);
  char buffer[32];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &tmNow);
  return String(buffer);
}

static String buildFirebaseUrl(const String& path) {
  String url = String(FIREBASE_DB_URL);
  if (url.endsWith("/")) {
    url.remove(url.length() - 1);
  }
  url += "/";
  url += path;
  url += ".json";

  if (String(FIREBASE_AUTH_TOKEN).length() > 0) {
    url += "?auth=";
    url += FIREBASE_AUTH_TOKEN;
  }
  return url;
}

static bool firebaseWrite(const String& method, const String& path, const String& body) {
  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  String url = buildFirebaseUrl(path);
  if (!http.begin(client, url)) {
    Serial.println("[Firebase] Failed to initialize HTTPS request.");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  int status = 0;
  if (method == "PUT") {
    status = http.PUT(body);
  } else if (method == "POST") {
    status = http.POST(body);
  } else {
    http.end();
    return false;
  }

  String response = http.getString();
  http.end();

  Serial.printf("[Firebase] %s %s -> %d\n", method.c_str(), path.c_str(), status);
  if (status < 200 || status >= 300) {
    Serial.printf("[Firebase] Response: %s\n", response.c_str());
    return false;
  }
  return true;
}

static void ensureWiFiConnected() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.print("[WiFi] Reconnecting");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startedAt) < 15000) {
    Serial.print(".");
    delay(350);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Reconnected. IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] Reconnect failed.");
  }
}

static float readAdxlAxisG(int pin, float zeroGVoltage) {
  long totalMilliVolts = 0;
  for (int i = 0; i < ADXL_SAMPLE_COUNT; i++) {
    totalMilliVolts += analogReadMilliVolts(pin);
    delay(2);
  }

  const float meanVoltage = (totalMilliVolts / static_cast<float>(ADXL_SAMPLE_COUNT)) / 1000.0f;
  return (meanVoltage - zeroGVoltage) / ADXL_SENSITIVITY_V_PER_G;
}

void setup() {
  Serial.begin(115200);
  delay(300);

  dht.begin();

  analogReadResolution(12);
  analogSetPinAttenuation(X_PIN, ADC_11db);
  analogSetPinAttenuation(Y_PIN, ADC_11db);
  analogSetPinAttenuation(Z_PIN, ADC_11db);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(350);
  }
  Serial.printf("\nConnected. IP: %s\n", WiFi.localIP().toString().c_str());

  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.println("Time sync initialized.");
}

void loop() {
  const unsigned long nowMs = millis();
  if (nowMs - lastPushAt < PUSH_INTERVAL_MS) {
    delay(25);
    return;
  }
  lastPushAt = nowMs;

  ensureWiFiConnected();
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("[Sensors] DHT11 read failed.");
    return;
  }

  const float ax = readAdxlAxisG(X_PIN, ADXL_ZERO_G_X_V);
  const float ay = readAdxlAxisG(Y_PIN, ADXL_ZERO_G_Y_V);
  const float az = readAdxlAxisG(Z_PIN, ADXL_ZERO_G_Z_V);

  String capturedAt = iso8601NowUtc();

  // Keep payload shape aligned with apps/sensor-ingestion-service expectations.
  String payload = "{";
  payload += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  payload += "\"captured_at\":\"" + capturedAt + "\",";
  payload += "\"firmware_version\":\"" + String(FIRMWARE_VERSION) + "\",";
  payload += "\"dht11\":{";
  payload += "\"temperature_c\":" + String(temperature, 2) + ",";
  payload += "\"humidity_pct\":" + String(humidity, 2);
  payload += "},";
  payload += "\"accelerometer\":{";
  payload += "\"x_g\":" + String(ax, 4) + ",";
  payload += "\"y_g\":" + String(ay, 4) + ",";
  payload += "\"z_g\":" + String(az, 4);
  payload += "}";
  payload += "}";

  String latestPath = String(FIREBASE_PREFIX) + "/telemetry/" + String(ASSET_ID) + "/latest";
  String historyPath = String(FIREBASE_PREFIX) + "/telemetry/" + String(ASSET_ID) + "/history";

  bool latestOk = firebaseWrite("PUT", latestPath, payload);
  bool historyOk = firebaseWrite("POST", historyPath, payload);

  if (latestOk && historyOk) {
    Serial.printf(
      "[Telemetry] pushed temp=%.2fC humidity=%.2f%% accel=(%.3f, %.3f, %.3f)g\n",
      temperature,
      humidity,
      ax,
      ay,
      az
    );
  } else {
    Serial.println("[Telemetry] Firebase push failed.");
  }
}
