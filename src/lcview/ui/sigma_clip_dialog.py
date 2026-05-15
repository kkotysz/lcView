"""Sigma clipping preview and point selection dialog."""

from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtWidgets

from lcview.core.lightcurve import LightCurve
from lcview.core.sigma_clip import SigmaClipResult, sigma_clip_light_curve
from lcview.display import fixed_text
from .plots import PlotPane


class SigmaRejectedTableModel(QtCore.QAbstractTableModel):
    headers = ["Reject", "#", "Time", "Flux", "Error"]

    def __init__(self, light_curve: LightCurve, initial_reject_mask: np.ndarray) -> None:
        super().__init__()
        self.light_curve = light_curve
        self.rejected_indexes = np.flatnonzero(initial_reject_mask)
        self.reject_flags = np.ones(len(self.rejected_indexes), dtype=bool)

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self.rejected_indexes)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self.headers)

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        source_index = int(self.rejected_indexes[row])
        if role == QtCore.Qt.CheckStateRole and col == 0:
            return QtCore.Qt.CheckState.Checked if self.reject_flags[row] else QtCore.Qt.CheckState.Unchecked
        if role not in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return None
        if col == 0:
            return ""
        if col == 1:
            return source_index + 1
        if col == 2:
            return fixed_text(self.light_curve.time[source_index])
        if col == 3:
            return fixed_text(self.light_curve.flux[source_index])
        if col == 4:
            return fixed_text(self.light_curve.error[source_index])
        return None

    def flags(self, index: QtCore.QModelIndex):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        return flags

    def setData(self, index: QtCore.QModelIndex, value, role=QtCore.Qt.EditRole) -> bool:
        if not index.isValid() or index.column() != 0 or role != QtCore.Qt.CheckStateRole:
            return False
        try:
            checked = QtCore.Qt.CheckState(value) == QtCore.Qt.CheckState.Checked
        except (TypeError, ValueError):
            checked = value == QtCore.Qt.CheckState.Checked
        self.reject_flags[index.row()] = checked
        self.dataChanged.emit(index, index, [QtCore.Qt.CheckStateRole])
        return True

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None

    def selected_reject_mask(self) -> np.ndarray:
        mask = np.zeros(len(self.light_curve.time), dtype=bool)
        mask[self.rejected_indexes[self.reject_flags]] = True
        return mask

    def set_all(self, rejected: bool) -> None:
        if len(self.reject_flags) == 0:
            return
        self.reject_flags[:] = bool(rejected)
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self.reject_flags) - 1, 0)
        self.dataChanged.emit(top_left, bottom_right, [QtCore.Qt.CheckStateRole])

    def set_source_indexes(self, source_indexes: np.ndarray, rejected: bool = True) -> int:
        if len(source_indexes) == 0:
            return 0
        selected = set(int(index) for index in source_indexes)
        changed = 0
        existing = {int(source_index): row for row, source_index in enumerate(self.rejected_indexes)}
        new_indexes = sorted(selected.difference(existing)) if rejected else []
        if new_indexes:
            start = len(self.rejected_indexes)
            self.beginInsertRows(QtCore.QModelIndex(), start, start + len(new_indexes) - 1)
            self.rejected_indexes = np.concatenate([self.rejected_indexes, np.asarray(new_indexes, dtype=int)])
            self.reject_flags = np.concatenate([self.reject_flags, np.ones(len(new_indexes), dtype=bool)])
            self.endInsertRows()
            changed += len(new_indexes)
        for row, source_index in enumerate(self.rejected_indexes):
            if int(source_index) in selected and self.reject_flags[row] != rejected:
                self.reject_flags[row] = bool(rejected)
                changed += 1
        if changed:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self.reject_flags) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [QtCore.Qt.CheckStateRole])
        return changed


