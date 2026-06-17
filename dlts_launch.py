"""
Small launcher to run the DLTS GUI as a separate Python process.

This avoids GUI event-loop conflicts when you are running inside an IPython
session that already has a different interactive framework (e.g. Qt).

Usage from IPython:
    from dlts_launch import launch_gui
    proc = launch_gui(simulation=True)

The function returns a subprocess.Popen object. Call proc.terminate() or
proc.kill() to stop the GUI process.

You can also run from PowerShell:
    python dlts_launch.py --simulation

"""

import subprocess
import sys
from pathlib import Path


def launch_gui(simulation=False, python_executable=None, cwd=None):
    """Launch the dlts GUI in a separate process.

    Parameters
    - simulation: if True, starts GUI in simulation mode
    - python_executable: path to python executable (defaults to sys.executable)
    - cwd: working directory to run the GUI from (defaults to the dltsOnHallProbeSetup folder)

    Returns
    - subprocess.Popen instance
    """
    python_executable = python_executable or sys.executable
    base_dir = Path(__file__).resolve().parent
    script = base_dir / 'dltsGUI.py'
    if not script.exists():
        raise FileNotFoundError(f"dltsGUI.py not found at {script}")

    args = [python_executable, str(script)]
    if simulation:
        args.append('--simulation')

    cwd = cwd or str(base_dir)
    proc = subprocess.Popen(args, cwd=cwd)
    return proc


def _cli():
    import argparse
    p = argparse.ArgumentParser(description='Launch DLTS GUI in separate process')
    p.add_argument('--simulation', action='store_true', help='Start GUI in simulation mode')
    args = p.parse_args()
    proc = launch_gui(simulation=args.simulation)
    print(f'Launched GUI (pid={proc.pid})')


if __name__ == '__main__':
    _cli()

