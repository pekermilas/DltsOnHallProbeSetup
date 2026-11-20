# Optical DLTS with the 365 nm light source

The 365 nm LED head (repository `BuiltLightSourceFor_O-DLTS_MCTS`) adds optical excitation to the
DLTS setup: O-DLTS / MCTS (the LED fills the traps instead of an electrical fill pulse), an LED
pulse combined with the electrical fill, or steady illumination during electrical DLTS. An
Agilent 33220A function generator drives the LED driver; the GUI sets it up, switches it on only
while data is being taken, and records the light pulses next to the capacitance.

Operating the head itself (zoom ring, arming switch, safety glasses) is in the light source's
own `docs/UserManual.md`. Read its safety section first: the light is invisible and can damage
eyes and skin.

## Wiring

| From | To | Purpose |
|---|---|---|
| 33220A front **Output** | LED driver **CTRL IN** (BNC to SMA) | LED current: 0–4 V sets 0 to full scale (1 A on the 1 Ω range, 100 mA on the 10 Ω range) |
| MFIA **Trigger Out 2** | 33220A rear **Trig In** | Locks each LED pulse to the MFIA cycle and the DAQ trigger |
| LED driver **I_MON** | MFIA **Aux In 2** | Records the actual LED current (needed for the default timing reference) |
| 33220A **USB** (or LAN) | PC | Control (VISA; `pyvisa` and a VISA library such as NI-VISA or Keysight IO Libraries) |

The existing wiring stays: Aux Out 1 looped to Aux In 1 (the bias, added onto Signal Output 1)
and Trigger Out 1 for the DAQ. The software sets Trigger Out 2 to Threshold 1, the same signal
Trigger Out 1 follows, so the LED and the acquisition share one trigger edge.

The driver's range jumper (JP1) is set by hand. Set **LED Driver Range** on the Light Source
panel to match it, or the current will be off by a factor of 10.

## Excitation methods

| Method | Sample bias | LED | Transients found from |
|---|---|---|---|
| 0 Electrical DLTS | Pulsed fill / reverse bias (unchanged) | Off | `AuxInput1` (bias) |
| 1 Optical Fill (O-DLTS/MCTS) | Held at the reverse level, `Aux Output Offset + Scale` | One pulse per MFIA cycle | `PulseReference` (LED pulse) |
| 2 Electrical + Optical | Pulsed (unchanged) | One pulse per cycle, inside the fill pulse | `AuxInput1` |
| 3 Electrical + Steady Light | Pulsed (unchanged) | Constant current during each acquisition | `AuxInput1` |

For an optical fill the MFIA threshold unit keeps running, so the cycle length is still State
Enable Time + State Disable Time and the DAQ trigger is unchanged; only Aux Output Scale is
pushed as 0 so the bias stays at the reverse level. The values on screen are not changed. The
transient window is the cycle minus the LED pulse width.

Methods are rows of `excitationTools.METHODS`; a new electrical or optical method is a new row
that says whether the bias pulses, what the 33220A outputs, and which channel the analysis uses.

## Light Source panel (Input Parameters tab)

| Parameter | Meaning |
|---|---|
| Excitation Method | One of the methods above |
| LED Driver Range | Must match the driver's JP1 jumper |
| LED Pulse Current (mA) | Pulse height; converted to the CTRL IN voltage (4 V at full scale) |
| LED Pulse Width (s) | Light pulse length |
| LED Pulse Delay (s) | From the MFIA Trigger Out 2 rising edge to the LED turning on |
| LED Steady Current (mA) | Method 3 only |
| Optical Timing Reference | `0 - I_MON (Aux In 2)` (default) or `1 - Commanded Timing` |
| Commanded Timing Offset (s) | Commanded Timing only: fixed lag between the trigger and the acquisition's t = 0 |
| Record I_MON | Record Aux In 2 as `AuxInput2` (always on with the I_MON reference) |
| AWG VISA Resource | The 33220A; **Refresh VISA List** fills the list |

Buttons: **Connect + Get Params** (checks the instrument is a 33220A, switches its output off,
sets the 50 Ω load), **Apply + Push Params** (checks the settings and pushes the MFIA bias for
the method), **Disconnect**, and **LED OFF** (output off immediately).

Apply and Run DLTS refuse settings that are unsafe or inconsistent:

- pulse current above the driver range;
- LED delay + width not ending before the next MFIA cycle;
- average current (pulse current × duty cycle) above 300 mA, the driver MOSFET's thermal limit;
- steady current above 200 mA;
- method 2 with an LED pulse longer than the electrical fill (State Disable Time);
- no 33220A connected for a method that uses the LED.

## What happens during a run

For each temperature step, right before the acquisition, the 33220A is configured (pulse:
`FUNC PULS`, burst of one pulse per external trigger, delay; steady: `FUNC DC`), its own output
limits (`VOLT:LIM`) are set to the requested level, and the output is switched on. Right after
the acquisition the output is switched off, also when the acquisition fails. The output is also
switched off on pause, at the end of the run, when the GUI closes and on the console-close
backstops. The driver's arming switch is the hardware interlock; the software cannot fire the
LED with it off.

`runParams.txt` is written at the start of the run (and again at the end) and includes the Light
Source parameters, so the live analysis knows the method and timing while the run is going.

## Data files

| Channel | When | Content |
|---|---|---|
| `AuxInput2` | I_MON recorded | Aux In 2, V (I_MON: 1 V/A on the 1 Ω range, 10 V/A on the 10 Ω range) |
| `PulseReference` | Optical Fill only | 0/1 marker, 1 while the LED is on |

With the I_MON reference, `PulseReference` is I_MON divided by the level the set current gives,
so 1 means the LED ran at the set current. If the LED never fired (arming switch off, cable
missing) it stays near 0 and the analysis reports that no pulses were found. With Commanded
Timing it is rebuilt from the delay, width and cycle length on the file's time axis.

Every analysis uses `PulseReference` when a file has it, else `AuxInput1`. Both are higher
during the fill, so the same falling-edge search finds the transient starts (Qualitative
Analysis, Detailed Analysis, and the Automated / Quick Analysis clustering). Electrical runs are
analyzed exactly as before.

Detailed Analysis reads no electrical fill-pulse information (V_fill, C_fill) from an
optical-fill run; C0 is the tail mean. Trap Concentration shows a warning with every result
from such data: its Nₜ model assumes an electrical fill pulse and is only a relative measure for
optical filling.

## Commissioning

1. Bench-test the driver with its 3 Ω dummy load (light source build guide, section A) before
   the LED head is connected.
2. Connect the 33220A in the GUI, set a low current (10 mA on the 100 mA range), Optical Fill,
   and run a single temperature step at room temperature with the arming switch on.
3. Watch I_MON on a scope (or open the step file): one clean pulse per MFIA cycle, at the set
   delay after the trigger, of the expected height, and 0 V between pulses.
4. Calibrate **Commanded Timing Offset** if you will use Commanded Timing: compare the rising
   edges of `AuxInput2` and of the commanded marker (offset 0) in the same file and enter the
   difference.
5. The LED pulse must last a few samples to show in I_MON: one sample is about 18.7 µs at the
   default 60 kSa/s Data Transfer Rate, and the impedance filter bandwidth smooths it further.
   For shorter pulses use Commanded Timing.
6. Find the saturating fill: raise the current, then the width, until the DLTS peak stops
   growing (light source manual, troubleshooting).