class SigmaClipPlotSelector(QtCore.QObject):
    selection_finished = QtCore.Signal(float, float, float, float)

    def __init__(self, plot: PlotPane, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.plot = plot
        self._rubber_band: QtWidgets.QRubberBand | None = None
        self._origin = QtCore.QPoint()
        self._active = False
        self._viewport = None
        if plot._plot is not None:
            self._viewport = plot._plot.viewport()
            self._viewport.installEventFilter(self)

    def dispose(self) -> None:
        if self._viewport is not None:
            self._viewport.removeEventFilter(self)
            self._viewport = None
        if self._rubber_band is not None:
            self._rubber_band.hide()
            self._rubber_band.deleteLater()
            self._rubber_band = None

    def eventFilter(self, watched, event) -> bool:
        if self.plot._plot is None or watched is not self._viewport:
            return False
        event_type = event.type()
        if event_type == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._active = True
            if self._rubber_band is None:
                self._rubber_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Shape.Rectangle, self.plot._plot.viewport())
            self._rubber_band.setGeometry(QtCore.QRect(self._origin, QtCore.QSize()))
            self._rubber_band.show()
            return True
        if event_type == QtCore.QEvent.Type.MouseMove and self._active and self._rubber_band is not None:
            self._rubber_band.setGeometry(QtCore.QRect(self._origin, event.position().toPoint()).normalized())
            return True
        if event_type == QtCore.QEvent.Type.MouseButtonRelease and self._active and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._active = False
            end = event.position().toPoint()
            if self._rubber_band is not None:
                self._rubber_band.hide()
            rect = QtCore.QRect(self._origin, end).normalized()
            if rect.width() >= 3 and rect.height() >= 3:
                x0, x1, y0, y1 = self._rect_to_data_bounds(rect)
                self.selection_finished.emit(x0, x1, y0, y1)
            return True
        return False

    def _rect_to_data_bounds(self, rect: QtCore.QRect) -> tuple[float, float, float, float]:
        assert self.plot._plot is not None
        view_box = self.plot._plot.plotItem.vb
        top_left = view_box.mapSceneToView(self.plot._plot.mapToScene(rect.topLeft()))
        bottom_right = view_box.mapSceneToView(self.plot._plot.mapToScene(rect.bottomRight()))
        x0, x1 = sorted((float(top_left.x()), float(bottom_right.x())))
        y0, y1 = sorted((float(top_left.y()), float(bottom_right.y())))
        return x0, x1, y0, y1


