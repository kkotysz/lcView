import numpy as np

from lcview.core.lightcurve import LightCurve
from lcview.core.phase import FoldedLightCurve, boxcar_smooth, evaluate_sincos_series, fit_sincos_series, fold_light_curve


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


def test_fit_sincos_series_recovers_harmonics():
    phase = np.linspace(0.0, 1.0, 200, endpoint=False)
    flux = 0.4 + 1.2 * np.sin(2.0 * np.pi * phase) - 0.7 * np.cos(4.0 * np.pi * phase)
    folded = FoldedLightCurve(phase=phase, flux=flux, error=np.full_like(phase, 0.1))

    fit = fit_sincos_series(folded, [1, 2])

    assert fit is not None
    assert fit.harmonics == (1, 2)
    expected = 0.4 + 1.2 * np.sin(2.0 * np.pi * fit.phase) - 0.7 * np.cos(4.0 * np.pi * fit.phase)
    assert np.max(np.abs(fit.flux - expected)) < 1e-10


def test_evaluate_sincos_series_uses_fit_coefficients_on_arbitrary_phase_grid():
    phase = np.linspace(0.0, 1.0, 200, endpoint=False)
    flux = 0.4 + 1.2 * np.sin(2.0 * np.pi * phase) - 0.7 * np.cos(4.0 * np.pi * phase)
    folded = FoldedLightCurve(phase=phase, flux=flux, error=np.full_like(phase, 0.1))
    fit = fit_sincos_series(folded, [1, 2])
    target_phase = np.array([0.125, 0.375, 0.625])

    evaluated = evaluate_sincos_series(target_phase, fit.harmonics, fit.coefficients)

    expected = 0.4 + 1.2 * np.sin(2.0 * np.pi * target_phase) - 0.7 * np.cos(4.0 * np.pi * target_phase)
    assert np.max(np.abs(evaluated - expected)) < 1e-10
