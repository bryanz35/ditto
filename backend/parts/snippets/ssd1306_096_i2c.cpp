// 0.96" SSD1306 OLED on I2C at 0x3C.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "pins.h"

Adafruit_SSD1306 display(128, 64, &Wire, -1);  // -1: the module has no reset pin

void setup() {
  Serial.begin(115200);
  Wire.begin(PIN_OLED1_SDA, PIN_OLED1_SCL);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 not found at 0x3C");
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Hello");
  display.display();
  Serial.println("P2D_READY");
}

void loop() {}
