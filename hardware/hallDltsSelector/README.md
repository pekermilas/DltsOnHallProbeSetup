# HDS-4: Hall/DLTS selector (replacement for the four manual A/B boxes)

Status: **design only, not built** (2026-11-24). Firmware and the Python driver are written and tested against a simulator (`tests/test_hall_dlts_selector.py`), but not on hardware.

## 1. Why

The Hall and DLTS setups share the whole bench except the measuring instrument: the Keithley 2450 (through the Arduino switch box) for Hall, the MFIA for DLTS. Today four manual "Data Transfer Switch" boxes pick the instrument for each stage contact (knob A = Hall, B = DLTS). See `docs/hardware_manual/connections_draft.md`.

HDS-4 does the same job under software control:
- **The software can check and set the routing.** A DLTS run can refuse to start when the sample is routed to the Keithley, and the reverse.
- **A combined Hall + DLTS sequence can run unattended.** This is stage 3 of `docs/planning/hall_dlts_merge_feasibility.md`.
- **There is a safe third state, OPEN.** The sample is disconnected from both instruments, which the manual boxes cannot do. It is the power-up state.

## 2. What it does

Four channels, P1–P4. Each channel connects its **STAGE** jack to either its **HALL** jack or its **DLTS** jack, or to neither.

```
            ┌──────── K_nA (Hall path) ──── HALL Pn ── Arduino switch box Pn ── Keithley 2450
STAGE Pn ───┤
            └──────── K_nB (DLTS path) ──── DLTS Pn ── MFIA (P1 HCUR, P2 LCUR, P3 LPOT, P4 free)
```

- Each path relay switches **both the centre conductor and the shield**. The instrument that is not in use is then fully disconnected, and the Keithley's floating LO/guard is never tied to the MFIA's grounded shields.
  - A per-channel jumper (JS_n) can tie the HALL and DLTS shields together instead, if the old boxes turn out to share shields and the measurements depend on it. Check the old boxes with an ohmmeter (shield A to shield B) before deciding.
- **Break-before-make.** The firmware never closes A and B of the same channel together. Changing a channel opens the closed path, waits 10 ms, then closes the new one.
- **Power-up and reset state: all OPEN.**
- **Hardware off switch.** The front RELAY POWER switch removes coil power: every relay opens whatever the software says. The firmware reads that switch (`PWR?`), so the software can report it.
- **Switch dry.** Change routing only with the instrument outputs off. The Hall software already turns the Keithley output off before switching. DLTS runs must do the same with the MFIA signal output before calling HDS-4. Hot switching ±10 V or 200 V wears reed contacts and puts transients on the sample.

## 3. Electrical design

| Block | Choice | Notes |
|---|---|---|
| Relays | 16 × reed relay, 1 Form A, 5 V coil, e.g. Coto 9001-05-00 (SIP) | Two per path (centre + shield), driven together. Look for: insulation resistance ≥ 10¹² Ω, switching ≥ 200 V DC, standoff ≥ 500 V, a few pF across open contacts, coil about 10 mA at 5 V. **Check the datasheet before ordering.** A 2 Form A part (one per path, 8 total) also works. |
| Coil driver | ULN2803A (8 Darlington channels with built-in clamp diodes) | Each channel drives one path's two coils in parallel (about 20 mA). COM pin to the switched +5 V coil supply. |
| Controller | Arduino Nano (ATmega328P), USB serial | D2–D9 → ULN2803 inputs 1–8 (P1A, P1B, P2A, P2B, P3A, P3B, P4A, P4B). |
| Status LEDs | HALL (green) = some channel on A, DLTS (blue) = some channel on B, OPEN (amber) = some channel open. One LED lit means a clean mode. | D10, D11, D12, each through 1 kΩ. |
| Relay power switch | SPST toggle in the +5 V coil supply (ULN COM and the relay coil +) | Off = all relays open. |
| Power sense | Coil supply → 10 kΩ / 10 kΩ divider → A0 | `PWR?` reads ON above ≈ 2 V. |
| Power | USB 5 V from the PC (or the powered hub) | Worst case 8 coils × 10 mA + Nano ≈ 120 mA. |
| Jacks | 12 × insulated bulkhead BNC (shield isolated from the panel) | Front: STAGE P1–P4. Rear: HALL P1–P4, DLTS P1–P4. Isolation keeps the switched shields apart from each other and from the case. |
| Case | Die-cast aluminium, about 190 × 120 × 55 mm (e.g. Hammond 1590D); check that 12 BNCs fit | Case to earth through a ground lug, connected to **no** signal shield. |
| Wiring | RG-316 or RG-174 coax from each jack to the relay board, as short as possible | Keep the HALL and DLTS runs apart. Leakage and capacitance matter: MFIA DLTS measures pF-level changes, and Hall can run at nA. |

