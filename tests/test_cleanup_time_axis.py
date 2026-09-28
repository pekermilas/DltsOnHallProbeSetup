"""impdData.cleanup_data() on both kinds of tickStamp channel: 60 MHz clock ticks
(untriggered acquisitions) and the DAQ grid's time axis in seconds (triggered
acquisitions, which runs use)."""
import numpy as np

import impedanceAnalysis_Tools as iaT
from conftest import SAMPLE_DT_S, TICKS_PER_SAMPLE, make_step


def cleaned(record):
    impd = iaT.impdData(fName=['p25p0.txt'])
    impd.dataTemps = [298]
    impd.dataValues = {298: {k: np.array(v, copy=True) for k, v in record.items()}}
    impd.cleanup_data()
    return impd.dataValues[298]


def test_seconds_axis_keeps_its_time_origin_and_units():
    """Used to turn t = 0 into -1 s and divide the axis by 60e6 (~1e-11 s)."""
    data = make_step(25.0, n=2048)
    t = np.arange(2048) * SAMPLE_DT_S
    for key in ('tickStampImps', 'tickStampDemods', 'timeStampImps', 'timeStampDemods'):
        data[key] = t.copy()

    out = cleaned(data)
    assert np.array_equal(out['tickStampImps'], t)
    assert np.array_equal(out['timeStampImps'], t)
    assert out['timeStampImps'][-1] == (2048 - 1) * SAMPLE_DT_S


def test_missing_sample_on_seconds_axis_is_interpolated_in_seconds():
    t = np.arange(100) * SAMPLE_DT_S
    data = {'tickStampImps': t.copy(), 'tickStampDemods': t.copy(), 'timeStampImps': t.copy(),
            'timeStampDemods': t.copy(), 'ImpedanceIm': np.ones(100)}
    data['tickStampImps'][40] = 0.0

    out = cleaned(data)
    assert out['tickStampImps'][0] == 0.0
    assert np.isclose(out['tickStampImps'][40], t[40])
    assert np.allclose(out['timeStampImps'], t)


def test_clock_ticks_are_still_filled_and_converted():
    data = make_step(25.0, n=256)
    data['tickStampImps'] = data['tickStampImps'].astype(np.int64)
    ticks = data['tickStampImps'].copy()
    data['tickStampImps'][10] = 0

    out = cleaned(data)
    assert out['tickStampImps'][10] == ticks[10]
    assert np.allclose(out['timeStampImps'], ticks / 60e6)
    assert np.diff(out['tickStampImps']).min() == TICKS_PER_SAMPLE


def test_axis_kind_detection():
    assert iaT.impdData._is_seconds_axis(np.arange(10) * SAMPLE_DT_S)
    assert not iaT.impdData._is_seconds_axis(np.arange(10, dtype=np.int64) * 1120)
    assert not iaT.impdData._is_seconds_axis((np.arange(10) * 1120).astype(float))
