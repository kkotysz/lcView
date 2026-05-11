"""Small plotting wrapper around pyqtgraph with a no-op fallback."""

from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtWidgets

try:
    import pyqtgraph as pg
except Exception:  # pragma: no cover - exercised only without optional GUI dependency
    pg = None


class PlotPane(QtWidgets.QWidget):
    clicked_x = QtCore.Signal(float)

    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: dict[str, object] = {}
        self._markers: list[object] = []
        self._selected_marker: object | None = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if pg is None:
            self._plot = None
            self._label = QtWidgets.QLabel(f"{title}\nInstall pyqtgraph to see interactive plots.")
            self._label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(self._label)
        else:
            self._plot = pg.PlotWidget(title=title)
            self._plot.setBackground("#ffffff")
            self._plot.showGrid(x=True, y=True, alpha=0.25)
            self._plot.scene().sigMouseClicked.connect(self._on_clicked)
            plot_item = self._plot.getPlotItem()
            for axis_name in ("left", "bottom"):
                axis = plot_item.getAxis(axis_name)
                axis.setPen(pg.mkPen("#4b5563"))
                axis.setTextPen(pg.mkPen("#111827"))
            layout.addWidget(self._plot)

    def set_labels(self, left: str, bottom: str) -> None:
        if self._plot is not None:
            self._plot.setLabel("left", left)
            self._plot.setLabel("bottom", bottom)

    def plot_line(self, name: str, x: np.ndarray, y: np.ndarray, color: str = "#2d7ff9") -> None:
        if self._plot is None:
            return
        item = self._items.get(name)
        pen = pg.mkPen(color, width=1.2)
        if item is None:
            self._items[name] = self._plot.plot(x, y, pen=pen)
        else:
            item.setData(x, y)

    def plot_error_bars(self, name: str, x: np.ndarray, y: np.ndarray, error: np.ndarray, color: str = "#475569") -> None:
        if self._plot is None:
            return
        self.clear_item(name)
        item = pg.ErrorBarItem(
            x=np.asarray(x, dtype=float),
            y=np.asarray(y, dtype=float),
            top=np.asarray(error, dtype=float),
            bottom=np.asarray(error, dtype=float),
            beam=0.0,
            pen=pg.mkPen(color, width=0.7),
        )
        self._items[name] = item
        self._plot.addItem(item)

    def plot_points(self, name: str, x: np.ndarray, y: np.ndarray, color: str = "#1d4ed8", size: int = 5) -> None:
        if self._plot is None:
            return
        item = self._items.get(name)
        effective_size = max(size, 5)
        brush = pg.mkBrush(color)
        pen = pg.mkPen("#0f172a", width=0.8)
        if item is None:
            self._items[name] = self._plot.plot(
                x,
                y,
                pen=None,
                symbol="o",
                symbolSize=effective_size,
                symbolBrush=brush,
                symbolPen=pen,
            )
        else:
            item.setData(x, y, symbolSize=effective_size, symbolBrush=brush, symbolPen=pen)

    def clear_item(self, name: str) -> None:
        if self._plot is None:
            self._items.pop(name, None)
            return
        item = self._items.pop(name, None)
        if item is not None:
            self._plot.removeItem(item)

    def clear_markers(self) -> None:
        if self._plot is None:
            return
        for marker in self._markers:
            self._plot.removeItem(marker)
        self._markers.clear()

    def add_vertical_marker(self, x: float, label: str = "", color: str = "#d33939") -> None:
        if self._plot is None:
            return
        line = pg.InfiniteLine(pos=x, angle=90, pen=pg.mkPen(color, width=1.0), label=label, labelOpts={"position": 0.92})
        self._markers.append(line)
        self._plot.addItem(line)

    def set_selected_marker(self, x: float, label: str = "") -> None:
        if self._plot is None:
            return
        self.clear_selected_marker()
        line = pg.InfiniteLine(
            pos=x,
            angle=90,
            pen=pg.mkPen("#f5a623", width=2.4),
            label=label,
            labelOpts={"position": 0.82, "color": "#f5a623"},
        )
        self._selected_marker = line
        self._plot.addItem(line)

    def clear_selected_marker(self) -> None:
        if self._plot is None or self._selected_marker is None:
            return
        self._plot.removeItem(self._selected_marker)
        self._selected_marker = None

    def auto_range(self) -> None:
        if self._plot is not None:
            self._plot.autoRange()

    def clear(self) -> None:
        if self._plot is None:
            return
        self._plot.clear()
        self._items.clear()
        self._markers.clear()
        self._selected_marker = None

    def _on_clicked(self, event) -> None:
        if self._plot is None or event.button() != QtCore.Qt.LeftButton:
            return
        point = self._plot.plotItem.vb.mapSceneToView(event.scenePos())
        self.clicked_x.emit(float(point.x()))
