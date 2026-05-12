"""Qt dialog for Akima detrending preview."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from lcview.core.detrending import DetrendResult, akima_detrend
from lcview.core.lightcurve import LightCurve
from .plots import PlotPane
from .widgets import SignificantDoubleSpinBox


class DetrendDialog(QtWidgets.QDialog):
    def __init__(self, light_curve: LightCurve, parent: QtWidgets.QWidget | None = None, *, y_inverted: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akima detrending")
        self.light_curve = light_curve
        self.y_inverted = bool(y_inverted)
        self.result: DetrendResult | None = None

        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        self.bin_spin = QtWidgets.QDoubleSpinBox()
        self.bin_spin.setRange(0.1, 100000.0)
        self.bin_spin.setDecimals(2)
        self.bin_spin.setValue(max(1.0, light_curve.baseline / 50.0))
        self.points_check = QtWidgets.QCheckBox("points per bin")
        self.period_spin = SignificantDoubleSpinBox()
        self.period_spin.setRange(0.0, 100000.0)
        self.period_spin.setValue(0.0)
        controls.addWidget(QtWidgets.QLabel("Bin"))
        controls.addWidget(self.bin_spin)
        controls.addWidget(self.points_check)
        controls.addWidget(QtWidgets.QLabel("Period"))
        controls.addWidget(self.period_spin)
        layout.addLayout(controls)

        self.plot = PlotPane("Detrending preview")
        self.plot.set_labels("Magnitude" if self.y_inverted else "Flux", "Time/phase")
        self.plot.set_y_inverted(self.y_inverted)
        layout.addWidget(self.plot, 1)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.bin_spin.valueChanged.connect(self.refresh)
        self.points_check.stateChanged.connect(self.refresh)
        self.period_spin.valueChanged.connect(self.refresh)
        self.refresh()

    @QtCore.Slot()
    def refresh(self) -> None:
        try:
            period = self.period_spin.value() or None
            self.result = akima_detrend(self.light_curve, self.bin_spin.value(), by_points=self.points_check.isChecked(), period=period)
        except Exception:
            return
        x = self.light_curve.time if period is None else self.light_curve.time % period / period
        self.plot.plot_points("lc", x, self.light_curve.flux, size=3)
        self.plot.plot_line("trend", self.result.trend_x, self.result.trend_y, color="#d33939")
        self.plot.auto_range()
