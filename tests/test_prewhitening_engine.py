from pathlib import Path

import numpy as np
import pytest

from lcview.core.lightcurve import read_light_curve
from lcview.core.periodogram import compute_periodogram
from lcview.core.prewhitening import PrewhiteningEngine
from lcview.native.build import NativeBuildError, build_native


FIXTURE = Path(__file__).parent / "fixtures" / "sample_light_curve.dat"


def test_periodogram_python_fallback():
    lc = read_light_curve(FIXTURE)
    result = compute_periodogram(lc, 0.5, 3.0, step=0.02, prefer_native=False)
    assert abs(result.best_frequency - 1.0) < 0.1
    assert result.peaks
    assert not result.used_native


def test_periodogram_python_progress_callback():
    lc = read_light_curve(FIXTURE)
    events = []
    compute_periodogram(lc, 0.5, 1.0, step=0.05, prefer_native=False, progress_callback=lambda percent, message: events.append((percent, message)))
    assert events
    assert events[0][0] == 0
    assert events[-1][0] == 100


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


def test_native_build_smoke():
    try:
        tools = build_native()
    except NativeBuildError as exc:
        pytest.skip(str(exc))
    assert tools.fwpeaks.exists()
    assert tools.hars_sin.exists()
    assert tools.hars_ite.exists()
