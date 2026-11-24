# Project status and handoff

Last updated: **2026-11-24**. Purpose: let anyone pick up the work on another PC, in another environment, or with another AI assistant, without the original chat history. Read this first, then `AGENTS.md` (repo root) for conventions.

Branch: `DLTSwithGUI_ModularTABS` (main branch: `main`). Remote: GitHub `pekermilas/DltsOnHallProbeSetup`. **The owner commits and pushes; assistants must not commit or push.**

## 1. The system in one paragraph

DLTS (deep-level transient spectroscopy) GUI in Python/tkinter (`DLTSGUI_MainWindow.py`).
- **Instruments:**
  - a Zurich Instruments MFIA (DEV32271) measures capacitance transients and makes the bias pulse;
  - an Instec mK2000B steps the temperature of an Instec HCP621G-PMH Hall-probe stage (77–850 K);
  - a home-built 365 nm LED source driven by an Agilent 33220A adds optical excitation (O-DLTS/MCTS). This is written in software but **not yet installed on the bench**.
- **Shared bench:** a separate program, `HallProbe_Software` (sibling repo), does Hall/resistivity measurements with a Keithley 2450 on the same stage. The two setups share everything except the MFIA vs the Keithley. Four manual A/B boxes pick the instrument per stage contact (A = Hall, B = DLTS).

## 2. Work streams

| Stream | State | Where |
|---|---|---|
| Launcher (.bat/.vbs/.lnk that find the repo) | Done, committed | `DLTSGUI.*` |
| Qualitative plot fixes and live auto-update | Done, committed | `liveDataTab.py` |
| O-DLTS light source integration (all excitation methods; I_MON or commanded timing reference) | Code done and tested offline (fake VISA). **Not on hardware.** Committed. | `excitationTools.py`, `agilent33220A_Control.py`, `docs/optical_dlts_light_source.md`, `tests/test_light_source.py` |
| Temperature driver bug fixes (go_to_temp args, safe disconnect, connect errors, Serial Port box, abort) | Done, tests pass. Committed (`167f46a`). Not yet checked on hardware. | `instecTempStage_Control.py`, `runParamsTab.py`, `tests/test_temperature_driver.py` |
| Hall + DLTS merge | **Study only, do not implement** until the owner says so | `docs/planning/hall_dlts_merge_feasibility.md` |
| Hardware manual | **v1.0 written** (2026-11-24): Part A for users, Part B for builders. Status marks Installed / Planned / Designed / TBD. Included in `docs/README.md` and in the PDF (`docs/DLTS_Software_Documentation.pdf`, rebuilt). | `docs/hardware_manual/HardwareManual.md` (working notes: `connections_draft.md`; photos: `photos/`) |
| HDS-4 Hall/DLTS relay selector | Designed (README, BOM, firmware, Python driver with tests). **Not built**, not in any GUI. | `hardware/hallDltsSelector/`, `hallDltsSelector_Control.py`, `tests/test_hall_dlts_selector.py` |

Not committed at the time of writing (the owner will commit):
- `docs/hardware_manual/` (draft and 15 photos)
- `hardware/hallDltsSelector/`
- `hallDltsSelector_Control.py`
- `tests/test_hall_dlts_selector.py`
- this file, `AGENTS.md`, `CLAUDE.md`
- edits to `docs/planning/hall_dlts_merge_feasibility.md`

## 3. Next steps (in the owner's order)

1. **Hardware manual follow-ups:** fill the TBD items:
   - USB hub port map (§B4) and tubing map (§B5);
   - vacuum pump model;
   - whether the A/B selector boxes switch the shields;
   - the switch box and magnet-box firmware.

   When the light source is installed, change its marks from Planned to Installed and add photos.
2. **Light source commissioning** (owner, at the bench):
   - wire cables 21–26 of the draft;
   - check that the 33220A idles at 0 V in triggered burst;
   - bench-test into a 3 Ω dummy load;
   - calibrate the Commanded Timing Offset against I_MON.
