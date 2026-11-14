// Vibration motor module: HIGH runs the motor, PWM (analogWrite) sets the strength.
#include <Arduino.h>
#include "pins.h"

void setup() {
  Serial.begin(115200);
  pinMode(PIN_VIBE1_SIG, OUTPUT);
  Serial.println("P2D_READY");
}

void loop() {
  analogWrite(PIN_VIBE1_SIG, 200);  // buzz for half a second
  delay(500);
  analogWrite(PIN_VIBE1_SIG, 0);
  delay(1500);
}
