// 30 mm arcade button: NO on a GPIO with INPUT_PULLUP, COM on GND, so LOW = pressed.
#include <Arduino.h>
#include "pins.h"

int last = HIGH;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_ARCADE1_NO, INPUT_PULLUP);
  Serial.println("P2D_READY");
}

void loop() {
  int now = digitalRead(PIN_ARCADE1_NO);
  if (now != last) {
    Serial.println(now == LOW ? "pressed" : "released");
    last = now;
    delay(20);  // crude debounce
  }
}
