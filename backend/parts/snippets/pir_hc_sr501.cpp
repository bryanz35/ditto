// HC-SR501 PIR: OUT goes HIGH (3.3 V) while motion is detected; print each change.
#include <Arduino.h>
#include "pins.h"

int last = -1;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PIR1_OUT, INPUT);
  Serial.println("P2D_READY");
}

void loop() {
  int now = digitalRead(PIN_PIR1_OUT);
  if (now != last) {
    Serial.println(now ? "motion" : "no_motion");
    last = now;
  }
  delay(50);
}
