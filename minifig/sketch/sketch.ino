// UNO Q MCU side: draws the minifig dot on the LED matrix and drives two DC motors.
// The Linux side (python/main.py) calls show_dot() and drive() over the Bridge.
//
// Motor driver: any dual H-bridge with PWM + 2 direction pins per motor
// (TB6612FNG, L298N, ...). Change the pins below to match your wiring.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

const int ROWS = 8;
const int COLS = 13;
const uint8_t DOT_BRIGHTNESS = 7;   // 0-7 with 3 grayscale bits

// PWM pins on the UNO Q are D3, D5, D6, D9, D10, D11
const int LEFT_PWM = D5, LEFT_IN1 = D4, LEFT_IN2 = D7;
const int RIGHT_PWM = D6, RIGHT_IN1 = D8, RIGHT_IN2 = D12;

const unsigned long WATCHDOG_MS = 500;   // stop if Linux side stops talking

Arduino_LED_Matrix matrix;
uint8_t frame[ROWS * COLS];
unsigned long lastCommand = 0;

void setMotor(int pwmPin, int in1, int in2, int speed) {
  speed = constrain(speed, -255, 255);
  digitalWrite(in1, speed > 0);
  digitalWrite(in2, speed < 0);
  analogWrite(pwmPin, abs(speed));
}

void drive(int speed) {
  setMotor(LEFT_PWM, LEFT_IN1, LEFT_IN2, speed);
  setMotor(RIGHT_PWM, RIGHT_IN1, RIGHT_IN2, speed);
  lastCommand = millis();
}

// col/row < 0 clears the display (no minifig seen)
void show_dot(int col, int row) {
  memset(frame, 0, sizeof(frame));
  if (col >= 0 && col < COLS && row >= 0 && row < ROWS) {
    frame[row * COLS + col] = DOT_BRIGHTNESS;
  }
  matrix.draw(frame);
}

void setup() {
  int pins[] = {LEFT_PWM, LEFT_IN1, LEFT_IN2, RIGHT_PWM, RIGHT_IN1, RIGHT_IN2};
  for (int p : pins) pinMode(p, OUTPUT);
  drive(0);

  matrix.begin();
  matrix.setGrayscaleBits(3);
  show_dot(-1, -1);

  Bridge.begin();
  // provide_safe runs the callbacks inside loop(), which is required for
  // functions that touch pins or the matrix
  Bridge.provide_safe("drive", drive);
  Bridge.provide_safe("show_dot", show_dot);
}

void loop() {
  if (millis() - lastCommand > WATCHDOG_MS) {
    drive(0);
  }
  delay(20);
}
