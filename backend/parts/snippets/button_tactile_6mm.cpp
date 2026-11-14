// 6 mm tactile button: leg 1 on a GPIO with INPUT_PULLUP, leg 3 on GND, so LOW = pressed.
#include <Arduino.h>
#include "pins.h"

int last = HIGH;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON1_1, INPUT_PULLUP);
  Serial.println("P2D_READY");
}

void loop() {
  int now = digitalRead(PIN_BUTTON1_1);
  if (now != last) {
    Serial.println(now == LOW ? "pressed" : "released");
    last = now;
    delay(20);  // crude debounce
  }
}
