"""Real-hardware HDF5 benchmark run, driven through the same code the GUI uses.

Sequence (mirrors liveDataTab.start_dlts / _handle_run_status / the Redo and
Remove & Retake buttons / DLTSGUI_MainWindow's close):
  connect + push params -> init_experiment -> run_experiment -> finish_experiment
  -> return_to_room_temp -> Redo one step -> return_to_room_temp ->
  Remove & Retake another step -> return_to_room_temp -> disconnect.
Instrumentation: stage temperature every 10 s, per-step phase timings, and a
live-ingest worker repeating liveDataTab._ingest_files_async's work on each file.
A watchdog aborts and parks the stage at room temperature if a step can't
stabilize within --step-limit minutes.

The MFIA uses the GUI's default parameters. Run hw_preflight.py first on a new
setup. This moves the stage and biases the mounted sample: only run it when the
sample and temperature range are safe.

Usage (the defaults are the 28 Sep 2026 run):
  python benchmarks/hardware/hw_run.py --start 25 --stop 50 --step 5 --room 30 \
      --points 18 --reps 100 --root "C:\\Users\\spencer\\Desktop\\DATA\\DLTS" --redo 45 --retake 40
Then: hw_analyze.py and build_report.py on the output folder it prints.
"""
import argparse, os, sys, time, json, shutil, threading, traceback, csv
from datetime import datetime
import numpy as np
from hw_common import DEFAULT_OUTPUT, dltsc, setup_gui_state, connect_impedance, connect_temperature

parser = argparse.ArgumentParser(description='Real-hardware HDF5 benchmark run.')
parser.add_argument('--start', type=float, default=25.0, help='initial temperature (C)')
parser.add_argument('--stop', type=float, default=50.0, help='final temperature (C)')
parser.add_argument('--step', type=float, default=5.0, help='temperature step (C)')
parser.add_argument('--room', type=float, default=30.0, help='room temperature to return to (C)')
parser.add_argument('--points', type=int, default=18, help='log2 of the points per step')
parser.add_argument('--reps', type=int, default=100, help='repetitions per step')
parser.add_argument('--root', default=r'C:\Users\spencer\Desktop\DATA\DLTS', help='Data Root Folder')
parser.add_argument('--redo', type=float, default=45.0, help='setpoint to Redo (omit with --no-redo)')
parser.add_argument('--retake', type=float, default=40.0, help='setpoint to Remove & Retake')
parser.add_argument('--no-redo', action='store_true')
parser.add_argument('--no-retake', action='store_true')
parser.add_argument('--step-limit', type=float, default=40.0, help='watchdog limit per step (minutes)')
parser.add_argument('--out', default=DEFAULT_OUTPUT, help='parent folder for this run\'s benchmark output')
args = parser.parse_args()

OUT = os.path.join(args.out, datetime.now().strftime('run_%Y%m%d_%H%M%S'))
log = setup_gui_state(os.path.join(OUT, 'run.log'),
                      t_overrides={'Initial Temperature (C)': str(args.start), 'Final Temperature (C)': str(args.stop),
                                   'Temperature Step (C)': str(args.step), 'Room Temperature (C)': str(args.room)},
                      d_overrides={'Number of Points (power of 2)': args.points, 'Number of Reps': args.reps,
                                   'Data File Format': 'HDF5', 'Data Root Folder': args.root})
log(f'Benchmark output: {OUT}')
import runDlts_Tools as rdT
import impedanceAnalysis_Tools as iaT

T0 = time.time()
phase = {'name': 'setup'}
events = []          # (t, kind, detail)
stepTimings = []     # one dict per _run_single_step write
liveIngest = []      # one dict per ingested file
stop = threading.Event()
run = None

def event(kind, **detail):
    events.append(dict(t=time.time() - T0, kind=kind, **detail))

def dump():
    with open(os.path.join(OUT, 'run_meta.json'), 'w') as f:
        json.dump(dict(args=vars(args), events=events, steps=stepTimings, liveIngest=liveIngest,
                       dataFolder=getattr(run, 'dataFolder', None)), f, indent=2, default=str)

