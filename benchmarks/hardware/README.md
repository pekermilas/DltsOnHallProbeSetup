# Real-hardware HDF5 benchmark

Runs a short DLTS temperature scan on the instruments (Zurich Instruments MFIA +
Instec mK2000B) through the application's own run code, writing HDF5, then checks
every file and compares the run against the same data stored as JSON `.txt`.

**This moves the stage and biases the mounted sample.** Only run it when the sample
and temperature range are safe. The MFIA uses the GUI's default parameters
(`hw_common.py`, copied from `runParamsTab.py`).

## Steps

```
python benchmarks/hardware/hw_preflight.py            # stage read-only, times 2^18-point pulls
python benchmarks/hardware/hw_run.py                  # ~65 min with the defaults below
python benchmarks/hardware/hw_analyze.py OUTPUT_DIR   # the folder hw_run.py printed
python benchmarks/hardware/build_report.py OUTPUT_DIR --pdf benchmarks/hardware/reports/HDF5_Hardware_Benchmark_YYYY-MM-DD.pdf
```

`hw_run.py` defaults are the 28 Sep 2026 run: `--start 25 --stop 50 --step 5 --room 30
--points 18 --reps 100 --redo 45 --retake 40 --root C:\Users\spencer\Desktop\DATA\DLTS`.
It follows the GUI's sequence (main run, return to room temperature, Redo, return,
Remove & Retake, return, close) and aborts to room temperature if a step can't
stabilize within `--step-limit` minutes.

Everything the scripts write goes to `benchmarks/hardware/output/run_<timestamp>/`
(git-ignored): the run log, stage-temperature log, timings, `analysis.json`,
`report.html` and a JSON copy of the run (about 60 MB per 2^18-point step). The run's
data files stay in the Data Root Folder, and nothing is written there by the analysis.

`hw_analyze.py` also runs the rate-window analysis both ways, Quick Analysis on the
Extract & Average transients and Detailed Analysis on its own Load Data, with the GUI's
default windows scaled to the run's reverse bias. One check requires the two to give the
same Et, σ and Nt; the report's section 06 shows S(T), the peaks and both fits.

## Files

- `hw_common.py`: GUI parameter defaults and the connect/push sequence.
- `hw_preflight.py`, `hw_run.py`, `hw_analyze.py`, `build_report.py`: the steps above.
- `report_template.html`: the report page (interactive charts; print styles for the PDF).
- `notes/<date>.html`: optional findings for a run's report (`build_report.py --notes`).
- `reports/`: stored PDFs, named by run date.
