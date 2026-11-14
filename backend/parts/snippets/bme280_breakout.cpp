// BME280 (GY-BME280 3.3 V module) on I2C at 0x76: SDO is pulled down on the module.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include "pins.h"

Adafruit_BME280 bme;

void setup() {
  Serial.begin(115200);
  Wire.begin(PIN_ENV1_SDA, PIN_ENV1_SCL);
  if (!bme.begin(0x76, &Wire)) {
    Serial.println("BME280 not found at 0x76");
  }
  Serial.println("P2D_READY");
}

void loop() {
  Serial.printf("temp=%.1fC humidity=%.0f%% pressure=%.0fhPa\n", bme.readTemperature(),
                bme.readHumidity(), bme.readPressure() / 100.0F);
  delay(2000);
}
