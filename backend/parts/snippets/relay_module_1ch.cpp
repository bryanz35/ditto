// 1-channel relay module (active high): toggles the relay every 2 seconds.
#include <Arduino.h>
#include "pins.h"

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELAY1_SIG, OUTPUT);
  digitalWrite(PIN_RELAY1_SIG, LOW);  // relay off
  Serial.println("P2D_READY");
}

void loop() {
  digitalWrite(PIN_RELAY1_SIG, HIGH);
  Serial.println("relay=on");
  delay(2000);
  digitalWrite(PIN_RELAY1_SIG, LOW);
  Serial.println("relay=off");
  delay(2000);
}
