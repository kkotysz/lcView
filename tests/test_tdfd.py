import numpy as np
import pytest

from lcview.core.frequency_model import FrequencyModel
from lcview.core.lightcurve import LightCurve
from lcview.core.tdfd import TdfdOptions, fit_fixed_frequencies, run_tdfd


def _light_curve(time, flux):
    return LightCurve(time, flux, np.full_like(time, 0.01))


def test_sliding_tdfd_recovers_time_variable_amplitude():
    time = np.linspace(0, 20, 1200)
    amplitude = 0.8 + 0.6 * (time - time.min()) / (time.max() - time.min())
    flux = amplitude * np.sin(2 * np.pi * 2.0 * time)
    model = FrequencyModel.empty()
    model.add_independent(2.0)

    result = run_tdfd(
        _light_curve(time, flux),
        model,
        options=TdfdOptions(auto_window=False, window_points=180, step_points=45, selected_base_index=0),
    )

    assert len(result.bins) > 8
    assert result.bins[0].frequencies.tolist() == [2.0]
    measured = np.array([row.amplitudes[0] for row in result.bins])
    expected = np.interp(result.window_centers, time, amplitude)
    assert measured[-1] > measured[0]
    assert np.median(np.abs(measured - expected)) < 0.08
    assert result.window_points == 180
    assert result.step_points == 45


def test_tdfd_fits_full_active_model_but_reports_independent_frequencies():
    time = np.linspace(0, 12, 900)
    flux = (
        1.0 * np.sin(2 * np.pi * 1.0 * time)
        + 0.55 * np.sin(2 * np.pi * 2.0 * time + 0.3)
        + 0.4 * np.sin(2 * np.pi * 2.7 * time - 0.2)
    )
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.add_independent(2.7)
    model.add_combination((2, 0))

    result = run_tdfd(
        _light_curve(time, flux),
        model,
        options=TdfdOptions(auto_window=False, window_points=240, step_points=60, selected_base_index=0),
    )

    assert result.frequency_labels == ("f1", "f2")
    assert [term.label for term in result.fit_terms] == ["f1", "f2", "2f1"]
    assert result.fit_parameter_count == 7
    assert np.std(result.residuals.flux) < 0.08


def test_tdfd_correction_removes_selected_family_only():
    time = np.linspace(0, 20, 1600)
    amp1 = 0.8 + 0.5 * np.sin(2 * np.pi * time / np.ptp(time))
    flux = (
        amp1 * np.sin(2 * np.pi * 1.0 * time)
        + 0.35 * np.sin(2 * np.pi * 2.0 * time + 0.4)
        + 0.65 * np.sin(2 * np.pi * 2.7 * time - 0.2)
    )
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.add_independent(2.7)
    model.add_combination((2, 0))

    result = run_tdfd(
        _light_curve(time, flux),
        model,
        options=TdfdOptions(auto_window=False, window_points=260, step_points=65, selected_base_index=0),
    )

    corrected = result.corrected_residuals
    assert corrected is not None
    amplitudes, _phases, _residuals = fit_fixed_frequencies(corrected, np.array([1.0, 2.0, 2.7]))
    assert amplitudes[0] < 0.18
    assert amplitudes[1] < 0.12
    assert amplitudes[2] == pytest.approx(0.65, abs=0.08)
    assert result.correction_term_indexes == (0, 2)


def test_tdfd_interpolates_sin_cos_coefficients_without_phase_wrap_jump():
    time = np.linspace(0, 24, 1400)
    phase = -2.8 + 5.6 * (time - time.min()) / (time.max() - time.min())
    flux = np.sin(2 * np.pi * 1.4 * time + phase)
    model = FrequencyModel.empty()
    model.add_independent(1.4)

    result = run_tdfd(
        _light_curve(time, flux),
        model,
        options=TdfdOptions(auto_window=False, window_points=220, step_points=55, selected_base_index=0),
    )

    interpolated_phase = np.unwrap(
        np.arctan2(result.interpolated_cos_coefficients[0], result.interpolated_sin_coefficients[0])
    )
    assert np.max(np.abs(np.diff(interpolated_phase))) < 0.08
    assert np.all(np.isfinite(result.corrected_residuals.flux))


def test_tdfd_skips_windows_when_too_few_points_for_full_model():
    time = np.linspace(0, 1, 8)
    flux = np.sin(2 * np.pi * time)
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.add_independent(2.0)

    result = run_tdfd(
        _light_curve(time, flux),
        model,
        options=TdfdOptions(auto_window=False, window_points=4, step_points=1, selected_base_index=0),
    )

    assert result.bins == []
    assert result.message.startswith("No TDFD windows")
    assert result.min_points_per_bin == 5
