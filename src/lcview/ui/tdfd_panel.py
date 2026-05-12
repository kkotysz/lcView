"""TDFD controls and result view."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets
import numpy as np

from lcview.core.tdfd import TdfdResult
from lcview.display import fixed_text
from .plots import PlotPane


class TdfdPanel(QtWidgets.QWidget):
    run_requested = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        self.bins_spin = QtWidgets.QSpinBox()
        self.bins_spin.setRange(2, 200)
        self.bins_spin.setValue(20)
        self.run_button = QtWidgets.QPushButton("Run TDFD")
        self.legend_check = QtWidgets.QCheckBox("Legend")
        self.legend_check.setChecked(True)
        controls.addWidget(QtWidgets.QLabel("Bins"))
        controls.addWidget(self.bins_spin)
        controls.addWidget(self.run_button)
        controls.addWidget(self.legend_check)
        controls.addStretch()
        layout.addLayout(controls)

        self.plot = PlotPane("TDFD amplitudes")
        self.plot.set_labels("Amplitude", "Time")
        layout.addWidget(self.plot, 3)
        self.summary = QtWidgets.QPlainTextEdit()
        self.summary.setReadOnly(True)
        layout.addWidget(self.summary, 1)
        self._result: TdfdResult | None = None
        self.run_button.clicked.connect(lambda: self.run_requested.emit(self.bins_spin.value()))
        self.legend_check.stateChanged.connect(lambda _: self._redraw_result())

    def set_legend_visible(self, visible: bool) -> None:
        self.legend_check.blockSignals(True)
        self.legend_check.setChecked(bool(visible))
        self.legend_check.blockSignals(False)
        self.plot.set_legend_visible(bool(visible))
        self._redraw_result()

    def set_result(self, result: TdfdResult) -> None:
        self._result = result
        self._redraw_result()

    def _redraw_result(self) -> None:
        result = self._result
        self.plot.clear()
        self.plot.set_legend_visible(self.legend_check.isChecked())
        if result is None:
            return
        if not result.bins:
            self.summary.setPlainText("No TDFD bins had enough data points.")
            return
        times = np.array([row.mid_time for row in result.bins])
        nfreq = len(result.bins[0].frequencies)
        for idx in range(nfreq):
            amps = np.array([row.amplitudes[idx] for row in result.bins])
            color = PlotPane.palette_color(idx)
            self.plot.plot_line(f"f{idx + 1}", times, amps, color=color, width=2.0, title=f"f{idx + 1}")
            self.plot.plot_points(f"f{idx + 1}_points", times, amps, color=color, size=4, opacity=0.82, pen_color=color)
        self.plot.auto_range()
        lines = [
            f"bins: {len(result.bins)}",
            f"residual std: {fixed_text(np.std(result.residuals.flux))}",
            "",
            "mid_time n_points residual_std",
        ]
        lines.extend(f"{fixed_text(row.mid_time):>8s} {row.n_points:8d} {fixed_text(row.residual_std):>12s}" for row in result.bins)
        self.summary.setPlainText("\n".join(lines))
