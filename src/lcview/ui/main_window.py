"""Main PySide6 application window."""

from __future__ import annotations

from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
import numpy as np

from lcview.core.combinations import FrequencyCandidate, classify_peak
from lcview.core.lightcurve import LightCurve, LightCurveTable, infer_light_curve_columns, read_light_curve_table
from lcview.core.phase import FoldedLightCurve, PhaseSeriesFit, boxcar_smooth, evaluate_sincos_series, fold_light_curve
from lcview.core.prewhitening import PrewhiteningEngine
from lcview.core.sigma_clip import sigma_clip_light_curve
from lcview.core.session import SessionState
from lcview.core.tdfd import TdfdOptions, run_tdfd
from lcview.display import fixed_text, frequency_text, period_text_from_frequency
from .column_selection_dialog import ColumnSelectionDialog
from .detrend_dialog import DetrendDialog
from .plots import PlotPane
from .prewhitening_panel import PrewhiteningPanel
from .results_panel import ResultsPanel
from .sigma_clip_dialog import SigmaClipDialog
from .tdfd_panel import TdfdPanel
from .widgets import SignificantDoubleSpinBox


DEFAULT_WINDOW_SIZE = QtCore.QSize(1440, 900)
WINDOW_SCREEN_MARGIN = 40
PHASE_TAB_TITLE = "Phase"
DAILY_ALIAS_OFFSET = 1.0
YEARLY_ALIAS_OFFSET = 1.0 / 365.25


class DftWorker(QtCore.QObject):
    progress = QtCore.Signal(int, str)
    finished = QtCore.Signal(object, object)
    failed = QtCore.Signal(str)

    def __init__(self, engine: PrewhiteningEngine, *, backend: str = "fwpeaks") -> None:
        super().__init__()
        self.engine = engine
        self.backend = backend

    @QtCore.Slot()
    def run(self) -> None:
        try:
            periodogram = self.engine.compute_periodogram(progress_callback=self.progress.emit, backend=self.backend)
            self.finished.emit(periodogram, self.engine.last_candidates)
        except Exception as exc:
            self.failed.emit(str(exc))


