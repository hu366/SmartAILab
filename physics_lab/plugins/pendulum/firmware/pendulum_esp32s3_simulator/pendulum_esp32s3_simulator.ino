/* Physics Lab pendulum simulator for ESP32-S3 boards.
 * Protocol: newline-delimited JSON at 115200 baud.
 */

#include <Arduino.h>
#include <math.h>

const char *DEVICE_ID = "esp32s3-pendulum-sim-01";
const int SAMPLE_COUNT = 101;
bool stopRequested = false;
bool pauseRequested = false;

void sendHello() {
  Serial.print("{\"type\":\"hello\",\"device_id\":\"");
  Serial.print(DEVICE_ID);
  Serial.println("\",\"experiment\":\"pendulum\",\"firmware\":\"pendulum-esp32s3-sim\",\"version\":\"1.0.0\",\"protocol\":1}");
}

void sendError(const char *message) {
  Serial.print("{\"type\":\"error\",\"message\":\"");
  Serial.print(message);
  Serial.println("\"}");
}

void collectPeriods() {
  stopRequested = false;
  pauseRequested = false;
  for (int index = 0; index < SAMPLE_COUNT; index++) {
    if (Serial.available() > 0) {
      String command = Serial.readStringUntil('\n');
      command.trim();
      if (command.indexOf("\"command\":\"stop\"") >= 0) {
        stopRequested = true;
      } else if (command.indexOf("\"command\":\"pause\"") >= 0) {
        pauseRequested = true;
      } else if (command.indexOf("\"command\":\"resume\"") >= 0) {
        pauseRequested = false;
      }
    }
    if (stopRequested) {
      Serial.println("{\"type\":\"stopped\"}");
      return;
    }
    if (pauseRequested) {
      delay(10);
      index--;
      continue;
    }
    float period = 2.0f + 0.18f * sinf(index / 8.0f);
    Serial.print("{\"type\":\"sample\",\"index\":");
    Serial.print(index);
    Serial.print(",\"period\":");
    Serial.print(period, 6);
    Serial.println("}");
    delay(18);
  }
  Serial.println("{\"type\":\"done\"}");
}

void handleCommand(const String &line) {
  if (line.indexOf("\"command\":\"hello\"") >= 0) {
    sendHello();
  } else if (line.indexOf("\"command\":\"collect_periods\"") >= 0) {
    collectPeriods();
  } else if (line.indexOf("\"command\":\"stop\"") >= 0) {
    stopRequested = true;
  } else if (line.indexOf("\"command\":\"pause\"") >= 0) {
    pauseRequested = true;
  } else if (line.indexOf("\"command\":\"resume\"") >= 0) {
    pauseRequested = false;
  } else {
    sendError("unsupported command");
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
}

void loop() {
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      handleCommand(line);
    }
  }
}
