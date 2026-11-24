# Hardware manual: connection notes (working draft)

Status: draft, built from the user's bench photos and notes of 2026-11-24. Photos are in [photos/](photos/). Entries marked **(photo)** were read from a photo; **(user)** come from the user's notes; **(spec)** come from the maker's specifications.

**Audience:** both users (people running Hall or DLTS measurements) and builders (people who maintain, rewire or extend the system).

**Procedures:** the software sets the measurement procedure:
- Hall: `HallProbe_Software`.
- DLTS: this repo; see `docs/running_a_dlts_experiment.md`.

The manual describes the hardware those procedures drive. Power-on order, safe bias/current and temperature ranges depend on the sample and device. They belong in each sample's run plan, inside the device limits of §7.

## 1. Equipment

| Item | Identification | Photo |
|---|---|---|
| Cryostat / Hall probe stage | Instec **HCP621G-PMH** (user). 77–850 K (user). Optical window on top. BNC feedthroughs **P1–P4** on the right side (the P1 label is worn to "P"). Five tube fittings on the front edge. | Instec_Stage, Instec_Stage_Ports |
| Temperature controller | Instec **mK2000B** (photo). Rear: SENSOR/HEATER, I/O PORT (D-sub, cabled), USB, ETHERNET. | MFIA_Back (bottom) |
| Water pump / chiller | Instec **C100W** (user; rear label "C100W-…", S/N "KSCH12…", 12 VDC). Rear: CONTROL (mini-DIN), COOLING LED, LOOP 1 MODE switch, FAN NO ICE / ICE switch. | MFIA_Back (right) |
| LN2 pump | Instec **LN2-P4C** (user). | Instec_Pump_Units |
| Vacuum pump | Oil-free electric pump (user; model to be added). | – |
| Impedance analyzer | Zurich Instruments **MFIA** 500 kHz / 5 MHz, S/N DEV32271. Calibration due April 2028 (photo). | MFIA_Front, MFIA_Back |
| Sourcemeter | Keithley **2450** SourceMeter. Front terminals unused; **rear** terminals cabled (the Hall software sets `:ROUT:TERM REAR`). | Sourcemeter_Front, Sourcemeter_Back |
| Hall switch box | Blue box driven by an Arduino with StandardFirmata (COM6). Rear inputs Hf, Lf, Ls, Hs; front outputs P4, P3, P2, P1. | SwitchBox_Back, SwitchBox_Front |
| Hall/DLTS selector | 4 manual A/B "Data Transfer Switch" boxes, stacked top to bottom for P1, P2, P3, P4, each with BNC A / I/O / B. **Knob A = Hall, B = DLTS** (user). | Hall_DLTS_Switches, P1Switch_Back |
| Magnet positioner | Linear stage (stepper and lead screw, GRBL, COM4) plus rotation stage (Arduino, COM3). Two ultrasonic distance sensors, wired to the Arduino in the magnet box; not used by the software yet (user). | Magnet_LinearStage_1/2 |
| Magnet control box | Rocker switches LINEAR (GRBL) and ROTATIONAL (ARDUINO). | Magnet_ControlBox |
| USB hub | 7-port powered hub on top of the Keithley. | USB_Hub |
| Waveform generator (planned, not installed) | Agilent **33220A**, 20 MHz function/arbitrary generator. Drives the LED driver; triggered by the MFIA. Controlled over USB or LAN (VISA) by `agilent33220A_Control.py`. | – |
| 365 nm pulsed light source (planned, not installed) | LED head on the cryostat lid (printed adapter over the stage window), plus an analog current-sink driver in a Hammond 1590B box. Driver panel:<br>• CTRL IN (SMA, 49.9 Ω)<br>• I_MON (SMA)<br>• +9 V input (adapter)<br>• arming switch S1, the hardware interlock<br>• UV ON lamp<br>• range jumper JP1 (1 A or 100 mA full scale)<br>Build and user docs: `BuiltLightSourceFor_O-DLTS_MCTS`. Software guide: `docs/optical_dlts_light_source.md`. | – |
| HDS-4 Hall/DLTS selector (designed, not built) | Relay box replacing the four A/B boxes. Design: `hardware/hallDltsSelector/`. | – |

## 2. Sample signal path (Hall vs DLTS)

Each stage contact has its own A/B selector. **A = Hall** (Keithley through the Arduino switch box); **B = DLTS** (MFIA). Turn all four knobs to the same side before a measurement.

```
Stage P1 ── I/O [selector P1] A ── SwitchBox P1      B ── MFIA Signal Output HCUR
Stage P2 ── I/O [selector P2] A ── SwitchBox P2      B ── MFIA Signal Input LCUR
Stage P3 ── I/O [selector P3] A ── SwitchBox P3      B ── MFIA Signal Input LPOT
Stage P4 ── I/O [selector P4] A ── SwitchBox P4      B ── (free)
```