### Pin and channel table

| Arduino pin | ULN2803 input / output | Relays | Path |
|---|---|---|---|
| D2 | 1 / 18 | K1A centre + K1A shield | STAGE P1 → HALL P1 |
| D3 | 2 / 17 | K1B centre + K1B shield | STAGE P1 → DLTS P1 |
| D4 | 3 / 16 | K2A ×2 | P2 → HALL |
| D5 | 4 / 15 | K2B ×2 | P2 → DLTS |
| D6 | 5 / 14 | K3A ×2 | P3 → HALL |
| D7 | 6 / 13 | K3B ×2 | P3 → DLTS |
| D8 | 7 / 12 | K4A ×2 | P4 → HALL |
| D9 | 8 / 11 | K4B ×2 | P4 → DLTS |
| D10, D11, D12 | – | LEDs HALL, DLTS, OPEN | – |
| A0 | – | coil supply sense | – |

ULN2803 pin 9 = GND, pin 10 = COM (switched +5 V). Each relay coil: + to the switched +5 V, − to its ULN output. The ULN2803's internal diodes clamp the coil kick, so no extra diodes are needed unless the relays have none and long leads are used.

## 4. Firmware protocol

Firmware: `firmware/hallDltsSelector/hallDltsSelector.ino`. Serial: **115200 baud, 8N1**. Commands end with `\n` (`\r` is ignored), are case-insensitive, and get one reply line each.

| Command | Reply | Meaning |
|---|---|---|
| `*IDN?` | `HDS4,HallDltsSelector,<serial>,<fw version>` | Identification; the driver checks for `HDS4`. |
| `MODE HALL` / `MODE DLTS` / `MODE OPEN` | `OK` | All four channels to A, to B, or open (break-before-make). |
| `MODE?` | `HALL`, `DLTS`, `OPEN` or `MIXED` | MIXED = channels differ. |
| `CH <1-4> A` / `B` / `OPEN` | `OK` | One channel. |
| `STATE?` | `P1=A,P2=A,P3=OPEN,P4=B` | Per channel. |
| `PWR?` | `ON` / `OFF` | Relay power switch (coil supply present). |
| anything else | `ERR <reason>` | Bad command or argument. Nothing changes. |

`MODE` and `CH` reply `OK` even when relay power is OFF: the commanded state is stored and takes effect when power returns. The driver warns when `PWR?` is `OFF`. Opening the USB port resets the Nano (DTR), which puts every channel back to OPEN. The driver waits 2 s after opening for the boot to finish.

## 5. Python driver

`hallDltsSelector_Control.py` (repo root, next to the other instrument drivers), class `selectorDevice`. It imports no app config, so both the DLTS and the Hall software can use it (feasibility study, stage 1).

```python
import hallDltsSelector_Control as hdsC
sel = hdsC.selectorDevice()
sel.connect_device('COM8')        # checks *IDN? contains HDS4
sel.set_mode('dlts')              # all channels to the MFIA
print(sel.get_state())            # {'P1': 'B', 'P2': 'B', 'P3': 'B', 'P4': 'B'}
sel.disconnect_device()           # leaves the routing as it is; open_all=True opens everything first
```

**Not yet wired into either GUI.** Planned integration:
- a selector panel on the DLTS Input Parameters tab and the Hall Hardware Test tab;
- `check_setup` refusing a DLTS run unless the mode is DLTS (and a Hall run unless HALL);
- the combined sequencer switching between them.

## 6. Build and test

1. **Bench-check the relay board before boxing it**, with an ohmmeter and the Arduino on USB:
   - `MODE HALL`: STAGE Pn to HALL Pn, centre and shield, below 1 Ω. STAGE Pn to DLTS Pn open.
   - `MODE DLTS`: the reverse.
   - `MODE OPEN`: everything open.
   - RELAY POWER off: everything open whatever the mode.
2. **Leakage.** With the Keithley on its 10 nA range, measure from each STAGE jack to every other jack with the box OPEN. It should be at the instrument floor (≥ 10¹² Ω).
3. **Capacitance.** In `MODE DLTS` with the stage disconnected, record the MFIA open reading. Then **redo the MFIA open/short compensation** with HDS-4 in the cable path, because the box adds a few pF.
4. **Swap-in.** Cable HDS-4 in place of the four A/B boxes:
   - STAGE Pn ← stage feedthrough Pn;
   - HALL Pn → Arduino switch box Pn;
   - DLTS P1 → MFIA HCUR, P2 → LCUR, P3 → LPOT, P4 free.

   Then repeat one known Hall measurement and one known DLTS measurement and compare with results taken through the old boxes.

## 7. Parts list

See `BOM.csv`. Prices are not listed. Check part numbers and stock before ordering.
