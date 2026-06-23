from pathlib import Path
import time

import numpy as np
import pytest

from lcview.core.lightcurve import read_light_curve
from lcview.core import periodogram as periodogram_module
from lcview.core import prewhitening as prewhitening_module
from lcview.core.periodogram import PeriodogramResult, compute_periodogram, compute_spectral_window
from lcview.core.prewhitening import PrewhiteningEngine
from lcview.core.results import build_frequency_report
from lcview.core.tdfd import TdfdResult
from lcview.native.build import NativeBuildError, build_native


FIXTURE = Path(__file__).parent / "fixtures" / "sample_light_curve.dat"


def test_periodogram_python_backend_when_explicit():
    lc = read_light_curve(FIXTURE)
    result = compute_periodogram(lc, 0.5, 3.0, step=0.02, backend="python")
    assert abs(result.best_frequency - 1.0) < 0.1
    assert result.peaks
    assert not result.used_native
    assert result.noise_level == pytest.approx(float(np.median(result.amplitude)))
    assert result.local_noise is not None
    assert len(result.local_noise) == len(result.amplitude)
    assert result.peaks[0]["local_snr"] == pytest.approx(result.peaks[0]["snr"])


def test_periodogram_noise_from_fwpeaks_snr_rows(tmp_path: Path):
    max_path = tmp_path / "lc.max"
    max_path.write_text(
        "% header\n"
        "  0     1.000000     1.000000    0.50000     5.00\n"
        "  1     2.000000     0.500000    0.90000     3.00\n"
    )

    peaks = periodogram_module._parse_max(max_path)

    assert periodogram_module._noise_from_peaks(peaks) == pytest.approx(0.2)


def test_periodogram_noise_fallback_uses_mean_amplitude_when_snr_missing():
    peaks = [{"frequency": 1.0, "amplitude": 0.4, "snr": None}]

    assert periodogram_module._noise_from_peaks(peaks) is None
    assert periodogram_module._mean_positive(np.array([0.2, 0.4, np.nan])) == pytest.approx(0.3)


def test_periodogram_python_backend_progress_callback():
    lc = read_light_curve(FIXTURE)
    events = []
    compute_periodogram(lc, 0.5, 1.0, step=0.05, backend="python", progress_callback=lambda percent, message: events.append((percent, message)))
    assert events
    assert events[0][0] == 0
    assert events[-1][0] == 99


def test_periodogram_python_backend_handles_zero_frequency():
    lc = read_light_curve(FIXTURE)
    result = compute_periodogram(lc, 0.0, 3.0, step=0.05, backend="python")

    assert not result.used_native
    assert np.isfinite(result.amplitude).all()
    assert abs(result.best_frequency - 1.0) < 0.1


def test_periodogram_result_snr_spectrum_uses_local_or_global_background():
    result = PeriodogramResult(
        frequency=np.array([1.0, 2.0]),
        amplitude=np.array([2.0, 4.0]),
        peaks=[],
        used_native=False,
        noise_level=0.5,
        local_noise=np.array([0.5, 1.0]),
    )

    assert result.snr_spectrum(adaptive=False).tolist() == pytest.approx([4.0, 8.0])
    assert result.snr_spectrum(adaptive=True).tolist() == pytest.approx([4.0, 4.0])
    assert result.snr_at_frequency(2.0, adaptive=True) == pytest.approx(4.0)


def test_compute_spectral_window_returns_normalized_overlay_grid():
    lc = read_light_curve(FIXTURE)
    frequency = np.linspace(0.5, 5.0, 120)

    window_frequency, window_amplitude = compute_spectral_window(lc, frequency, max_points=40, chunk_size=16)

    assert len(window_frequency) == len(window_amplitude)
    assert len(window_frequency) <= 40
    assert np.isfinite(window_amplitude).all()
    assert np.all(window_amplitude >= 0)
    assert float(np.max(window_amplitude)) <= 1.0 + 1e-6


def test_periodogram_requires_fwpeaks_unless_python_is_explicit(monkeypatch):
    lc = read_light_curve(FIXTURE)

    def fail_native():
        raise NativeBuildError("no compiler")

    monkeypatch.setattr(periodogram_module, "ensure_native", fail_native)

    with pytest.raises(RuntimeError, match="Python DFT backend explicitly"):
        compute_periodogram(lc, 0.5, 1.0, step=0.05)


def test_engine_session_and_candidates(tmp_path: Path):
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    engine = PrewhiteningEngine.from_file(lc_path)
    engine.state.settings.start_frequency = 0.5
    engine.state.settings.end_frequency = 3.0
    engine.state.settings.precision = 20
    periodogram = engine.compute_periodogram()
    assert periodogram.peaks
    assert engine.initial_candidates()
    engine.add_independent(periodogram.best_frequency)
    assert engine.model.bases
    assert engine.state.json_path.exists()


