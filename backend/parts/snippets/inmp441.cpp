// INMP441 I2S microphone (L/R tied to GND = left channel): read samples and print the peak level.
// I2S API: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2s.html
#include <Arduino.h>
#include <ESP_I2S.h>
#include "pins.h"

I2SClass i2s;
int32_t samples[256];

void setup() {
  Serial.begin(115200);
  i2s.setPins(PIN_MIC1_SCK, PIN_MIC1_WS, -1, PIN_MIC1_SD);  // bclk, ws, dout (unused), din
  // The mic sends 24-bit samples in 32-bit slots.
  if (!i2s.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("I2S init failed");
  }
  Serial.println("P2D_READY");
}

void loop() {
  size_t n = i2s.readBytes((char *)samples, sizeof(samples)) / sizeof(samples[0]);
  int32_t peak = 0;
  for (size_t i = 0; i < n; i++) {
    int32_t s = abs(samples[i] >> 8);  // drop the 8 padding bits
    if (s > peak) peak = s;
  }
  Serial.printf("mic_peak=%ld\n", (long)peak);
  delay(200);
}
