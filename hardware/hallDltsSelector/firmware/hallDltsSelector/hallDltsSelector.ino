// HDS-4 Hall/DLTS selector firmware (Arduino Nano, ATmega328P).
// See ../../README.md for the hardware and the command table.
//
// Each stage contact Pn has two paths: A (Hall, Keithley via the Arduino switch
// box) and B (DLTS, MFIA). Each path is one ULN2803 channel driving two reed
// relays (centre + shield). Rules:
//   - power-up / reset: every channel OPEN;
//   - A and B of one channel are never closed together;
//   - changing a channel is break-before-make (open, wait BREAK_MS, close).

#include <Arduino.h>

const char *FW_VERSION = "1.0";
const char *SERIAL_NO = "0001";        // set per unit

const uint8_t PIN_A[4] = {2, 4, 6, 8};  // P1..P4 Hall path
const uint8_t PIN_B[4] = {3, 5, 7, 9};  // P1..P4 DLTS path
const uint8_t LED_HALL = 10;
const uint8_t LED_DLTS = 11;
const uint8_t LED_OPEN = 12;
const uint8_t PIN_PWR_SENSE = A0;       // coil supply through a 10k/10k divider

const unsigned long BREAK_MS = 10;      // both paths open before closing the new one
const unsigned long SETTLE_MS = 5;      // reed operate + bounce

enum Pos : uint8_t { POS_OPEN = 0, POS_A = 1, POS_B = 2 };
Pos state[4] = {POS_OPEN, POS_OPEN, POS_OPEN, POS_OPEN};

char line[48];
uint8_t lineLen = 0;

void updateLeds() {
  bool anyA = false, anyB = false, anyOpen = false;
  for (uint8_t i = 0; i < 4; i++) {
    anyA |= (state[i] == POS_A);
    anyB |= (state[i] == POS_B);
    anyOpen |= (state[i] == POS_OPEN);
  }
  digitalWrite(LED_HALL, anyA ? HIGH : LOW);
  digitalWrite(LED_DLTS, anyB ? HIGH : LOW);
  digitalWrite(LED_OPEN, anyOpen ? HIGH : LOW);
}

// Move several channels at once, break-before-make for all of them together.
void applyPositions(const Pos target[4]) {
  bool changed = false;
  for (uint8_t i = 0; i < 4; i++) {
    if (target[i] != state[i]) {
      changed = true;
      digitalWrite(PIN_A[i], LOW);
      digitalWrite(PIN_B[i], LOW);
    }
  }
  if (!changed) return;
  delay(BREAK_MS);
  for (uint8_t i = 0; i < 4; i++) {
    if (target[i] == POS_A) digitalWrite(PIN_A[i], HIGH);
    else if (target[i] == POS_B) digitalWrite(PIN_B[i], HIGH);
    state[i] = target[i];
  }
  delay(SETTLE_MS);
  updateLeds();
}

const char *posName(Pos p) {
  return p == POS_A ? "A" : (p == POS_B ? "B" : "OPEN");
}

bool parsePos(const char *s, Pos *out) {
  if (strcmp(s, "A") == 0) { *out = POS_A; return true; }
  if (strcmp(s, "B") == 0) { *out = POS_B; return true; }
  if (strcmp(s, "OPEN") == 0) { *out = POS_OPEN; return true; }
  return false;
}

void replyMode() {
  bool allA = true, allB = true, allOpen = true;
  for (uint8_t i = 0; i < 4; i++) {
    allA &= (state[i] == POS_A);
    allB &= (state[i] == POS_B);
    allOpen &= (state[i] == POS_OPEN);
  }
  Serial.println(allA ? "HALL" : allB ? "DLTS" : allOpen ? "OPEN" : "MIXED");
}

void handle(char *cmd) {
  for (char *p = cmd; *p; p++) *p = toupper(*p);
  while (*cmd == ' ') cmd++;
  char *arg1 = strchr(cmd, ' ');
  if (arg1) { *arg1++ = '\0'; while (*arg1 == ' ') arg1++; }
  char *arg2 = arg1 ? strchr(arg1, ' ') : NULL;
  if (arg2) { *arg2++ = '\0'; while (*arg2 == ' ') arg2++; }

  if (strcmp(cmd, "*IDN?") == 0) {
    Serial.print("HDS4,HallDltsSelector,"); Serial.print(SERIAL_NO);
    Serial.print(","); Serial.println(FW_VERSION);
  } else if (strcmp(cmd, "MODE?") == 0) {
    replyMode();
  } else if (strcmp(cmd, "MODE") == 0) {
    Pos p;
    if (!arg1) { Serial.println("ERR missing mode"); return; }
    if (strcmp(arg1, "HALL") == 0) p = POS_A;
    else if (strcmp(arg1, "DLTS") == 0) p = POS_B;
    else if (strcmp(arg1, "OPEN") == 0) p = POS_OPEN;
    else { Serial.println("ERR mode must be HALL, DLTS or OPEN"); return; }
    Pos target[4] = {p, p, p, p};
    applyPositions(target);
    Serial.println("OK");
  } else if (strcmp(cmd, "CH") == 0) {
    if (!arg1 || !arg2) { Serial.println("ERR usage: CH <1-4> A|B|OPEN"); return; }
    int ch = atoi(arg1);
    Pos p;
    if (ch < 1 || ch > 4 || arg1[1] != '\0') { Serial.println("ERR channel must be 1-4"); return; }
    if (!parsePos(arg2, &p)) { Serial.println("ERR position must be A, B or OPEN"); return; }
    Pos target[4] = {state[0], state[1], state[2], state[3]};
    target[ch - 1] = p;
    applyPositions(target);
    Serial.println("OK");
  } else if (strcmp(cmd, "STATE?") == 0) {
    for (uint8_t i = 0; i < 4; i++) {
      Serial.print("P"); Serial.print(i + 1); Serial.print("="); Serial.print(posName(state[i]));
      Serial.print(i < 3 ? "," : "\n");
    }
  } else if (strcmp(cmd, "PWR?") == 0) {
    // Divider halves the 5 V coil supply: ON above ~2 V at the pin (~410 counts).
    Serial.println(analogRead(PIN_PWR_SENSE) > 410 ? "ON" : "OFF");
  } else if (*cmd == '\0') {
    Serial.println("ERR empty command");
  } else {
    Serial.println("ERR unknown command");
  }
}

void setup() {
  for (uint8_t i = 0; i < 4; i++) {
    digitalWrite(PIN_A[i], LOW); pinMode(PIN_A[i], OUTPUT);
    digitalWrite(PIN_B[i], LOW); pinMode(PIN_B[i], OUTPUT);
  }
  pinMode(LED_HALL, OUTPUT); pinMode(LED_DLTS, OUTPUT); pinMode(LED_OPEN, OUTPUT);
  updateLeds();
  Serial.begin(115200);
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[lineLen] = '\0';
      handle(line);
      lineLen = 0;
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    } else {
      // Over-long line: drop it and report once it ends.
      lineLen = 0;
      while (Serial.available() > 0 && Serial.read() != '\n') {}
      Serial.println("ERR line too long");
    }
  }
}