def test_engine_candidate_classification_does_not_block_with_many_bases(tmp_path: Path, monkeypatch):
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    engine = PrewhiteningEngine.from_file(lc_path)
    for frequency in [2.710707, 2.80118, 2.856856, 2.130927, 3.823947, 4.710507, 14.319544, 0.236658, 2.603257, -1.225853, 4.430682, 2.304929, 4.943379, 0.539251, 5.812692]:
        engine.add_independent(frequency)
    engine.state.settings.start_frequency = 0.0
    engine.state.settings.end_frequency = 10.0
    peaks = [
        {"frequency": 0.5 + index * 0.17, "amplitude": 1.0 / (index + 1), "snr": 4.0}
        for index in range(50)
    ]
    periodogram = PeriodogramResult(
        frequency=np.linspace(0.0, 10.0, 100),
        amplitude=np.linspace(0.1, 1.0, 100),
        peaks=peaks,
        used_native=True,
        noise_level=0.1,
    )
    monkeypatch.setattr(prewhitening_module, "compute_periodogram", lambda *args, **kwargs: periodogram)

    started = time.perf_counter()
    result = engine.compute_periodogram()
    elapsed = time.perf_counter() - started

    assert result is periodogram
    assert len(engine.last_candidates) == len(peaks)
    assert elapsed < 0.5


def test_engine_reads_component_residual_file(tmp_path: Path):
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    engine = PrewhiteningEngine.from_file(lc_path)
    engine.state.work_dir.mkdir(parents=True, exist_ok=True)
    data = np.array([[0.0, 1.0, 0.1], [1.0, -1.0, 0.1]])
    np.savetxt(engine.component_path(0), data)

    component = engine.component_light_curve(0)
    assert component is not None
    assert component.flux.tolist() == [1.0, -1.0]


def test_fast_fit_handles_multiple_independent_frequencies(tmp_path: Path):
    time = np.linspace(0.0, 20.0, 800)
    flux = 1.2 * np.sin(2.0 * np.pi * 1.0 * time + 0.3) + 0.7 * np.sin(2.0 * np.pi * 2.5 * time - 0.4)
    error = np.full_like(time, 0.01)
    lc_path = tmp_path / "multi.dat"
    np.savetxt(lc_path, np.column_stack([time, flux, error]))
    engine = PrewhiteningEngine.from_file(lc_path)
    engine.add_independent(1.0)
    engine.add_independent(2.5)

    fit = engine.fit_model()

    assert not fit.used_native
    assert fit.converged
    assert np.std(fit.residuals.flux) < 1e-10
    assert (engine.state.work_dir / "resid.dat").exists()
    assert engine.component_path(0).exists()
    assert engine.component_path(1).exists()
    assert "Ampl. #  1" in fit.ampl_text
    assert len(fit.fourier_terms) == 2
    first, second = fit.fourier_terms
    assert first.frequency == pytest.approx(1.0)
    assert first.sin_coefficient == pytest.approx(1.2 * np.cos(0.3), abs=1e-10)
    assert first.cos_coefficient == pytest.approx(1.2 * np.sin(0.3), abs=1e-10)
    assert second.frequency == pytest.approx(2.5)
    assert second.sin_coefficient == pytest.approx(0.7 * np.cos(-0.4), abs=1e-10)
    assert second.cos_coefficient == pytest.approx(0.7 * np.sin(-0.4), abs=1e-10)
    assert fit.report is not None
    assert fit.report.nobs == len(time)
    assert fit.report.rows[0].amplitude == pytest.approx(1.2, abs=1e-10)
    assert fit.report.rows[0].phase_cycles == pytest.approx((0.3 / (2 * np.pi)) % 1.0, abs=1e-10)


def test_frequency_report_returns_errors_and_phase_cycles(tmp_path: Path):
    rng = np.random.default_rng(123)
    time_values = np.linspace(0.0, 20.0, 1200)
    amplitude = 1.4
    phase = 0.35
    error = np.full_like(time_values, 0.05)
    flux = amplitude * np.sin(2.0 * np.pi * 1.5 * time_values + phase) + rng.normal(0.0, 0.02, size=time_values.size)
    lc_path = tmp_path / "lc.dat"
    np.savetxt(lc_path, np.column_stack([time_values, flux, error]))
    engine = PrewhiteningEngine.from_file(lc_path)
    engine.add_independent(1.5)

    report = build_frequency_report(engine.light_curve, engine.model, fit_source="test")

    row = report.rows[0]
    assert row.kind == "independent"
    assert row.frequency == pytest.approx(1.5)
    expected_frequency_error = (
        np.sqrt(6.0)
        / (np.pi * engine.light_curve.baseline)
        * float(report.sdev)
        / (float(row.amplitude) * np.sqrt(report.nobs))
    )
    assert row.frequency_error == pytest.approx(expected_frequency_error)
    assert row.period_error == pytest.approx(row.frequency_error / row.frequency**2)
    assert row.amplitude == pytest.approx(amplitude, abs=0.01)
    assert row.amplitude_error is not None and row.amplitude_error > 0
    assert row.phase_cycles == pytest.approx((phase / (2 * np.pi)) % 1.0, abs=0.003)
    assert row.phase_error_cycles is not None and row.phase_error_cycles > 0


