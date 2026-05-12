"""Small plotting wrapper around pyqtgraph with a no-op fallback."""

from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtWidgets

try:
    import pyqtgraph as pg
except Exception:  # pragma: no cover - exercised only without optional GUI dependency
    pg = None


PLOT_COLORS = (
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#f97316",
    "#7c3aed",
    "#0891b2",
    "#be123c",
    "#4d7c0f",
)


class PlotPane(QtWidgets.QWidget):
    clicked_x = QtCore.Signal(float)

    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: dict[str, object] = {}
        self._markers: list[object] = []
        self._selected_marker: object | None = None
        self._legend: object | None = None
        self._y_inverted = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if pg is None:
            self._plot = None
            self._label = QtWidgets.QLabel(f"{title}\nInstall pyqtgraph to see interactive plots.")
            self._label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(self._label)
        else:
            self._plot = pg.PlotWidget(title=title)
            self._plot.setBackground("#fbfbf8")
            self._plot.showGrid(x=True, y=True, alpha=0.18)
            self._plot.scene().sigMouseClicked.connect(self._on_clicked)
            plot_item = self._plot.getPlotItem()
            self._legend = plot_item.addLegend(offset=(12, 12))
            self._legend.setVisible(False)
            for axis_name in ("left", "bottom"):
                axis = plot_item.getAxis(axis_name)
                axis.setPen(pg.mkPen("#4b5563"))
                axis.setTextPen(pg.mkPen("#111827"))
                axis.setStyle(tickFont=self.font())
            layout.addWidget(self._plot)

    @classmethod
    def palette_color(cls, index: int) -> str:
        return PLOT_COLORS[index % len(PLOT_COLORS)]

    def set_labels(self, left: str, bottom: str) -> None:
        if self._plot is not None:
            self._plot.setLabel("left", left)
            self._plot.setLabel("bottom", bottom)

    def set_y_inverted(self, inverted: bool) -> None:
        self._y_inverted = bool(inverted)
        if self._plot is not None:
            self._plot.getPlotItem().getViewBox().invertY(self._y_inverted)

    def set_legend_visible(self, visible: bool) -> None:
        if self._legend is not None:
            self._legend.setVisible(visible)

    def plot_line(
        self,
        name: str,
        x: np.ndarray,
        y: np.ndarray,
        color: str = "#2563eb",
        width: float = 1.4,
        *,
        style: str = "solid",
        title: str | None = None,
        opacity: float = 1.0,
    ) -> None:
        if self._plot is None:
            return
        item = self._items.get(name)
        pen = self._pen(color, width=width, style=style, opacity=opacity)
        if item is None:
            kwargs = {"pen": pen}
            if title:
                kwargs["name"] = title
            item = self._plot.plot(x, y, **kwargs)
            self._configure_plot_data_item(item)
            self._items[name] = item
        else:
            item.setPen(pen)
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
            pen=self._pen(color, width=0.7, opacity=0.75),
        )
        self._items[name] = item
        self._plot.addItem(item)

    def plot_points(
        self,
        name: str,
        x: np.ndarray,
        y: np.ndarray,
        color: str = "#1d4ed8",
        size: int = 5,
        *,
        opacity: float = 0.72,
        pen_color: str | None = "#0f172a",
        title: str | None = None,
    ) -> None:
        if self._plot is None:
            return
        item = self._items.get(name)
        effective_size = max(size, 3)
        brush = pg.mkBrush(self._color(color, opacity))
        pen = None if pen_color is None else self._pen(pen_color, width=0.6, opacity=min(1.0, opacity + 0.2))
        if item is None:
            kwargs = {}
            if title:
                kwargs["name"] = title
            item = self._plot.plot(
                x,
                y,
                pen=None,
                symbol="o",
                symbolSize=effective_size,
                symbolBrush=brush,
                symbolPen=pen,
                **kwargs,
            )
            self._items[name] = item
        else:
            item.setData(x, y, symbolSize=effective_size, symbolBrush=brush, symbolPen=pen)

    def plot_hline(
        self,
        name: str,
        y: float,
        *,
        color: str = "#b45309",
        width: float = 1.4,
        style: str = "dash",
        label: str = "",
        opacity: float = 0.95,
    ) -> None:
        if self._plot is None or not np.isfinite(y):
            return
        item = self._items.get(name)
        pen = self._pen(color, width=width, style=style, opacity=opacity)
        if item is None:
            item = pg.InfiniteLine(
                pos=float(y),
                angle=0,
                pen=pen,
                label=label,
                labelOpts={"position": 0.95, "color": color},
            )
            item.setZValue(1)
            self._items[name] = item
            self._plot.addItem(item)
        else:
            item.setValue(float(y))
            item.setPen(pen)

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

    def add_vertical_marker(
        self,
        x: float,
        label: str = "",
        color: str = "#dc2626",
        *,
        width: float = 0.9,
        opacity: float = 0.48,
        style: str = "solid",
    ) -> None:
        if self._plot is None:
            return
        line = pg.InfiniteLine(
            pos=x,
            angle=90,
            pen=self._pen(color, width=width, style=style, opacity=opacity),
            label=label,
            labelOpts={"position": 0.92, "color": color},
        )
        line.setZValue(5)
        self._markers.append(line)
        self._plot.addItem(line)

    def set_selected_marker(self, x: float, label: str = "") -> None:
        if self._plot is None:
            return
        self.clear_selected_marker()
        line = pg.InfiniteLine(
            pos=x,
            angle=90,
            pen=self._pen("#f59e0b", width=2.6),
            label=label,
            labelOpts={"position": 0.82, "color": "#f59e0b"},
        )
        line.setZValue(20)
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
        for name in list(self._items):
            self.clear_item(name)
        self.clear_markers()
        self.clear_selected_marker()
        self._clear_legend_entries()

    def _on_clicked(self, event) -> None:
        if self._plot is None or event.button() != QtCore.Qt.LeftButton:
            return
        point = self._plot.plotItem.vb.mapSceneToView(event.scenePos())
        self.clicked_x.emit(float(point.x()))

    def _configure_plot_data_item(self, item: object) -> None:
        for method_name, args, kwargs in (
            ("setClipToView", (True,), {}),
            ("setDownsampling", (), {"auto": True, "method": "peak"}),
        ):
            method = getattr(item, method_name, None)
            if method is None:
                continue
            try:
                method(*args, **kwargs)
            except TypeError:
                pass

    def _clear_legend_entries(self) -> None:
        if self._legend is None:
            return
        clear = getattr(self._legend, "clear", None)
        if clear is not None:
            clear()
            return
        for item in list(getattr(self._legend, "items", [])):
            label = item[1]
            text = getattr(label, "text", "")
            try:
                self._legend.removeItem(text)
            except Exception:
                pass

    @staticmethod
    def _pen_style(style: str):
        if style in {"dash", "dashed"}:
            return QtCore.Qt.PenStyle.DashLine
        if style in {"dot", "dotted"}:
            return QtCore.Qt.PenStyle.DotLine
        return QtCore.Qt.PenStyle.SolidLine

    @staticmethod
    def _bounded_opacity(opacity: float) -> float:
        return max(0.0, min(1.0, float(opacity)))

    def _color(self, color: str, opacity: float = 1.0):
        qcolor = pg.mkColor(color)
        qcolor.setAlphaF(self._bounded_opacity(opacity))
        return qcolor

    def _pen(self, color: str, *, width: float = 1.0, style: str = "solid", opacity: float = 1.0):
        return pg.mkPen(self._color(color, opacity), width=width, style=self._pen_style(style))
