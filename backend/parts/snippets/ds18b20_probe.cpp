// DS18B20 probe on 1-Wire: needs a 4.7k pull-up from DATA to 3V3. Prints the first sensor in C.
#include <Arduino.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "pins.h"

OneWire oneWire(PIN_TEMP1_DATA);
DallasTemperature sensors(&oneWire);

void setup() {
  Serial.begin(115200);
  sensors.begin();
  if (sensors.getDeviceCount() == 0) {
    Serial.println("DS18B20 not found: check wiring and the 4.7k pull-up");
  }
  Serial.println("P2D_READY");
}

void loop() {
  sensors.requestTemperatures();
  float c = sensors.getTempCByIndex(0);
  if (c == DEVICE_DISCONNECTED_C) {
    Serial.println("temp=error");
  } else {
    Serial.printf("temp=%.2fC\n", c);
  }
  delay(1000);
}
