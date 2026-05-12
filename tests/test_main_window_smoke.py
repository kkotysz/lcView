import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from lcview.core.combinations import classify_peak
from lcview.core.frequency_model import FrequencyModel
from lcview.core.lightcurve import LightCurve
from lcview.core.periodogram import PeriodogramResult
from lcview.core.prewhitening import FitResult, FourierTerm, PrewhiteningEngine
from lcview.core.sigma_clip import SigmaClipResult
from lcview.core.tdfd import TdfdBin, TdfdResult
from lcview.ui import main_window as main_window_module
from lcview.ui.main_window import DftWorker, FitWorker, MainWindow


FIXTURE = Path(__file__).parent / "fixtures" / "sample_light_curve.dat"


def _skip_without_pyqtgraph(plot) -> None:
    if plot._plot is None:
        pytest.skip("pyqtgraph is not installed")


def _selected_marker_value(plot) -> float:
    marker = plot._selected_marker
    assert marker is not None
    return float(marker.value())


def test_initial_window_geometry_fits_available_screen():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    screen = QtGui.QGuiApplication.primaryScreen()
    assert screen is not None
    available = screen.availableGeometry()

    window = MainWindow()

    assert window.width() <= available.width()
    assert window.height() <= available.height()
    assert window.minimumSizeHint().height() <= available.height()
    window.close()


def test_phase_controls_only_show_on_phase_tab():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()

    assert window.tabs.currentIndex() != window.phase_tab_index
    assert window.phase_controls_group.isHidden()

    window.tabs.setCurrentIndex(window.phase_tab_index)
    assert not window.phase_controls_group.isHidden()

    window.tabs.setCurrentIndex(0)
    assert window.phase_controls_group.isHidden()
    window.close()


def test_frequency_views_exposes_phase_controls_and_syncs_with_main_controls():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()

    assert window.frequency_period_spin is not None
    assert window.frequency_frequency_spin is not None
    assert window.frequency_repeats_spin is not None
    assert window.frequency_shift_slider is not None
    assert window.frequency_smooth_check is not None
    assert window.frequency_source_combo is not None

    window.frequency_period_spin.setValue(0.25)
    assert window.phase_period_spin.value() == pytest.approx(0.25)
    assert window.phase_frequency_spin.value() == pytest.approx(4.0)

    window.phase_repeats_spin.setValue(3)
    assert window.frequency_repeats_spin.value() == 3

    window.frequency_smooth_check.setChecked(True)
    assert window.smooth_check.isChecked()
    window.close()