The MFIA runs in **2-terminal mode** (user): the sample sits between P1 (HCUR) and P2 (LCUR). HPOT is not connected. The LPOT cable to P3 is unused in 2-terminal mode; it is in place for a future 4-terminal setup, which would also need HPOT wired.

## 3. Cable table

| # | From | To | Source |
|---|---|---|---|
| 1 | Keithley 2450 rear Sense HI | Switch box rear Hs | user |
| 2 | Keithley 2450 rear Force HI | Switch box rear Hf | user |
| 3 | Keithley 2450 rear Sense LO | Switch box rear Ls | user |
| 4 | Keithley 2450 rear Force LO | Switch box rear Lf | user |
| 5–8 | Switch box front P1, P2, P3, P4 | Selector P1–P4, port A | user |
| 9–12 | Selector P1–P4, port I/O | Stage feedthrough P1–P4 | user |
| 13 | Selector P1, port B | MFIA front Signal Output HCUR | user, photo |
| 14 | Selector P2, port B | MFIA front Signal Input LCUR | user, photo |
| 15 | Selector P3, port B | MFIA front Signal Input LPOT | user, photo |
| 16 | Selector P4, port B | free | user |
| 17 | MFIA front Aux Output 1 | MFIA front Aux Input 1 | user, photo |
| 18 | MFIA rear Trigger In 1 | cable plugged in, far end loose ("SMU 3 FORCE" label) | user, photo |
| 19 | MFIA rear USB / LAN | PC / network | photo |
| 20 | mK2000B rear I/O PORT | PC, serial COM7 | photo, code |

Port orders as seen from the back:
- Keithley rear, left to right: Sense HI, Force HI, Sense LO, Force LO.
- Switch box rear, left to right: Force HI, Force LO, Sense LO, Sense HI.
- Switch box front, left to right: P4, P3, P2, P1.

### 3a. Light source cables (planned; ports confirmed free in the photos)

| # | From | To | Cable | Purpose |
|---|---|---|---|---|
| 21 | MFIA rear **Trigger Out 2** | 33220A rear **Trig In** (Ext Trig) | BNC–BNC, 50 Ω | Fires one LED pulse per MFIA cycle. The software sets Trigger Out 2 to Threshold 1, the same signal the DAQ triggers on. |
| 22 | 33220A front **Output** | LED driver **CTRL IN** (J1, SMA) | BNC–SMA, 50 Ω coax | LED current: 0–4 V gives 0 to full scale. The software sets the 33220A to `OUTP:LOAD 50` (the driver input is 49.9 Ω). |
| 23 | LED driver **I_MON** (J2, SMA) | MFIA front **Aux Input 2** (1 MΩ) | SMA–BNC coax | Records the real LED current as `AuxInput2`: 1 V/A on the 1 A range, 10 V/A on the 100 mA range. Optional, but needed for the default timing reference. |
| 24 | LED driver **LED output** | LED head on the cryostat lid | Twisted pair, all the way to the head | Keep it away from the MFIA HCUR/LCUR cables (pickup at the LED edges). |
| 25 | 9 V adapter | LED driver **J3 +9 V** | adapter lead | Driver and LED supply. |
| 26 | 33220A rear USB (or LAN) | PC | USB / LAN | VISA control (Light Source panel on the Input Parameters tab). |

Nothing else changes: Aux Out 1 → Aux In 1 (bias) and the selector wiring stay as they are. For optical-fill runs the MFIA holds the bias at the reverse level and the LED provides the fill.

### 3b. Whole DLTS signal chain with the light source

```
 PC ─USB/LAN─ MFIA ─USB/LAN─ PC          PC ─USB/VISA─ 33220A          PC ─serial COM7─ mK2000B ── stage heater/sensor

 MFIA Aux Out 1 ──► MFIA Aux In 1                 (bias pulse, added to the signal output)
 MFIA Trig Out 2 ─► 33220A Trig In
 33220A Output ───► LED driver CTRL IN ──twisted pair──► LED head (cryostat lid, over the window)
 LED driver I_MON ► MFIA Aux In 2
 MFIA HCUR ──► selector P1 (B) ──► stage P1 ┐
 MFIA LCUR ──► selector P2 (B) ──► stage P2 ┘ sample (2-terminal)
 MFIA LPOT ──► selector P3 (B) ──► stage P3   (unused in 2-terminal mode)
```

### 3c. With the HDS-4 selector (when built)

The four A/B boxes are replaced by one box; every other cable stays.

