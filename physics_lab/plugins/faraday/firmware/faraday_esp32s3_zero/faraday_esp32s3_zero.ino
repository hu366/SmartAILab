/*
 * SmartAILab Faraday magneto-optical sampling firmware.
 *
 * Based on the SmartAILab dual photodiode reference firmware:
 *   - left ADC: GPIO 7
 *   - right ADC: GPIO 8
 *   - 20 ADC reads per 0.1 s average
 *   - 10 short averages per formal 1 s output
 *
 * The serial protocol is physics-lab-jsonl v1.
 */

#include <Arduino.h>

const int PIN_RIGHT = 8;
const int PIN_LEFT = 7;
const int SAMPLES_PER_READ = 20;
const int READ_INTERVAL_MS = 100;
const int AVERAGE_COUNT = 10;
const float ADC_MAX_VALUE = 4095.0f;
const unsigned long BAUD_RATE = 115200;

enum Mode { IDLE, DEBUG_MODE, FORMAL_MODE };
Mode mode = IDLE;
bool paused = false;
unsigned long lastReadTime = 0;
float sumR = 0.0f;
float sumL = 0.0f;
int readCount = 0;
int outputIndex = 0;
int outputTarget = 0;

String jsonCommand(const String& json) {
  int key = json.indexOf("\"command\"");
  if (key < 0) {
    return "";
  }
  int colon = json.indexOf(':', key);
  int firstQuote = json.indexOf('"', colon + 1);
  int secondQuote = json.indexOf('"', firstQuote + 1);
  if (colon < 0 || firstQuote < 0 || secondQuote < 0) {
    return "";
  }
  return json.substring(firstQuote + 1, secondQuote);
}

int jsonInteger(const String& json, const char* key, int fallback) {
  String field = String("\"") + key + "\"";
  int position = json.indexOf(field);
  if (position < 0) {
    return fallback;
  }
  int colon = json.indexOf(':', position + field.length());
  if (colon < 0) {
    return fallback;
  }
  int end = json.indexOf(',', colon + 1);
  if (end < 0) {
    end = json.indexOf('}', colon + 1);
  }
  if (end < 0) {
    end = json.length();
  }
  String value = json.substring(colon + 1, end);
  value.trim();
  return value.toInt();
}

void resetAccumulator() {
  sumR = 0.0f;
  sumL = 0.0f;
  readCount = 0;
}

void sendError(const char* message) {
  Serial.print("{\"type\":\"error\",\"message\":\"");
  Serial.print(message);
  Serial.println("\"}");
}

void sendDone(const char* completedMode) {
  Serial.print("{\"type\":\"done\",\"mode\":\"");
  Serial.print(completedMode);
  Serial.println("\"}");
}

bool sendSample(float left, float right, const char* sampleMode) {
  if (right <= 0.0f || left <= 0.0f || right > ADC_MAX_VALUE || left > ADC_MAX_VALUE) {
    // Report the event so the host can preserve its provenance. It is not a
    // valid sample and must not advance the formal valid-sample target.
    Serial.print("{\"type\":\"sample\",\"mode\":\"");
    Serial.print(sampleMode);
    Serial.print("\",\"index\":");
    Serial.print(outputIndex);
    Serial.print(",\"raw_left\":");
    Serial.print(left, 3);
    Serial.print(",\"raw_right\":");
    Serial.print(right, 3);
    Serial.println(",\"r\":0,\"valid\":false,\"reason\":\"optical_out_of_range\"}");
    resetAccumulator();
    return false;
  }
  Serial.print("{\"type\":\"sample\",\"mode\":\"");
  Serial.print(sampleMode);
  Serial.print("\",\"index\":");
  Serial.print(outputIndex++);
  Serial.print(",\"raw_left\":");
  Serial.print(left, 3);
  Serial.print(",\"raw_right\":");
  Serial.print(right, 3);
  Serial.print(",\"r\":");
  Serial.print(left / right, 6);
  Serial.print(",\"valid\":true");
  Serial.println("}");
  return true;
}

void sendHello() {
  Serial.println("{\"type\":\"hello\",\"device_id\":\"faraday-esp32s3-zero-01\",\"experiment\":\"faraday\",\"firmware\":\"faraday-esp32s3-zero\",\"version\":\"1.0.0\",\"protocol\":1}");
}

void handleCommand() {
  if (Serial.available() == 0) {
    return;
  }
  String json = Serial.readStringUntil('\n');
  json.trim();
  if (json.length() == 0) {
    sendError("invalid_json_command");
    return;
  }
  String command = jsonCommand(json);
  if (command == "hello") {
    sendHello();
  } else if (command == "debug_start") {
    resetAccumulator();
    outputIndex = 0;
    mode = DEBUG_MODE;
    paused = false;
  } else if (command == "debug_stop") {
    mode = IDLE;
    paused = false;
    resetAccumulator();
    sendDone("debug");
  } else if (command == "collect") {
    outputTarget = max(1, jsonInteger(json, "count", 1));
    resetAccumulator();
    outputIndex = 0;
    mode = FORMAL_MODE;
    paused = false;
  } else if (command == "pause") {
    paused = true;
  } else if (command == "resume") {
    paused = false;
  } else if (command == "stop") {
    mode = IDLE;
    paused = false;
    resetAccumulator();
    sendDone("stopped");
  } else {
    sendError("unknown_command");
  }
}

void collectAndOutput() {
  if (mode == IDLE || paused || millis() - lastReadTime < READ_INTERVAL_MS) {
    return;
  }
  lastReadTime = millis();
  float currentRight = 0.0f;
  float currentLeft = 0.0f;
  for (int index = 0; index < SAMPLES_PER_READ; index++) {
    currentRight += analogRead(PIN_RIGHT);
    currentLeft += analogRead(PIN_LEFT);
    delayMicroseconds(100);
  }
  float averageRight = currentRight / SAMPLES_PER_READ;
  float averageLeft = currentLeft / SAMPLES_PER_READ;
  if (mode == DEBUG_MODE) {
    sendSample(averageLeft, averageRight, "debug");
    return;
  }
  sumR += averageRight;
  sumL += averageLeft;
  readCount++;
  if (readCount < AVERAGE_COUNT) {
    return;
  }
  bool emitted = sendSample(sumL / AVERAGE_COUNT, sumR / AVERAGE_COUNT, "formal");
  resetAccumulator();
  if (emitted && outputIndex >= outputTarget) {
    mode = IDLE;
    sendDone("formal");
  }
}

void setup() {
  Serial.begin(BAUD_RATE);
  Serial.setTimeout(50);
  analogSetAttenuation(ADC_11db);
  delay(1000);
}

void loop() {
  handleCommand();
  collectAndOutput();
}