def test_dft_finished_selects_visible_candidate_after_amplitude_sort(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    _skip_without_pyqtgraph(window.dft_plot)
    window._select_frequency(9.0, amplitude=5.0, label="old")
    periodogram = PeriodogramResult(
        frequency=np.array([1.0, 2.0, 9.0]),
        amplitude=np.array([0.2, 1.5, 5.0]),
        peaks=[],
        used_native=False,
    )
    candidates = [
        classify_peak(1.0, 0.2, window.engine.model, window.engine.light_curve.baseline),
        classify_peak(2.0, 1.5, window.engine.model, window.engine.light_curve.baseline),
    ]

    window._dft_finished(periodogram, candidates)

    assert window.selected_frequency == 2.0
    assert window.phase_period_spin.value() == 0.5
    assert _selected_marker_value(window.dft_plot) == 2.0
    assert window.prewhitening_panel.selected_candidate() == candidates[1]
    window.close()


def test_dft_finished_falls_back_to_best_frequency_without_candidates(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    _skip_without_pyqtgraph(window.dft_plot)
    window._select_frequency(7.0, amplitude=2.0, label="old")
    periodogram = PeriodogramResult(
        frequency=np.array([1.0, 2.0]),
        amplitude=np.array([0.3, 1.2]),
        peaks=[],
        used_native=False,
    )

    window._dft_finished(periodogram, [])

    assert window.selected_frequency == 2.0
    assert window.phase_period_spin.value() == 0.5
    assert _selected_marker_value(window.dft_plot) == 2.0
    window.close()


def test_main_window_selected_frequency_updates_phase_controls(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.model.add_independent(2.0)
    window._refresh_frequency_views()

    window._select_frequency(2.0, amplitude=0.3, label="f1", status="test")
    assert window.selected_frequency == 2.0
    assert window.phase_period_spin.value() == 0.5
    assert window.phase_period_spin.text() == "0.5"
    assert "f = 2" in window.selection_label.text()

    window.phase_period_spin.setValue(0.25)
    assert abs(window.phase_frequency_spin.value() - 4.0) < 1e-8
    window.close()


def test_load_file_with_existing_freq_starts_fit(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.write_freq_file(tmp_path / "freq")
    window = MainWindow()
    calls = []
    window.start_fit = lambda: calls.append("fit")
    window.start_dft = lambda: calls.append("dft")

    window.load_file(lc_path)

    assert calls == ["fit"]
    window.close()


def test_load_file_prompts_for_columns_when_table_has_extra_columns(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "wide.csv"
    lc_path.write_text("time,airmass,mag,err\n1.0,1.2,10.1,0.01\n2.0,1.3,10.4,0.02\n")

    class FakeColumnDialog:
        def __init__(self, table, parent=None, initial_columns=None):
            assert table.column_count == 4
            assert table.column_names == ["time", "airmass", "mag", "err"]

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted

        def selected_columns(self):
            return (0, 2, 3)

    monkeypatch.setattr(main_window_module, "ColumnSelectionDialog", FakeColumnDialog)
    window = MainWindow()
    calls = []
    window.start_dft = lambda: calls.append("dft")

    window.load_file(lc_path)

    assert window.engine is not None
    assert window.engine.light_curve.flux.tolist() == [10.1, 10.4]
    assert window.engine.light_curve.error.tolist() == [0.01, 0.02]
    assert window.magnitude_axis_check.isChecked()
    assert calls == ["dft"]
    window.close()


def test_magnitude_axis_toggle_inverts_all_brightness_plots():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()

    window.magnitude_axis_check.setChecked(True)

    assert window.lc_plot._y_inverted
    assert window.phase_plot._y_inverted
    assert window.frequency_lc_plot._y_inverted
    assert window.frequency_phase_plot._y_inverted

    window.magnitude_axis_check.setChecked(False)

    assert not window.lc_plot._y_inverted
    assert not window.phase_plot._y_inverted
    assert not window.frequency_lc_plot._y_inverted
    assert not window.frequency_phase_plot._y_inverted
    window.close()


def test_start_fit_does_not_refresh_periodogram_by_default(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window.start_fit()

    assert len(workers) == 1
    assert isinstance(workers[0], FitWorker)
    assert not workers[0].refine_frequencies
    assert not workers[0].refresh_periodogram
    window.close()


def test_start_fit_and_dft_refreshes_periodogram(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window.start_fit_and_dft()

    assert len(workers) == 1
    assert isinstance(workers[0], FitWorker)
    assert not workers[0].refine_frequencies
    assert workers[0].refresh_periodogram
    window.close()


def test_add_independent_fits_and_refreshes_dft(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window._add_independent(1.0)

    assert window.engine.model.bases == [1.0]
    assert len(workers) == 1
    assert isinstance(workers[0], FitWorker)
    assert workers[0].refresh_periodogram
    window.close()


def test_add_candidate_fits_and_refreshes_dft(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.add_independent(1.0)
    window.engine.add_independent(2.0)
    candidate = classify_peak(3.0, 0.5, window.engine.model, window.engine.light_curve.baseline)
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window._add_candidate(candidate)

    assert (1, 1) in window.engine.model.terms
    assert len(workers) == 1
    assert isinstance(workers[0], FitWorker)
    assert workers[0].refresh_periodogram
    window.close()


def test_remove_independent_frequency_removes_base_frequency(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.add_independent(1.0)
    window.engine.add_independent(2.0)
    window.engine.add_combination((1, 1))
    window._select_frequency(1.0, label="f1", base_index=0)
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window._remove_term(0)

    assert window.engine.model.bases == [2.0]
    assert window.engine.model.terms == [(1,)]
    assert window.selected_frequency is None
    assert len(workers) == 1
    assert isinstance(workers[0], FitWorker)
    assert not workers[0].refresh_periodogram
    window.close()


def test_remove_combination_keeps_base_frequencies(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.add_independent(1.0)
    window.engine.add_independent(2.0)
    combo_index = window.engine.add_combination((1, 1))
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window._remove_term(combo_index)

    assert window.engine.model.bases == [1.0, 2.0]
    assert window.engine.model.terms == [(1, 0), (0, 1)]
    assert len(workers) == 1
    window.close()


def test_remove_base_clears_selected_dependent_combination(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.add_independent(1.0)
    window.engine.add_independent(2.0)
    window.engine.add_combination((1, 1))
    window._frequency_row_selected(window.engine.model.rows()[2])
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window._remove_term(0)

    assert window.selected_frequency is None
    assert window.selected_coefficients is None
    assert len(workers) == 1
    window.close()


def test_edit_base_frequency_updates_selection_and_refreshes_dft(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.add_independent(2.0)
    window._select_frequency(2.0, label="f1", base_index=0, coefficients=(1,))
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window._edit_base_frequency(0, 1.0)

    assert window.engine.model.bases == [1.0]
    assert window.selected_frequency == 1.0
    assert window.phase_period_spin.value() == 1.0
    assert window.selected_base_index == 0
    assert len(workers) == 1
    assert isinstance(workers[0], FitWorker)
    assert workers[0].refresh_periodogram
    window.close()


def test_edit_base_frequency_updates_selected_combination_frequency(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.add_independent(2.0)
    window.engine.add_independent(3.0)
    window.engine.add_combination((1, 1))
    window._frequency_row_selected(window.engine.model.rows()[2])
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window._edit_base_frequency(0, 1.0)

    assert window.selected_frequency == 4.0
    assert window.selected_coefficients == (1, 1)
    assert window.phase_period_spin.value() == 0.25
    assert len(workers) == 1
    assert workers[0].refresh_periodogram
    window.close()


def test_start_dft_uses_fwpeaks_backend_by_default(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window.start_dft()

    assert len(workers) == 1
    assert isinstance(workers[0], DftWorker)
    assert workers[0].backend == "fwpeaks"
    window.close()


def test_start_dft_uses_python_backend_only_when_selected(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    index = window.dft_backend_combo.findData("python")
    assert index >= 0
    window.dft_backend_combo.setCurrentIndex(index)
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window.start_dft()

    assert len(workers) == 1
    assert isinstance(workers[0], DftWorker)
    assert workers[0].backend == "python"
    assert window.engine.state.settings.dft_backend == "python"
    window.close()


def test_dft_finished_updates_status_and_percent(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.statusBar().showMessage("Calculating DFT...")
    periodogram = PeriodogramResult(
        frequency=np.array([1.0, 2.0]),
        amplitude=np.array([0.3, 1.2]),
        peaks=[],
        used_native=True,
    )

    window._dft_finished(periodogram, [])

    assert window.dft_progress.value() == 100
    assert "100%" in window.progress_label.text()
    assert "Calculating DFT" not in window.statusBar().currentMessage()
    assert window.recalc_button.isEnabled()
    window.close()


def test_dft_plot_draws_snr5_threshold_and_peak_markers(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    _skip_without_pyqtgraph(window.dft_plot)
    periodogram = PeriodogramResult(
        frequency=np.array([1.0, 2.0, 3.0]),
        amplitude=np.array([0.2, 1.0, 0.5]),
        peaks=[{"frequency": 2.0, "amplitude": 1.0, "snr": 5.0}],
        used_native=True,
        noise_level=0.2,
    )

    window._plot_periodogram(periodogram)

    assert "dft_snr5" in window.dft_plot._items
    snr_line = window.dft_plot._items["dft_snr5"]
    assert float(snr_line.value()) == pytest.approx(1.0)
    assert snr_line.pen.style() == QtCore.Qt.PenStyle.DashLine
    assert "dft_peaks" in window.dft_plot._items

    window.dft_snr5_check.setChecked(False)
    assert "dft" in window.dft_plot._items
    assert "dft_snr5" not in window.dft_plot._items
    window.close()


def test_dft_overlay_toggles_do_not_change_selected_frequency(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.model.add_independent(1.0)
    _skip_without_pyqtgraph(window.dft_plot)
    periodogram = PeriodogramResult(
        frequency=np.array([1.0, 2.0]),
        amplitude=np.array([0.4, 0.8]),
        peaks=[{"frequency": 2.0, "amplitude": 0.8, "snr": 4.0}],
        used_native=True,
        noise_level=0.2,
    )

    window._plot_periodogram(periodogram)
    window._select_frequency(2.0, amplitude=0.8, label="peak")
    assert window.selected_frequency == 2.0
    assert _selected_marker_value(window.dft_plot) == 2.0
    assert len(window.dft_plot._markers) == 1

    window.dft_accepted_markers_check.setChecked(False)
    window.dft_peak_markers_check.setChecked(False)

    assert window.selected_frequency == 2.0
    assert _selected_marker_value(window.dft_plot) == 2.0
    assert len(window.dft_plot._markers) == 0
    assert "dft_peaks" not in window.dft_plot._items
    window.close()


def test_dft_plot_draws_daily_and_yearly_alias_markers_without_changing_selection(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.model.add_independent(2.0)
    _skip_without_pyqtgraph(window.dft_plot)
    window.dft_daily_aliases_check.setChecked(True)
    window.dft_yearly_aliases_check.setChecked(True)
    periodogram = PeriodogramResult(
        frequency=np.linspace(0.5, 3.5, 16),
        amplitude=np.linspace(0.1, 0.3, 16),
        peaks=[],
        used_native=True,
        noise_level=0.1,
    )

    window._plot_periodogram(periodogram)
    window._select_frequency(2.0, label="f1", base_index=0)

    marker_values = [float(marker.value()) for marker in window.dft_plot._markers]
    assert any(value == pytest.approx(1.0) for value in marker_values)
    assert any(value == pytest.approx(3.0) for value in marker_values)
    assert any(value == pytest.approx(2.0 - main_window_module.YEARLY_ALIAS_OFFSET) for value in marker_values)
    assert any(value == pytest.approx(2.0 + main_window_module.YEARLY_ALIAS_OFFSET) for value in marker_values)
    alias_pens = [
        marker.pen
        for marker in window.dft_plot._markers
        if marker.pen.style() in (QtCore.Qt.PenStyle.DashLine, QtCore.Qt.PenStyle.DotLine)
    ]
    assert alias_pens
    assert all(pen.widthF() >= 1.3 for pen in alias_pens)
    assert all(pen.color().alphaF() > 0.7 for pen in alias_pens)
    assert window.selected_frequency == 2.0
    assert _selected_marker_value(window.dft_plot) == 2.0

    window.dft_daily_aliases_check.setChecked(False)
    window.dft_yearly_aliases_check.setChecked(False)

    assert window.selected_frequency == 2.0
    assert _selected_marker_value(window.dft_plot) == 2.0
    window.close()


def test_dft_alias_markers_follow_selected_nonaccepted_frequency(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    _skip_without_pyqtgraph(window.dft_plot)
    window.dft_daily_aliases_check.setChecked(True)
    periodogram = PeriodogramResult(
        frequency=np.linspace(0.5, 3.5, 16),
        amplitude=np.linspace(0.1, 0.3, 16),
        peaks=[],
        used_native=True,
        noise_level=0.1,
    )
    window._plot_periodogram(periodogram)

    window._select_frequency(2.0, label="clicked")
    first_marker_values = [float(marker.value()) for marker in window.dft_plot._markers]
    assert any(value == pytest.approx(1.0) for value in first_marker_values)
    assert any(value == pytest.approx(3.0) for value in first_marker_values)

    window._select_frequency(2.2, label="clicked")
    second_marker_values = [float(marker.value()) for marker in window.dft_plot._markers]
    assert any(value == pytest.approx(1.2) for value in second_marker_values)
    assert any(value == pytest.approx(3.2) for value in second_marker_values)
    assert not any(value == pytest.approx(1.0) for value in second_marker_values)
    assert not any(value == pytest.approx(3.0) for value in second_marker_values)
    assert _selected_marker_value(window.dft_plot) == 2.2
    window.close()


def test_start_refine_fit_uses_refine_worker_without_auto_dft(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    workers = []
    window._run_worker = lambda worker, start_slot: workers.append(worker)

    window.start_refine_fit()

    assert len(workers) == 1
    assert isinstance(workers[0], FitWorker)
    assert workers[0].refine_frequencies
    assert not workers[0].refresh_periodogram
    window.close()


def test_fit_finished_without_periodogram_clears_candidates_but_keeps_stale_dft(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.add_independent(1.0)
    periodogram = PeriodogramResult(
        frequency=np.array([1.0, 2.0]),
        amplitude=np.array([0.3, 1.2]),
        peaks=[],
        used_native=False,
    )
    candidate = classify_peak(2.0, 1.2, window.engine.model, window.engine.light_curve.baseline)
    window._plot_periodogram(periodogram)
    window._set_candidates_and_select([candidate])

    fit = window.engine.fit_model()
    window._fit_finished(fit, None, [], False)

    assert window.prewhitening_panel.candidate_proxy.rowCount() == 0
    assert "dft" in window.dft_plot._items
    assert window.engine.last_periodogram is None
    assert "Previous DFT is stale" in window.statusBar().currentMessage()
    window.close()


def test_selected_component_source_uses_resid_file(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.model.add_independent(2.0)
    window.engine.state.work_dir.mkdir(parents=True, exist_ok=True)
    window.engine.component_path(0).write_text("0.0 11.0 0.1\n1.0 12.0 0.1\n")
    window._select_frequency(2.0, label="f1", base_index=0)
    index = window.phase_source_combo.findData("component")
    window.phase_source_combo.setCurrentIndex(index)

    lc = window._active_light_curve()

    assert lc is not None
    assert lc.flux.tolist() == [11.0, 12.0]
    window.phase_repeats_spin.setValue(4)
    folded = window._fold_active_light_curve(lc, 1.0)
    assert len(folded.phase) == 8
    window.close()


def test_phase_controls_accept_precise_manual_period_and_frequency(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    assert window.phase_period_spin.singleStep() == 0.00001
    assert window.phase_frequency_spin.singleStep() == 0.00001
    assert not window.phase_period_spin.keyboardTracking()
    assert not window.phase_frequency_spin.keyboardTracking()

    window.phase_period_spin.lineEdit().setText("0.123456789")
    window._mark_phase_edited("period", "0.123456789")
    window._phase_now_clicked()
    assert abs(window.phase_period_spin.value() - 0.123456789) < 1e-12
    assert abs(window.phase_frequency_spin.value() - (1.0 / 0.123456789)) < 1e-10
    assert "0.123456789" in window.phase_period_spin.text()

    window.phase_frequency_spin.lineEdit().setText("3.141592653")
    window._mark_phase_edited("frequency", "3.141592653")
    window._phase_now_clicked()
    assert abs(window.phase_frequency_spin.value() - 3.141592653) < 1e-12
    assert abs(window.phase_period_spin.value() - (1.0 / 3.141592653)) < 1e-10

    window.phase_period_spin.lineEdit().setText("1")
    window._mark_phase_edited("period", "0,25")
    window._phase_now_clicked()
    assert abs(window.phase_period_spin.value() - 0.25) < 1e-12
    assert abs(window.phase_frequency_spin.value() - 4.0) < 1e-12
    window.close()


def test_phase_scale_buttons_keep_period_and_frequency_synced(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)

    window._set_phase_values(period=0.25)
    window._scale_phase_period(2.0)
    assert abs(window.phase_period_spin.value() - 0.5) < 1e-12
    assert abs(window.phase_frequency_spin.value() - 2.0) < 1e-12

    window._scale_phase_frequency(0.5)
    assert abs(window.phase_frequency_spin.value() - 1.0) < 1e-12
    assert abs(window.phase_period_spin.value() - 1.0) < 1e-12
    window.close()


def test_phase_repeats_update_plotted_data(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    _skip_without_pyqtgraph(window.phase_plot)

    window._plot_phase(1.0)
    phase_item = window.phase_plot._items["phase"]
    x_one, _ = phase_item.getData()
    window.phase_repeats_spin.setValue(4)
    phase_item = window.phase_plot._items["phase"]
    x_four, _ = phase_item.getData()

    assert len(x_four) == len(x_one) * 4
    assert max(x_four) < 4.0
    window.close()


def test_phase_smooth_and_hide_raw_controls(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    _skip_without_pyqtgraph(window.phase_plot)

    window.smooth_check.setChecked(True)
    window._phase_current_period()
    assert "phase_smooth" in window.phase_plot._items
    assert "phase" in window.phase_plot._items
    assert window.phase_plot._items["phase_smooth"].opts["pen"].widthF() >= 3.0

    window.hide_phase_check.setChecked(True)
    window._phase_current_period()
    assert "phase_smooth" in window.phase_plot._items
    assert "phase" not in window.phase_plot._items

    window.smooth_check.setChecked(False)
    window._phase_current_period()
    assert "phase_smooth" not in window.phase_plot._items
    window.close()


def test_phase_sincos_fit_includes_accepted_harmonics(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.model.add_independent(2.0)
    window.engine.model.add_combination((2,))
    window._current_fit = FitResult(
        residuals=window.engine.light_curve,
        model=window.engine.model.clone(),
        converged=True,
        fourier_terms=(
            FourierTerm((1,), 2.0, 1.0, 0.2, 1.0198, 0.1974),
            FourierTerm((2,), 4.0, 0.4, 0.1, 0.4123, 0.2450),
        ),
    )
    window._select_frequency(2.0, label="f1", base_index=0)
    _skip_without_pyqtgraph(window.phase_plot)

    window.phase_fit_check.setChecked(True)
    window._phase_current_period()

    assert window._phase_fit_harmonics() == (1, 2)
    assert "phase_fit" in window.phase_plot._items
    assert window.phase_plot._items["phase_fit"].opts["pen"].widthF() >= 2.5
    _, phase_fit_flux = window.phase_plot._items["phase_fit"].getData()
    assert phase_fit_flux[0] == pytest.approx(0.3)
    window.close()


def test_phase_sincos_fit_uses_harmonics_relative_to_current_phase_frequency(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.model.add_independent(2.0)
    window.engine.model.add_combination((2,))
    window._current_fit = FitResult(
        residuals=window.engine.light_curve,
        model=window.engine.model.clone(),
        converged=True,
        fourier_terms=(FourierTerm((1,), 2.0, 1.0, 0.0, 1.0, 0.0),),
    )
    window._set_phase_values(frequency=4.0)

    assert window._phase_fit_harmonics() == (1,)
    window.close()


def test_frequency_view_sincos_fit_toggle_draws_time_and_phase_fit(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    window.engine.model.add_independent(2.0)
    window.engine.model.add_combination((2,))
    window._current_fit = FitResult(
        residuals=window.engine.light_curve,
        model=window.engine.model.clone(),
        converged=True,
        fourier_terms=(
            FourierTerm((1,), 2.0, 1.0, 0.2, 1.0198, 0.1974),
            FourierTerm((2,), 4.0, 0.4, 0.1, 0.4123, 0.2450),
        ),
    )
    window._select_frequency(2.0, label="f1", base_index=0, coefficients=(1,))
    _skip_without_pyqtgraph(window.frequency_lc_plot)
    _skip_without_pyqtgraph(window.frequency_phase_plot)
    assert not window.phase_fit_check.isChecked()

    window.frequency_fit_check.setChecked(True)
    window._update_frequency_preview(2.0)

    assert "lc_fit" in window.frequency_lc_plot._items
    assert "phase_fit" in window.frequency_phase_plot._items
    assert "phase_fit" not in window.phase_plot._items
    assert window.frequency_lc_plot._items["lc_fit"].opts["pen"].widthF() >= 2.4
    assert window.frequency_phase_plot._items["phase_fit"].opts["pen"].widthF() >= 2.5
    _, phase_fit_flux = window.frequency_phase_plot._items["phase_fit"].getData()
    assert phase_fit_flux[0] == pytest.approx(0.3)

    window.frequency_fit_check.setChecked(False)

    assert "lc_fit" not in window.frequency_lc_plot._items
    assert "phase_fit" not in window.frequency_phase_plot._items
    window.close()


def test_phase_errors_toggle_adds_error_bars(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    _skip_without_pyqtgraph(window.phase_plot)

    window.phase_errors_check.setChecked(True)
    window._phase_current_period()
    assert "phase_errors" in window.phase_plot._items

    window.phase_errors_check.setChecked(False)
    window._phase_current_period()
    assert "phase_errors" not in window.phase_plot._items
    window.close()


def test_light_curve_errors_are_independent_from_phase_errors(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text(FIXTURE.read_text())
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    _skip_without_pyqtgraph(window.lc_plot)

    window.phase_errors_check.setChecked(True)
    window._plot_light_curve(window.engine.light_curve)
    assert "lc_errors" not in window.lc_plot._items

    window.light_curve_errors_check.setChecked(True)
    assert "lc_errors" in window.lc_plot._items
    window.close()


def test_sigma_clip_uses_dialog_selected_rejections(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    lc_path = tmp_path / "sample.dat"
    lc_path.write_text("0 1 0.1\n1 10 0.1\n2 1 0.1\n3 -9 0.1\n")
    window = MainWindow()
    window.engine = PrewhiteningEngine.from_file(lc_path)
    light_curve = window.engine.light_curve
    keep_mask = np.array([True, False, True, False])
    result = SigmaClipResult(
        cleaned=light_curve.masked(keep_mask),
        rejected=light_curve.masked(~keep_mask),
        keep_mask=keep_mask,
        sigma=3.5,
    )

    class FakeSigmaDialog:
        def __init__(self, light_curve_arg, result_arg, parent=None, *, y_inverted=False):
            assert light_curve_arg is light_curve
            assert result_arg is result

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted

        def selected_reject_mask(self):
            return np.array([False, False, False, True])

    monkeypatch.setattr(main_window_module, "sigma_clip_light_curve", lambda light_curve_arg, sigma: result)
    monkeypatch.setattr(main_window_module, "SigmaClipDialog", FakeSigmaDialog)
    dft_calls = []
    window.start_dft = lambda: dft_calls.append("dft")

    window._sigma_clip()

    assert window.engine.light_curve.time.tolist() == light_curve.time[:3].tolist()
    assert dft_calls == ["dft"]
    window.close()


def test_tdfd_plot_uses_distinct_colors_points_and_toggleable_legend():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    _skip_without_pyqtgraph(window.tdfd_panel.plot)
    residuals = LightCurve(
        time=np.array([0.0, 1.0]),
        flux=np.array([0.1, -0.1]),
        error=np.array([0.01, 0.01]),
    )
    result = TdfdResult(
        bins=[
            TdfdBin(0.0, 1.0, 0.5, np.array([1.0, 2.0]), np.array([0.2, 0.3]), np.array([0.0, 0.0]), 0.1, 20),
            TdfdBin(1.0, 2.0, 1.5, np.array([1.0, 2.0]), np.array([0.4, 0.6]), np.array([0.0, 0.0]), 0.2, 20),
        ],
        residuals=residuals,
    )

    window.tdfd_panel.set_result(result)

    assert "f1" in window.tdfd_panel.plot._items
    assert "f2" in window.tdfd_panel.plot._items
    assert "f1_points" in window.tdfd_panel.plot._items
    assert "f2_points" in window.tdfd_panel.plot._items
    color_1 = window.tdfd_panel.plot._items["f1"].opts["pen"].color().name()
    color_2 = window.tdfd_panel.plot._items["f2"].opts["pen"].color().name()
    assert color_1 != color_2
    assert window.tdfd_panel.plot._legend.isVisible()

    window.tdfd_panel.legend_check.setChecked(False)

    assert not window.tdfd_panel.plot._legend.isVisible()
    assert "f1" in window.tdfd_panel.plot._items
    window.close()