class SigmaClipDialog(QtWidgets.QDialog):
    def __init__(
        self,
        light_curve: LightCurve,
        result: SigmaClipResult,
        parent: QtWidgets.QWidget | None = None,
        *,
        y_inverted: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sigma clipping preview")
        self.light_curve = light_curve
        self.clip_result = result
        self.y_inverted = bool(y_inverted)
        self.result_mode = "close"
        self.table_model = SigmaRejectedTableModel(light_curve, ~result.keep_mask)

        layout = QtWidgets.QVBoxLayout(self)
        options = QtWidgets.QHBoxLayout()
        self.sigma_spin = QtWidgets.QDoubleSpinBox()
        self.sigma_spin.setRange(0.1, 20.0)
        self.sigma_spin.setDecimals(2)
        self.sigma_spin.setSingleStep(0.1)
        self.sigma_spin.setValue(float(result.sigma))
        self.maxiters_spin = QtWidgets.QSpinBox()
        self.maxiters_spin.setRange(1, 100)
        self.maxiters_spin.setValue(6)
        self.preview_button = QtWidgets.QPushButton("Preview clip")
        self.summary_label = QtWidgets.QLabel()
        options.addWidget(QtWidgets.QLabel("Sigma"))
        options.addWidget(self.sigma_spin)
        options.addWidget(QtWidgets.QLabel("Max iter"))
        options.addWidget(self.maxiters_spin)
        options.addWidget(self.preview_button)
        options.addWidget(self.summary_label, 1)
        layout.addLayout(options)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.plot = PlotPane("Sigma clipping preview")
        self.plot.set_labels("Magnitude" if self.y_inverted else "Flux", "Time")
        self.plot.set_y_inverted(self.y_inverted)
        self.plot_selector = SigmaClipPlotSelector(self.plot, self)
        splitter.addWidget(self.plot)

        table_container = QtWidgets.QWidget()
        table_layout = QtWidgets.QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        controls = QtWidgets.QHBoxLayout()
        self.select_all_button = QtWidgets.QPushButton("Reject all")
        self.select_none_button = QtWidgets.QPushButton("Reject none")
        self.selection_mode_combo = QtWidgets.QComboBox()
        self.selection_mode_combo.addItem("Box: reject", True)
        self.selection_mode_combo.addItem("Box: keep", False)
        controls.addWidget(self.select_all_button)
        controls.addWidget(self.select_none_button)
        controls.addWidget(QtWidgets.QLabel("Mouse selection"))
        controls.addWidget(self.selection_mode_combo)
        controls.addStretch(1)
        table_layout.addLayout(controls)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.resizeColumnsToContents()
        table_layout.addWidget(self.table, 1)
        splitter.addWidget(table_container)
        splitter.setSizes([420, 220])
        layout.addWidget(splitter, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.clip_close_button = QtWidgets.QPushButton("Clip and close")
        self.clip_continue_button = QtWidgets.QPushButton("Clip and continue")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        buttons.addWidget(self.clip_close_button)
        buttons.addWidget(self.clip_continue_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.clip_close_button.clicked.connect(self._clip_and_close)
        self.clip_continue_button.clicked.connect(self._clip_and_continue)
        self.cancel_button.clicked.connect(self.reject)
        self.preview_button.clicked.connect(self.recompute_clip)
        self.select_all_button.clicked.connect(lambda: self._set_all(True))
        self.select_none_button.clicked.connect(lambda: self._set_all(False))
        self.table_model.dataChanged.connect(lambda *_: self.refresh_plot())
        self.plot_selector.selection_finished.connect(self.apply_plot_selection)
        self.refresh_plot()

    def selected_reject_mask(self) -> np.ndarray:
        return self.table_model.selected_reject_mask()

    def cleaned_light_curve(self) -> LightCurve:
        return self.light_curve.masked(~self.selected_reject_mask())

    def sigma_value(self) -> float:
        return float(self.sigma_spin.value())

    def maxiters_value(self) -> int:
        return int(self.maxiters_spin.value())

    @QtCore.Slot()
    def recompute_clip(self) -> None:
        self.set_result(sigma_clip_light_curve(self.light_curve, sigma=self.sigma_value(), maxiters=self.maxiters_value()))

    def set_result(self, result: SigmaClipResult) -> None:
        self.clip_result = result
        self.table_model = SigmaRejectedTableModel(self.light_curve, ~result.keep_mask)
        self.table.setModel(self.table_model)
        self.table.resizeColumnsToContents()
        self.table_model.dataChanged.connect(lambda *_: self.refresh_plot())
        self.refresh_plot()

    def _clip_and_close(self) -> None:
        self.result_mode = "close"
        self.accept()

    def _clip_and_continue(self) -> None:
        self.result_mode = "continue"
        self.accept()

    def _set_all(self, rejected: bool) -> None:
        self.table_model.set_all(rejected)
        self.refresh_plot()

    def apply_plot_selection(self, x0: float, x1: float, y0: float, y1: float, rejected: bool | None = None) -> int:
        if rejected is None:
            rejected = bool(self.selection_mode_combo.currentData())
        in_box = (
            (self.light_curve.time >= x0)
            & (self.light_curve.time <= x1)
            & (self.light_curve.flux >= y0)
            & (self.light_curve.flux <= y1)
        )
        changed = self.table_model.set_source_indexes(np.flatnonzero(in_box), rejected=bool(rejected))
        if changed:
            self.refresh_plot()
        return changed

    @QtCore.Slot()
    def refresh_plot(self) -> None:
        reject_mask = self.selected_reject_mask()
        keep_mask = ~reject_mask
        rejected_count = int(np.count_nonzero(reject_mask))
        self.summary_label.setText(f"Sigma={fixed_text(self.sigma_value())}; selected {rejected_count} rejected points.")
        enabled = rejected_count > 0
        self.clip_close_button.setEnabled(enabled)
        self.clip_continue_button.setEnabled(enabled)
        self.plot.plot_points("kept", self.light_curve.time[keep_mask], self.light_curve.flux[keep_mask], color="#2563eb", size=3, opacity=0.45, pen_color=None)
        if np.any(reject_mask):
            self.plot.plot_points(
                "rejected",
                self.light_curve.time[reject_mask],
                self.light_curve.flux[reject_mask],
                color="#dc2626",
                size=7,
                opacity=0.95,
                pen_color="#7f1d1d",
            )
        else:
            self.plot.clear_item("rejected")
        self.plot.auto_range()

    def closeEvent(self, event) -> None:
        self.plot_selector.dispose()
        super().closeEvent(event)
