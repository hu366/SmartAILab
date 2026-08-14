/* Physics Lab temperature simulator for ESP32-S3 boards.
 * Protocol: newline-delimited JSON at 115200 baud.
 */

#include <Arduino.h>
#include <math.h>

const char *DEVICE_ID = "esp32s3-temperature-sim-01";
const int PROTOCOL_VERSION = 1;
const int DEFAULT_SAMPLE_COUNT = 30;
bool stopRequested = false;
bool pauseRequested = false;

void sendHello() {
  Serial.print("{\"type\":\"hello\",\"device_id\":\"");
  Serial.print(DEVICE_ID);
  Serial.print("\",\"experiment\":\"temperature\",\"firmware\":\"temperature-esp32s3-sim\",\"version\":\"1.0.0\",\"protocol\":");
  Serial.print(PROTOCOL_VERSION);
  Serial.println("}");
}

void sendError(const char *message) {
  Serial.print("{\"type\":\"error\",\"message\":\"");
  Serial.print(message);
  Serial.println("\"}");
}

int requestedSampleCount(const String &line) {
  const String marker = "\"count\":";
  int start = line.indexOf(marker);
  if (start < 0) {
    return DEFAULT_SAMPLE_COUNT;
  }
  start += marker.length();
  int end = line.indexOf(',', start);
  if (end < 0) {
    end = line.indexOf('}', start);
  }
  int count = line.substring(start, end).toInt();
  return constrain(count, 1, 200);
}

void collectTemperature(int sampleCount) {
  stopRequested = false;
  pauseRequested = false;
  for (int index = 0; index < sampleCount; index++) {
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
    float temperature = 23.5f + 1.8f * sinf(index / 4.0f);
    Serial.print("{\"type\":\"sample\",\"index\":");
    Serial.print(index);
    Serial.print(",\"temperature\":");
    Serial.print(temperature, 6);
    Serial.println("}");
    delay(30);
  }
  Serial.println("{\"type\":\"done\"}");
}

void handleCommand(const String &line) {
  if (line.indexOf("\"command\":\"hello\"") >= 0) {
    sendHello();
  } else if (line.indexOf("\"command\":\"collect_temperature\"") >= 0) {
    collectTemperature(requestedSampleCount(line));
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
