# Feasibility study: merging the DLTS and Hall probe software

Status: **study only, nothing implemented.** Written 2026-11-24.
Scope: `DltsOnHallProbeSetup` (this repo), `HallProbe_Software`, and `InstrumentControlLibraries`, all under `Documents\GitHub`.
Method: read-only survey of all three repos. File and line references are as of the date above.

---

## 1. Summary

**A merge is feasible, but a big-bang merge into one codebase is not recommended.** The two programs are similar in style, but their measurement code barely overlaps. What they really share is the bench:
- the Instec stage and mK2000B controller;
- the sample;
- the switch box;
- the PC.

**Recommended route: three stages, each useful on its own.** Each stage can be stopped after.

| Stage | What | Size | Risk | Needed for |
|---|---|---|---|---|
| 0 | Fix the existing driver bugs listed in §6; add a minimal Hall test suite | small | low | everything after it |
| 1 | **Shared instrument package** used by both apps (mK2000B first), plus an **instrument lock** so only one app holds a port | medium | low–medium | safe coexistence; the planned new DLTS methods |
| 2 | **One launcher window hosting both apps** as tab groups in one process, with a shared device registry | medium–large | medium | sequential Hall then DLTS on one sample without restarting |
| 3 | **Combined measurement sequencer** (Hall and DLTS at each temperature of one sweep) | large | medium–high | automatic n(T), μ(T) next to DLTS spectra and Nt |

**The deciding question is hardware, not software.** Can the switch box connect the sample contacts to the MFIA as well as the Keithley? This is open (see §3.3 and §8).
- **If it cannot:** stage 3 needs a hardware change to the switch box, or a manual recabling step between measurement types.
- **Either way:** stages 1–2 are worth doing.

---

## 2. What each program is today

