import numpy as np

from lcview.core.lightcurve import LightCurve
from lcview.core.phase import boxcar_smooth, fold_light_curve


def _sample_light_curve() -> LightCurve:
    return LightCurve(
        time=np.array([0.0, 0.25, 0.5, 0.75]),
        flux=np.array([1.0, 2.0, 3.0, 4.0]),
        error=np.array([0.1, 0.2, 0.3, 0.4]),
    )


def test_fold_light_curve_repeats_and_sorts_phase():
    folded = fold_light_curve(_sample_light_curve(), 1.0, repeats=4)
    assert len(folded.phase) == 16
    assert folded.phase[0] == 0.0
    assert folded.phase[-1] == 3.75
    assert np.all(np.diff(folded.phase) >= 0)


def test_fold_light_curve_shift_preserves_flux_and_error_values():
    light_curve = _sample_light_curve()
    unshifted = fold_light_curve(light_curve, 1.0)
    shifted = fold_light_curve(light_curve, 1.0, shift_fraction=0.25)
    assert np.allclose(np.sort(shifted.phase), np.sort(np.mod(unshifted.phase + 0.25, 1.0)))
    assert sorted(shifted.flux.tolist()) == sorted(light_curve.flux.tolist())
    assert sorted(shifted.error.tolist()) == sorted(light_curve.error.tolist())


def test_boxcar_smooth_keeps_length_and_handles_small_windows():
    values = np.arange(5, dtype=float)
    assert boxcar_smooth(values, 1).tolist() == values.tolist()
    assert len(boxcar_smooth(values, 3)) == len(values)
    assert len(boxcar_smooth(values, 99)) == len(values)
