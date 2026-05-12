from pathlib import Path
import time

import numpy as np
import pytest

from lcview.core.lightcurve import read_light_curve
from lcview.core import periodogram as periodogram_module
from lcview.core import prewhitening as prewhitening_module
from lcview.core.periodogram import PeriodogramResult, compute_periodogram
from lcview.core.prewhitening import PrewhiteningEngine
from lcview.native.build import NativeBuildError, build_native


FIXTURE = Path(__file__).parent / "fixtures" / "sample_light_curve.dat"


def test_periodogram_python_backend_when_explicit():
    lc = read_light_curve(FIXTURE)
    result = compute_periodogram(lc, 0.5, 3.0, step=0.02, backend="python")
    assert abs(result.best_frequency - 1.0) < 0.1
    assert result.peaks
    assert not result.used_native
    assert result.noise_level == pytest.approx(float(np.median(result.amplitude)))


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


def test_native_build_smoke():
    try:
        tools = build_native()
    except NativeBuildError as exc:
        pytest.skip(str(exc))
    assert tools.fwpeaks.exists()
    assert tools.hars_sin.exists()
    assert tools.hars_ite.exists()
