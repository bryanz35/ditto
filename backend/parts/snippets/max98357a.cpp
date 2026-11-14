// MAX98357A I2S amplifier: play a 440 Hz square-wave beep for half a second.
// I2S API: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2s.html
#include <Arduino.h>
#include <ESP_I2S.h>
#include "pins.h"

I2SClass i2s;
const uint32_t kRate = 16000;

void setup() {
  Serial.begin(115200);
  i2s.setPins(PIN_AMP1_BCLK, PIN_AMP1_LRC, PIN_AMP1_DIN);  // bclk, ws, dout
  if (!i2s.begin(I2S_MODE_STD, kRate, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("I2S init failed");
  }
  int16_t buf[kRate / 440];  // one period of 440 Hz
  for (size_t i = 0; i < sizeof(buf) / sizeof(buf[0]); i++) {
    buf[i] = i < sizeof(buf) / sizeof(buf[0]) / 2 ? 3000 : -3000;  // low amplitude
  }
  for (uint32_t written = 0; written < kRate / 2; written += sizeof(buf) / sizeof(buf[0])) {
    i2s.write((const uint8_t *)buf, sizeof(buf));
  }
  Serial.println("P2D_READY");
}

void loop() {}
