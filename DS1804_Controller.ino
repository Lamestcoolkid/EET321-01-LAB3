/*
 * DS1804_Controller.ino
 * EET321 Lab 3 - SCR Characterization
 *
 * Controls a DS1804-010 digital potentiometer (10kΩ, 100 positions)
 * via its 3-wire interface (CS, U/D, INC).
 *
 * Pin Assignments:
 *   Pin 4 -> DS1804 CS  (active LOW)
 *   Pin 3 -> DS1804 U/D (HIGH = Up, LOW = Down)
 *   Pin 2 -> DS1804 INC (falling edge increments/decrements)
 *
 * Serial Commands (9600 baud):
 *   "MAX"     -> Set wiper to position 99 (full 10kΩ)
 *   "MIN"     -> Set wiper to position 0  (minimum)
 *   "SET:nn"  -> Set wiper to absolute position nn (0-99)
 *   "DOWN"    -> Step wiper down by 1
 *   "UP"      -> Step wiper up by 1
 *   "POS?"    -> Query current position
 *   "READY?"  -> Handshake ping
 *
 * DS1804 Timing (from datasheet):
 *   t_CSS (CS setup)  >= 50ns  -- met by digitalWrite overhead
 *   t_WH  (INC high)  >= 50ns
 *   t_WL  (INC low)   >= 50ns
 *   Using 1ms pulses for reliable operation at any baud rate.
 */

// ── Pin definitions ──────────────────────────────────────────────────────────
const int PIN_CS  = 4;
const int PIN_UD  = 3;
const int PIN_INC = 2;

// ── State ────────────────────────────────────────────────────────────────────
int currentPos = 0;  // Unknown at startup; will be zeroed on init

// ── DS1804 low-level helpers ─────────────────────────────────────────────────

void ds1804_pulse_inc() {
  // INC falls → wiper moves in U/D direction
  digitalWrite(PIN_INC, LOW);
  delayMicroseconds(100);   // t_WL
  digitalWrite(PIN_INC, HIGH);
  delayMicroseconds(100);   // t_WH
}

void ds1804_step(int steps, bool goUp) {
  // Select direction
  digitalWrite(PIN_UD, goUp ? HIGH : LOW);
  delayMicroseconds(50);

  // Assert CS (active LOW)
  digitalWrite(PIN_CS, LOW);
  delayMicroseconds(50);

  for (int i = 0; i < steps; i++) {
    ds1804_pulse_inc();
  }

  // De-assert CS to latch new position into NV memory
  // (keep CS low ≥ 50ns before raising; already satisfied)
  digitalWrite(PIN_CS, HIGH);
  delayMicroseconds(50);
}

// Drive wiper all the way down then up to a known position
void ds1804_init_to_max() {
  // Step down 100 times to guarantee we're at position 0
  ds1804_step(100, false);
  // Step up 99 times to reach position 99
  ds1804_step(99, true);
  currentPos = 99;
}

void ds1804_goto(int target) {
  target = constrain(target, 0, 99);
  if (target == currentPos) return;

  int delta = target - currentPos;
  bool goUp = (delta > 0);
  ds1804_step(abs(delta), goUp);
  currentPos = target;
}

// ── Arduino setup / loop ─────────────────────────────────────────────────────

void setup() {
  Serial.begin(9600);

  pinMode(PIN_CS,  OUTPUT);
  pinMode(PIN_UD,  OUTPUT);
  pinMode(PIN_INC, OUTPUT);

  // Safe idle state
  digitalWrite(PIN_CS,  HIGH);
  digitalWrite(PIN_INC, HIGH);
  digitalWrite(PIN_UD,  HIGH);

  // Drive to max (position 99 = 10kΩ) at startup
  ds1804_init_to_max();

  Serial.println("READY");
}

void loop() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  if (cmd == "READY?") {
    Serial.println("READY");

  } else if (cmd == "POS?") {
    Serial.println(currentPos);

  } else if (cmd == "MAX") {
    ds1804_goto(99);
    Serial.println("OK:99");

  } else if (cmd == "MIN") {
    ds1804_goto(0);
    Serial.println("OK:0");

  } else if (cmd == "DOWN") {
    ds1804_goto(currentPos - 1);
    Serial.println("OK:" + String(currentPos));

  } else if (cmd == "UP") {
    ds1804_goto(currentPos + 1);
    Serial.println("OK:" + String(currentPos));

  } else if (cmd.startsWith("SET:")) {
    int target = cmd.substring(4).toInt();
    ds1804_goto(target);
    Serial.println("OK:" + String(currentPos));

  } else {
    Serial.println("ERR:UNKNOWN_CMD");
  }
}
