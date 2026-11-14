// KY-040 rotary encoder: polls CLK/DT for the position (one step per CLK falling edge) and SW for presses.
#include <Arduino.h>
#include "pins.h"

int position = 0;
int lastClk = HIGH;
int lastSw = HIGH;

void setup() {
  Serial.begin(115200);
  // The module pulls CLK and DT up; SW may have no pull-up, so use the internal one on all three.
  pinMode(PIN_KNOB1_CLK, INPUT_PULLUP);
  pinMode(PIN_KNOB1_DT, INPUT_PULLUP);
  pinMode(PIN_KNOB1_SW, INPUT_PULLUP);
  lastClk = digitalRead(PIN_KNOB1_CLK);
  Serial.println("P2D_READY");
}

void loop() {
  int clk = digitalRead(PIN_KNOB1_CLK);
  if (clk != lastClk && clk == LOW) {
    position += digitalRead(PIN_KNOB1_DT) != clk ? 1 : -1;  // DT still HIGH: clockwise
    Serial.printf("position=%d\n", position);
  }
  lastClk = clk;

  int sw = digitalRead(PIN_KNOB1_SW);
  if (sw != lastSw && sw == LOW) {
    Serial.println("pressed");
  }
  lastSw = sw;
  delay(1);  // crude debounce
}
