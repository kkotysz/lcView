"""TDFD controls and result view."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets
import numpy as np

from lcview.core.tdfd import TdfdOptions, TdfdResult
from lcview.display import fixed_text
from .plots import PlotPane


class TdfdPanel(QtWidgets.QWidget):
    run_requested = QtCore.Signal()
    apply_requested = QtCore.Signal()
    clear_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QGridLayout()

        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItem("Current residual", "residual")
        self.source_combo.addItem("Original", "original")
        self.source_combo.addItem("Selected component", "component")
        self.auto_window_check = QtWidgets.QCheckBox("Auto window")
        self.auto_window_check.setChecked(True)
        self.window_points_spin = QtWidgets.QSpinBox()
        self.window_points_spin.setRange(1, 1_000_000)
        self.window_points_spin.setValue(30)
        self.step_points_spin = QtWidgets.QSpinBox()
        self.step_points_spin.setRange(1, 1_000_000)
        self.step_points_spin.setValue(8)
        self.bins_spin = self.window_points_spin
        self.run_button = QtWidgets.QPushButton("Run TDFD")
        self.apply_button = QtWidgets.QPushButton("Apply correction")
        self.clear_button = QtWidgets.QPushButton("Clear correction")
        self.legend_check = QtWidgets.QCheckBox("Legend")
        self.legend_check.setChecked(True)
        self.division_check = QtWidgets.QCheckBox("Division")
        self.division_check.setChecked(True)
        self.division_frequency_label = QtWidgets.QLabel("Family")
        self.division_frequency_combo = QtWidgets.QComboBox()
        self.division_frequency_combo.setMinimumWidth(180)

        controls.addWidget(QtWidgets.QLabel("Source"), 0, 0)
        controls.addWidget(self.source_combo, 0, 1)
        controls.addWidget(self.auto_window_check, 0, 2)
        controls.addWidget(QtWidgets.QLabel("Window pts"), 0, 3)
        controls.addWidget(self.window_points_spin, 0, 4)
        controls.addWidget(QtWidgets.QLabel("Step pts"), 0, 5)
        controls.addWidget(self.step_points_spin, 0, 6)
        controls.addWidget(self.run_button, 0, 7)
        controls.addWidget(QtWidgets.QLabel("Apply family"), 1, 0)
        controls.addWidget(self.division_frequency_combo, 1, 1, 1, 2)
        controls.addWidget(self.apply_button, 1, 3)
        controls.addWidget(self.clear_button, 1, 4)
        controls.addWidget(self.legend_check, 1, 5)
        controls.addWidget(self.division_check, 1, 6)
        controls.setColumnStretch(8, 1)
        layout.addLayout(controls)

        self.status_label = QtWidgets.QLabel("TDFD: no result")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.plot = PlotPane("TDFD amplitudes")
        self.plot.set_labels("Amplitude", "Time")
        layout.addWidget(self.plot, 3)
        self.phase_plot = PlotPane("TDFD phases")
        self.phase_plot.set_labels("Phase [rad]", "Time")
        layout.addWidget(self.phase_plot, 2)
        self.division_label = QtWidgets.QLabel("Division: no TDFD result")
        self.division_label.setWordWrap(True)
        layout.addWidget(self.division_label)
        self.division_plot = PlotPane("TDFD sliding windows")
        self.division_plot.set_labels("Flux", "Time")
        layout.addWidget(self.division_plot, 2)
        self.summary = QtWidgets.QPlainTextEdit()
        self.summary.setReadOnly(True)
        layout.addWidget(self.summary, 1)

        self._result: TdfdResult | None = None
        self.run_button.clicked.connect(self.run_requested.emit)
        self.apply_button.clicked.connect(self.apply_requested.emit)
        self.clear_button.clicked.connect(self.clear_requested.emit)
        self.legend_check.stateChanged.connect(lambda _: self._redraw_result())
        self.division_check.stateChanged.connect(lambda _: self._redraw_result())
        self.division_frequency_combo.currentIndexChanged.connect(lambda _: self._redraw_result(refresh_combo=False))
        self.auto_window_check.stateChanged.connect(lambda _: self._sync_window_controls())
        self._sync_window_controls()

    def _sync_window_controls(self) -> None:
        enabled = not self.auto_window_check.isChecked()
        self.window_points_spin.setEnabled(enabled)
        self.step_points_spin.setEnabled(enabled)

    def set_legend_visible(self, visible: bool) -> None:
        self.legend_check.blockSignals(True)
        self.legend_check.setChecked(bool(visible))
        self.legend_check.blockSignals(False)
        self.plot.set_legend_visible(bool(visible))
        self.phase_plot.set_legend_visible(bool(visible))
        self._redraw_result()

    def set_correction_status(self, text: str) -> None:
        if self._result is None:
            self.status_label.setText(text or "TDFD: no result")
        else:
            self.status_label.setText(text or self._result_status_text(self._result))

    def configure_sources(self, *, has_residual: bool, has_component: bool) -> None:
        current = self.source_combo.currentData()
        for index in range(self.source_combo.count()):
            data = self.source_combo.itemData(index)
            enabled = True
            if data == "residual":
                enabled = has_residual
            elif data == "component":
                enabled = has_component
            self.source_combo.model().item(index).setEnabled(enabled)
        current_enabled = current == "original" or (current == "residual" and has_residual) or (current == "component" and has_component)
        if current_enabled:
            index = self.source_combo.findData(current)
            if index >= 0:
                self.source_combo.setCurrentIndex(index)
        elif has_residual:
            self.source_combo.setCurrentIndex(self.source_combo.findData("residual"))
        else:
            self.source_combo.setCurrentIndex(self.source_combo.findData("original"))

    def set_families(self, families: list[tuple[int, str, float]]) -> None:
        current = self.division_frequency_combo.currentData()
        self.division_frequency_combo.blockSignals(True)
        self.division_frequency_combo.clear()
        for base_index, label, frequency in families:
            self.division_frequency_combo.addItem(f"{label}  f={fixed_text(float(frequency))}", int(base_index))
        target = self.division_frequency_combo.findData(current)
        self.division_frequency_combo.setCurrentIndex(target if target >= 0 else (0 if families else -1))
        self.division_frequency_combo.setEnabled(bool(families))
        self.apply_button.setEnabled(bool(families))
        self.division_frequency_combo.blockSignals(False)

    def set_options_from_settings(
        self,
        *,
        source: str,
        auto_window: bool,
        window_points: int,
        step_points: int,
        selected_base_index: int | None,
    ) -> None:
        index = self.source_combo.findData(source)
        if index >= 0:
            self.source_combo.setCurrentIndex(index)
        self.auto_window_check.setChecked(bool(auto_window))
        if window_points > 0:
            self.window_points_spin.setValue(int(window_points))
        if step_points > 0:
            self.step_points_spin.setValue(int(step_points))
        if selected_base_index is not None:
            target = self.division_frequency_combo.findData(int(selected_base_index))
            if target >= 0:
                self.division_frequency_combo.setCurrentIndex(target)
        self._sync_window_controls()

    def options(self) -> TdfdOptions:
        return TdfdOptions(
            source=str(self.source_combo.currentData() or "residual"),
            auto_window=self.auto_window_check.isChecked(),
            window_points=self.window_points_spin.value(),
            step_points=self.step_points_spin.value(),
            selected_base_index=self.selected_base_index(),
        )

    def selected_base_index(self) -> int | None:
        value = self.division_frequency_combo.currentData()
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def set_result(self, result: TdfdResult) -> None:
        self._result = result
        self._redraw_result()

    def result(self) -> TdfdResult | None:
        return self._result

    def clear_result(self) -> None:
        self._result = None
        self.plot.clear()
        self.phase_plot.clear()
        self.division_plot.clear()
        self.division_label.setText("Division: no TDFD result")
        self.status_label.setText("TDFD: no result")
        self.summary.clear()

    def _redraw_result(self, *, refresh_combo: bool = True) -> None:
        result = self._result
        self.plot.clear()
        self.phase_plot.clear()
        self.division_plot.clear()
        show_division = self.division_check.isChecked()
        self.division_label.setVisible(show_division)
        self.division_plot.setVisible(show_division)
        self.division_frequency_label.setVisible(False)
        self.plot.set_legend_visible(self.legend_check.isChecked())
        self.phase_plot.set_legend_visible(self.legend_check.isChecked())
        if result is None:
            self.division_label.setText("Division: no TDFD result")
            return
        if refresh_combo:
            self._set_result_family_items(result)
        self.status_label.setText(self._result_status_text(result))
        if show_division:
            self._draw_division_plot(result)
        if not result.bins:
            self.summary.setPlainText(result.message or "No TDFD windows had enough data points.")
            return
        times = result.window_centers
        labels = result.frequency_labels or tuple(f"f{index + 1}" for index in range(len(result.report_terms)))
        for idx, label in enumerate(labels):
            amps = np.array([row.amplitudes[idx] for row in result.bins])
            phases = np.unwrap(np.array([row.phases[idx] for row in result.bins]))
            color = PlotPane.palette_color(idx)
            self.plot.plot_line(label, times, amps, color=color, width=2.0, title=label)
            self.plot.plot_points(f"{label}_points", times, amps, color=color, size=4, opacity=0.82, pen_color=color)
            self.phase_plot.plot_line(label, times, phases, color=color, width=1.7, title=label)
            self.phase_plot.plot_points(f"{label}_phase_points", times, phases, color=color, size=3, opacity=0.75, pen_color=color)
        self.plot.auto_range()
        self.phase_plot.auto_range()
        lines = [
            f"windows used: {len(result.bins)}",
            f"window points: {result.window_points}",
            f"step points: {result.step_points}",
            f"fit parameters: {result.fit_parameter_count}",
            f"fit terms: {', '.join(term.label for term in result.fit_terms) or 'none'}",
            f"correction terms: {', '.join(result.fit_terms[index].label for index in result.correction_term_indexes) or 'none'}",
            f"full-model residual std: {fixed_text(np.std(result.residuals.flux))}",
            f"corrected residual std: {fixed_text(np.std(result.corrected_residuals.flux)) if result.corrected_residuals else 'n/a'}",
            "",
            "mid_time n_points residual_std",
        ]
        lines.extend(f"{fixed_text(row.mid_time):>8s} {row.n_points:8d} {fixed_text(row.residual_std):>12s}" for row in result.bins)
        self.summary.setPlainText("\n".join(lines))

    def _result_status_text(self, result: TdfdResult) -> str:
        source = result.options.source
        family = self._family_text(result)
        return (
            f"TDFD ready: source={source}, family={family}, "
            f"window={result.window_points} pts, step={result.step_points} pts"
        )

    def _set_result_family_items(self, result: TdfdResult) -> None:
        current = self.division_frequency_combo.currentData()
        self.division_frequency_combo.blockSignals(True)
        self.division_frequency_combo.clear()
        for term in result.report_terms:
            if term.base_index is not None:
                self.division_frequency_combo.addItem(f"{term.label}  f={fixed_text(float(term.frequency))}", int(term.base_index))
        target = self.division_frequency_combo.findData(current)
        if target < 0 and result.selected_base_index is not None:
            target = self.division_frequency_combo.findData(int(result.selected_base_index))
        self.division_frequency_combo.setCurrentIndex(target if target >= 0 else (0 if self.division_frequency_combo.count() else -1))
        self.division_frequency_combo.setEnabled(self.division_frequency_combo.count() > 0)
        self.apply_button.setEnabled(self.division_frequency_combo.count() > 0)
        self.division_frequency_combo.blockSignals(False)

    def _family_text(self, result: TdfdResult) -> str:
        base_index = self.selected_base_index()
        if base_index is None:
            base_index = result.selected_base_index
        for term in result.report_terms:
            if term.base_index == base_index:
                return f"{term.label}={fixed_text(term.frequency)}"
        return "none"

    def _draw_division_plot(self, result: TdfdResult) -> None:
        light_curve = result.source_light_curve or result.residuals
        if len(light_curve.time) == 0:
            return
        family_text = self._family_text(result)
        self.division_label.setText(
            f"Division for {family_text}; sliding windows={len(result.window_centers)}, "
            f"window={result.window_points} pts, step={result.step_points} pts. "
            "Gray points are the TDFD source; colored ticks mark window centers."
        )
        self.division_plot.plot_points(
            "tdfd_source",
            light_curve.time,
            light_curve.flux,
            color="#475569",
            size=3,
            opacity=0.45,
            pen_color=None,
        )
        if len(result.window_centers) == 0:
            self.division_plot.auto_range()
            return
        ymin = float(np.nanmin(light_curve.flux))
        ymax = float(np.nanmax(light_curve.flux))
        yrange = ymax - ymin if ymax > ymin else 1.0
        center_y = np.full_like(result.window_centers, ymin + 0.08 * yrange, dtype=float)
        self.division_plot.plot_points(
            "tdfd_window_centers",
            result.window_centers,
            center_y,
            color="#dc2626",
            size=5,
            opacity=0.9,
            pen_color="#7f1d1d",
        )
        for index, (start, end) in enumerate(zip(result.window_starts, result.window_ends)):
            color = PlotPane.palette_color(index)
            self.division_plot.add_vertical_marker(float(start), "", color=color, width=0.8, opacity=0.22, style="dash")
            self.division_plot.add_vertical_marker(float(end), "", color=color, width=0.8, opacity=0.22, style="dash")
        self.division_plot.auto_range()