| | DLTS (`DltsOnHallProbeSetup`) | Hall (`HallProbe_Software`) |
|---|---|---|
| Entry point | `DLTSGUI_MainWindow.py` | `hallProbeGUI.py` |
| Size (project .py, excl. legacy) | ≈16 000 lines; analysis is ~60 % | ≈9 000 lines |
| GUI | tkinter, `ttk.Notebook`; 5 tabs | tkinter, `ttk.Notebook`; 5 tabs |
| Global state | `dltsConfig` (`dltsc`). Module globals; `init()` exists but the GUI never calls it | `hallProbeConfig` (`hpc`). Module globals, no `init()` |
| Run model | one daemon run thread, flags in `dltsc`; UI updated via `root.after` | one daemon run thread, flags in `hpc`; UI via `logQueue` and `liveQueue` pumps |
| Instruments | MFIA (zhinst, dev32271); mK2000B (serial COM7); Agilent 33220A (pyvisa, new and not yet attached) | Keithley 2450 (pyvisa USB); mK2000B (serial COM7); switch box Arduino (pyfirmata2, COM6); magnet GRBL (COM4) and rotation Arduino (COM3) |
| Data | `root\MMDDYY\HHMMSS\`, one HDF5 per setpoint, `format_version=1`, `run_params` JSON attribute, `runParams.txt` | `root\MMDDYY\HHMMSS\`, per-round HDF5 merged into `<Prefix>_run.h5`, `format_version=1`, `run_params` JSON attribute |
| Tests | 18 files, ~194 tests (offline fakes) | **none** |
| Docs | `docs/` and `docs/reference/*.md`, PDF build | `docs/reference/*.md`, PDF build, KNOWN_ISSUES.md |
| Launcher | `.lnk` → `.vbs` (repo search, single instance) → `.bat` (conda) | same design (`HallProbe.vbs` was modelled on DLTSGUI.vbs) |
| Python | 3.13 (conda); `requirements.txt` | 3.13 (conda); no requirements file (pyvisa, pyserial, pyfirmata2, numpy, lmfit, matplotlib, PIL, h5py) |
| Naming | snake_case methods (`go_to_temp`) | camelCase methods (`goToTemp`) |
| UI scaling | fixed pixel sizes | `uiScale` (scales fonts, images and padding with the window) |

The two apps already share a lot of design:
- same launcher design;
- same folder layout;
- same HDF5 conventions;
- same one-run-thread model;
- same lock and timeout code in the mK2000B driver. The Hall driver was ported from the DLTS one, and the DLTS one was originally copied from the Hall one.

That makes them good candidates for sharing code.

### 2.1 `InstrumentControlLibraries`

This is a loose folder of scripts: no package, no tests, no README.
- Its `ziDevice` (14 KB) and `agi33220A` are older and different from the DLTS copies (`zurichInstruments_Control.py` 36 KB, `agilent33220A_Control.py` `awgDevice`).
- It has no mK2000B driver and no Keithley 2450 driver.
- Neither app imports it.

It could become the shared package's home (§5, stage 1), but its current contents are not a base to build on.

---

## 3. Overlap and conflicts

### 3.1 Shared hardware

| Hardware | DLTS | Hall | Conflict today |
|---|---|---|---|
| Instec stage and mK2000B (COM7) | yes | yes | **Yes.** Windows serial ports are exclusive. Whichever app connects first holds COM7 for its whole session. The other app fails, silently in DLTS: `connect_temp_controller` prints and returns 0. |
| Switch box (COM6) | not used | yes | Relays stay where Hall left them, because disconnecting does not reset the pins. DLTS cannot see or set them. |
| Sample contacts | MFIA (wiring TBD) | Keithley via switch box | See §3.3. |
| MFIA | yes | no | LabOne allows several clients, so no port conflict. |
| Keithley 2450 | no | yes | – |
| Magnet | no | yes | The magnet position may matter for DLTS (field at the sample). Nothing records it in DLTS files. |
| 33220A and LED | yes (planned) | no | – |

### 3.2 Behavioural conflicts around the shared temperature controller

| Behaviour | DLTS | Hall |
|---|---|---|
| Room temperature | `Troom` from the parameters | `hpc.roomTemprValue` = **32.4 °C** default |
| Room ramp | `roomRamp` (default 10 °C/min) | `ROOM_RAMP_C_PER_MIN = 10` |
| On close | ramps to room, waits, sends STOP only if arrived; "Close now" leaves it ramping | ramps to room, disconnects **without** STOP |
| Hold after close | no | yes: an I-V temperature hold can be left running on purpose (HP-10) |
| Disconnect | STOP by default | STOP by default |
| Abort source | driver's own `_aborted` only | `_aborted` **or** `hpc.run_abortRequested`, with interruptible waits (0.2 s) |

If both apps run against the same controller, one app's disconnect (STOP) or close (room ramp) can cancel the other's setpoint. A shared driver plus an instrument lock (stage 1) removes this whole class of problem.

### 3.3 The switch box: the key unknown

> **Answered 2026-11-24** (bench photos, `docs/hardware_manual/connections_draft.md`): it is option 1 in a structured form. Four manual A/B selector boxes sit between the stage feedthroughs and the instruments, one per contact. A goes to the Arduino switch box (Keithley path). B goes to the MFIA: P1→HCUR, P2→LCUR, P3→LPOT, P4 free. A combined Hall + DLTS run therefore needs either an operator prompt to turn four knobs, or a later upgrade to relay- or Arduino-driven A/B selectors (which would make stage 3 fully automatic).

What the Hall code says (`switchBox.py`, `docs/reference/switchBox.md`):
- The software routes **only the Keithley's four terminals** (Force HI/LO, Sense HI/LO) to sample contacts P1–P4. It uses 12 digital pins (three per terminal) through StandardFirmata (pyfirmata2).
- Configurations 1–20 are resistivity and Hall permutations.
- There is **no "all open" state** and **no route to the MFIA or a BNC**.
- The switch box firmware is not in the repo (`ArduinoCodes/` holds only the magnet sketch). The meaning of each pin code (P1=000, P2=010, P3=100, P4=101) is not documented.

The user confirmed the switch box is part of the system between the sample and the instruments. The software does not show how the MFIA reaches the sample. Possibilities:
1. the MFIA is cabled to the sample through a separate path, or by swapping cables, so no switching is possible;
2. the switch box hardware has unused channels or relays that could route the MFIA;
3. the MFIA goes through the Keithley terminal lines (unlikely; it would need the Keithley disconnected or in high-Z).

**This decides stage 3:**
- With (2), a combined Hall + DLTS sequence can be fully automatic.
- With (1), the best possible is "pause and prompt the operator to recable".
- With (3), the Keithley output-off state and lead capacitance need careful study before DLTS through those lines can be trusted.

### 3.4 Software conflicts if both apps run in one process

| Item | Detail | Fix |
|---|---|---|
| Module name clash | both repos have a top-level `postprocessingTab.py` (DLTS's is empty) | delete DLTS's empty one, or move each app into a package |
| Flat imports | both use `import X` from the repo root; two roots on `sys.path` is fragile | put each app in a package (`dlts/`, `hall/`) or keep separate processes |
| Two `tk.Tk()` roots | each entry point creates its own root, and each config module holds `root` and `tabControl` | change each entry point to build into a given parent notebook. Tab constructors already go through `dltsc.tabControl` / `hpc.tabControl`, so this is mostly at the entry point |
| Close handlers | each has its own `on_closing`, atexit and console handlers that ramp the stage | one shared shutdown coordinator that ramps once |
| Two run flags | `dltsc.run_busy` and `hpc.run_busy` | a shared "bench busy" flag in the registry so only one run uses the bench |
| Log and message areas | different (`dltsc.log_to_textbox`; `hpc.logQueue`) | keep separate per app; no need to unify |
| UI scaling | Hall scales, DLTS is fixed | leave as is; cosmetic |
| Dependencies | DLTS: torch, zhinst, scikit-learn, etc. Hall: pyfirmata2 | one conda environment works; add `pyfirmata2` to the DLTS requirements or a combined requirements file |
| Global config names | no clash (`dltsc` / `hpc` are different modules) | – |

---

## 4. Options considered

| Option | Description | Verdict |
|---|---|---|
| A. Status quo plus coordination | Keep two programs. Add an OS-level instrument lock and fix the drivers in both copies. | Cheapest. Fixes the dangerous part (COM7 contention), but the two copies of each driver keep drifting. Can be done as part of stage 1. |
| B. Shared instrument package | One package of drivers imported by both apps (mK2000B, later Keithley, switch box, magnet, MFIA, 33220A) plus the lock. Apps stay separate. | **Recommended first real step (stage 1).** Small blast radius; fixes the drift; prepares the planned new DLTS methods. |
| C. Suite: one window, both apps | A launcher builds one Tk root, a top-level notebook "DLTS" / "Hall" (or merged tab lists), and a device registry that hands the same mK2000B object to both. | **Feasible (stage 2).** Little change to the tab code; mostly entry points, shutdown and the registry. Worth it if you move between the two measurements on one sample often. |
| D. Full merge into one codebase | One config module, one run engine, one data format, unified naming. | **Not recommended.** Largest effort, highest regression risk (Hall has no tests), little gain over C plus E. |
| E. Combined sequencer | A run engine above both apps: at each temperature, run a Hall round, switch the routing, run a DLTS acquisition. | Valuable scientifically. Needs C (or D) **and** the switch box answer in §3.3. Stage 3. |

---

## 5. Recommended plan in detail

### Stage 0: groundwork (no merge yet)

- Fix the driver bugs in §6 (in both repos, or once in stage 1).
- **Hall test suite.** Fakes for pyvisa (Keithley), pyserial (mK2000B, GRBL) and pyfirmata2 (switch box), following the DLTS patterns (`tests/conftest.py`, `FakeSerial`, `FakeInstrument`). Cover:
  - `run_Experiment` for each type with fakes;
  - `measure_tempRound`;
  - h5 write and merge;
  - `analysisTools` against `testData/hallData_Astrid`.
  - Without this, every later stage is a blind refactor of Hall.
- Add `requirements.txt` to Hall.
- Delete DLTS's empty `postprocessingTab.py`.
- Document the switch box firmware and pin meaning: put the sketch in the repo.

### Stage 1: shared instrument package and instrument lock

**Where:** a new repo or folder, for example `labInstruments/` as an installable package (`pip install -e`). This avoids copy-paste. `InstrumentControlLibraries` could be restructured into this, or kept as an archive.

**Contents, in order:**

1. **`instec_mk2000b`**: one driver. The API (from the line-by-line comparison) needs:
   - `mK2000B(port, timeout=2.0, retries=1)`, with no import of any app's config module.
   - `connect()`, `disconnect(stop_control=True, lock_timeout=5.0)`. Use Hall's safe version: close the port in `finally` even if STOP fails.
   - `start_ramp(T, ramp, lock_timeout=None)`, `stop_control()`, `read_temp(retries)`, `abort()`, `reset_abort()`, `is_connected`.
   - `go_to_temp(Tf, ramp, delay, should_abort=None)` and `go_to_room_temp(Tr, ramp, tolerance, extra_wait_s, should_abort=None)`. Both honour their arguments and wait in steps that can be interrupted. Hall passes `lambda: hpc.run_abortRequested`; DLTS passes `lambda: dltsc.run_abortRequested`.
   - Pure helpers: `expected_del_t`, `build_temp_grid` (static), `measure_proxy_temp`.
   - Callbacks: `on_state_change` (so Hall can keep `hpc.tControllerOnOff` updated) and `log` (replaces `print`).
   - DLTS parameter layer (`params`, `configure`, `load_params`, `set_param_value`, `tempGrid`, `tRamp`, `tStableDelay`, `Troom`, `roomRamp`) as a thin subclass or adapter in the DLTS repo.
   - Compatibility: camelCase aliases or Hall's existing module wrappers (`tpT.connect_tController` etc.), so Hall's ~15 call sites need no edits at first.
   - Call sites to switch over:
     - DLTS: `runParamsTab.connect_and_get_params` / `apply_and_push_params`; `runDlts_Tools.init_experiment`, `_read_stage_temp`, `_run_single_step`, `return_to_room_temp`; `DLTSGUI_MainWindow._send_room_ramp`, `_finish_close`, `_wait_for_room_temp`; `benchmarks/hardware/*`; `examples/standalone_*`.
     - Hall: `experimentTab`, `hallProbeGUI.on_closing`, `hardwareTab`, `ivTab`, `ivTools`.
2. **Instrument lock** (`bench_lock`): a lock file per instrument (for example `%PROGRAMDATA%\OzturkLab\locks\COM7.lock`) holding the app name, PID and time.
   - Taken on connect, released on disconnect. A stale lock (dead PID) is cleared automatically.
   - The connect error then says "*Temperature controller is in use by HallProbe (PID 1234) since 14:02*" instead of a generic serial error.
   - This also covers the switch box (COM6) and, if wanted, the Keithley.
3. **Port selection in DLTS**: replace the hard-coded COM7 with a port setting, as Hall already has.
4. **Later, as needed:** Keithley 2450 (`ivTools.IVTools` minus run logic), switch box, magnet, MFIA `ziDevice`, 33220A `awgDevice`.
   - Move a driver only when a second user of it appears. For DLTS-only instruments that second user is the planned new DLTS methods.

**Shared conventions for the package:**
- Drivers never import app config.
- Drivers report state through return values and callbacks.
- Every driver has a fake for tests.
- Units are explicit in names.

Risk: low–medium. Behaviour changes are limited to the bug fixes. Both test suites (Hall's from stage 0) guard the switch.

### Stage 2: one window hosting both apps

- A new entry point (for example `LabSuite.py` with its own `.lnk`/`.vbs`/`.bat` of the same design) creates one `tk.Tk`, a top-level notebook with "DLTS" and "Hall" pages, and a nested notebook in each page.
- Each app's entry point is split into `build_into(parentNotebook)` and its own `__main__`, so both apps can still run on their own.
- A **device registry** (in the shared package) holds one connected object per instrument. Both apps call `registry.get('mK2000B')` instead of creating their own, so there is one owner per port.
- A **shutdown coordinator** runs once: LED off → Keithley output off → room ramp → wait or close-now → disconnect. This replaces the two `on_closing`, atexit and console handlers. Hall's "keep the hold after exit" option becomes a choice in this coordinator.
- A **bench-busy flag** in the registry: starting a run in one app is refused while the other is running, with a clear message.
- The apps need packaging (`dlts/`, `hall/` folders, or a `sys.path` arrangement that handles the `postprocessingTab` clash).

Size: medium–large. Most of it is entry points and shutdown. Tab code is untouched except where tabs create devices.

### Stage 3: combined sequencer

- A third run engine: for each temperature in the grid, go to the temperature once, then:
  1. Hall round(s), including magnet moves;
  2. switch routing to the MFIA (or prompt the operator if routing is manual);
  3. DLTS acquisition, including the LED if used;
  4. switch back.
- **Data:** one run folder holding both kinds of files (the folder and HDF5 conventions already match), plus a top-level `runParams.txt` that records the sequence.
- **Analysis gain:** Trap Concentration needs N_D(T). It could take n(T) from the Hall result in the same folder instead of a separately entered value.
- **Prerequisites:**
  - the switch box answer (§3.3);
  - the magnet's effect on DLTS (move it to "Back" before DLTS steps; record its position in the DLTS file);
  - settling time after switching (relay transients on a high-impedance sample).

Size: large. Risk: medium–high, mostly in hardware behaviour, not code.

---

## 6. Existing issues found during the survey (not fixed)

These are worth fixing whether or not any merge happens.

**DLTS (`instecTempStage_Control.py` and callers)**

> **Update 2026-11-24:** items 1–5 and 7 are fixed (see `docs/reference/instecTempStage_Control.md`, Notes; tests in `tests/test_temperature_driver.py`). DLTS now has a Serial Port box, so the stage 1 "port selection" step is done. Items 6 and 8 remain.

1. `go_to_temp` overwrites its `ramp` and `delayTime` arguments with `self.tRamp` / `self.tStableDelay` (lines 257–258).
   - Harmless in the current run engine, which passes those same values.
   - Surprising for any other caller (examples, future methods).
2. `disconnect_temp_controller`: if writing STOP raises, `ser.close()` is skipped and the port stays open (lines 164–173; the `finally` only releases the lock). Hall fixed the same bug in its copy.
3. COM7 is hard-coded; there is no port setting in the GUI.
4. `runParamsTab.connect_and_get_params('temperature')` creates a new `mK2000B` without closing the old one. A reconnect in the same session can fail on "port in use".
5. A failed connect prints and returns 0. The failure only shows later, in `check_setup`.
6. `dltsc.init()` is never called by the GUI, so some flags start as `None` instead of `False` (for example `run_busy`).
7. `query()` calls `Serial.query`, which does not exist (dead code).
8. Stale docs:
   - `data_formats.md` says `runParams.txt` is written only at finish; it is now written at start and at finish.
   - `docs/README.md` gives an old test count.

**Hall**
1. `measure_tempRound` ignores the -1 (aborted) return of `goToTemp`.
2. HP-1: magnet move with `linear_alt=False` sends a bare `G00` that does not move (open).
3. HP-6: magnet move code duplicated in `magnetTab.py` and `magnetTools.py`.
4. `switchBox.disconn_arduino` leaves the relays wherever they were.
5. No tests, no requirements file.
6. Stale docs: `switchBox.md` and `other_scripts.md` still list HP-2 as open; KNOWN_ISSUES.md says it was fixed on 2026-11-16.

---

## 7. Effort and risk summary

Sizes are relative:
- **small:** a focused session;
- **medium:** a few sessions;
- **large:** a multi-week effort including hardware testing.

| Stage | Size | Main risk | Mitigation |
|---|---|---|---|
| 0 | small–medium (the Hall tests are most of it) | none to the running system | – |
| 1 (mK2000B and lock only) | medium | a temperature regression on the shared stage | both test suites; a bench test of ramp, abort, room return and close in each app |
| 1 (more drivers) | medium each | per instrument | move only when a second user exists |
| 2 | medium–large | shutdown ordering; two apps' globals in one process | the shutdown coordinator gets its own tests; keep both standalone entry points working |
| 3 | large | switch box routing; measurement interference (magnet, relays, LED) | hardware commissioning first; manual-prompt fallback |

---

## 8. Open questions for the user

1. **Switch box:** how does the MFIA reach the sample today? Can the switch box hardware route the MFIA (spare relays or channels)? Where is its firmware?
2. Is the magnet ever near the sample during DLTS? Does its position need recording?
3. **Usage:** how often is the same sample measured by both Hall and DLTS in one cool-down? This decides whether stage 2 or 3 is worth it.
4. **Room temperature:** should both apps agree on one value (Hall's default is 32.4 °C)?
5. Who maintains the Hall software? Can it adopt snake_case for new shared code, with camelCase aliases kept?
6. Shared package location: restructure `InstrumentControlLibraries`, or start a new repo?

---

## 9. Source of findings

The survey ran on 2026-11-24 over:
- `HallProbe_Software`: all modules, `docs/reference`, KNOWN_ISSUES.md;
- `DltsOnHallProbeSetup`: all modules, `docs`, `tests`;
- `InstrumentControlLibraries` and `CryoStage_Software`.

Key claims were checked against the code, in particular `instecTempStage_Control.py` lines 156–179 and 251–258, and the duplicate `postprocessingTab.py` in both repos.

At the time, this repo had uncommitted light source work (excitationTools, agilent33220A_Control and related). This study does not depend on it.