| HDS-4 jack | Connects to |
|---|---|
| STAGE P1–P4 (front) | Stage feedthroughs P1–P4 |
| HALL P1–P4 (rear) | Arduino switch box front P1–P4 |
| DLTS P1 / P2 / P3 / P4 (rear) | MFIA HCUR / LCUR / LPOT / free |
| USB | PC or the powered hub (one more COM port, see §4) |

After the swap, redo the MFIA open/short compensation (the box adds a few pF).

## 4. USB and serial port map (placeholder)

| Hub port / PC port | Cable to | Windows port | Used by |
|---|---|---|---|
| _TBD_ | Keithley 2450 (USB) | VISA `USB0::0x05E6::0x2450::04375166::INSTR` | Hall |
| _TBD_ | Switch box Arduino | COM6 (Hall default) | Hall |
| _TBD_ | Magnet GRBL | COM4 (Hall default) | Hall |
| _TBD_ | Magnet rotation Arduino | COM3 (Hall default) | Hall |
| _TBD_ | mK2000B (I/O port, via USB-serial?) | COM7 | Hall, DLTS |
| _TBD_ | MFIA (USB or LAN) | LabOne data server | DLTS |
| _TBD_ | Agilent 33220A (planned) | VISA | DLTS |
| _TBD_ | HDS-4 selector (designed) | COM _TBD_ | DLTS, Hall (planned) |

## 5. Tubing map (placeholder)

| Stage fitting (front edge, left to right) | Connects to | Medium |
|---|---|---|
| 1 | _TBD_ | _TBD_ (vacuum / LN2 / water / purge) |
| 2 | _TBD_ | _TBD_ |
| 3 | _TBD_ | _TBD_ |
| 4 | _TBD_ | _TBD_ |
| 5 | _TBD_ | _TBD_ |

## 6. Checks against the software

- The Arduino switch box only routes the Keithley's four terminals (as in `switchBox.py`). Moving between Hall and DLTS uses the four manual selectors, so a combined Hall + DLTS run needs an operator prompt or motorised selectors (feasibility study, stage 3).
- The Aux Out 1 → Aux In 1 bias loop is present, as `zurichInstruments_Control` expects.
- The DLTS GUI default is `Equivalent Circuit Mode = 0 - 4-Terminal`, but the bench is wired and run in 2-terminal mode. It must be set to `1 - 2-Terminal` on the Input Parameters tab for each run.

## 7. Device operating limits

These are device limits only. A sample's safe limits are usually tighter.

| Device | Limit | Source |
|---|---|---|
| Instec HCP621G-PMH stage | 77–850 K | user |
| Keithley 2450 | Ranges 20 mV–200 V and 10 nA–1 A; 20 W four-quadrant source/sink. Front-panel markings: 210 V peak HI to LO, 5 V peak between sense and force, 250 V peak LO to chassis. | spec, photo |
| MFIA Signal Output | Ranges ±10 mV, ±100 mV, ±1 V, ±10 V; 100 mA maximum drive | spec |
| MFIA Signal Input | Voltage input 3 V peak (front-panel marking); current input ranges from 1 nA (this unit qualifies, S/N ≥ DEV3200) up to 10 mA | spec, photo |
| MFIA Aux In / Aux Out | ±10 V; Aux In 1 can be added to the signal output (±10 V, DC–2 MHz) | spec |
| LED driver (planned) | CTRL IN 0–4 V into 49.9 Ω gives 0–1 A (1 Ω range) or 0–100 mA (10 Ω range). 1 A DC for seconds only (Q1 ≈ 4 W). Software caps: 0.3 A average, 0.2 A steady. Keep the AWG low level at 0 V. | light source repo |
| LED head | 365 nm UV: eye and skin hazard. Run it only clamped in the lid adapter. Wear OD ≥ 4 glasses at 365 nm when the head is out. Arming switch off before touching the head or sample. | light source user manual |
| Agilent 33220A | Up to 10 Vpp into 50 Ω. The software sets voltage limits (`VOLT:LIM`) to protect the LED driver. | spec, `agilent33220A_Control.py` |
| HDS-4 selector (designed) | Switch dry (instrument outputs off). Reed contacts: check the chosen relay's switching voltage (≥ 200 V needed for the Keithley's full range). | `hardware/hallDltsSelector/README.md` |

Sources:
- [Tektronix 2450 specifications](https://www.tek.com/en/documents/specification/model-2450-interactive-sourcemeter-instrument-specifications)
- [Keithley 2450 brochure](https://xdevs.com/doc/Keithley/2450/2450_brochure_3230_J.pdf)
- [MFIA specifications](https://docs.zhinst.com/mfia_user_manual/specifications.html)
- [MFLI/MFIA specification](https://www.zhinst.com/products/mfli/specifications)

The full per-range tables are in those documents.
