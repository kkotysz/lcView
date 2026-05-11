"""Main PySide6 application window."""

from __future__ import annotations

from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
import numpy as np

from lcview.core.combinations import FrequencyCandidate, classify_peak
from lcview.core.lightcurve import LightCurve
from lcview.core.phase import FoldedLightCurve, boxcar_smooth, fold_light_curve
from lcview.core.prewhitening import PrewhiteningEngine
from lcview.core.sigma_clip import sigma_clip_light_curve
from lcview.core.tdfd import run_tdfd
from lcview.display import frequency_text, period_text_from_frequency, sig_text
from .detrend_dialog import DetrendDialog
from .plots import PlotPane
from .prewhitening_panel import PrewhiteningPanel
from .tdfd_panel import TdfdPanel
from .widgets import SignificantDoubleSpinBox


class DftWorker(QtCore.QObject):
    progress = QtCore.Signal(int, str)
    finished = QtCore.Signal(object, object)
    failed = QtCore.Signal(str)

    def __init__(self, engine: PrewhiteningEngine) -> None:
        super().__init__()
        self.engine = engine

    @QtCore.Slot()
    def run(self) -> None:
        try:
            periodogram = self.engine.compute_periodogram(progress_callback=self.progress.emit)
            self.finished.emit(periodogram, self.engine.last_candidates)
        except Exception as exc:
            self.failed.emit(str(exc))


