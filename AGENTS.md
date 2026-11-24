# Notes for AI assistants and new contributors

Start with **`docs/planning/PROJECT_STATUS.md`**. It has the current state, what is committed, the next steps, and the owner's decisions. This file covers conventions only.

## Rules

- **Do not commit or push.** The repository owner handles git.
- **Do not change behaviour the owner has decided on.** For example, the MFIA `Equivalent Circuit Mode` default stays `0 - 4-Terminal`, even though the bench runs 2-terminal. See PROJECT_STATUS §4.
- **Run the offline test suite after code changes** (`python -m pytest -q -p no:cacheprovider`). Add tests for new behaviour using the fakes in `tests/` (no hardware).
- **Update the matching `docs/reference/<module>.md`** when you change a module.

## Code conventions

- tkinter GUI. Cross-module and GUI state lives in **`dltsConfig.py` module globals**: declared at module level and reset in `init()`, imported as `dltsc`. Tab modules build their widgets against `dltsc.<name>`; do not hide GUI state in classes or closures.
- Instrument drivers are classes in `<maker><Model>_Control.py` files. They import no app config (so the Hall software can share them later), return 0 / -1, and keep the reason for failure in an attribute such as `lastError`.
- **Fits:** lmfit, data errors as weights, report standard errors of every fitted and derived parameter. For non-linear models, also offer a smoothing-spline option with bootstrap errors.
- **Units:** Kelvin in the analysis tabs; °C in the hardware tabs.
- Naming: camelCase for most variables and functions in older modules, snake_case in newer ones. Follow the file you are editing.

## Layout

- `DLTSGUI_MainWindow.py`: entry point.
- Tab modules: `runParamsTab.py`, `liveDataTab.py`, `dataAnalysisTab.py`, `detailedAnalysisTab.py`, `trapConcentrationTab.py`.
- Run engine: `runDlts_Tools.py`.
- Drivers:
  - `zurichInstruments_Control.py` (MFIA)
  - `instecTempStage_Control.py` (mK2000B)
  - `agilent33220A_Control.py` (light source AWG)
  - `hallDltsSelector_Control.py` (planned HDS-4 box)
- Analysis: `impedanceAnalysis_Tools.py`, `dltsPhysics.py`, `excitationTools.py`.
- Folders:
  - `hardware/`: hardware designs (HDS-4 selector);
  - `docs/`: user guides, `docs/reference/` per module, `docs/planning/` plans and status, `docs/hardware_manual/` bench wiring;
  - `tests/`: offline tests; `benchmarks/hardware/`: scripts that need the real instruments.
