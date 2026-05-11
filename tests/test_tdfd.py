import numpy as np

from lcview.core.frequency_model import FrequencyModel
from lcview.core.lightcurve import LightCurve
from lcview.core.tdfd import run_tdfd


def test_native_tdfd_without_fdecomp():
    time = np.linspace(0, 10, 500)
    flux = np.sin(2 * np.pi * 2.0 * time)
    err = np.full_like(time, 0.01)
    lc = LightCurve(time, flux, err)
    model = FrequencyModel.empty()
    model.add_independent(2.0)

    result = run_tdfd(lc, model, bins=10)
    assert len(result.bins) == 10
    assert np.median([row.amplitudes[0] for row in result.bins]) > 0.8
    assert len(result.residuals.time) == len(time)
