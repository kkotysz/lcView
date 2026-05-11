"""TDFD controls and result view."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets
import numpy as np

from lcview.core.tdfd import TdfdResult
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
        controls.addWidget(QtWidgets.QLabel("Bins"))
        controls.addWidget(self.bins_spin)
        controls.addWidget(self.run_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.plot = PlotPane("TDFD amplitudes")
        self.plot.set_labels("Amplitude", "Time")
        layout.addWidget(self.plot, 3)
        self.summary = QtWidgets.QPlainTextEdit()
        self.summary.setReadOnly(True)
        layout.addWidget(self.summary, 1)
        self.run_button.clicked.connect(lambda: self.run_requested.emit(self.bins_spin.value()))

    def set_result(self, result: TdfdResult) -> None:
        self.plot.clear()
        if not result.bins:
            self.summary.setPlainText("No TDFD bins had enough data points.")
            return
        times = np.array([row.mid_time for row in result.bins])
        nfreq = len(result.bins[0].frequencies)
        for idx in range(nfreq):
            amps = np.array([row.amplitudes[idx] for row in result.bins])
            self.plot.plot_line(f"f{idx + 1}", times, amps)
        self.plot.auto_range()
        lines = [
            f"bins: {len(result.bins)}",
            f"residual std: {np.std(result.residuals.flux):.6f}",
            "",
            "mid_time n_points residual_std",
        ]
        lines.extend(f"{row.mid_time:12.5f} {row.n_points:8d} {row.residual_std:12.6f}" for row in result.bins)
        self.summary.setPlainText("\n".join(lines))
