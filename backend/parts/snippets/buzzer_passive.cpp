// Passive buzzer: needs a square wave (tone), not a steady HIGH.
#include <Arduino.h>
#include "pins.h"

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER1_SIG, OUTPUT);
  tone(PIN_BUZZER1_SIG, 2000, 200);  // 2 kHz for 200 ms
  Serial.println("P2D_READY");
}

void loop() {}
