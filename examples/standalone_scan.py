"""Minimal DLTS temperature scan with both instruments, no GUI.

For each setpoint: ramp and stabilize, take one triggered acquisition, write
<folder>/p25p0.h5 etc. (the same step-file format the GUI writes, readable by
every analysis tab), then return to room temperature. This bypasses dltsRun,
so it has no Pause/Redo/Retake; use the GUI (or benchmarks/hardware/hw_run.py)
for those.

    python examples/standalone_scan.py --folder C:\\temp\\scan1 --start 25 --stop 50 --step 5 --room 30

Safety: heats/cools the stage and biases the mounted sample.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import instecTempStage_Control as tsC
import zurichInstruments_Control as ziC

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('--folder', required=True)
parser.add_argument('--start', type=float, default=25.0)
parser.add_argument('--stop', type=float, default=50.0)
parser.add_argument('--step', type=float, default=5.0)
parser.add_argument('--room', type=float, default=25.0)
parser.add_argument('--points', type=int, default=16)
parser.add_argument('--reps', type=int, default=100)
args = parser.parse_args()

stage = tsC.mK2000B()
tParams = stage.configure({'Initial Temperature (C)': args.start, 'Final Temperature (C)': args.stop,
                           'Temperature Step (C)': args.step, 'Room Temperature (C)': args.room})
dev = ziC.ziDevice()
stage.connect_temp_controller()
dev.connect_device()
if not stage.state or dev.device is None:
    sys.exit('Could not connect to both instruments.')

os.makedirs(args.folder, exist_ok=True)
zParams = dev.configure()
runParams = {**zParams, **{k: v for k, v in tParams.items() if k != 'Temperature Grid (C)'},
             'Number of Points (power of 2)': args.points, 'Number of Reps': args.reps, 'Data File Format': 'HDF5'}
with open(os.path.join(args.folder, 'runParams.txt'), 'w') as f:
    json.dump(runParams, f, indent=4)   # the analysis tabs read pulse timings from this

roomStatus = None
try:
    for T in stage.tempGrid:
        stage.go_to_temp(T, stage.tRamp, stage.tStableDelay)
        before = stage.read_temp()
        data = dev.pull_data(plot=False, trigger=True, numPoints=2 ** args.points, numReps=args.reps)
        after = stage.read_temp()
        name = ('n' if T < 0 else 'p') + str(abs(float(T))).replace('.', 'p') + '.h5'
        dev.writeDataH5(data, os.path.join(args.folder, name), setpoint_C=T,
                        stage_temperature_C=(before + after) / 2, runParams=runParams)
        print(f'{time.strftime("%H:%M:%S")}  {name}: stage {(before + after) / 2:.3f} C')
finally:
    roomStatus = stage.go_to_room_temp()          # 0 = arrived
    stage.disconnect_temp_controller(stopControl=(roomStatus == 0))
    dev.disconnect_device()