def test_frequency_report_kinds_disabled_rows_and_propagated_rayleigh(tmp_path: Path):
    time_values = np.linspace(0.0, 10.0, 500)
    error = np.full_like(time_values, 0.02)
    flux = np.sin(2 * np.pi * time_values) + 0.2 * np.sin(4 * np.pi * time_values)
    lc_path = tmp_path / "lc.dat"
    np.savetxt(lc_path, np.column_stack([time_values, flux, error]))
    engine = PrewhiteningEngine.from_file(lc_path)
    engine.add_independent(1.0)
    engine.add_independent(1.7)
    harmonic_index = engine.add_combination((2, 0))
    combination_index = engine.add_combination((1, 1))
    engine.set_term_enabled(combination_index, False)

    report = build_frequency_report(engine.light_curve, engine.model, fit_source="test")
    by_label = {row.label: row for row in report.rows}

    assert by_label["2f1"].kind == "harmonic"
    assert by_label["f1 + f2"].kind == "combination"
    assert by_label["f1 + f2"].status == "disabled"
    assert by_label["f1 + f2"].amplitude is None
    assert by_label["2f1"].frequency_error == pytest.approx(2.0 * float(by_label["f1"].frequency_error))
    combo_error = np.hypot(float(by_label["f1"].frequency_error), float(by_label["f2"].frequency_error))
    assert by_label["f1 + f2"].frequency_error == pytest.approx(combo_error)
    assert report.n_terms == 4
    assert report.n_active_terms == 3
    assert harmonic_index >= 0


def test_fourier_terms_parse_from_ampl_text():
    text = """\
           a0:     3.500000
Frequency #  1:     2.0000000
Ampl. #  1:    4.000000
Phase #  1:    0.500000
Term #  1: 1 0
"""

    offset, terms = PrewhiteningEngine._fourier_terms_from_ampl_text(text)

    assert offset == pytest.approx(3.5)
    assert len(terms) == 1
    assert terms[0].term == (1, 0)
    assert terms[0].frequency == pytest.approx(2.0)
    assert terms[0].sin_coefficient == pytest.approx(4.0 * np.cos(0.5))
    assert terms[0].cos_coefficient == pytest.approx(4.0 * np.sin(0.5))


def test_tdfd_correction_is_residual_layer_not_frequency_model(tmp_path: Path):
    lc_path = tmp_path / "lc.dat"
    time_values = np.linspace(0, 5, 100)
    error = np.full_like(time_values, 0.01)
    np.savetxt(lc_path, np.column_stack([time_values, np.sin(2 * np.pi * time_values), error]))
    engine = PrewhiteningEngine.from_file(lc_path)
    engine.add_independent(1.0)
    base_residual = engine.light_curve.with_flux(np.ones_like(engine.light_curve.flux))
    corrected = engine.light_curve.with_flux(np.zeros_like(engine.light_curve.flux))
    engine.residuals = base_residual
    result = TdfdResult(
        bins=[],
        residuals=base_residual,
        source_light_curve=base_residual,
        corrected_residuals=corrected,
        selected_base_index=0,
        correction_term_indexes=(0,),
    )

    returned = engine.apply_tdfd_correction(result)

    assert returned is corrected
    assert engine.residuals is corrected
    assert engine.tdfd_correction_active
    assert engine.model.bases == [1.0]
    assert engine.last_periodogram is None

    assert engine.clear_tdfd_correction()
    assert engine.residuals is base_residual
    assert not engine.tdfd_correction_active
    assert engine.model.bases == [1.0]


def test_model_change_disables_stale_tdfd_correction(tmp_path: Path):
    lc_path = tmp_path / "lc.dat"
    time_values = np.linspace(0, 5, 100)
    error = np.full_like(time_values, 0.01)
    np.savetxt(lc_path, np.column_stack([time_values, np.sin(2 * np.pi * time_values), error]))
    engine = PrewhiteningEngine.from_file(lc_path)
    engine.add_independent(1.0)
    base_residual = engine.light_curve.with_flux(np.ones_like(engine.light_curve.flux))
    corrected = engine.light_curve.with_flux(np.zeros_like(engine.light_curve.flux))
    engine.residuals = base_residual
    engine.apply_tdfd_correction(
        TdfdResult(
            bins=[],
            residuals=base_residual,
            source_light_curve=base_residual,
            corrected_residuals=corrected,
            selected_base_index=0,
            correction_term_indexes=(0,),
        )
    )

    engine.add_independent(2.0)

    assert not engine.tdfd_correction_active
    assert engine.tdfd_result is None
    assert engine.residuals is base_residual
    assert engine.tdfd_correction_stale_reason == "Accepted frequencies changed"


def test_native_build_smoke():
    try:
        tools = build_native()
    except NativeBuildError as exc:
        pytest.skip(str(exc))
    assert tools.fwpeaks.exists()
    assert tools.hars_sin.exists()
    assert tools.hars_ite.exists()
