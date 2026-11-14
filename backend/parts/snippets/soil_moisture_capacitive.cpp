// Capacitive soil moisture sensor: raw 12-bit reading, higher = drier. Calibrate dry/wet per soil.
#include <Arduino.h>
#include "pins.h"

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  Serial.println("P2D_READY");
}

void loop() {
  Serial.printf("soil_raw=%d\n", analogRead(PIN_SOIL1_AOUT));
  delay(1000);
}
