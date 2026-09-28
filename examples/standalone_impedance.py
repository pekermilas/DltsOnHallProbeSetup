"""Standalone impedance analyzer (Zurich Instruments MFIA dev32271), no GUI.

Connects, pushes the GUI's default parameters (with any overrides), takes one
triggered, averaged acquisition, saves it as an HDF5 step file and plots it.

    python examples/standalone_impedance.py --out C:\\temp\\test_acq.h5
    python examples/standalone_impedance.py --points 18 --reps 100 --enable 0.5 --disable 0.001 --scale -5 --offset 0

Safety: the MFIA applies the pulse bias (Aux output) to the mounted sample.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib.pyplot as plt
import numpy as np
import zurichInstruments_Control as ziC

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('--out', required=True, help='HDF5 file to write (e.g. C:\\temp\\test_acq.h5)')
parser.add_argument('--points', type=int, default=16, help='log2 of the points (grid columns)')
parser.add_argument('--reps', type=int, default=100, help='triggered repetitions averaged')
parser.add_argument('--enable', type=float, help='State Enable Time (s) = reverse-bias duration')
parser.add_argument('--disable', type=float, help='State Disable Time (s) = fill-pulse duration')
parser.add_argument('--scale', type=float, help='Aux Output Scale (V)')
parser.add_argument('--offset', type=float, help='Aux Output Offset (V)')
parser.add_argument('--no-plot', action='store_true')
args = parser.parse_args()

overrides = {name: value for name, value in (('State Enable Time', args.enable), ('State Disable Time', args.disable),
                                             ('Aux Output Scale', args.scale), ('Aux Output Offset', args.offset))
             if value is not None}
dev = ziC.ziDevice()
dev.connect_device()
if dev.device is None:
    sys.exit('Could not connect to the MFIA (is LabOne / the data server running?).')
try:
    params = dev.configure(overrides)
    print('Parameters pushed:', params)
    t0 = time.time()
    data = dev.pull_data(plot=False, trigger=True, numPoints=2 ** args.points, numReps=args.reps)
    print(f'Acquired {data["ImpedanceIm"].size} points in {time.time() - t0:.1f} s')
    dev.writeDataH5(data, args.out, runParams=params)
    print('Wrote', args.out)
finally:
    dev.disconnect_device()

if not args.no_plot:
    t_ms = np.asarray(data['timeStampImps']) * 1e3
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(9, 6))
    ax1.plot(t_ms, data['AuxInput1']); ax1.set_ylabel('Aux input 1 (V)')
    ax2.plot(t_ms, data['ImpedanceIm']); ax2.set_ylabel('ImpedanceIm'); ax2.set_xlabel('time (ms)')
    ax2.ticklabel_format(axis='y', useOffset=False)
    fig.tight_layout(); plt.show()
