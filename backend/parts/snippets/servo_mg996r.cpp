// MG996R servo: 50 Hz pulses, sweeps between 0 and 180 degrees with ESP32Servo.
// It can draw over 1 A when it starts or stalls: power it from a 5 V supply, not the board's regulator.
#include <Arduino.h>
#include <ESP32Servo.h>
#include "pins.h"

Servo servo;

void setup() {
  Serial.begin(115200);
  servo.setPeriodHertz(50);
  servo.attach(PIN_SERVO1_PWM, 1000, 2000);  // datasheet pulse range in microseconds
  servo.write(90);
  Serial.println("P2D_READY");
}

void loop() {
  servo.write(0);
  delay(1500);
  servo.write(180);
  delay(1500);
}
