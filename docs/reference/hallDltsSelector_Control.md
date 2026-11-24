# hallDltsSelector_Control

`hallDltsSelector_Control.py` drives the **HDS-4 Hall/DLTS selector**, a planned relay box (revision 3) that switches each stage contact P1–P4 between:
- **A, the Hall path:** the Keithley through the Arduino switch box. This is also the state at boot and with no relay power.
- **B, the DLTS path:** the MFIA.

It is built and coded **the same way as the Hall software's switch box** (`HallProbe_Software/switchBox.py`):
- The Arduino runs the stock **StandardFirmata** sketch.
- This module writes the pins through **pyfirmata2**.
- The code has the same layout: a class, a mode table, `set_pins` / `set_state`, `connect_arduino` / `disconn_arduino`, and a module singleton with wrapper functions.

The one difference: the board handle and the connection flag live on the object, not in an app config module, so the DLTS and the Hall software can both use it.

Hardware, diagrams and build steps: [`hardware/hallDltsSelector/README.md`](../../hardware/hallDltsSelector/README.md). Status: designed, not built, not used by any GUI yet. Tests: `tests/test_hall_dlts_selector.py`, which uses a fake pyfirmata2 board.

## Class constants

| Name | Value | Meaning |
|---|---|---|
| `CONTROL_PINS` | `{'P1': 2, 'P2': 3, 'P3': 4, 'P4': 5}` | Digital pin driving each contact's relay pair (centre + guard). |
| `LED_PINS` | `{'hall': 10, 'dlts': 11}` | Front LEDs. |
| `POWER_SENSE_PIN` | `0` | Analog pin A0, reading the switched coil supply through a 10 kΩ/10 kΩ divider. |
| `POWER_ON_LEVEL` | `0.4` | A0 fraction (of 5 V) above which relay power counts as on. |
| `RELAY_ON_LEVEL` | `1` | The pin level that energizes a relay (DLTS). It needs a HIGH-level-trigger module, because StandardFirmata boots every pin LOW. |
| `POSITION_NAMES` | `{'A': 'Hall', 'B': 'DLTS'}` | |
| `DLTS_CABLING` | dict | What each B jack is cabled to (P1 HCUR, P2 LCUR, P3 LPOT, P4 free). |

## class HallDltsSelector(boardFactory=pyfirmata2.Arduino)

`boardFactory` builds the board from a port name; the tests pass a fake board.

| Method | Returns | Notes |
|---|---|---|
| `configurations(mode)` | `{'P1': 'A', ...}` | `'hall'` → all A, `'dlts'` → all B. Anything else raises `ValueError`. |
| `set_pins(P)` | `(pinsDict, pinMap)` | `pinsDict` = `{pin: level}` for all four contacts. Contacts missing from `P` keep their position. Bad contact or position raises `ValueError`. |
| `set_state(pinsDict, pinMap=None)` | `0` | Writes `board.digital[pin].write(level)` and the LEDs. Raises `RuntimeError` if not connected. |
| `connect_arduino(port)` | `0` / `-1` | Opens the board, starts A0 reporting (`samplingOn(100)`), and writes every contact to Hall. `-1` if no port is given. |
| `disconn_arduino(to_hall=False)` | `0` | `board.exit()` and `board.sp.close()`. The routing is left as it is unless `to_hall=True`. |
| `set_mode(mode)` | `0` | All four contacts. |
| `set_channel(contact, position)` | `0` | Contact `1`–`4` or `'P1'`–`'P4'`; position `'A'` or `'B'`. |
| `get_state()` / `get_mode()` | dict / `'hall'`, `'dlts'`, `'mixed'` | The positions **last written**. Firmata cannot read outputs back. |
| `relay_power()` | `True` / `False` / `None` | From the A0 callback. `None` until the first sample. |
| `require_mode(mode)` | `None` or a message | For a run's setup check (planned). Fails when not connected, in another mode, or (for DLTS) with relay power off. |
| `routing_table()` | `str` | Each contact, its position and what it is connected to. |

Module-level wrappers, like `switchBox.py`: `configurations`, `set_pins`, `set_state`, `connect_arduino`, `disconn_arduino`, `set_mode`, `set_channel`, `get_state`, `get_mode`, `relay_power`, `require_mode`, `routing_table`. They act on the singleton `selector`.

Switch only with the instrument outputs off: the Keithley output and the MFIA signal output.
