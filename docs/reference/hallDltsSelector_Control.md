# hallDltsSelector_Control

`hallDltsSelector_Control.py` drives the **HDS-4 Hall/DLTS selector**. HDS-4 is a planned relay box that connects each stage contact P1–P4 to the Hall path (A: Keithley through the Arduino switch box), the DLTS path (B: MFIA), or to neither (OPEN). The hardware, the firmware command table and the build steps are in [`hardware/hallDltsSelector/README.md`](../../hardware/hallDltsSelector/README.md).

Status: designed, not built. It is not used by any GUI yet. Tests: `tests/test_hall_dlts_selector.py`, which runs against a simulator of the firmware.

The module imports no app config, so the Hall software can use it too.

## Constants

| Name | Value | Meaning |
|---|---|---|
| `BAUD` | `115200` | Serial speed. |
| `TIMEOUT_S` | `2.0` | Read/write timeout; a silent box raises `SelectorError`. |
| `BOOT_WAIT_S` | `2.0` | Wait after opening the port. Opening resets the Nano, and every channel goes OPEN. |
| `IDN_TAG` | `'HDS4'` | Must appear in the `*IDN?` reply. |
| `CHANNELS`, `MODES`, `POSITIONS` | `P1..P4`; `hall`, `dlts`, `open`; `A`, `B`, `OPEN` | Allowed values. |
| `DLTS_CABLING` | dict | What each B jack is cabled to (P1 HCUR, P2 LCUR, P3 LPOT, P4 free). |

`list_ports()` returns the serial port names Windows reports.

## class selectorDevice(port=None, instrument=None)

`instrument` is an already-open serial-like object; the tests pass a simulator.

| Method | Returns | Notes |
|---|---|---|
| `connect_device(port=None)` | `0` / `-1` | Opens the port and checks `*IDN?`. The reason for a failure is in `lastError`. |
| `disconnect_device(open_all=False)` | `0` / `-1` | Closes the port. The routing is left as it is unless `open_all=True`. |
| `set_mode(mode)` | `None` | `'hall'`, `'dlts'` or `'open'`, applied to all channels with break-before-make. Raises `ValueError` before sending for a bad mode. |
| `set_channel(channel, position)` | `None` | Channel `1`–`4` or `'P1'`–`'P4'`; position `'A'`, `'B'` or `'OPEN'`. |
| `get_mode()` | `'hall'`, `'dlts'`, `'open'` or `'mixed'` | |
| `get_state()` | `{'P1': 'A', ...}` | |
| `relay_power()` | `bool` | Whether the front RELAY POWER switch is on. |
| `require_mode(mode)` | `None` or a message | For a run's setup check (planned): `None` if the box is in `mode` with relay power on. |
| `query(cmd)` | reply line | Raises `SelectorError` on `ERR ...` or no reply. |

Switch only with the instrument outputs off: the Keithley output and the MFIA signal output.
