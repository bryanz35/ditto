// Plant monitor (golden firmware for fixtures/specs/plant_monitor.json): soil moisture, temperature and humidity on an OLED,
// beeps when the soil is dry.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "pins.h"

const unsigned long READ_INTERVAL_MS = 10UL * 60UL * 1000UL;
const int DRY_THRESHOLD = 2600;  // raw 12-bit ADC; higher = drier. Calibrate in dry and wet soil.

Adafruit_BME280 bme;
Adafruit_SSD1306 display(128, 64, &Wire, -1);
unsigned long lastRead = 0;

void beep(int times) {
  for (int i = 0; i < times; i++) {
    tone(PIN_BUZZER1_SIG, 2000, 150);
    delay(300);
  }
}

void readAndShow() {
  int soil = analogRead(PIN_SOIL1_AOUT);
  float temp = bme.readTemperature();
  float humidity = bme.readHumidity();
  bool dry = soil > DRY_THRESHOLD;

  display.clearDisplay();
  display.setCursor(0, 0);
  display.printf("Soil: %d %s\n", soil, dry ? "DRY" : "ok");
  display.printf("Temp: %.1f C\n", temp);
  display.printf("Hum:  %.0f %%\n", humidity);
  display.display();
  Serial.printf("soil=%d temp=%.1f humidity=%.0f\n", soil, temp, humidity);

  if (dry) {
    beep(3);
  }
}

void setup() {
  Serial.begin(115200);
  Wire.begin(PIN_ENV1_SDA, PIN_ENV1_SCL);  // env1 and oled1 share this I2C bus
  analogReadResolution(12);
  pinMode(PIN_BUZZER1_SIG, OUTPUT);
  if (!bme.begin(0x76, &Wire)) {
    Serial.println("BME280 not found at 0x76");
  }
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 not found at 0x3C");
  }
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  readAndShow();
  lastRead = millis();
  Serial.println("P2D_READY");
}

void loop() {
  if (millis() - lastRead >= READ_INTERVAL_MS) {
    lastRead = millis();
    readAndShow();
  }
}