class FitWorker(QtCore.QObject):
    progress = QtCore.Signal(int, str)
    finished = QtCore.Signal(object, object, object, bool)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        engine: PrewhiteningEngine,
        *,
        refine_frequencies: bool = False,
        refresh_periodogram: bool = False,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.refine_frequencies = refine_frequencies
        self.refresh_periodogram = refresh_periodogram

    @QtCore.Slot()
    def run(self) -> None:
        try:
            message = "Refining frequencies" if self.refine_frequencies else "Fitting fixed-frequency model"
            self.progress.emit(5, message)
            fit = self.engine.fit_model(refine_frequencies=self.refine_frequencies)
            periodogram = None
            candidates = []
            if self.refresh_periodogram:
                self.progress.emit(65, "Refreshing DFT")
                fit_progress = lambda percent, msg: self.progress.emit(65 + int(percent * 0.35), msg)
                periodogram = self.engine.compute_periodogram(fit.residuals, progress_callback=fit_progress)
                candidates = self.engine.last_candidates
            self.finished.emit(fit, periodogram, candidates, self.refresh_periodogram)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, path: str | Path | None = None, *, dft_backend: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("lcView prewhitening")
        self.engine: PrewhiteningEngine | None = None
        self._initial_dft_backend = dft_backend
        self._thread: QtCore.QThread | None = None
        self._worker: QtCore.QObject | None = None
        self.selected_frequency: float | None = None
        self.selected_base_index: int | None = None
        self.selected_amplitude: float | None = None
        self.selected_marker_label = ""
        self.selected_coefficients: tuple[int, ...] | None = None
        self._syncing_phase_controls = False
        self._phase_last_edited = "period"
        self._pending_phase_text: dict[str, str | None] = {"period": None, "frequency": None}
        self._current_light_curve_plot: LightCurve | None = None
        self._current_periodogram_plot = None
        self._current_fit = None
        self._pending_column_table: LightCurveTable | None = None
        self._pending_column_selection: tuple[int, int, int] | None = None
        self._syncing_frequency_phase_controls = False
        self._syncing_frequency_selection = False
        self._syncing_results_selection = False

        self._build_ui()
        self._set_initial_geometry()
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
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(6)
        dft_grid = QtWidgets.QGridLayout()
        dft_grid.setContentsMargins(0, 0, 0, 0)
        dft_grid.setHorizontalSpacing(6)
        dft_grid.setVerticalSpacing(3)
        self.start_spin = SignificantDoubleSpinBox()
        self.start_spin.setRange(0, 100000)
        self.start_spin.setValue(0.0)
        self.start_spin.setMaximumWidth(96)
        self.end_spin = SignificantDoubleSpinBox()
        self.end_spin.setRange(0.001, 100000)
        self.end_spin.setValue(80.0)
        self.end_spin.setMaximumWidth(96)
        self.precision_spin = QtWidgets.QDoubleSpinBox()
        self.precision_spin.setRange(1, 500)
        self.precision_spin.setValue(10)
        self.precision_spin.setMaximumWidth(96)
        self.dft_backend_combo = QtWidgets.QComboBox()
        self.dft_backend_combo.addItem("fwpeaks (native)", "fwpeaks")
        self.dft_backend_combo.addItem("Python DFT (manual)", "python")
        self.dft_backend_combo.setToolTip("fwpeaks is the normal backend. Python DFT is a slower explicit fallback.")
        self.dft_backend_combo.setMaximumWidth(190)
        self.recalc_button = QtWidgets.QPushButton("Calculate DFT")
        dft_grid.addWidget(QtWidgets.QLabel("Start f"), 0, 0)
        dft_grid.addWidget(self.start_spin, 0, 1)
        dft_grid.addWidget(QtWidgets.QLabel("End f"), 0, 2)
        dft_grid.addWidget(self.end_spin, 0, 3)
        dft_grid.addWidget(QtWidgets.QLabel("Precision"), 1, 0)
        dft_grid.addWidget(self.precision_spin, 1, 1)
        dft_grid.addWidget(QtWidgets.QLabel("Backend"), 1, 2)
        dft_grid.addWidget(self.dft_backend_combo, 1, 3)
        dft_grid.setColumnStretch(4, 1)
        left_layout.addLayout(dft_grid)
        left_layout.addWidget(self.recalc_button)
        self.dft_progress = QtWidgets.QProgressBar()
        self.dft_progress.setRange(0, 100)
        self.dft_progress.setValue(0)
        self.dft_progress.setTextVisible(True)
        self.dft_progress.setFormat("%p%")
        self.dft_progress.setMaximumHeight(16)
        self.progress_label = QtWidgets.QLabel("Idle")
        self.progress_label.setWordWrap(False)
        self.progress_label.setMaximumHeight(self.progress_label.fontMetrics().height() + 6)
        left_layout.addWidget(self.dft_progress)
        left_layout.addWidget(self.progress_label)
        selection_group = QtWidgets.QGroupBox("Selected frequency")
        selection_layout = QtWidgets.QVBoxLayout(selection_group)
        selection_layout.setContentsMargins(8, 4, 8, 6)
        selection_layout.setSpacing(2)
        self.selection_label = QtWidgets.QLabel("No frequency selected")
        self.selection_label.setWordWrap(True)
        selection_layout.addWidget(self.selection_label)
        selection_group.setMaximumHeight(112)
        left_layout.addWidget(selection_group)

        self.phase_controls_group = QtWidgets.QGroupBox("Phase controls")
        phase_layout = QtWidgets.QFormLayout(self.phase_controls_group)
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
        self.phase_fit_check = QtWidgets.QCheckBox("Sin/cos fit")
        self.phase_fit_check.setToolTip("Fit a sin/cos series in phase; accepted harmonic terms are included automatically.")
        self.hide_phase_check = QtWidgets.QCheckBox("Hide raw phase")
        self.phase_errors_check = QtWidgets.QCheckBox("Errors")
        smooth_controls = QtWidgets.QHBoxLayout()
        smooth_controls.addWidget(self.smooth_check)
        smooth_controls.addWidget(QtWidgets.QLabel("Window"))
        smooth_controls.addWidget(self.smooth_window_spin)
        smooth_controls.addWidget(self.phase_fit_check)
        smooth_controls.addStretch(1)
        self.phase_source_combo = QtWidgets.QComboBox()
        self.phase_source_combo.addItem("Residual", "residual")
        self.phase_source_combo.addItem("Original", "original")
        self.phase_source_combo.addItem("Selected component (resid0X)", "component")
        self.phase_source_combo.setCurrentIndex(self.phase_source_combo.findData("component"))
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
        left_layout.addWidget(self.phase_controls_group)

        self.prewhitening_panel = PrewhiteningPanel()
        left_layout.addWidget(self.prewhitening_panel, 1)

        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidget(left)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        central.addWidget(left_scroll)

        self.tabs = QtWidgets.QTabWidget()
        lc_view = QtWidgets.QWidget()
        lc_view_layout = QtWidgets.QVBoxLayout(lc_view)
        lc_view_layout.setContentsMargins(0, 0, 0, 0)
        lc_controls = QtWidgets.QHBoxLayout()
        self.light_curve_errors_check = QtWidgets.QCheckBox("Errors")
        self.light_curve_errors_check.setToolTip("Show light-curve error bars. Disabled by default for large data sets.")
        self.magnitude_axis_check = QtWidgets.QCheckBox("Mag axis")
        self.magnitude_axis_check.setToolTip("Invert Y axes for magnitude data. This changes display only, not calculations.")
        lc_controls.addWidget(self.light_curve_errors_check)
        lc_controls.addWidget(self.magnitude_axis_check)
        lc_controls.addStretch(1)
        lc_view_layout.addLayout(lc_controls)
        self.lc_plot = PlotPane("Light curve")
        self.lc_plot.set_labels("Flux", "Time")
        lc_view_layout.addWidget(self.lc_plot, 1)

        dft_view = QtWidgets.QWidget()
        dft_view_layout = QtWidgets.QVBoxLayout(dft_view)
        dft_view_layout.setContentsMargins(0, 0, 0, 0)
        dft_controls = QtWidgets.QHBoxLayout()
        self.dft_snr5_check = QtWidgets.QCheckBox("5 S/N")
        self.dft_snr5_check.setChecked(True)
        self.dft_snr5_check.setToolTip("Show the global amplitude threshold corresponding to S/N=5.")
        self.dft_accepted_markers_check = QtWidgets.QCheckBox("Accepted markers")
        self.dft_accepted_markers_check.setChecked(True)
        self.dft_accepted_markers_check.setToolTip("Show accepted model frequencies on the DFT plot.")
        self.dft_peak_markers_check = QtWidgets.QCheckBox("Peak markers")
        self.dft_peak_markers_check.setChecked(True)
        self.dft_peak_markers_check.setToolTip("Show prominent DFT peaks from the current calculation.")
        self.dft_daily_aliases_check = QtWidgets.QCheckBox("Daily aliases")
        self.dft_daily_aliases_check.setToolTip("Show +/- 1 1/d aliases for accepted and selected frequencies.")
        self.dft_yearly_aliases_check = QtWidgets.QCheckBox("Yearly aliases")
        self.dft_yearly_aliases_check.setToolTip("Show +/- 1/365.25 1/d aliases for accepted and selected frequencies.")
        for checkbox in (
            self.dft_snr5_check,
            self.dft_accepted_markers_check,
            self.dft_peak_markers_check,
            self.dft_daily_aliases_check,
            self.dft_yearly_aliases_check,
        ):
            dft_controls.addWidget(checkbox)
        dft_controls.addStretch(1)
        dft_view_layout.addLayout(dft_controls)
        self.dft_plot = PlotPane("DFT")
        self.dft_plot.set_labels("Amplitude", "Frequency")
        dft_view_layout.addWidget(self.dft_plot, 1)

        self.phase_plot = PlotPane("Phase")
        self.phase_plot.set_labels("Flux", "Phase")
        self.tdfd_panel = TdfdPanel()
        freq_view = QtWidgets.QWidget()
        freq_view_layout = QtWidgets.QVBoxLayout(freq_view)
        freq_controls = QtWidgets.QHBoxLayout()
        self.frequency_view_combo = QtWidgets.QComboBox()
        self.frequency_view_combo.setMinimumWidth(240)
        self.frequency_fit_check = QtWidgets.QCheckBox("Sin/cos fit")
        self.frequency_fit_check.setToolTip("Show the Fourier model fit on both the time plot and folded phase plot.")
        freq_controls.addWidget(QtWidgets.QLabel("Frequency"))
        freq_controls.addWidget(self.frequency_view_combo, 1)
        freq_controls.addWidget(self.frequency_fit_check)
        freq_view_layout.addLayout(freq_controls)
        freq_phase_group = QtWidgets.QGroupBox("Phase controls")
        freq_phase_layout = QtWidgets.QFormLayout(freq_phase_group)
        self.frequency_period_spin = SignificantDoubleSpinBox(digits=10)
        self.frequency_period_spin.setRange(0.0000001, 1_000_000.0)
        self.frequency_period_spin.setSingleStep(0.00001)
        self.frequency_period_spin.setKeyboardTracking(False)
        self.frequency_frequency_spin = SignificantDoubleSpinBox(digits=10)
        self.frequency_frequency_spin.setRange(0.0000001, 1_000_000.0)
        self.frequency_frequency_spin.setSingleStep(0.00001)
        self.frequency_frequency_spin.setKeyboardTracking(False)
        freq_period_controls = QtWidgets.QHBoxLayout()
        self.frequency_period_double_button = QtWidgets.QPushButton("x2")
        self.frequency_period_half_button = QtWidgets.QPushButton("/2")
        freq_period_controls.addWidget(self.frequency_period_spin, 1)
        freq_period_controls.addWidget(self.frequency_period_double_button)
        freq_period_controls.addWidget(self.frequency_period_half_button)
        freq_frequency_controls = QtWidgets.QHBoxLayout()
        self.frequency_frequency_double_button = QtWidgets.QPushButton("x2")
        self.frequency_frequency_half_button = QtWidgets.QPushButton("/2")
        freq_frequency_controls.addWidget(self.frequency_frequency_spin, 1)
        freq_frequency_controls.addWidget(self.frequency_frequency_double_button)
        freq_frequency_controls.addWidget(self.frequency_frequency_half_button)
        self.frequency_repeats_spin = QtWidgets.QSpinBox()
        self.frequency_repeats_spin.setRange(1, 4)
        self.frequency_shift_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.frequency_shift_slider.setRange(-500, 500)
        self.frequency_shift_label = QtWidgets.QLabel("+0.000")
        freq_shift_controls = QtWidgets.QHBoxLayout()
        freq_shift_controls.addWidget(self.frequency_shift_slider, 1)
        freq_shift_controls.addWidget(self.frequency_shift_label)
        self.frequency_smooth_check = QtWidgets.QCheckBox("Smooth")
        self.frequency_smooth_window_spin = QtWidgets.QSpinBox()
        self.frequency_smooth_window_spin.setRange(1, 1_000_000)
        self.frequency_hide_phase_check = QtWidgets.QCheckBox("Hide raw phase")
        self.frequency_errors_check = QtWidgets.QCheckBox("Errors")
        self.frequency_source_combo = QtWidgets.QComboBox()
        self.frequency_source_combo.addItem("Residual", "residual")
        self.frequency_source_combo.addItem("Original", "original")
        self.frequency_source_combo.addItem("Selected component (resid0X)", "component")
        self.frequency_source_combo.setCurrentIndex(self.frequency_source_combo.findData("component"))
        freq_overlay_controls = QtWidgets.QHBoxLayout()
        freq_overlay_controls.addWidget(self.frequency_smooth_check)
        freq_overlay_controls.addWidget(QtWidgets.QLabel("Window"))
        freq_overlay_controls.addWidget(self.frequency_smooth_window_spin)
        freq_overlay_controls.addWidget(self.frequency_hide_phase_check)
        freq_overlay_controls.addWidget(self.frequency_errors_check)
        freq_overlay_controls.addStretch(1)
        freq_phase_layout.addRow("Period [d]", freq_period_controls)
        freq_phase_layout.addRow("Frequency [1/d]", freq_frequency_controls)
        freq_phase_layout.addRow("Phases", self.frequency_repeats_spin)
        freq_phase_layout.addRow("Shift [cycle]", freq_shift_controls)
        freq_phase_layout.addRow(freq_overlay_controls)
        freq_phase_layout.addRow("Source", self.frequency_source_combo)
        freq_view_layout.addWidget(freq_phase_group)
        freq_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.frequency_lc_plot = PlotPane("Selected frequency light curve")
        self.frequency_lc_plot.set_labels("Flux", "Time")
        self.frequency_phase_plot = PlotPane("Selected frequency phase")
        self.frequency_phase_plot.set_labels("Flux", "Phase")
        freq_split.addWidget(self.frequency_lc_plot)
        freq_split.addWidget(self.frequency_phase_plot)
        freq_view_layout.addWidget(freq_split, 1)
        self.results_panel = ResultsPanel()
        self.petersen_text = QtWidgets.QPlainTextEdit()
        self.petersen_text.setReadOnly(True)
        self.tabs.addTab(lc_view, "Light curve")
        self.tabs.addTab(dft_view, "DFT")
        self.phase_tab_index = self.tabs.addTab(self.phase_plot, PHASE_TAB_TITLE)
        self.tabs.addTab(freq_view, "Frequency views")
        self.tabs.addTab(self.results_panel, "Results")
        self.tabs.addTab(self.tdfd_panel, "TDFD")
        self.tabs.addTab(self.petersen_text, "Petersen")
        central.addWidget(self.tabs)
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
        self.phase_fit_check.stateChanged.connect(lambda _: self._phase_current_period())
        self.hide_phase_check.stateChanged.connect(lambda _: self._phase_current_period())
        self.phase_errors_check.stateChanged.connect(lambda _: self._phase_current_period())
        self.phase_source_combo.currentIndexChanged.connect(lambda _: self._phase_now_clicked())
        self.tabs.currentChanged.connect(self._active_tab_changed)
        self.light_curve_errors_check.stateChanged.connect(lambda _: self._light_curve_options_changed())
        self.magnitude_axis_check.stateChanged.connect(lambda _: self._magnitude_axis_changed())
        self.dft_snr5_check.stateChanged.connect(lambda _: self._dft_options_changed())
        self.dft_accepted_markers_check.stateChanged.connect(lambda _: self._dft_options_changed())
        self.dft_peak_markers_check.stateChanged.connect(lambda _: self._dft_options_changed())
        self.dft_daily_aliases_check.stateChanged.connect(lambda _: self._dft_options_changed())
        self.dft_yearly_aliases_check.stateChanged.connect(lambda _: self._dft_options_changed())
        self.tdfd_panel.legend_check.stateChanged.connect(lambda _: self._settings_changed())
        self.tdfd_panel.source_combo.currentIndexChanged.connect(lambda _: self._settings_changed())
        self.tdfd_panel.auto_window_check.stateChanged.connect(lambda _: self._settings_changed())
        self.tdfd_panel.window_points_spin.valueChanged.connect(lambda _: self._settings_changed())
        self.tdfd_panel.step_points_spin.valueChanged.connect(lambda _: self._settings_changed())
        self.tdfd_panel.division_frequency_combo.currentIndexChanged.connect(lambda _: self._settings_changed())
        self.use_selected_button.clicked.connect(self._use_selected_period)
        self.phase_now_button.clicked.connect(self._phase_now_clicked)
        self.frequency_view_combo.currentIndexChanged.connect(self._frequency_view_changed)
        self.frequency_fit_check.stateChanged.connect(lambda _: self._frequency_view_options_changed())
        self.frequency_period_spin.valueChanged.connect(self._frequency_period_changed)
        self.frequency_frequency_spin.valueChanged.connect(self._frequency_frequency_changed)
        self.frequency_period_spin.editingFinished.connect(lambda: self._frequency_period_changed(self.frequency_period_spin.value()))
        self.frequency_frequency_spin.editingFinished.connect(lambda: self._frequency_frequency_changed(self.frequency_frequency_spin.value()))
        self.frequency_period_double_button.clicked.connect(lambda: self._scale_phase_period(2.0))
        self.frequency_period_half_button.clicked.connect(lambda: self._scale_phase_period(0.5))
        self.frequency_frequency_double_button.clicked.connect(lambda: self._scale_phase_frequency(2.0))
        self.frequency_frequency_half_button.clicked.connect(lambda: self._scale_phase_frequency(0.5))
        self.frequency_repeats_spin.valueChanged.connect(lambda value: self._frequency_repeats_changed(value))
        self.frequency_shift_slider.valueChanged.connect(lambda value: self.phase_shift_slider.setValue(value))
        self.frequency_smooth_check.stateChanged.connect(lambda _: self._frequency_phase_checkbox_changed(self.smooth_check, self.frequency_smooth_check))
        self.frequency_smooth_window_spin.valueChanged.connect(lambda value: self._frequency_smooth_window_changed(value))
        self.frequency_hide_phase_check.stateChanged.connect(lambda _: self._frequency_phase_checkbox_changed(self.hide_phase_check, self.frequency_hide_phase_check))
        self.frequency_errors_check.stateChanged.connect(lambda _: self._frequency_phase_checkbox_changed(self.phase_errors_check, self.frequency_errors_check))
        self.frequency_source_combo.currentIndexChanged.connect(self._frequency_source_changed)
        self.start_spin.valueChanged.connect(self._settings_changed)
        self.end_spin.valueChanged.connect(self._settings_changed)
        self.precision_spin.valueChanged.connect(self._settings_changed)
        self.dft_backend_combo.currentIndexChanged.connect(self._settings_changed)
        self.dft_plot.clicked_x.connect(self._dft_clicked)
        self.prewhitening_panel.frequency_selected.connect(self._frequency_row_selected)
        self.prewhitening_panel.candidate_selected.connect(self._candidate_selected)
        self.prewhitening_panel.add_independent_requested.connect(self._add_independent)
        self.prewhitening_panel.add_independents_requested.connect(self._add_independents)
        self.prewhitening_panel.add_candidate_requested.connect(self._add_candidate)
        self.prewhitening_panel.add_candidates_requested.connect(self._add_candidates)
        self.prewhitening_panel.base_frequency_edited.connect(self._edit_base_frequency)
        self.prewhitening_panel.remove_term_requested.connect(self._remove_term)
        self.prewhitening_panel.clear_frequencies_requested.connect(self._clear_frequencies)
        self.prewhitening_panel.toggle_term_requested.connect(self._toggle_term)
        self.prewhitening_panel.fit_requested.connect(self.start_fit)
        self.prewhitening_panel.refine_requested.connect(self.start_refine_fit)
        self.prewhitening_panel.undo_requested.connect(self._undo)
        self.prewhitening_panel.redo_requested.connect(self._redo)
        self.prewhitening_panel.export_requested.connect(self._export)
        self.prewhitening_panel.detrend_requested.connect(self._detrend)
        self.prewhitening_panel.sigma_clip_requested.connect(self._sigma_clip)
        self.prewhitening_panel.tdfd_requested.connect(self._run_tdfd)
        self.tdfd_panel.run_requested.connect(self._run_tdfd)
        self.tdfd_panel.apply_requested.connect(self._apply_tdfd_correction)
        self.tdfd_panel.clear_requested.connect(self._clear_tdfd_correction)
        self.results_panel.row_selected.connect(self._results_row_selected)
        self.results_panel.export_requested.connect(self._export_results_csv)
        self._sync_frequency_phase_controls_from_main()
        self._active_tab_changed(self.tabs.currentIndex())

    def _set_initial_geometry(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(DEFAULT_WINDOW_SIZE)
            return

        available = screen.availableGeometry()
        max_width = max(1, available.width() - WINDOW_SCREEN_MARGIN)
        max_height = max(1, available.height() - WINDOW_SCREEN_MARGIN)
        width = min(DEFAULT_WINDOW_SIZE.width(), max_width)
        height = min(DEFAULT_WINDOW_SIZE.height(), max_height)
        x = available.x() + max(0, (available.width() - width) // 2)
        y = available.y() + max(0, (available.height() - height) // 2)
        self.setGeometry(x, y, width, height)

    @QtCore.Slot(int)
    def _active_tab_changed(self, index: int) -> None:
        self.phase_controls_group.setVisible(index == self.phase_tab_index)

    @QtCore.Slot()
    def open_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open light curve")
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        try:
            columns = self._light_curve_columns_for_file(path)
            if columns is None:
                self.statusBar().showMessage("Load canceled")
                return
            self.engine = PrewhiteningEngine.from_file(path, columns=columns)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(exc))
            return
        settings = self.engine.state.settings
        if self._initial_dft_backend is not None:
            settings.dft_backend = self._initial_dft_backend
        self._set_dft_backend(settings.dft_backend)
        self._set_checkbox_checked(self.dft_snr5_check, settings.show_dft_snr5)
        self._set_checkbox_checked(self.dft_accepted_markers_check, settings.show_dft_accepted_markers)
        self._set_checkbox_checked(self.dft_peak_markers_check, settings.show_dft_peak_markers)
        self._set_checkbox_checked(self.dft_daily_aliases_check, settings.show_dft_daily_aliases)
        self._set_checkbox_checked(self.dft_yearly_aliases_check, settings.show_dft_yearly_aliases)
        self._set_checkbox_checked(self.light_curve_errors_check, settings.show_light_curve_errors)
        self._set_checkbox_checked(self.magnitude_axis_check, self._initial_magnitude_axis_setting(settings.invert_y_axis))
        settings.invert_y_axis = self.magnitude_axis_check.isChecked()
        self.tdfd_panel.set_legend_visible(settings.show_tdfd_legend)
        self._pending_column_table = None
        self._pending_column_selection = None
        self._apply_brightness_axis_direction()
        self.engine.save_state()
        self.start_spin.setValue(settings.start_frequency)
        self.end_spin.setValue(settings.end_frequency)
        self.precision_spin.setValue(settings.precision)
        self._set_default_smooth_window(self.engine.light_curve)
        self._refresh_frequency_views()
        self.tdfd_panel.set_options_from_settings(
            source=settings.tdfd_source,
            auto_window=settings.tdfd_auto_window,
            window_points=settings.tdfd_window_points,
            step_points=settings.tdfd_step_points,
            selected_base_index=settings.tdfd_selected_base_index,
        )
        self._plot_light_curve(self.engine.light_curve)
        self.selected_frequency = None
        self.selected_base_index = None
        self.selected_amplitude = None
        self.selected_marker_label = ""
        self.selected_coefficients = None
        self._current_periodogram_plot = None
        self._current_fit = None
        self.tdfd_panel.clear_result()
        self.results_panel.set_report(None)
        self.dft_plot.clear()
        self.dft_plot.clear_selected_marker()
        self.statusBar().showMessage(f"Loaded {path}")
        if self.engine.model.active_terms():
            self.start_fit()
        else:
            self.start_dft()

    def _light_curve_columns_for_file(self, path: Path) -> tuple[int, int, int] | None:
        table = read_light_curve_table(path)
        self._pending_column_table = table
        self._pending_column_selection = None
        if table.column_count < 3:
            raise ValueError(f"Need at least three columns in {path}")
        if table.column_count == 3:
            columns = infer_light_curve_columns(table)
            self._pending_column_selection = columns
            return columns
        initial_columns = None
        state = SessionState.for_light_curve(path)
        settings = state.settings
        if settings.time_column is not None and settings.flux_column is not None and settings.error_column is not None:
            initial = (settings.time_column, settings.flux_column, settings.error_column)
            if all(0 <= column < table.column_count for column in initial) and len(set(initial)) == 3:
                initial_columns = initial
        dialog = ColumnSelectionDialog(table, self, initial_columns=initial_columns)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        columns = dialog.selected_columns()
        self._pending_column_selection = columns
        return columns

    def _initial_magnitude_axis_setting(self, saved_invert_y_axis: bool) -> bool:
        if saved_invert_y_axis:
            return True
        if self._pending_column_table is None or self._pending_column_selection is None:
            return False
        flux_column = self._pending_column_selection[1]
        if flux_column < 0 or flux_column >= self._pending_column_table.column_count:
            return False
        name = self._pending_column_table.column_names[flux_column].strip().lower()
        return any(token in name for token in ("mag", "magnitude"))

    def _settings_changed(self) -> None:
        if self.engine is None:
            return
        self.engine.state.settings.start_frequency = self.start_spin.value()
        self.engine.state.settings.end_frequency = self.end_spin.value()
        self.engine.state.settings.precision = self.precision_spin.value()
        self.engine.state.settings.dft_backend = self.dft_backend_combo.currentData() or "fwpeaks"
        self.engine.state.settings.show_dft_snr5 = self.dft_snr5_check.isChecked()
        self.engine.state.settings.show_dft_accepted_markers = self.dft_accepted_markers_check.isChecked()
        self.engine.state.settings.show_dft_peak_markers = self.dft_peak_markers_check.isChecked()
        self.engine.state.settings.show_dft_daily_aliases = self.dft_daily_aliases_check.isChecked()
        self.engine.state.settings.show_dft_yearly_aliases = self.dft_yearly_aliases_check.isChecked()
        self.engine.state.settings.show_light_curve_errors = self.light_curve_errors_check.isChecked()
        self.engine.state.settings.invert_y_axis = self.magnitude_axis_check.isChecked()
        self.engine.state.settings.show_tdfd_legend = self.tdfd_panel.legend_check.isChecked()
        tdfd_options = self.tdfd_panel.options()
        self.engine.state.settings.tdfd_source = tdfd_options.source
        self.engine.state.settings.tdfd_auto_window = tdfd_options.auto_window
        self.engine.state.settings.tdfd_window_points = int(tdfd_options.window_points or 0)
        self.engine.state.settings.tdfd_step_points = int(tdfd_options.step_points or 0)
        self.engine.state.settings.tdfd_selected_base_index = tdfd_options.selected_base_index
        self.engine.save_state()

    def _light_curve_options_changed(self) -> None:
        self._settings_changed()
        if self._current_light_curve_plot is not None:
            self._plot_light_curve(self._current_light_curve_plot)

    def _dft_options_changed(self) -> None:
        self._settings_changed()
        self._refresh_dft_overlays()

    def _magnitude_axis_changed(self) -> None:
        self._settings_changed()
        self._apply_brightness_axis_direction()
        self._refresh_brightness_plots()

    def _set_dft_backend(self, backend: str) -> None:
        index = self.dft_backend_combo.findData(backend)
        if index < 0:
            index = self.dft_backend_combo.findData("fwpeaks")
        self.dft_backend_combo.blockSignals(True)
        self.dft_backend_combo.setCurrentIndex(index)
        self.dft_backend_combo.blockSignals(False)

    @staticmethod
    def _set_checkbox_checked(checkbox: QtWidgets.QCheckBox, checked: bool) -> None:
        checkbox.blockSignals(True)
        checkbox.setChecked(bool(checked))
        checkbox.blockSignals(False)

    @staticmethod
    def _set_spin_value(spin: QtWidgets.QAbstractSpinBox, value) -> None:
        spin.blockSignals(True)
        spin.setValue(value)
        spin.blockSignals(False)

    @staticmethod
    def _set_combo_data(combo: QtWidgets.QComboBox, data) -> None:
        index = combo.findData(data)
        if index < 0:
            index = 0
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _sync_frequency_phase_controls_from_main(self) -> None:
        if not hasattr(self, "frequency_period_spin"):
            return
        self._syncing_frequency_phase_controls = True
        self._set_spin_value(self.frequency_period_spin, self.phase_period_spin.value())
        self._set_spin_value(self.frequency_frequency_spin, self.phase_frequency_spin.value())
        self._set_spin_value(self.frequency_repeats_spin, self.phase_repeats_spin.value())
        self._set_spin_value(self.frequency_shift_slider, self.phase_shift_slider.value())
        self.frequency_shift_label.setText(self.phase_shift_label.text())
        self._set_checkbox_checked(self.frequency_smooth_check, self.smooth_check.isChecked())
        self._set_spin_value(self.frequency_smooth_window_spin, self.smooth_window_spin.value())
        self._set_checkbox_checked(self.frequency_hide_phase_check, self.hide_phase_check.isChecked())
        self._set_checkbox_checked(self.frequency_errors_check, self.phase_errors_check.isChecked())
        self._set_combo_data(self.frequency_source_combo, self.phase_source_combo.currentData())
        self._syncing_frequency_phase_controls = False

    def _frequency_period_changed(self, period: float) -> None:
        if self._syncing_frequency_phase_controls or period <= 0:
            return
        self._phase_last_edited = "period"
        self._set_phase_values(period=period)
        self._phase_current_period()

    def _frequency_frequency_changed(self, frequency: float) -> None:
        if self._syncing_frequency_phase_controls or frequency <= 0:
            return
        self._phase_last_edited = "frequency"
        self._set_phase_values(frequency=frequency)
        self._phase_current_period()

    def _frequency_repeats_changed(self, value: int) -> None:
        if self._syncing_frequency_phase_controls:
            return
        self.phase_repeats_spin.setValue(value)

    def _frequency_smooth_window_changed(self, value: int) -> None:
        if self._syncing_frequency_phase_controls:
            return
        self.smooth_window_spin.setValue(value)

    def _frequency_phase_checkbox_changed(self, target: QtWidgets.QCheckBox, source: QtWidgets.QCheckBox) -> None:
        if self._syncing_frequency_phase_controls:
            return
        target.setChecked(source.isChecked())

    def _frequency_source_changed(self, index: int) -> None:
        if self._syncing_frequency_phase_controls:
            return
        data = self.frequency_source_combo.itemData(index)
        target_index = self.phase_source_combo.findData(data)
        if target_index >= 0:
            self.phase_source_combo.setCurrentIndex(target_index)

    def _brightness_axis_label(self) -> str:
        return "Magnitude" if self.magnitude_axis_check.isChecked() else "Flux"

    def _apply_brightness_axis_direction(self) -> None:
        inverted = self.magnitude_axis_check.isChecked()
        label = self._brightness_axis_label()
        for plot in (self.lc_plot, self.phase_plot, self.frequency_lc_plot, self.frequency_phase_plot):
            plot.set_y_inverted(inverted)
        self.lc_plot.set_labels(label, "Time")
        self.phase_plot.set_labels(label, "Phase")
        self.frequency_lc_plot.set_labels(label, "Time")
        self.frequency_phase_plot.set_labels(label, "Phase")

    def _refresh_brightness_plots(self) -> None:
        if self._current_light_curve_plot is not None:
            self._plot_light_curve(self._current_light_curve_plot)
        self._phase_current_period()

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
        if self._thread is not None:
            self.statusBar().showMessage("A calculation is already running")
            return
        self._settings_changed()
        self._set_calculation_controls_enabled(False)
        self.dft_progress.setValue(0)
        backend = self.engine.state.settings.dft_backend
        self.progress_label.setText("Starting DFT (0%)")
        self.statusBar().showMessage(f"Calculating DFT with {backend}...")
        worker = DftWorker(self.engine, backend=backend)
        worker.progress.connect(self._progress_changed)
        worker.finished.connect(self._dft_finished)
        worker.failed.connect(self._worker_failed)
        self._run_worker(worker, worker.run)

    @QtCore.Slot()
    def start_fit(self) -> None:
        self._start_fit(refine_frequencies=False, refresh_periodogram=False)

    def start_fit_and_dft(self) -> None:
        self._start_fit(refine_frequencies=False, refresh_periodogram=True)

    @QtCore.Slot()
    def start_refine_fit(self) -> None:
        self._start_fit(refine_frequencies=True, refresh_periodogram=False)

    def _start_fit(self, *, refine_frequencies: bool, refresh_periodogram: bool) -> None:
        if self.engine is None:
            return
        if self._thread is not None:
            self.statusBar().showMessage("A calculation is already running")
            return
        self._set_calculation_controls_enabled(False)
        self.dft_progress.setValue(0)
        if refine_frequencies:
            self.progress_label.setText("Starting frequency refinement")
            self.statusBar().showMessage("Refining accepted frequencies...")
        elif refresh_periodogram:
            backend = self.engine.state.settings.dft_backend
            self.progress_label.setText("Starting fit + DFT")
            self.statusBar().showMessage(f"Fitting model, then refreshing DFT with {backend}...")
        else:
            self.progress_label.setText("Starting fit")
            self.statusBar().showMessage("Fitting model. DFT will not be refreshed automatically.")
        worker = FitWorker(self.engine, refine_frequencies=refine_frequencies, refresh_periodogram=refresh_periodogram)
        worker.progress.connect(self._progress_changed)
        worker.finished.connect(self._fit_finished)
        worker.failed.connect(self._worker_failed)
        self._run_worker(worker, worker.run)

    @QtCore.Slot(object, object)
    def _dft_finished(self, periodogram, candidates) -> None:
        self._finish_thread()
        self._set_calculation_controls_enabled(True)
        backend = "fwpeaks" if periodogram.used_native else "Python fallback"
        self._progress_changed(100, f"DFT ready ({backend})")
        self._plot_periodogram(periodogram)
        status_message = f"DFT ready ({backend}, {len(periodogram.frequency)} points, {len(candidates)} candidates)"
        self.statusBar().showMessage(status_message)
        selected = self._set_candidates_and_select(candidates)
        if selected is None and periodogram.best_frequency:
            self._select_frequency(periodogram.best_frequency, amplitude=float(np.max(periodogram.amplitude)), label="best peak")
            selected = True
        if selected is None:
            self.statusBar().showMessage(status_message)

    @QtCore.Slot(object, object, object, bool)
    def _fit_finished(self, fit, periodogram, candidates, refreshed_periodogram: bool) -> None:
        self._finish_thread()
        self._set_calculation_controls_enabled(True)
        self._current_fit = fit
        if self.engine is not None and getattr(fit, "report", None) is not None:
            self.engine.last_report = fit.report
        ready_message = "Frequencies refined" if getattr(fit, "used_native", False) else "Fit ready"
        if refreshed_periodogram and periodogram is not None:
            backend = "fwpeaks" if periodogram.used_native else "Python fallback"
            ready_message = f"Fit + DFT ready ({backend})"
        self._progress_changed(100, ready_message)
        self._refresh_frequency_views()
        self._plot_light_curve(fit.residuals)
        self._sync_selected_frequency_after_fit()
        if periodogram is not None:
            self._plot_periodogram(periodogram)
            status_message = f"{ready_message}: {len(periodogram.frequency)} points, {len(candidates)} candidates"
            self.statusBar().showMessage(status_message)
            selected = self._set_candidates_and_select(candidates)
            if selected is None and periodogram.best_frequency:
                self._select_frequency(periodogram.best_frequency, amplitude=float(np.max(periodogram.amplitude)), label="best peak")
                selected = True
            if selected is None:
                self.statusBar().showMessage(status_message)
            return

        self.prewhitening_panel.set_candidates([])
        self._refresh_markers()
        suffix = "Previous DFT is stale; click Calculate DFT to refresh peak candidates."
        if not fit.converged:
            self.statusBar().showMessage(f"{ready_message} with convergence warning. {suffix}")
        else:
            self.statusBar().showMessage(f"{ready_message}. {suffix}")

    @QtCore.Slot(str)
    def _worker_failed(self, message: str) -> None:
        self._finish_thread()
        self._set_calculation_controls_enabled(True)
        self.progress_label.setText("Failed")
        self.dft_progress.setValue(0)
        self.statusBar().showMessage("Calculation failed")
        QtWidgets.QMessageBox.critical(self, "Calculation failed", message)

    def _set_calculation_controls_enabled(self, enabled: bool) -> None:
        self.recalc_button.setEnabled(enabled)
        self.prewhitening_panel.fit_button.setEnabled(enabled)
        self.prewhitening_panel.refine_button.setEnabled(enabled)
        self.tdfd_panel.run_button.setEnabled(enabled)
        self.tdfd_panel.apply_button.setEnabled(enabled and self.tdfd_panel.division_frequency_combo.count() > 0)
        self.tdfd_panel.clear_button.setEnabled(enabled)

    @QtCore.Slot(int, str)
    def _progress_changed(self, percent: int, message: str) -> None:
        value = max(0, min(100, int(percent)))
        self.dft_progress.setValue(value)
        self.progress_label.setText(f"{message} ({value}%)")

    def _plot_light_curve(self, light_curve: LightCurve) -> None:
        self._current_light_curve_plot = light_curve
        self.lc_plot.plot_points("lc", light_curve.time, light_curve.flux, color="#1d4ed8", size=3, opacity=0.58)
        if self.light_curve_errors_check.isChecked():
            self.lc_plot.plot_error_bars("lc_errors", light_curve.time, light_curve.flux, light_curve.error)
        else:
            self.lc_plot.clear_item("lc_errors")
        self.lc_plot.auto_range()

    def _plot_periodogram(self, periodogram) -> None:
        self._current_periodogram_plot = periodogram
        self.dft_plot.plot_line(
            "dft",
            periodogram.frequency,
            periodogram.amplitude,
            color="#2563eb",
            width=1.5,
            title="DFT",
        )
        self._refresh_dft_overlays(periodogram)
        self.dft_plot.auto_range()

    def _refresh_dft_overlays(self, periodogram=None) -> None:
        if periodogram is None:
            periodogram = self._current_periodogram_plot
        if periodogram is not None and self.dft_snr5_check.isChecked():
            noise_level = getattr(periodogram, "noise_level", None)
            if noise_level is not None and np.isfinite(noise_level) and noise_level > 0:
                self.dft_plot.plot_hline(
                    "dft_snr5",
                    5.0 * float(noise_level),
                    color="#b45309",
                    width=1.4,
                    style="dash",
                    label="5 S/N",
                )
            else:
                self.dft_plot.clear_item("dft_snr5")
        else:
            self.dft_plot.clear_item("dft_snr5")

        if periodogram is not None and self.dft_peak_markers_check.isChecked():
            peak_frequency = []
            peak_amplitude = []
            for peak in periodogram.peaks:
                frequency = peak.get("frequency")
                amplitude = peak.get("amplitude")
                try:
                    frequency = float(frequency)
                    amplitude = float(amplitude)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(frequency) and np.isfinite(amplitude):
                    peak_frequency.append(frequency)
                    peak_amplitude.append(amplitude)
            if peak_frequency:
                self.dft_plot.plot_points(
                    "dft_peaks",
                    np.asarray(peak_frequency, dtype=float),
                    np.asarray(peak_amplitude, dtype=float),
                    color="#0f766e",
                    size=4,
                    opacity=0.82,
                    pen_color="#064e3b",
                )
            else:
                self.dft_plot.clear_item("dft_peaks")
        else:
            self.dft_plot.clear_item("dft_peaks")
        self._refresh_markers()

    def _sync_selected_frequency_after_fit(self) -> None:
        if self.engine is None or self.selected_frequency is None:
            return
        if self.selected_coefficients is not None and len(self.selected_coefficients) == len(self.engine.model.bases):
            frequency = self.engine.model.frequency_for_term(self.selected_coefficients)
            self._select_frequency(
                frequency,
                label=self.engine.model.label_for_term(self.selected_coefficients),
                status="accepted",
                base_index=self._base_index_from_coefficients(self.selected_coefficients),
                coefficients=self.selected_coefficients,
            )
            return
        if self.selected_base_index is not None and self.selected_base_index < len(self.engine.model.bases):
            frequency = self.engine.model.bases[self.selected_base_index]
            self._select_frequency(
                frequency,
                label=f"f{self.selected_base_index + 1}",
                status="accepted",
                base_index=self.selected_base_index,
                coefficients=self.engine.model.identity_term(self.selected_base_index),
            )
            return
        self._phase_current_period()

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

    def _draw_phase_plot(
        self,
        plot: PlotPane,
        folded: FoldedLightCurve,
        *,
        show_fit: bool | None = None,
        harmonics: tuple[int, ...] | None = None,
    ) -> PhaseSeriesFit | None:
        show_raw = not self.hide_phase_check.isChecked()
        if show_raw:
            plot.plot_points("phase", folded.phase, folded.flux, color="#1d4ed8", size=3, opacity=0.54, z=10)
            if self.phase_errors_check.isChecked():
                plot.plot_error_bars("phase_errors", folded.phase, folded.flux, folded.error, z=5)
            else:
                plot.clear_item("phase_errors")
        else:
            plot.clear_item("phase")
            plot.clear_item("phase_errors")
        if self.smooth_check.isChecked():
            smoothed = boxcar_smooth(folded.flux, self.smooth_window_spin.value())
            plot.plot_line("phase_smooth", folded.phase, smoothed, color="#f97316", width=3.4, z=20)
        else:
            plot.clear_item("phase_smooth")
        if show_fit is None:
            show_fit = self.phase_fit_check.isChecked()
        if harmonics is None:
            harmonics = self._phase_fit_harmonics()
        if show_fit:
            fit = self._fourier_phase_fit(folded, harmonics)
            if fit is not None:
                plot.plot_line("phase_fit", fit.phase, fit.flux, color="#dc2626", width=2.8, z=30)
                return fit
            else:
                plot.clear_item("phase_fit")
        else:
            plot.clear_item("phase_fit")
        return None

    def _fourier_phase_fit(self, folded: FoldedLightCurve, harmonics: tuple[int, ...]) -> PhaseSeriesFit | None:
        fit = self._current_fit
        if fit is None or not getattr(fit, "fourier_terms", ()):
            return None
        phase_frequency = self.phase_frequency_spin.value()
        if phase_frequency <= 0:
            return None
        unique_harmonics = tuple(sorted({int(value) for value in harmonics if int(value) > 0}))
        if not unique_harmonics:
            return None
        harmonic_index = {harmonic: index for index, harmonic in enumerate(unique_harmonics)}
        include_offset = self.phase_source_combo.currentData() == "original"
        coefficients = np.zeros(1 + 2 * len(unique_harmonics), dtype=float)
        if include_offset:
            coefficients[0] = float(getattr(fit, "offset", 0.0))
        matched = False
        tolerance = max(1e-8, abs(phase_frequency) * 1e-5)
        for term in fit.fourier_terms:
            frequency = float(term.frequency)
            if frequency <= 0:
                continue
            ratio = frequency / phase_frequency
            harmonic = int(round(ratio))
            if harmonic not in harmonic_index:
                continue
            if abs(frequency - harmonic * phase_frequency) > max(tolerance, abs(frequency) * 1e-5):
                continue
            target = harmonic_index[harmonic]
            coefficients[1 + 2 * target] += float(term.sin_coefficient)
            coefficients[2 + 2 * target] += float(term.cos_coefficient)
            matched = True
        if not matched:
            return None
        max_phase = float(np.max(folded.phase)) if folded.phase.size else 1.0
        repeats = max(1, int(np.floor(max_phase)) + 1)
        grid = np.linspace(0.0, float(repeats), max(120, repeats * 400), endpoint=True)
        fitted_flux = evaluate_sincos_series(grid, unique_harmonics, coefficients)
        return PhaseSeriesFit(grid, fitted_flux, unique_harmonics, coefficients)

    def _phase_fit_harmonics(self) -> tuple[int, ...]:
        frequency = self.phase_frequency_spin.value()
        if self.engine is None or frequency <= 0:
            return (1,)
        harmonics = {1}
        tolerance = max(1e-8, abs(frequency) * 1e-5)
        for term in self.engine.model.active_terms():
            term_frequency = self.engine.model.frequency_for_term(term)
            if term_frequency <= 0:
                continue
            ratio = term_frequency / frequency
            harmonic = int(round(ratio))
            if harmonic > 0 and abs(term_frequency - harmonic * frequency) <= max(tolerance, abs(term_frequency) * 1e-5):
                harmonics.add(harmonic)
        return tuple(sorted(harmonics))

    def _refresh_frequency_views(self) -> None:
        if self.engine is None:
            return
        self.prewhitening_panel.set_frequency_model(self.engine.model)
        self._refresh_frequency_view_combo()
        self._sync_frequency_selection_widgets()
        self._refresh_results_panel()
        self._refresh_tdfd_controls()
        self._refresh_markers()
        self._refresh_petersen()

    def _refresh_results_panel(self) -> None:
        if self.engine is None:
            self.results_panel.set_report(None)
            return
        self.results_panel.set_report(self.engine.last_report)
        self._sync_results_selection()

    def _sync_results_selection(self) -> None:
        if self._syncing_results_selection:
            return
        coefficients = self._accepted_selection_coefficients()
        self._syncing_results_selection = True
        try:
            self.results_panel.select_coefficients(coefficients)
        finally:
            self._syncing_results_selection = False

    def _refresh_tdfd_controls(self) -> None:
        if self.engine is None:
            self.tdfd_panel.configure_sources(has_residual=False, has_component=False)
            self.tdfd_panel.set_families([])
            return
        families: list[tuple[int, str, float]] = []
        for row in self.engine.model.rows():
            base_index = self._base_index_from_coefficients(row["coefficients"])
            if base_index is not None and row["enabled"] and row["frequency"] > 0:
                families.append((base_index, str(row["label"]), float(row["frequency"])))
        self.tdfd_panel.set_families(families)
        has_component = self._selected_component_light_curve() is not None
        self.tdfd_panel.configure_sources(has_residual=self.engine.residuals is not None, has_component=has_component)
        preferred_source = self.engine.state.settings.tdfd_source
        if preferred_source == "residual" and self.engine.residuals is not None:
            self.tdfd_panel.source_combo.setCurrentIndex(self.tdfd_panel.source_combo.findData("residual"))
        elif preferred_source == "component" and has_component:
            self.tdfd_panel.source_combo.setCurrentIndex(self.tdfd_panel.source_combo.findData("component"))
        if self.engine.tdfd_correction_stale_reason and self.engine.tdfd_result is None:
            self.tdfd_panel.clear_result()
            self.tdfd_panel.set_correction_status(f"TDFD correction disabled: {self.engine.tdfd_correction_stale_reason}")
        elif self.engine.tdfd_correction_active:
            self.tdfd_panel.set_correction_status(f"TDFD correction active: {self.engine.tdfd_correction_label}")

    def _refresh_markers(self) -> None:
        if self.engine is None:
            return
        self.dft_plot.clear_markers()
        if self.dft_accepted_markers_check.isChecked():
            for row in self.engine.model.rows():
                if row["enabled"]:
                    self.dft_plot.add_vertical_marker(row["frequency"], row["label"])
        if self.dft_daily_aliases_check.isChecked():
            self._add_alias_markers(DAILY_ALIAS_OFFSET, "1d", "#0891b2", "dash")
        if self.dft_yearly_aliases_check.isChecked():
            self._add_alias_markers(YEARLY_ALIAS_OFFSET, "1y", "#7c3aed", "dot")
        if self.selected_frequency is not None:
            label = self.selected_marker_label or frequency_text(self.selected_frequency)
            self.dft_plot.set_selected_marker(self.selected_frequency, label)

    def _add_alias_markers(self, offset: float, label_suffix: str, color: str, style: str) -> None:
        low, high = self._dft_frequency_bounds()
        drawn: list[float] = []
        for source_frequency, source_label in self._alias_marker_sources():
            for sign, sign_label in ((-1.0, "-"), (1.0, "+")):
                alias_frequency = source_frequency + sign * offset
                if alias_frequency <= 0 or alias_frequency < low or alias_frequency > high:
                    continue
                tolerance = max(1e-8, abs(alias_frequency) * 1e-6)
                if any(abs(alias_frequency - existing) <= tolerance for existing in drawn):
                    continue
                drawn.append(alias_frequency)
                label = f"{source_label} {sign_label}{label_suffix}" if source_label else f"{sign_label}{label_suffix}"
                self.dft_plot.add_vertical_marker(
                    alias_frequency,
                    label,
                    color=color,
                    width=1.35,
                    opacity=0.78,
                    style=style,
                )

    def _dft_frequency_bounds(self) -> tuple[float, float]:
        periodogram = self._current_periodogram_plot
        if periodogram is not None and len(periodogram.frequency) > 0:
            frequency = np.asarray(periodogram.frequency, dtype=float)
            finite = frequency[np.isfinite(frequency)]
            if finite.size:
                return float(np.min(finite)), float(np.max(finite))
        return float(min(self.start_spin.value(), self.end_spin.value())), float(max(self.start_spin.value(), self.end_spin.value()))

    def _alias_marker_sources(self) -> list[tuple[float, str]]:
        if self.engine is None:
            return []
        sources: list[tuple[float, str]] = []
        for row in self.engine.model.rows():
            if row["enabled"]:
                self._append_alias_source(sources, float(row["frequency"]), str(row["label"]))
        if self.selected_frequency is not None:
            self._append_alias_source(sources, self.selected_frequency, "selected")
        return sources

    @staticmethod
    def _append_alias_source(sources: list[tuple[float, str]], frequency: float, label: str) -> None:
        if not np.isfinite(frequency) or frequency <= 0:
            return
        tolerance = max(1e-8, abs(frequency) * 1e-6)
        if any(abs(frequency - existing) <= tolerance for existing, _ in sources):
            return
        sources.append((float(frequency), label))

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
                lines.append(f"{fixed_text(longer):>8s} {fixed_text(shorter / longer):>8s} f{i + 1}/f{j + 1}")
        self.petersen_text.setPlainText("\n".join(lines))

    @QtCore.Slot(float)
    def _dft_clicked(self, frequency: float) -> None:
        if self.engine is None or self.engine.last_periodogram is None:
            return
        pg = self.engine.last_periodogram
        peak_frequency, peak_amplitude = self._nearest_periodogram_peak(pg, frequency)
        candidate = classify_peak(
            peak_frequency,
            peak_amplitude,
            self.engine.model,
            self.engine.light_curve.baseline,
            start_frequency=float(np.min(pg.frequency)),
            end_frequency=float(np.max(pg.frequency)),
        )
        self._set_candidates_and_select([candidate, *self.engine.last_candidates[:20]], selected_candidate=candidate)
        self.statusBar().showMessage(f"{frequency_text(candidate.frequency)}: {candidate.kind}, {candidate.resolved}")

    def _nearest_periodogram_peak(self, periodogram, clicked_frequency: float) -> tuple[float, float]:
        peaks: list[tuple[float, float]] = []
        for peak in getattr(periodogram, "peaks", ()):
            try:
                frequency = float(peak.get("frequency"))
                amplitude = float(peak.get("amplitude"))
            except (AttributeError, TypeError, ValueError):
                continue
            if np.isfinite(frequency) and np.isfinite(amplitude):
                peaks.append((frequency, amplitude))

        frequencies = np.asarray(periodogram.frequency, dtype=float)
        amplitudes = np.asarray(periodogram.amplitude, dtype=float)
        if len(frequencies) >= 3:
            peak_indexes = np.where((amplitudes[1:-1] >= amplitudes[:-2]) & (amplitudes[1:-1] >= amplitudes[2:]))[0] + 1
            if peak_indexes.size:
                peaks.extend((float(frequencies[index]), float(amplitudes[index])) for index in peak_indexes)
        if peaks:
            return min(peaks, key=lambda item: abs(item[0] - clicked_frequency))
        nearest = int(np.argmin(np.abs(frequencies - clicked_frequency)))
        return float(frequencies[nearest]), float(amplitudes[nearest])

    def _candidate_selected(self, candidate: FrequencyCandidate) -> None:
        self._select_candidate(candidate)

    def _set_candidates_and_select(
        self,
        candidates: list[FrequencyCandidate],
        selected_candidate: FrequencyCandidate | None = None,
    ) -> FrequencyCandidate | None:
        selected = self.prewhitening_panel.set_candidates(candidates, selected_candidate=selected_candidate)
        if selected is not None:
            self._select_candidate(selected)
        return selected

    def _select_candidate(self, candidate: FrequencyCandidate) -> None:
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
            coefficients=row["coefficients"],
        )

    def _results_row_selected(self, row) -> None:
        if self._syncing_results_selection:
            return
        self._select_frequency(
            row.frequency,
            amplitude=row.amplitude,
            label=row.label,
            status=row.status,
            base_index=self._base_index_from_coefficients(row.coefficients),
            coefficients=row.coefficients,
        )

    def _base_index_from_coefficients(self, coefficients: tuple[int, ...]) -> int | None:
        nonzero = [(idx, value) for idx, value in enumerate(coefficients) if value]
        if len(nonzero) == 1 and nonzero[0][1] == 1:
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
        coefficients: tuple[int, ...] | None = None,
    ) -> None:
        if frequency <= 0:
            return
        self.selected_frequency = float(frequency)
        self.selected_base_index = base_index if base_index is not None else self._base_index_for_frequency(frequency)
        self.selected_amplitude = amplitude
        self.selected_marker_label = label or frequency_text(self.selected_frequency)
        self.selected_coefficients = coefficients
        if self.engine is not None:
            self._sync_frequency_selection_widgets()
            self._refresh_tdfd_controls()
            self._refresh_markers()
        else:
            self.dft_plot.set_selected_marker(self.selected_frequency, self.selected_marker_label)
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
        amp = "" if self.selected_amplitude is None else f"\nAmplitude: {fixed_text(self.selected_amplitude)}"
        amp_status = "" if self.selected_amplitude is None else f", amp {fixed_text(self.selected_amplitude)}"
        snr_text = "" if snr is None else f"\nS/N: {fixed_text(snr)}"
        rayleigh_text = "" if rayleigh is None else f"\nRayleigh: {fixed_text(rayleigh)}"
        detail = f", {label}" if label else ""
        extra = f", {status}" if status else ""
        self.selection_label.setText(
            f"f = {frequency_text(self.selected_frequency)} 1/d\n"
            f"P = {fixed_text(period)} d"
            f"{amp}{snr_text}{rayleigh_text}\n"
            f"Status: {(status or 'selected')}{detail}"
        )
        self.statusBar().showMessage(
            f"Selected f={frequency_text(self.selected_frequency)}  P={fixed_text(period)} d{amp_status}{detail}{extra}"
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
        self._sync_frequency_phase_controls_from_main()

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
        self._sync_frequency_phase_controls_from_main()
        self._plot_phase(self.phase_period_spin.value())
        if self.selected_frequency is not None:
            self._update_frequency_preview(self.selected_frequency)

    def _refresh_frequency_view_combo(self) -> None:
        self.frequency_view_combo.blockSignals(True)
        self.frequency_view_combo.clear()
        if self.engine is not None:
            for row in self.engine.model.rows():
                base_index = self._base_index_from_coefficients(row["coefficients"])
                if base_index is not None and row["frequency"] > 0:
                    self.frequency_view_combo.addItem(
                        f"{row['label']}  f={frequency_text(row['frequency'])}  P={period_text_from_frequency(row['frequency'])}",
                        {
                            "frequency": row["frequency"],
                            "base_index": base_index,
                            "coefficients": row["coefficients"],
                            "term_index": row["index"],
                            "label": row["label"],
                        },
                    )
        self.frequency_view_combo.setCurrentIndex(-1)
        self.frequency_view_combo.blockSignals(False)

    def _frequency_view_changed(self, index: int) -> None:
        if self._syncing_frequency_selection:
            return
        item = self.frequency_view_combo.itemData(index)
        if isinstance(item, dict) and item.get("frequency"):
            self._select_frequency(
                float(item["frequency"]),
                label=str(item.get("label") or self.frequency_view_combo.itemText(index)),
                status="accepted",
                base_index=item.get("base_index"),
                coefficients=tuple(item.get("coefficients", ())),
            )

    def _sync_frequency_selection_widgets(self) -> None:
        if self.engine is None or self._syncing_frequency_selection:
            return
        self._syncing_frequency_selection = True
        try:
            coefficients = self._accepted_selection_coefficients()
            if coefficients is None:
                self.prewhitening_panel.select_term()
            else:
                self.prewhitening_panel.select_term(coefficients=coefficients)
            combo_index = self._frequency_view_combo_index_for_coefficients(coefficients)
            self.frequency_view_combo.blockSignals(True)
            try:
                self.frequency_view_combo.setCurrentIndex(combo_index)
            finally:
                self.frequency_view_combo.blockSignals(False)
            self._sync_results_selection()
        finally:
            self._syncing_frequency_selection = False

    def _accepted_selection_coefficients(self) -> tuple[int, ...] | None:
        if self.engine is None or self.selected_frequency is None:
            return None
        if self.selected_coefficients is not None and len(self.selected_coefficients) == len(self.engine.model.bases):
            return tuple(self.selected_coefficients)
        if self.selected_base_index is not None and 0 <= self.selected_base_index < len(self.engine.model.bases):
            return self.engine.model.identity_term(self.selected_base_index)
        return None

    def _frequency_view_combo_index_for_coefficients(self, coefficients: tuple[int, ...] | None) -> int:
        base_index = self._base_index_from_coefficients(coefficients or ())
        if base_index is None:
            return -1
        for index in range(self.frequency_view_combo.count()):
            item = self.frequency_view_combo.itemData(index)
            if isinstance(item, dict) and item.get("base_index") == base_index:
                return index
        return -1

    def _frequency_view_options_changed(self) -> None:
        frequency = self.selected_frequency
        if frequency is None:
            item = self.frequency_view_combo.currentData()
            if isinstance(item, dict) and item.get("frequency"):
                frequency = float(item["frequency"])
        if frequency is not None:
            self._update_frequency_preview(frequency)

    def _update_frequency_preview(self, frequency: float) -> None:
        lc = self._active_light_curve()
        if lc is None or frequency <= 0:
            return
        period = self.phase_period_spin.value() or (1.0 / frequency)
        folded = self._fold_active_light_curve(lc, period)
        self.frequency_lc_plot.plot_points("lc", lc.time, lc.flux, color="#1d4ed8", size=3, opacity=0.58, z=10)
        if self.phase_errors_check.isChecked():
            self.frequency_lc_plot.plot_error_bars("lc_errors", lc.time, lc.flux, lc.error, z=5)
        else:
            self.frequency_lc_plot.clear_item("lc_errors")
        harmonics = self._phase_fit_harmonics()
        fit = self._draw_phase_plot(
            self.frequency_phase_plot,
            folded,
            show_fit=self.frequency_fit_check.isChecked(),
            harmonics=harmonics,
        )
        self._draw_time_fit(lc, period, fit)
        self.frequency_lc_plot.auto_range()
        self.frequency_phase_plot.auto_range()

    def _draw_time_fit(self, light_curve: LightCurve, period: float, fit: PhaseSeriesFit | None) -> None:
        if fit is None or period <= 0:
            self.frequency_lc_plot.clear_item("lc_fit")
            return
        phase = np.mod(light_curve.time / period + self._phase_shift_fraction(), 1.0)
        fit_flux = evaluate_sincos_series(phase, fit.harmonics, fit.coefficients)
        valid = np.isfinite(light_curve.time) & np.isfinite(fit_flux)
        if not np.any(valid):
            self.frequency_lc_plot.clear_item("lc_fit")
            return
        time = np.asarray(light_curve.time, dtype=float)[valid]
        flux = np.asarray(fit_flux, dtype=float)[valid]
        order = np.argsort(time)
        self.frequency_lc_plot.plot_line("lc_fit", time[order], flux[order], color="#dc2626", width=2.5, z=30)

    def _add_independent(self, frequency: float) -> None:
        if self.engine is None:
            return
        self.engine.add_independent(frequency)
        self._refresh_frequency_views()
        self.start_fit_and_dft()

    def _add_independents(self, candidates) -> None:
        if self.engine is None:
            return
        added = 0
        for candidate in candidates:
            frequency = float(getattr(candidate, "frequency", np.nan))
            if not np.isfinite(frequency) or frequency <= 0:
                continue
            self.engine.add_independent(frequency)
            added += 1
        if added == 0:
            self.statusBar().showMessage("No valid candidates selected")
            return
        self._refresh_frequency_views()
        self.statusBar().showMessage(f"Added {added} independent frequencies")
        self.start_fit_and_dft()

    def _add_candidate(self, candidate) -> None:
        if self.engine is None:
            return
        self.engine.add_combination(candidate.coefficients)
        self._refresh_frequency_views()
        self.start_fit_and_dft()

    def _add_candidates(self, candidates) -> None:
        if self.engine is None:
            return
        added = 0
        for candidate in candidates:
            if candidate.kind == "independent" or not any(candidate.coefficients):
                frequency = float(candidate.frequency)
                if not np.isfinite(frequency) or frequency <= 0:
                    continue
                self.engine.add_independent(frequency)
            else:
                self.engine.add_combination(candidate.coefficients)
            added += 1
        if added == 0:
            self.statusBar().showMessage("No valid candidates selected")
            return
        self._refresh_frequency_views()
        self.statusBar().showMessage(f"Added {added} selected candidates")
        self.start_fit_and_dft()

    def _edit_base_frequency(self, base_index: int, frequency: float) -> None:
        if self.engine is None:
            return
        if not np.isfinite(frequency) or frequency <= 0:
            self.statusBar().showMessage("Base frequency must be positive")
            return
        previous_coefficients = self.selected_coefficients
        selected_was_base = self.selected_base_index == base_index
        self.engine.set_base_frequency(base_index, frequency)
        self._refresh_frequency_views()
        if previous_coefficients is not None and len(previous_coefficients) == len(self.engine.model.bases):
            self._select_frequency(
                self.engine.model.frequency_for_term(previous_coefficients),
                label=self.engine.model.label_for_term(previous_coefficients),
                status="accepted",
                base_index=self._base_index_from_coefficients(previous_coefficients),
                coefficients=previous_coefficients,
            )
        elif selected_was_base:
            coefficients = self.engine.model.identity_term(base_index)
            self._select_frequency(
                frequency,
                label=f"f{base_index + 1}",
                status="accepted",
                base_index=base_index,
                coefficients=coefficients,
            )
        elif self.selected_frequency is not None:
            self.selected_base_index = self._base_index_for_frequency(self.selected_frequency)
            self._refresh_markers()
        self.start_fit_and_dft()

    def _remove_term(self, index: int) -> None:
        if self.engine is None:
            return
        removed_frequency = None
        removed_coefficients = None
        removed_base_index = None
        rows = self.engine.model.rows()
        if 0 <= index < len(rows):
            removed_frequency = float(rows[index]["frequency"])
            removed_coefficients = rows[index]["coefficients"]
            removed_base_index = self._base_index_from_coefficients(removed_coefficients)
        self.engine.remove_term_or_base(index)
        selection_removed = False
        if removed_frequency is not None and self.selected_frequency is not None:
            tolerance = max(1e-8, abs(removed_frequency) * 1e-6)
            selection_removed = abs(self.selected_frequency - removed_frequency) <= tolerance
        if removed_base_index is not None and self.selected_coefficients is not None:
            if removed_base_index < len(self.selected_coefficients) and self.selected_coefficients[removed_base_index] != 0:
                selection_removed = True
        elif removed_coefficients is not None and self.selected_coefficients == removed_coefficients:
            selection_removed = True
        if selection_removed:
            self.selected_frequency = None
            self.selected_base_index = None
            self.selected_amplitude = None
            self.selected_marker_label = ""
            self.selected_coefficients = None
            self.selection_label.setText("No frequency selected")
            self.dft_plot.clear_selected_marker()
        elif self.selected_frequency is not None:
            self.selected_base_index = self._base_index_for_frequency(self.selected_frequency)
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
        self.selected_marker_label = ""
        self.selected_coefficients = None
        self._current_fit = None
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

    def _export_results_csv(self) -> None:
        if self.engine is None:
            return
        default = self.engine.state.light_curve_path.with_suffix(".results.csv")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export results CSV", str(default), "CSV files (*.csv)")
        if not path:
            return
        exported = self.results_panel.export_csv(path)
        self.statusBar().showMessage(f"Exported results {exported}")

    def _detrend(self) -> None:
        if self.engine is None:
            return
        dialog = DetrendDialog(self.engine.residuals or self.engine.light_curve, self, y_inverted=self.magnitude_axis_check.isChecked())
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.result is not None:
            self.engine.light_curve = dialog.result.corrected
            self.engine.residuals = dialog.result.corrected
            self._plot_light_curve(dialog.result.corrected)
            self.start_dft()

    def _sigma_clip(self) -> None:
        if self.engine is None:
            return
        applied = False
        while self.engine is not None:
            source_light_curve = self.engine.residuals or self.engine.light_curve
            result = sigma_clip_light_curve(source_light_curve, self.engine.state.settings.sigma)
            dialog = SigmaClipDialog(source_light_curve, result, self, y_inverted=self.magnitude_axis_check.isChecked())
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                if applied:
                    self._start_after_sigma_clip()
                return
            sigma_value = getattr(dialog, "sigma_value", lambda: self.engine.state.settings.sigma)
            self.engine.state.settings.sigma = float(sigma_value())
            reject_mask = np.asarray(dialog.selected_reject_mask(), dtype=bool)
            continue_clipping = getattr(dialog, "result_mode", "close") == "continue"
            if not self._apply_sigma_clip_mask(reject_mask, refit_for_preview=continue_clipping):
                if continue_clipping:
                    continue
                return
            applied = True
            if continue_clipping:
                continue
            self._start_after_sigma_clip()
            return

    def _apply_sigma_clip_mask(self, reject_mask: np.ndarray, *, refit_for_preview: bool) -> bool:
        if self.engine is None:
            return False
        reject_mask = np.asarray(reject_mask, dtype=bool)
        if reject_mask.shape != (len(self.engine.light_curve.time),):
            QtWidgets.QMessageBox.critical(
                self,
                "Sigma clip failed",
                "Sigma clipping source no longer matches the original light curve. Refit the model and try again.",
            )
            return False
        if not np.any(reject_mask):
            self.statusBar().showMessage("Sigma clip canceled: no points selected for rejection")
            return False
        keep_mask = ~reject_mask
        if not np.any(keep_mask):
            QtWidgets.QMessageBox.warning(self, "Sigma clip canceled", "Cannot reject all light-curve points.")
            return False
        self.engine.apply_observation_mask(keep_mask)
        self._current_fit = None
        self._current_periodogram_plot = None
        self.prewhitening_panel.set_candidates([])
        self.dft_plot.clear()
        if refit_for_preview and self.engine.model.active_terms():
            try:
                fit = self.engine.fit_model()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Sigma clip refit failed", str(exc))
                self._plot_light_curve(self.engine.light_curve)
                self._refresh_frequency_views()
                return False
            self._current_fit = fit
            self._plot_light_curve(fit.residuals)
            self._sync_selected_frequency_after_fit()
        else:
            self._plot_light_curve(self.engine.light_curve)
        self._refresh_frequency_views()
        self.statusBar().showMessage(f"Sigma clip removed {int(np.count_nonzero(reject_mask))} points")
        return True

    def _start_after_sigma_clip(self) -> None:
        if self.engine is None:
            return
        if self.engine.model.active_terms():
            self.start_fit_and_dft()
        else:
            self.start_dft()

    def _tdfd_source_light_curve(self, options: TdfdOptions) -> LightCurve:
        if self.engine is None:
            raise RuntimeError("No light curve loaded")
        if options.source == "original":
            return self.engine.light_curve
        if options.source == "component":
            component = self._selected_component_light_curve()
            if component is None:
                raise RuntimeError("Selected component is not available. Fit the model first or select another TDFD source.")
            return component
        return self.engine.residuals or self.engine.light_curve

    def _calculate_tdfd_result(self, options: TdfdOptions):
        if self.engine is None:
            raise RuntimeError("No light curve loaded")
        source = self._tdfd_source_light_curve(options)
        return run_tdfd(source, self.engine.model, options=options)

    def _run_tdfd(self) -> None:
        if self.engine is None:
            return
        self._settings_changed()
        options = self.tdfd_panel.options()
        try:
            result = self._calculate_tdfd_result(options)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "TDFD failed", str(exc))
            return
        self.engine.tdfd_result = result
        self.tdfd_panel.set_result(result)
        self.statusBar().showMessage(result.message)

    def _apply_tdfd_correction(self) -> None:
        if self.engine is None:
            return
        self._settings_changed()
        options = self.tdfd_panel.options()
        result = self.tdfd_panel.result()
        if (
            result is None
            or result.options.source != options.source
            or result.options.auto_window != options.auto_window
            or int(result.options.window_points or 0) != int(options.window_points or 0)
            or int(result.options.step_points or 0) != int(options.step_points or 0)
            or result.selected_base_index != options.selected_base_index
        ):
            try:
                result = self._calculate_tdfd_result(options)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "TDFD correction failed", str(exc))
                return
            self.tdfd_panel.set_result(result)
        if not result.correction_term_indexes:
            self.statusBar().showMessage("TDFD correction canceled: no selected family terms")
            return
        corrected = self.engine.apply_tdfd_correction(result)
        self._current_periodogram_plot = None
        self.prewhitening_panel.set_candidates([])
        self._plot_light_curve(corrected)
        self._refresh_frequency_views()
        self.tdfd_panel.set_correction_status(f"TDFD correction active: {self.engine.tdfd_correction_label}")
        self.statusBar().showMessage(f"Applied {self.engine.tdfd_correction_label}; refreshing residual DFT")
        self.start_dft()

    def _clear_tdfd_correction(self) -> None:
        if self.engine is None:
            return
        changed = self.engine.clear_tdfd_correction()
        self._refresh_frequency_views()
        self._plot_light_curve(self.engine.residuals or self.engine.light_curve)
        if changed:
            self.tdfd_panel.set_correction_status("TDFD correction cleared")
            self.statusBar().showMessage("TDFD correction cleared; refreshing residual DFT")
            self.start_dft()
        else:
            self.tdfd_panel.set_correction_status("TDFD: no active correction")
            self.statusBar().showMessage("No active TDFD correction")

    def build_native_tools(self) -> None:
        try:
            from lcview.native.build import build_native

            tools = build_native(force=True)
            self.statusBar().showMessage(f"Built native tools in {tools.fwpeaks.parent}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Native build failed", str(exc))
