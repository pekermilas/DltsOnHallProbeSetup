"""Preflight before a hardware benchmark: read the stage (no ramp, controller left as
it was) and time acquisitions at the requested size, to check pull_data() finishes
well inside its 60 s completion timeout.

Usage: python benchmarks/hardware/hw_preflight.py [--points 18] [--reps 1 2 10]
"""
import argparse, os, time
import numpy as np
from hw_common import DEFAULT_OUTPUT, dltsc, setup_gui_state, connect_impedance

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('--points', type=int, default=18, help='log2 of the points per acquisition')
parser.add_argument('--reps', type=int, nargs='+', default=[1, 2, 10], help='repetition counts to time')
parser.add_argument('--out', default=DEFAULT_OUTPUT)
args = parser.parse_args()
log = setup_gui_state(os.path.join(args.out, 'preflight.log'))

import instecTempStage_Control as tsC
tdev = tsC.mK2000B()
tdev.connect_temp_controller()
log(f'Stage connected={tdev.state}, T = {tdev.read_temp()} C')
tdev.disconnect_temp_controller(stopControl=False)   # leave the controller exactly as it was

connect_impedance(log)
dev = dltsc.impDev
dev.reload_params()
for reps in args.reps:
    t = time.perf_counter()
    data = dev.pull_data(plot=False, trigger=True, numPoints=2 ** args.points, numReps=reps)
    log(f'pull_data 2**{args.points} x {reps} rep(s): {time.perf_counter() - t:.1f} s')
    for k, v in data.items():
        a = np.asarray(v)
        log(f'   {k}: shape={a.shape} dtype={a.dtype} min={np.nanmin(a):.6g} max={np.nanmax(a):.6g}')
dev.disconnect_device()
log('preflight done')
