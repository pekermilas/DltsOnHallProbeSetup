"""Standalone temperature stage (Instec mK2000B on COM7), no GUI.

Reads the stage, optionally ramps to a setpoint and waits until it is stable,
then leaves the controller holding (or stops it with --stop).

    python examples/standalone_temperature.py                 # read only
    python examples/standalone_temperature.py --goto 30       # ramp to 30 C at 5 C/min, wait
    python examples/standalone_temperature.py --goto 30 --ramp 10 --stop

Safety: --goto heats or cools the mounted sample.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import instecTempStage_Control as tsC

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('--port', default='COM7')
parser.add_argument('--goto', type=float, help='setpoint (C) to ramp to and stabilize at')
parser.add_argument('--ramp', type=float, default=5.0, help='ramp rate (C/min)')
parser.add_argument('--delay', type=float, default=0.0, help='extra wait after stabilizing (s)')
parser.add_argument('--stop', action='store_true', help='send TEMPerature:STOP when done')
args = parser.parse_args()

stage = tsC.mK2000B(port=args.port)
stage.configure({'Temperature Ramp (C/min)': args.ramp, 'Stability Delay (s)': args.delay})
stage.connect_temp_controller()
if not stage.state:
    sys.exit(f'Could not open {args.port}.')
try:
    print(f'Stage at {stage.read_temp():.3f} C')
    if args.goto is not None:
        tolerance = stage.expected_del_t(args.goto)
        print(f'Ramping to {args.goto} C at {stage.tRamp} C/min; stable within {tolerance:.3f} C...')
        t0 = time.time()
        stage.go_to_temp(args.goto, stage.tRamp, stage.tStableDelay)
        print(f'Stable at {stage.read_temp():.3f} C after {time.time() - t0:.0f} s')
finally:
    # stopControl=False leaves the controller holding its last setpoint.
    stage.disconnect_temp_controller(stopControl=args.stop)
