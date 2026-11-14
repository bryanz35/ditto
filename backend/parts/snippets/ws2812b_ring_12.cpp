// 12-pixel NeoPixel ring: all pixels dim blue (low brightness keeps the current well under 720 mA).
#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include "pins.h"

Adafruit_NeoPixel ring(12, PIN_RING1_DIN, NEO_GRB + NEO_KHZ800);

void setup() {
  Serial.begin(115200);
  ring.begin();
  ring.setBrightness(40);
  for (int i = 0; i < 12; i++) {
    ring.setPixelColor(i, ring.Color(0, 0, 255));
  }
  ring.show();
  Serial.println("P2D_READY");
}

void loop() {}