class FitWorker(QtCore.QObject):
    progress = QtCore.Signal(int, str)
    finished = QtCore.Signal(object, object, object)
    failed = QtCore.Signal(str)

    def __init__(self, engine: PrewhiteningEngine) -> None:
        super().__init__()
        self.engine = engine

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self.progress.emit(0, "Fitting model")
            fit = self.engine.fit_model()
            self.progress.emit(65, "Refreshing DFT")
            fit_progress = lambda percent, message: self.progress.emit(65 + int(percent * 0.35), message)
            periodogram = self.engine.compute_periodogram(fit.residuals, progress_callback=fit_progress)
            candidates = self.engine.last_candidates
            self.finished.emit(fit, periodogram, candidates)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, path: str | Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("lcView prewhitening")
        self.resize(1440, 900)
        self.engine: PrewhiteningEngine | None = None
        self._thread: QtCore.QThread | None = None
        self._worker: QtCore.QObject | None = None
        self.selected_frequency: float | None = None
        self.selected_base_index: int | None = None
        self.selected_amplitude: float | None = None
        self._syncing_phase_controls = False
        self._phase_last_edited = "period"
        self._pending_phase_text: dict[str, str | None] = {"period": None, "frequency": None}
        self._current_light_curve_plot: LightCurve | None = None

        self._build_ui()
        if path is not None:
            self.load_file(Path(path))

    def _build_ui(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        tools_menu = self.menuBar().addMenu("Tools")
        open_action = QtGui.QAction("Open light curve", self)
        open_action.triggered.connect(self.open_file)
        export_action = QtGui.QAction("Export legacy files", self)
        export_action.triggered.connect(self._export)
        quit_action = QtGui.QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        build_action = QtGui.QAction("Build native tools", self)
        build_action.triggered.connect(self.build_native_tools)
        file_menu.addAction(open_action)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        tools_menu.addAction(build_action)

        central = QtWidgets.QSplitter()
        self.setCentralWidget(central)

        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        form = QtWidgets.QFormLayout()
        self.start_spin = SignificantDoubleSpinBox()
        self.start_spin.setRange(0, 100000)
        self.start_spin.setValue(0.0)
        self.end_spin = SignificantDoubleSpinBox()
        self.end_spin.setRange(0.001, 100000)
        self.end_spin.setValue(80.0)
        self.precision_spin = QtWidgets.QDoubleSpinBox()
        self.precision_spin.setRange(1, 500)
        self.precision_spin.setValue(10)
        self.recalc_button = QtWidgets.QPushButton("Calculate DFT")
        form.addRow("Start frequency", self.start_spin)
        form.addRow("End frequency", self.end_spin)
        form.addRow("Precision", self.precision_spin)
        left_layout.addLayout(form)
        left_layout.addWidget(self.recalc_button)
        self.dft_progress = QtWidgets.QProgressBar()
        self.dft_progress.setRange(0, 100)
        self.dft_progress.setValue(0)
        self.dft_progress.setTextVisible(True)
        self.progress_label = QtWidgets.QLabel("Idle")
        left_layout.addWidget(self.dft_progress)
        left_layout.addWidget(self.progress_label)
        selection_group = QtWidgets.QGroupBox("Selected frequency")
        selection_layout = QtWidgets.QVBoxLayout(selection_group)
        self.selection_label = QtWidgets.QLabel("No frequency selected")
        self.selection_label.setWordWrap(True)
        selection_layout.addWidget(self.selection_label)
        left_layout.addWidget(selection_group)

        phase_group = QtWidgets.QGroupBox("Phase controls")
        phase_layout = QtWidgets.QFormLayout(phase_group)
        self.phase_period_spin = SignificantDoubleSpinBox(digits=10)
        self.phase_period_spin.setRange(0.0000001, 1_000_000.0)
        self.phase_period_spin.setSingleStep(0.00001)
        self.phase_period_spin.setKeyboardTracking(False)
        self.phase_period_spin.setValue(1.0)
        self.phase_frequency_spin = SignificantDoubleSpinBox(digits=10)
        self.phase_frequency_spin.setRange(0.0000001, 1_000_000.0)
        self.phase_frequency_spin.setSingleStep(0.00001)
        self.phase_frequency_spin.setKeyboardTracking(False)
        self.phase_frequency_spin.setValue(1.0)
        period_controls = QtWidgets.QHBoxLayout()
        self.period_double_button = QtWidgets.QPushButton("x2")
        self.period_half_button = QtWidgets.QPushButton("/2")
        self.period_double_button.setToolTip("Fold with twice the period")
        self.period_half_button.setToolTip("Fold with half the period")
        period_controls.addWidget(self.phase_period_spin, 1)
        period_controls.addWidget(self.period_double_button)
        period_controls.addWidget(self.period_half_button)
        frequency_controls = QtWidgets.QHBoxLayout()
        self.frequency_double_button = QtWidgets.QPushButton("x2")
        self.frequency_half_button = QtWidgets.QPushButton("/2")
        self.frequency_double_button.setToolTip("Fold with twice the frequency")
        self.frequency_half_button.setToolTip("Fold with half the frequency")
        frequency_controls.addWidget(self.phase_frequency_spin, 1)
        frequency_controls.addWidget(self.frequency_double_button)
        frequency_controls.addWidget(self.frequency_half_button)
        self.phase_repeats_spin = QtWidgets.QSpinBox()
        self.phase_repeats_spin.setRange(1, 4)
        self.phase_repeats_spin.setValue(1)
        self.phase_shift_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.phase_shift_slider.setRange(-500, 500)
        self.phase_shift_slider.setValue(0)
        self.phase_shift_label = QtWidgets.QLabel("+0.000")
        shift_controls = QtWidgets.QHBoxLayout()
        shift_controls.addWidget(self.phase_shift_slider, 1)
        shift_controls.addWidget(self.phase_shift_label)
        self.smooth_check = QtWidgets.QCheckBox("Smooth")
        self.smooth_window_spin = QtWidgets.QSpinBox()
        self.smooth_window_spin.setRange(1, 1_000_000)
        self.smooth_window_spin.setValue(3)
        self.hide_phase_check = QtWidgets.QCheckBox("Hide raw phase")
        self.phase_errors_check = QtWidgets.QCheckBox("Errors")
        smooth_controls = QtWidgets.QHBoxLayout()
        smooth_controls.addWidget(self.smooth_check)
        smooth_controls.addWidget(QtWidgets.QLabel("Window"))
        smooth_controls.addWidget(self.smooth_window_spin)
        smooth_controls.addStretch(1)
        self.phase_source_combo = QtWidgets.QComboBox()
        self.phase_source_combo.addItem("Residual", "residual")
        self.phase_source_combo.addItem("Original", "original")
        self.phase_source_combo.addItem("Selected component (resid0X)", "component")
        phase_buttons = QtWidgets.QHBoxLayout()
        self.use_selected_button = QtWidgets.QPushButton("Use selected")
        self.phase_now_button = QtWidgets.QPushButton("Phase now")
        phase_buttons.addWidget(self.use_selected_button)
        phase_buttons.addWidget(self.phase_now_button)
        phase_layout.addRow("Period [d]", period_controls)
        phase_layout.addRow("Frequency [1/d]", frequency_controls)
        phase_layout.addRow("Phases", self.phase_repeats_spin)
        phase_layout.addRow("Shift [cycle]", shift_controls)
        phase_layout.addRow(smooth_controls)
        phase_layout.addRow(self.hide_phase_check)
        phase_layout.addRow(self.phase_errors_check)
        phase_layout.addRow("Source", self.phase_source_combo)
        phase_layout.addRow(phase_buttons)
        left_layout.addWidget(phase_group)

        self.prewhitening_panel = PrewhiteningPanel()
        left_layout.addWidget(self.prewhitening_panel, 1)
        central.addWidget(left)

        tabs = QtWidgets.QTabWidget()
        self.lc_plot = PlotPane("Light curve")
        self.lc_plot.set_labels("Flux", "Time")
        self.dft_plot = PlotPane("DFT")
        self.dft_plot.set_labels("Amplitude", "Frequency")
        self.phase_plot = PlotPane("Phase")
        self.phase_plot.set_labels("Flux", "Phase")
        self.tdfd_panel = TdfdPanel()
        freq_view = QtWidgets.QWidget()
        freq_view_layout = QtWidgets.QVBoxLayout(freq_view)
        freq_controls = QtWidgets.QHBoxLayout()
        self.frequency_view_combo = QtWidgets.QComboBox()
        self.frequency_view_combo.setMinimumWidth(240)
        freq_controls.addWidget(QtWidgets.QLabel("Frequency"))
        freq_controls.addWidget(self.frequency_view_combo, 1)
        freq_view_layout.addLayout(freq_controls)
        freq_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.frequency_lc_plot = PlotPane("Selected frequency light curve")
        self.frequency_lc_plot.set_labels("Flux", "Time")
        self.frequency_phase_plot = PlotPane("Selected frequency phase")
        self.frequency_phase_plot.set_labels("Flux", "Phase")
        freq_split.addWidget(self.frequency_lc_plot)
        freq_split.addWidget(self.frequency_phase_plot)
        freq_view_layout.addWidget(freq_split, 1)
        self.petersen_text = QtWidgets.QPlainTextEdit()
        self.petersen_text.setReadOnly(True)
        tabs.addTab(self.lc_plot, "Light curve")
        tabs.addTab(self.dft_plot, "DFT")
        tabs.addTab(self.phase_plot, "Phase")
        tabs.addTab(freq_view, "Frequency views")
        tabs.addTab(self.tdfd_panel, "TDFD")
        tabs.addTab(self.petersen_text, "Petersen")
        central.addWidget(tabs)
        central.setSizes([460, 980])

        self.recalc_button.clicked.connect(self.start_dft)
        self.phase_period_spin.valueChanged.connect(self._phase_period_changed)
        self.phase_frequency_spin.valueChanged.connect(self._phase_frequency_changed)
        self.phase_period_spin.editingFinished.connect(self._phase_period_edited)
        self.phase_frequency_spin.editingFinished.connect(self._phase_frequency_edited)
        self.phase_period_spin.lineEdit().textEdited.connect(lambda text: self._mark_phase_edited("period", text))
        self.phase_frequency_spin.lineEdit().textEdited.connect(lambda text: self._mark_phase_edited("frequency", text))
        self.period_double_button.clicked.connect(lambda: self._scale_phase_period(2.0))
        self.period_half_button.clicked.connect(lambda: self._scale_phase_period(0.5))
        self.frequency_double_button.clicked.connect(lambda: self._scale_phase_frequency(2.0))
        self.frequency_half_button.clicked.connect(lambda: self._scale_phase_frequency(0.5))
        self.phase_repeats_spin.valueChanged.connect(lambda _: self._phase_current_period())
        self.phase_shift_slider.valueChanged.connect(self._phase_shift_changed)
        self.smooth_check.stateChanged.connect(lambda _: self._phase_current_period())
        self.smooth_window_spin.valueChanged.connect(lambda _: self._phase_current_period())
        self.hide_phase_check.stateChanged.connect(lambda _: self._phase_current_period())
        self.phase_errors_check.stateChanged.connect(lambda _: self._phase_current_period())
        self.phase_source_combo.currentIndexChanged.connect(lambda _: self._phase_now_clicked())
        self.use_selected_button.clicked.connect(self._use_selected_period)
        self.phase_now_button.clicked.connect(self._phase_now_clicked)
        self.frequency_view_combo.currentIndexChanged.connect(self._frequency_view_changed)
        self.start_spin.valueChanged.connect(self._settings_changed)
        self.end_spin.valueChanged.connect(self._settings_changed)
        self.precision_spin.valueChanged.connect(self._settings_changed)
        self.dft_plot.clicked_x.connect(self._dft_clicked)
        self.prewhitening_panel.frequency_selected.connect(self._frequency_row_selected)
        self.prewhitening_panel.candidate_selected.connect(self._candidate_selected)
        self.prewhitening_panel.add_independent_requested.connect(self._add_independent)
        self.prewhitening_panel.add_candidate_requested.connect(self._add_candidate)
        self.prewhitening_panel.remove_term_requested.connect(self._remove_term)
        self.prewhitening_panel.clear_frequencies_requested.connect(self._clear_frequencies)
        self.prewhitening_panel.toggle_term_requested.connect(self._toggle_term)
        self.prewhitening_panel.fit_requested.connect(self.start_fit)
        self.prewhitening_panel.undo_requested.connect(self._undo)
        self.prewhitening_panel.redo_requested.connect(self._redo)
        self.prewhitening_panel.export_requested.connect(self._export)
        self.prewhitening_panel.detrend_requested.connect(self._detrend)
        self.prewhitening_panel.sigma_clip_requested.connect(self._sigma_clip)
        self.prewhitening_panel.tdfd_requested.connect(lambda: self._run_tdfd(self.tdfd_panel.bins_spin.value()))
        self.tdfd_panel.run_requested.connect(self._run_tdfd)

    @QtCore.Slot()
    def open_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open light curve")
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        try:
            self.engine = PrewhiteningEngine.from_file(path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(exc))
            return
        settings = self.engine.state.settings
        self.start_spin.setValue(settings.start_frequency)
        self.end_spin.setValue(settings.end_frequency)
        self.precision_spin.setValue(settings.precision)
        self._set_default_smooth_window(self.engine.light_curve)
        self._refresh_frequency_views()
        self._plot_light_curve(self.engine.light_curve)
        self.selected_frequency = None
        self.selected_base_index = None
        self.dft_plot.clear_selected_marker()
        self.statusBar().showMessage(f"Loaded {path}")
        if self.engine.model.active_terms():
            self.start_fit()
        else:
            self.start_dft()

    def _settings_changed(self) -> None:
        if self.engine is None:
            return
        self.engine.state.settings.start_frequency = self.start_spin.value()
        self.engine.state.settings.end_frequency = self.end_spin.value()
        self.engine.state.settings.precision = self.precision_spin.value()
        self.engine.save_state()

    def _run_worker(self, worker: QtCore.QObject, start_slot) -> None:
        if self._thread is not None:
            self.statusBar().showMessage("A calculation is already running")
            return
        self._thread = QtCore.QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(start_slot)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _finish_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread = None
            self._worker = None

    @QtCore.Slot()
    def start_dft(self) -> None:
        if self.engine is None:
            return
        self._settings_changed()
        self.recalc_button.setEnabled(False)
        self.dft_progress.setValue(0)
        self.progress_label.setText("Starting DFT")
        self.statusBar().showMessage("Calculating DFT...")
        worker = DftWorker(self.engine)
        worker.progress.connect(self._progress_changed)
        worker.finished.connect(self._dft_finished)
        worker.failed.connect(self._worker_failed)
        self._run_worker(worker, worker.run)

    @QtCore.Slot()
    def start_fit(self) -> None:
        if self.engine is None:
            return
        self.recalc_button.setEnabled(False)
        self.dft_progress.setValue(0)
        self.progress_label.setText("Starting fit")
        self.statusBar().showMessage("Fitting prewhitening model...")
        worker = FitWorker(self.engine)
        worker.progress.connect(self._progress_changed)
        worker.finished.connect(self._fit_finished)
        worker.failed.connect(self._worker_failed)
        self._run_worker(worker, worker.run)

    @QtCore.Slot(object, object)
    def _dft_finished(self, periodogram, candidates) -> None:
        self._finish_thread()
        self.recalc_button.setEnabled(True)
        self._progress_changed(100, "DFT ready")
        self._plot_periodogram(periodogram)
        self.prewhitening_panel.set_candidates(candidates)
        if periodogram.best_frequency:
            self._select_frequency(periodogram.best_frequency, amplitude=float(np.max(periodogram.amplitude)), label="best peak")

    @QtCore.Slot(object, object, object)
    def _fit_finished(self, fit, periodogram, candidates) -> None:
        self._finish_thread()
        self.recalc_button.setEnabled(True)
        self._progress_changed(100, "Fit ready")
        self._refresh_frequency_views()
        self._plot_light_curve(fit.residuals)
        self._plot_periodogram(periodogram)
        self.prewhitening_panel.set_candidates(candidates)
        if not candidates:
            self.statusBar().showMessage("Fit ready" if fit.converged else "Fit finished with convergence warning")

    @QtCore.Slot(str)
    def _worker_failed(self, message: str) -> None:
        self._finish_thread()
        self.recalc_button.setEnabled(True)
        self.progress_label.setText("Failed")
        self.dft_progress.setValue(0)
        QtWidgets.QMessageBox.critical(self, "Calculation failed", message)

    @QtCore.Slot(int, str)
    def _progress_changed(self, percent: int, message: str) -> None:
        self.dft_progress.setValue(max(0, min(100, int(percent))))
        self.progress_label.setText(message)

    def _plot_light_curve(self, light_curve: LightCurve) -> None:
        self._current_light_curve_plot = light_curve
        self.lc_plot.plot_points("lc", light_curve.time, light_curve.flux, size=3)
        if self.phase_errors_check.isChecked():
            self.lc_plot.plot_error_bars("lc_errors", light_curve.time, light_curve.flux, light_curve.error)
        else:
            self.lc_plot.clear_item("lc_errors")
        self.lc_plot.auto_range()

    def _plot_periodogram(self, periodogram) -> None:
        self.dft_plot.plot_line("dft", periodogram.frequency, periodogram.amplitude)
        self._refresh_markers()
        self.dft_plot.auto_range()

    def _active_light_curve(self) -> LightCurve | None:
        if self.engine is None:
            return None
        source = self.phase_source_combo.currentData()
        if source == "original":
            return self.engine.light_curve
        if source == "component":
            component = self._selected_component_light_curve()
            if component is not None:
                return component
        return self.engine.residuals or self.engine.light_curve

    def _selected_component_light_curve(self) -> LightCurve | None:
        if self.engine is None or self.selected_base_index is None:
            return None
        return self.engine.component_light_curve(self.selected_base_index)

    def _plot_phase(self, period: float) -> None:
        lc = self._active_light_curve()
        if lc is None or period <= 0:
            return
        folded = self._fold_active_light_curve(lc, period)
        self._draw_phase_plot(self.phase_plot, folded)
        self.phase_plot.auto_range()

    def _set_default_smooth_window(self, light_curve: LightCurve) -> None:
        self.smooth_window_spin.setValue(max(3, len(light_curve.time) // 30))

    def _phase_shift_fraction(self) -> float:
        return self.phase_shift_slider.value() / 1000.0

    def _fold_active_light_curve(self, light_curve: LightCurve, period: float) -> FoldedLightCurve:
        return fold_light_curve(
            light_curve,
            period,
            repeats=self.phase_repeats_spin.value(),
            shift_fraction=self._phase_shift_fraction(),
        )

    def _draw_phase_plot(self, plot: PlotPane, folded: FoldedLightCurve) -> None:
        show_raw = not self.hide_phase_check.isChecked()
        if show_raw:
            plot.plot_points("phase", folded.phase, folded.flux, size=3)
            if self.phase_errors_check.isChecked():
                plot.plot_error_bars("phase_errors", folded.phase, folded.flux, folded.error)
            else:
                plot.clear_item("phase_errors")
        else:
            plot.clear_item("phase")
            plot.clear_item("phase_errors")
        if self.smooth_check.isChecked():
            smoothed = boxcar_smooth(folded.flux, self.smooth_window_spin.value())
            plot.plot_line("phase_smooth", folded.phase, smoothed, color="#16a34a")
        else:
            plot.clear_item("phase_smooth")

    def _refresh_frequency_views(self) -> None:
        if self.engine is None:
            return
        self.prewhitening_panel.set_frequency_model(self.engine.model)
        self._refresh_frequency_view_combo()
        self._refresh_markers()
        self._refresh_petersen()

    def _refresh_markers(self) -> None:
        if self.engine is None:
            return
        self.dft_plot.clear_markers()
        for row in self.engine.model.rows():
            if row["enabled"]:
                self.dft_plot.add_vertical_marker(row["frequency"], row["label"])
        if self.selected_frequency is not None:
            self.dft_plot.set_selected_marker(self.selected_frequency, frequency_text(self.selected_frequency))

    def _refresh_petersen(self) -> None:
        if self.engine is None:
            return
        bases = self.engine.model.bases
        lines = ["# longer_period shorter/longer label"]
        for i, first in enumerate(bases):
            for j, second in enumerate(bases):
                if i >= j or first <= 0 or second <= 0:
                    continue
                p1, p2 = 1.0 / first, 1.0 / second
                longer, shorter = max(p1, p2), min(p1, p2)
                lines.append(f"{sig_text(longer):>8s} {sig_text(shorter / longer):>8s} f{i + 1}/f{j + 1}")
        self.petersen_text.setPlainText("\n".join(lines))

    @QtCore.Slot(float)
    def _dft_clicked(self, frequency: float) -> None:
        if self.engine is None or self.engine.last_periodogram is None:
            return
        pg = self.engine.last_periodogram
        idx = int(np.argmin(np.abs(pg.frequency - frequency)))
        candidate = classify_peak(pg.frequency[idx], pg.amplitude[idx], self.engine.model, self.engine.light_curve.baseline)
        self.prewhitening_panel.set_candidates([candidate, *self.engine.last_candidates[:20]])
        self._select_frequency(
            candidate.frequency,
            amplitude=candidate.amplitude,
            label=candidate.label,
            status=f"{candidate.kind}, {candidate.resolved}",
            snr=candidate.snr,
            rayleigh=candidate.rayleigh,
        )
        self.statusBar().showMessage(f"{frequency_text(candidate.frequency)}: {candidate.kind}, {candidate.resolved}")

    def _candidate_selected(self, candidate: FrequencyCandidate) -> None:
        self._select_frequency(
            candidate.frequency,
            amplitude=candidate.amplitude,
            label=candidate.label,
            status=f"{candidate.kind}, {candidate.resolved}",
            snr=candidate.snr,
            rayleigh=candidate.rayleigh,
        )

    def _frequency_row_selected(self, row: dict) -> None:
        self._select_frequency(
            row["frequency"],
            label=row["label"],
            status=row["kind"],
            base_index=self._base_index_from_coefficients(row["coefficients"]),
        )

    def _base_index_from_coefficients(self, coefficients: tuple[int, ...]) -> int | None:
        nonzero = [(idx, value) for idx, value in enumerate(coefficients) if value]
        if len(nonzero) == 1:
            return nonzero[0][0]
        return None

    def _base_index_for_frequency(self, frequency: float) -> int | None:
        if self.engine is None:
            return None
        tolerance = max(1e-8, abs(frequency) * 1e-6)
        for row in self.engine.model.rows():
            base_index = self._base_index_from_coefficients(row["coefficients"])
            if base_index is not None and abs(row["frequency"] - frequency) <= tolerance:
                return base_index
        return None

    def _select_frequency(
        self,
        frequency: float,
        *,
        amplitude: float | None = None,
        label: str = "",
        status: str = "",
        snr: float | None = None,
        rayleigh: float | None = None,
        base_index: int | None = None,
    ) -> None:
        if frequency <= 0:
            return
        self.selected_frequency = float(frequency)
        self.selected_base_index = base_index if base_index is not None else self._base_index_for_frequency(frequency)
        self.selected_amplitude = amplitude
        self.dft_plot.set_selected_marker(self.selected_frequency, label or frequency_text(self.selected_frequency))
        self._set_phase_values(period=1.0 / self.selected_frequency)
        self._update_selection_status(status=status, label=label, snr=snr, rayleigh=rayleigh)
        self._phase_current_period()
        self._update_frequency_preview(self.selected_frequency)

    def _update_selection_status(
        self,
        *,
        status: str = "",
        label: str = "",
        snr: float | None = None,
        rayleigh: float | None = None,
    ) -> None:
        if self.selected_frequency is None:
            self.selection_label.setText("No frequency selected")
            self.statusBar().showMessage("No frequency selected")
            return
        period = 1.0 / self.selected_frequency
        amp = "" if self.selected_amplitude is None else f"\nAmplitude: {self.selected_amplitude:.5f}"
        amp_status = "" if self.selected_amplitude is None else f", amp {self.selected_amplitude:.5f}"
        snr_text = "" if snr is None else f"\nS/N: {snr:.2f}"
        rayleigh_text = "" if rayleigh is None else f"\nRayleigh: {sig_text(rayleigh)}"
        detail = f", {label}" if label else ""
        extra = f", {status}" if status else ""
        self.selection_label.setText(
            f"f = {frequency_text(self.selected_frequency)} 1/d\n"
            f"P = {sig_text(period)} d"
            f"{amp}{snr_text}{rayleigh_text}\n"
            f"Status: {(status or 'selected')}{detail}"
        )
        self.statusBar().showMessage(
            f"Selected f={frequency_text(self.selected_frequency)}  P={sig_text(period)} d{amp_status}{detail}{extra}"
        )

    def _set_phase_values(self, *, period: float | None = None, frequency: float | None = None) -> None:
        if period is None and frequency is None:
            return
        if frequency is None:
            frequency = 1.0 / period
        if period is None:
            period = 1.0 / frequency
        self._syncing_phase_controls = True
        self.phase_period_spin.setValue(period)
        self.phase_frequency_spin.setValue(frequency)
        self._syncing_phase_controls = False
        self._pending_phase_text["period"] = None
        self._pending_phase_text["frequency"] = None

    def _phase_period_changed(self, period: float) -> None:
        if self._syncing_phase_controls or period <= 0:
            return
        self._phase_last_edited = "period"
        self._set_phase_values(period=period)
        self._phase_current_period()

    def _phase_frequency_changed(self, frequency: float) -> None:
        if self._syncing_phase_controls or frequency <= 0:
            return
        self._phase_last_edited = "frequency"
        self._set_phase_values(frequency=frequency)
        self._phase_current_period()

    def _mark_phase_edited(self, source: str, text: str | None = None) -> None:
        self._phase_last_edited = source
        if text is not None and source in self._pending_phase_text:
            self._pending_phase_text[source] = text

    def _value_from_phase_text(self, source: str, spin: QtWidgets.QDoubleSpinBox) -> float:
        text = self._pending_phase_text.get(source) or spin.lineEdit().text()
        value = spin.valueFromText(text)
        return max(spin.minimum(), min(spin.maximum(), value))

    def _phase_period_edited(self) -> None:
        period = self._value_from_phase_text("period", self.phase_period_spin)
        self._phase_last_edited = "period"
        self._set_phase_values(period=period)
        self._phase_current_period()

    def _phase_frequency_edited(self) -> None:
        frequency = self._value_from_phase_text("frequency", self.phase_frequency_spin)
        self._phase_last_edited = "frequency"
        self._set_phase_values(frequency=frequency)
        self._phase_current_period()

    def _phase_now_clicked(self) -> None:
        if self._phase_last_edited == "frequency":
            self._phase_frequency_edited()
        else:
            self._phase_period_edited()

    def _phase_shift_changed(self, value: int) -> None:
        self.phase_shift_label.setText(f"{value / 1000.0:+.3f}")
        self._phase_current_period()

    def _scale_phase_period(self, factor: float) -> None:
        period = self.phase_period_spin.value() * factor
        if period <= 0:
            return
        self._phase_last_edited = "period"
        self._set_phase_values(period=period)
        self._phase_current_period()

    def _scale_phase_frequency(self, factor: float) -> None:
        frequency = self.phase_frequency_spin.value() * factor
        if frequency <= 0:
            return
        self._phase_last_edited = "frequency"
        self._set_phase_values(frequency=frequency)
        self._phase_current_period()

    def _use_selected_period(self) -> None:
        if self.selected_frequency is not None:
            self._phase_last_edited = "frequency"
            self._set_phase_values(frequency=self.selected_frequency)
            self._phase_current_period()

    def _phase_current_period(self) -> None:
        self._plot_phase(self.phase_period_spin.value())
        if self._current_light_curve_plot is not None:
            self._plot_light_curve(self._current_light_curve_plot)
        if self.selected_frequency is not None:
            self._update_frequency_preview(self.selected_frequency)

    def _refresh_frequency_view_combo(self) -> None:
        self.frequency_view_combo.blockSignals(True)
        self.frequency_view_combo.clear()
        if self.engine is not None:
            for row in self.engine.model.rows():
                if row["enabled"] and row["frequency"] > 0:
                    base_index = self._base_index_from_coefficients(row["coefficients"])
                    self.frequency_view_combo.addItem(
                        f"{row['label']}  f={frequency_text(row['frequency'])}  P={period_text_from_frequency(row['frequency'])}",
                        {"frequency": row["frequency"], "base_index": base_index},
                    )
        self.frequency_view_combo.blockSignals(False)

    def _frequency_view_changed(self, index: int) -> None:
        item = self.frequency_view_combo.itemData(index)
        if isinstance(item, dict) and item.get("frequency"):
            self._select_frequency(
                float(item["frequency"]),
                label=self.frequency_view_combo.itemText(index),
                status="accepted",
                base_index=item.get("base_index"),
            )

    def _update_frequency_preview(self, frequency: float) -> None:
        lc = self._active_light_curve()
        if lc is None or frequency <= 0:
            return
        period = self.phase_period_spin.value() or (1.0 / frequency)
        folded = self._fold_active_light_curve(lc, period)
        self.frequency_lc_plot.plot_points("lc", lc.time, lc.flux, size=3)
        if self.phase_errors_check.isChecked():
            self.frequency_lc_plot.plot_error_bars("lc_errors", lc.time, lc.flux, lc.error)
        else:
            self.frequency_lc_plot.clear_item("lc_errors")
        self.frequency_lc_plot.auto_range()
        self._draw_phase_plot(self.frequency_phase_plot, folded)
        self.frequency_phase_plot.auto_range()

    def _add_independent(self, frequency: float) -> None:
        if self.engine is None:
            return
        self.engine.add_independent(frequency)
        self._refresh_frequency_views()
        self.start_fit()

    def _add_candidate(self, candidate) -> None:
        if self.engine is None:
            return
        self.engine.add_combination(candidate.coefficients)
        self._refresh_frequency_views()
        self.start_fit()

    def _remove_term(self, index: int) -> None:
        if self.engine is None:
            return
        self.engine.remove_term(index)
        self._refresh_frequency_views()
        self.start_fit()

    def _clear_frequencies(self) -> None:
        if self.engine is None:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Clear frequencies",
            "Remove all accepted frequencies from this session?",
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.engine.clear_frequencies()
        self.selected_frequency = None
        self.selected_base_index = None
        self.selected_amplitude = None
        self.selection_label.setText("No frequency selected")
        self.dft_plot.clear_selected_marker()
        self.prewhitening_panel.set_candidates([])
        self._refresh_frequency_views()
        self._plot_light_curve(self.engine.light_curve)
        self.start_dft()

    def _toggle_term(self, index: int, enabled: bool) -> None:
        if self.engine is None:
            return
        self.engine.set_term_enabled(index, enabled)
        self._refresh_frequency_views()
        self.start_fit()

    def _undo(self) -> None:
        if self.engine and self.engine.undo():
            self._refresh_frequency_views()
            self.start_fit()

    def _redo(self) -> None:
        if self.engine and self.engine.redo():
            self._refresh_frequency_views()
            self.start_fit()

    def _export(self) -> None:
        if self.engine is None:
            return
        path = self.engine.export_legacy()
        self.statusBar().showMessage(f"Exported {path}")

    def _detrend(self) -> None:
        if self.engine is None:
            return
        dialog = DetrendDialog(self.engine.residuals or self.engine.light_curve, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.result is not None:
            self.engine.light_curve = dialog.result.corrected
            self.engine.residuals = dialog.result.corrected
            self._plot_light_curve(dialog.result.corrected)
            self.start_dft()

    def _sigma_clip(self) -> None:
        if self.engine is None:
            return
        result = sigma_clip_light_curve(self.engine.residuals or self.engine.light_curve, self.engine.state.settings.sigma)
        if len(result.rejected.time):
            answer = QtWidgets.QMessageBox.question(self, "Sigma clip", f"Remove {len(result.rejected.time)} rejected points?")
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        self.engine.light_curve = result.cleaned
        self.engine.residuals = result.cleaned
        self._plot_light_curve(result.cleaned)
        self.start_dft()

    def _run_tdfd(self, bins: int) -> None:
        if self.engine is None:
            return
        try:
            result = run_tdfd(self.engine.residuals or self.engine.light_curve, self.engine.model, bins)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "TDFD failed", str(exc))
            return
        self.tdfd_panel.set_result(result)
        self.statusBar().showMessage("TDFD ready")

    def build_native_tools(self) -> None:
        try:
            from lcview.native.build import build_native

            tools = build_native(force=True)
            self.statusBar().showMessage(f"Built native tools in {tools.fwpeaks.parent}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Native build failed", str(exc))