# --- temperature monitor (shares the controller's serial lock) ----------------
def monitor():
    with open(os.path.join(OUT, 'stage_temperature.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['t_s', 'T_C', 'phase'])
        while not stop.is_set():
            try:
                w.writerow([f'{time.time() - T0:.1f}', dltsc.tempDev.read_temp(), phase['name']]); f.flush()
            except Exception as exc:
                log(f'monitor: read_temp failed: {exc}')
            stop.wait(10)

# --- watchdog: a step that can't stabilize would otherwise wait forever -------
def watchdog():
    limit = args.step_limit * 60
    while not stop.is_set():
        started = phase.get('started')
        if started and phase['name'].startswith('step') and time.time() - started > limit:
            log(f'WATCHDOG: {phase["name"]} exceeded {args.step_limit:.0f} min; aborting run.')
            event('watchdog', phase=phase['name'])
            dltsc.run_abortRequested = True
            dltsc.tempDev.abort()
            return
        stop.wait(15)

# --- live ingest (liveDataTab._ingest_files_async's worker, same calls) ------
def live_worker():
    impd, seen = None, set()
    while not stop.is_set():
        new = [p for p in list(dltsc.run_dataFileNames or []) if p not in seen and os.path.exists(p)]
        for path in new:
            seen.add(path)
            rec = dict(file=os.path.basename(path), t=time.time() - T0)
            try:
                t = time.perf_counter()
                if impd is None:
                    impd = iaT.impdData(fName=[path]); res = impd.read_data()
                else:
                    res = impd.append_data(fName=[path])
                rec['read_s'] = time.perf_counter() - t; rec['result'] = res
                t = time.perf_counter(); impd.cleanup_data(); rec['cleanup_s'] = time.perf_counter() - t
                t = time.perf_counter(); impd.dataEmissionClusterParams = None
                impd.selected_emissions(emissionIndex=0); rec['cluster_s'] = time.perf_counter() - t
                t = time.perf_counter()
                impd.filter_emissions(method='pca', emissionIndex=0, recalculate=True, interactivePlot=False)
                rec['denoise_s'] = time.perf_counter() - t
                t = time.perf_counter(); impd.selected_emissions(emissionIndex=-1)
                rec['allEmissions_s'] = time.perf_counter() - t
                rec['nTemps'] = len(impd.dataTemps)
            except Exception as exc:
                rec['error'] = f'{type(exc).__name__}: {exc}'
            liveIngest.append(rec)
            log(f'live ingest {rec}')
        stop.wait(1)

# --- instrument the run's hardware calls (instance attributes only) ----------
def instrument(run):
    imp, tmp = run.impDevice, run.tempDevice
    cur = {}
    realGo, realPull, realWrite = tmp.go_to_temp, imp.pull_data, imp.writeDataH5

    def go(Tf, ramp, delay):
        cur.clear(); cur.update(setpoint=float(Tf), phase=phase['name'], start=time.time() - T0)
        phase['started'] = time.time()
        log(f'{phase["name"]}: ramping to {Tf} C'); t = time.perf_counter()
        r = realGo(Tf, ramp, delay); cur['ramp_stabilize_s'] = time.perf_counter() - t
        return r
    def pull(**kw):
        t = time.perf_counter(); d = realPull(**kw); cur['acquire_s'] = time.perf_counter() - t
        cur['nPoints'] = int(np.asarray(d['ImpedanceIm']).size); return d
    def write(data, fName, **kw):
        t = time.perf_counter(); r = realWrite(data, fName, **kw); cur['write_h5_s'] = time.perf_counter() - t
        cur.update(file=os.path.basename(fName), size_MB=os.path.getsize(fName) / 1e6,
                   stage_T=kw.get('stage_temperature_C'), end=time.time() - T0)
        stepTimings.append(dict(cur)); dump()
        log(f'{phase["name"]}: wrote {cur["file"]} ({cur["size_MB"]:.2f} MB) in {cur["write_h5_s"]:.2f} s, '
            f'stage {kw.get("stage_temperature_C")} C')
        return r
    tmp.go_to_temp, imp.pull_data, imp.writeDataH5 = go, pull, write


def room(label):
    phase.update(name=f'room:{label}', started=None)
    t = time.perf_counter(); s = run.return_to_room_temp()
    event('room', label=label, status=s, seconds=time.perf_counter() - t); dump()
    return s


def run_steps(label, indices=None, deleteFirst=False):
    phase.update(name=f'step:{label}')
    t = time.perf_counter(); s = run.run_experiment(indices=indices, deleteFirst=deleteFirst)
    event('run', label=label, status=s, seconds=time.perf_counter() - t,
          indices=indices, deleteFirst=deleteFirst, stepStatus=dict(run.stepStatus)); dump()
    log(f'{label}: {s} in {time.perf_counter() - t:.0f} s; stepStatus={run.stepStatus}')
    return s


roomStatus = None
try:
    phase['name'] = 'connect'
    connect_temperature(log)
    connect_impedance(log)
    for target in (monitor, watchdog, live_worker):
        threading.Thread(target=target, daemon=True).start()

    log('DLTS run started...')
    run = rdT.dltsRun()
    dltsc.run_dltsInstance = run
    if run.init_experiment() < 0:
        raise RuntimeError('init_experiment failed')
    grid = [float(x) for x in run.tempDevice.tempGrid]
    log(f'Data folder: {run.dataFolder}; grid: {grid}')
    event('init', folder=run.dataFolder, grid=grid)
    for i in range(len(grid)):
        run.stepStatus[i] = 'pending'
    instrument(run)

    status = run_steps('main')
    if status == 'completed':
        run.finish_experiment()
        log('DLTS run completed!')
        roomStatus = room('after main')

        keep = os.path.join(OUT, 'before_redo_retake'); os.makedirs(keep, exist_ok=True)
        plan = []
        if not args.no_redo and args.redo in grid:
            plan.append(('redo', args.redo, False))
        if not args.no_retake and args.retake in grid:
            plan.append(('retake', args.retake, True))
        for kind, T, deleteFirst in plan:
            if dltsc.run_abortRequested:
                break
            idx = grid.index(T)
            shutil.copy2(run.dataFileNames[idx], keep)
            log(f'{"Removing and retaking" if deleteFirst else "Redoing"} 1 step(s)... ({T} C)')
            if run_steps(f'{kind} {T:g}C', indices=[idx], deleteFirst=deleteFirst) == 'completed':
                log('Redo/Retake completed.')
            roomStatus = room(f'after {kind}')
    if dltsc.run_abortRequested:
        dltsc.tempDev._aborted = False    # let the room-temperature return proceed
        roomStatus = room('final')
except BaseException as exc:
    log('ERROR: ' + ''.join(traceback.format_exception(exc)))
    event('error', message=repr(exc))
    try:
        dltsc.tempDev._aborted = False
        phase['name'] = 'room:emergency'
        roomStatus = dltsc.tempDev.go_to_room_temp(Tr=args.room, ramp=10.0)
    except Exception as exc2:
        log(f'emergency room return failed: {exc2}')
finally:
    time.sleep(3)   # let the live worker pick up the last file
    deadline = time.time() + 600
    while time.time() < deadline and run is not None and run.dataFileNames and \
            len({r['file'] for r in liveIngest}) < len(run.dataFileNames):
        time.sleep(2)
    stop.set(); time.sleep(2)
    # DLTSGUI_MainWindow._finish_close: STOP only once the stage is at room temperature.
    try:
        dltsc.tempDev.disconnect_temp_controller(stopControl=(roomStatus == 0))
    except Exception as exc:
        log(f'temp disconnect: {exc}')
    try:
        dltsc.impDev.disconnect_device()
    except Exception as exc:
        log(f'MFIA disconnect: {exc}')
    event('closed', roomStatus=roomStatus, stopControl=(roomStatus == 0)); dump()
    log(f'Closed. Room-temperature status {roomStatus}; controller STOP sent: {roomStatus == 0}')
    log(f'Next: python benchmarks/hardware/hw_analyze.py "{OUT}"')
