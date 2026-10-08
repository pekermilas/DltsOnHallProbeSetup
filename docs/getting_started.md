# Getting started

## What the software does

The DLTS control GUI runs a deep-level transient spectroscopy temperature scan on
two instruments and analyzes the result:

- **Zurich Instruments MFIA** impedance analyzer (device `dev32271`). It applies the
  fill / reverse-bias pulse train through its Aux output, measures the sample's
  impedance, and averages many triggered repetitions per temperature.
- **Instec mK2000B** temperature controller (serial port `COM7`). It ramps the stage
  to each setpoint and holds it.

For each setpoint the software ramps, waits until the stage is stable, acquires one
averaged record and writes it as one file (`p25p0.h5`, `p30p0.h5`, ...). The analysis
tabs turn those files into averaged capacitance transients, DLTS rate-window spectra
and an Arrhenius plot (activation energy, capture cross-section, trap density).

## Requirements

- Windows PC with the instruments connected. This PC: Python 3.13.9 (Anaconda at
  `C:\Users\spencer\anaconda3`).
- **Zurich Instruments LabOne** installed and its data server running. The MFIA is
  found by `zhinst.core.ziDiscovery` (on this PC: data server `192.168.176.30:8004`).
- **Instec controller** on a USB-serial port. The code expects `COM7`
  (`instecTempStage_Control.mK2000B(port='COM7')`); change it there if Windows assigns
  another port.
- Python packages: `pip install -r requirements.txt` from the repository folder.
  Tested versions are in that file (zhinst-core 26.01, zhinst-toolkit 1.3,
  h5py 3.12 with HDF5 1.14, numpy 2.1).

Check the installation without any instrument attached:

```
python -m pytest tests -q
```

All tests run offline (fake devices, synthetic data). They take about 30 s.

## Start the GUI

```
python DLTSGUI_MainWindow.py
```

The window opens maximized with four tabs:

| Tab | What it is for | Reference |
|---|---|---|
| Input Parameters | MFIA, temperature and output settings; connect and push them to the instruments; export an HDF5 step to text | [runParamsTab](reference/runParamsTab.md) |
| Live Tools | Run DLTS, pause/resume/redo/retake steps, watch the data come in, load a finished run, Qualitative Analysis (averaged transients and temperature trace of the running experiment) | [liveDataTab](reference/liveDataTab.md) |
| Quick Analysis | Offline Data (load a saved folder, extract and average transients), five rate windows, DLTS spectra and an Arrhenius fit | [dataAnalysisTab](reference/dataAnalysisTab.md) |
| Detailed Analysis | Many rate windows, bootstrap peak errors, weighted Arrhenius fit, transient and rate-window maps | [detailedAnalysisTab](reference/detailedAnalysisTab.md) |

Closing the window always returns the stage to the Room Temperature set on the Input
Parameters tab first (a dialog shows the stage temperature until it arrives). See
[DLTSGUI_MainWindow](reference/DLTSGUI_MainWindow.md).

## Repository layout

| Path | Contents |
|---|---|
| `DLTSGUI_MainWindow.py` | GUI entry point |
| `runParamsTab.py`, `liveDataTab.py`, `dataAnalysisTab.py`, `detailedAnalysisTab.py` | The four tabs |
| `zurichInstruments_Control.py` | MFIA driver (`ziDevice`), data file writers |
| `instecTempStage_Control.py` | Temperature controller driver (`mK2000B`) |
| `runDlts_Tools.py` | The run sequence (`dltsRun`): init, steps, redo/retake, finish, room return |
| `impedanceAnalysis_Tools.py` | Analysis library (`impdData`): reading, cleanup, emission selection, denoising |
| `dltsConfig.py` | Shared state between the tabs, logging, GUI-label to value conversion |
| `convert_json_to_h5.py`, `convert_h5_to_text.py` | Data converters |
| `examples/` | Standalone scripts: stage, MFIA, a minimal scan, offline analysis |
| `benchmarks/` | Synthetic and real-hardware HDF5 benchmarks, stored reports |
| `tests/` | pytest suite |
| `DLTS_APP.py`, `DrKayisScript.py` | Older standalone PyQt6 analysis apps the tabs were ported from |

Next: [Running a DLTS experiment](running_a_dlts_experiment.md), or the
[Quick run examples](quick_run.md).
