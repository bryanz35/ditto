// 28BYJ-48 stepper on a ULN2003 board: half-steps the four coils, one turn each way.
// 4096 half-steps per output turn; 2 ms per step (500 Hz) stays under the motor's 600 Hz pull-in rate.
#include <Arduino.h>
#include "pins.h"

const int COILS[4] = {PIN_STEPPER1_IN1, PIN_STEPPER1_IN2, PIN_STEPPER1_IN3, PIN_STEPPER1_IN4};
// Coils on in each half-step, IN1 as the high bit: 1, 1+2, 2, 2+3, 3, 3+4, 4, 4+1.
const uint8_t HALF_STEPS[8] = {0b1000, 0b1100, 0b0100, 0b0110, 0b0010, 0b0011, 0b0001, 0b1001};
const int STEPS_PER_TURN = 4096;
int phase = 0;

void step(int dir) {
  phase = (phase + dir + 8) % 8;
  for (int i = 0; i < 4; i++) digitalWrite(COILS[i], (HALF_STEPS[phase] >> (3 - i)) & 1);
  delay(2);
}

void release() {
  for (int pin : COILS) digitalWrite(pin, LOW);  // coils off between moves: no current, no heat
}

void setup() {
  Serial.begin(115200);
  for (int pin : COILS) pinMode(pin, OUTPUT);
  release();
  Serial.println("P2D_READY");
}

void loop() {
  for (int i = 0; i < STEPS_PER_TURN; i++) step(1);
  release();
  delay(1000);
  for (int i = 0; i < STEPS_PER_TURN; i++) step(-1);
  release();
  delay(1000);
}
