// Golden firmware for fixtures/specs/uno_counter.json: counts seconds on the OLED, beeps every 10.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "pins.h"

Adafruit_SSD1306 display(128, 64, &Wire, -1);
unsigned long last = 0;
unsigned long seconds = 0;

void setup() {
  Serial.begin(115200);
  Wire.begin();  // the Uno's I2C is fixed to A4/A5
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  pinMode(PIN_BUZZER1_SIG, OUTPUT);
  Serial.println("P2D_READY");
}

void loop() {
  if (millis() - last < 1000) return;
  last += 1000;
  seconds++;
  display.clearDisplay();
  display.setTextSize(3);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 20);
  display.print(seconds);
  display.display();
  if (seconds % 10 == 0) tone(PIN_BUZZER1_SIG, 2000, 150);
}
