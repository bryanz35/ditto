// HC-SR04P ultrasonic ranger: 10 us TRIG pulse, ECHO high time / 58 = distance in cm.
#include <Arduino.h>
#include "pins.h"

void setup() {
  Serial.begin(115200);
  pinMode(PIN_SONAR1_TRIG, OUTPUT);
  pinMode(PIN_SONAR1_ECHO, INPUT);
  digitalWrite(PIN_SONAR1_TRIG, LOW);
  Serial.println("P2D_READY");
}

void loop() {
  digitalWrite(PIN_SONAR1_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_SONAR1_TRIG, LOW);
  unsigned long us = pulseIn(PIN_SONAR1_ECHO, HIGH, 30000);  // 0 on timeout (nothing in range)
  if (us == 0) {
    Serial.println("distance=out_of_range");
  } else {
    Serial.printf("distance=%.1fcm\n", us / 58.0);
  }
  delay(100);  // datasheet: wait at least 60 ms between pings
}
