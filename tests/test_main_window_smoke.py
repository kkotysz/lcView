import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6 import QtWidgets

from lcview.core.frequency_model import FrequencyModel
from lcview.core.prewhitening import PrewhiteningEngine
from lcview.ui.main_window import MainWindow


FIXTURE = Path(__file__).parent / "fixtures" / "sample_light_curve.dat"


def _skip_without_pyqtgraph(plot) -> None:
    if plot._plot is None:
        pytest.skip("pyqtgraph is not installed")


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

    window.hide_phase_check.setChecked(True)
    window._phase_current_period()
    assert "phase_smooth" in window.phase_plot._items
    assert "phase" not in window.phase_plot._items

    window.smooth_check.setChecked(False)
    window._phase_current_period()
    assert "phase_smooth" not in window.phase_plot._items
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