3. **Bench check of the temperature fixes:** connect on COM7, do one short ramp, close the program.
4. **Later, only when asked:**
   - build HDS-4 and wire it into the GUIs;
   - feasibility stages 1–3 (shared driver package, a single window for both apps, the combined sequencer);
   - an optical-fill Nt model in Trap Concentration.

## 4. Decisions the owner has made (do not re-open)

- **MFIA:** the bench runs in **2-terminal** mode (sample between P1/HCUR and P2/LCUR; HPOT unconnected; the LPOT→P3 cable is unused). The GUI default stays `0 - 4-Terminal`. **Do not change the default.**
- **Selector knobs:** A = Hall, B = DLTS. The MFIA Trigger In 1 cable has a loose far end. The ultrasonic sensors on the magnet stage are wired to the magnet-box Arduino; leave them out for now.
- **Equipment names:** Instec C100W water pump, Instec LN2-P4C LN2 pump. The vacuum pump is oil-free; its model is still to be given.
- **Hardware manual audience:** users and builders. Procedures are those of the software (Hall or DLTS). Power-on order and sample limits depend on the sample and device. The manual gives device limits only.
- **Light source:**
  - Pulse source: the Agilent 33220A.
  - Modes: all modes are supported (optical fill, combined electrical + optical, steady light), and the design stays extensible for future electrical/optical methods.
  - Timing reference: I_MON on Aux In 2 is the default; commanded timing is selectable.
- **Merge:** no big-bang merge. Staged plan in the feasibility study.

## 5. Standing preferences for code (also in `AGENTS.md`)

- **Shared state in `dltsConfig.py`.** All cross-module/GUI state lives there as module globals: declared at module level and reset in `dltsConfig.init()`. Tabs build their UI against `dltsc.<name>`. Do not introduce classes or module-local state for GUI state, even when porting code written in another style. Instrument drivers are classes and import no app config.
- **Fits carry errors.** Every fit uses lmfit with per-point uncertainties as weights and reports the standard errors of all fitted and derived parameters. For models beyond linear, also offer a smoothing-spline alternative with bootstrap errors, selectable in the UI. Do not keep an unweighted fit just to match old numbers.
- **Temperature units:** Kelvin in the analysis tabs (Quick, Detailed, Trap Concentration); °C in the hardware tabs (Input Parameters, Live Tools, room-temperature dialog) "for now".
- **Trap concentration:**
  - Detailed Analysis has the Dr. Kayi v3.1 Et/σ corrections and a simple uncorrected Nt.
  - The Trap Concentration tab has the Nt physics (`dltsPhysics.py`) and reads traps from the last Detailed or Quick run.
  - `tests/test_kayi_v31_compat.py` compares the code with v3.1.
- **Hardware facts:** never guess a connection from a photo; list the uncertain ones back to the owner.

## 6. How to run and test

- **Python:** 3.13 (Anaconda). On the lab PCs it is `C:\Users\<user>\anaconda3\python.exe`. Packages: `pip install -r requirements.txt`.
- **Tests:** all offline, no hardware needed. About 300 tests; all pass as of 2026-11-24.

  ```
  python -m pytest -q -p no:cacheprovider
  ```

- **GUI:** `DLTSGUI.lnk` / `DLTSGUI.vbs`, or `python DLTSGUI_MainWindow.py`.
- **Git** may not be on PATH on the lab PC; GitHub Desktop's bundled git works.

## 7. Key documents

| Topic | File |
|---|---|
| Docs index | `docs/README.md` |
| Module reference | `docs/reference/*.md` |
| Running a DLTS experiment | `docs/running_a_dlts_experiment.md` |
| Light source software guide | `docs/optical_dlts_light_source.md` |
| Merge feasibility study | `docs/planning/hall_dlts_merge_feasibility.md` |
| Hardware connection draft | `docs/hardware_manual/connections_draft.md` |
| HDS-4 selector design | `hardware/hallDltsSelector/README.md` |
| Sibling repos | `HallProbe_Software` (Hall GUI), `BuiltLightSourceFor_O-DLTS_MCTS` (LED head and driver build/user docs), `InstrumentControlLibraries` (old loose drivers, unused) |
