import os
import sys

import matplotlib
matplotlib.use('Agg')

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zurichInstruments_Control as ziC

# MFIA demodulator/impedance sample interval at the rate the app assumes
# (liveDataTab's samplingRateS), and the 60 MHz clock it counts ticks in.
SAMPLE_DT_S = 1.8666666666666665e-05
TICKS_PER_SAMPLE = 1120


def make_step(T, n=2**14, seed=0, fill_ms=1.0, rb_ms=500.0):
    """Synthetic pull_data() output for one temperature step: 8 channels,
    repeated fill pulse / reverse-bias cycles with a capacitance transient
    whose time constant depends on T."""
    rng = np.random.default_rng(seed)
    fillN, rbN = int(fill_ms * 1e-3 / SAMPLE_DT_S), int(rb_ms * 1e-3 / SAMPLE_DT_S)
    k = np.arange(n) % (fillN + rbN)
    exc = np.where(k < fillN, 0.0, -5.0) + rng.normal(0, 1e-3, n)
    tau = 0.02 * np.exp(-(T - 50) / 30)
    cap = (1e-10 + 1e-12 * np.exp(-(k - fillN) * SAMPLE_DT_S / tau) * (k >= fillN)
           + rng.normal(0, 1e-15, n))
    tick = np.uint64(123456789012) + np.arange(n, dtype=np.uint64) * np.uint64(TICKS_PER_SAMPLE)
    t = (tick / 60e6) - (tick / 60e6)[0]
    return dict(tickStampImps=tick, tickStampDemods=tick.copy(),
                timeStampImps=t, timeStampDemods=t.copy(),
                ImpedanceRe=rng.normal(1e3, 1, n), ImpedanceIm=cap,
                AbsZ=rng.normal(1e3, 1, n), AuxInput1=exc)


def step_file_name(T, ext):
    """The data file name init_experiment() gives setpoint T, e.g. n10p0.h5."""
    return ('n' if T < 0 else 'p') + str(abs(float(T))).replace('.', 'p') + ext


@pytest.fixture
def zi_device():
    """A ziDevice without a hardware connection: enough for its file writers."""
    return ziC.ziDevice.__new__(ziC.ziDevice)


def write_run(dev, folder, temps, ext, n=2**14, rb_ms=500.0):
    """Write one file per temperature (plus runParams.txt) the way a run does."""
    paths = []
    for i, T in enumerate(temps):
        path = os.path.join(folder, step_file_name(T, ext))
        data = make_step(T, n=n, seed=i, rb_ms=rb_ms)
        if ext == '.h5':
            dev.writeDataH5(data, path, setpoint_C=T)
        else:
            dev.writeDataJson(data, path)
        paths.append(path)
    dev.writeDataJson({'Number of Reps': 1}, os.path.join(folder, 'runParams.txt'))
    return paths
