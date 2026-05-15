"""Frequency-results report panel."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from lcview.core.results import FrequencyReport, FrequencyReportRow
from lcview.display import fixed_text
from .models import COEFFICIENTS_ROLE, FrequencyReportTableModel


class ResultsPanel(QtWidgets.QWidget):
    row_selected = QtCore.Signal(object)
    export_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        self.summary_label = QtWidgets.QLabel("Results: no fit report")
        self.summary_label.setWordWrap(True)
        self.copy_button = QtWidgets.QPushButton("Copy TSV")
        self.export_button = QtWidgets.QPushButton("Export CSV")
        controls.addWidget(self.summary_label, 1)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.export_button)
        layout.addLayout(controls)

        self.model = FrequencyReportTableModel()
        self.proxy = QtCore.QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(QtCore.Qt.ItemDataRole.UserRole)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        mono.setPointSize(max(9, mono.pointSize() - 1))
        self.table.setFont(mono)
        layout.addWidget(self.table, 1)

        self.copy_button.clicked.connect(self.copy_tsv)
        self.export_button.clicked.connect(self.export_requested.emit)
        selection = self.table.selectionModel()
        selection.currentRowChanged.connect(self._current_row_changed)

    def set_report(self, report: FrequencyReport | None) -> None:
        self.model.set_report(report)
        self.proxy.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
        self._fit_columns()
        self.summary_label.setText(self._summary_text(report))

    def selected_row(self) -> FrequencyReportRow | None:
        proxy_index = self.table.currentIndex()
        if not proxy_index.isValid():
            return None
        source_index = self.proxy.mapToSource(proxy_index)
        return self.model.row_at(source_index.row())

    def select_coefficients(self, coefficients: tuple[int, ...] | None) -> bool:
        selection = self.table.selectionModel()
        if selection is None:
            return False
        blocker = QtCore.QSignalBlocker(selection)
        try:
            if coefficients is None:
                selection.clearSelection()
                self.table.setCurrentIndex(QtCore.QModelIndex())
                return False
            for source_row, row in enumerate(self.model.rows):
                if tuple(row.coefficients) != tuple(coefficients):
                    continue
                source_index = self.model.index(source_row, 0)
                proxy_index = self.proxy.mapFromSource(source_index)
                if not proxy_index.isValid():
                    return False
                self.table.selectRow(proxy_index.row())
                self.table.setCurrentIndex(proxy_index)
                self.table.scrollTo(proxy_index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
                return True
            selection.clearSelection()
            self.table.setCurrentIndex(QtCore.QModelIndex())
            return False
        finally:
            del blocker

    def copy_tsv(self) -> str:
        text = self.model.tsv_text()
        QtWidgets.QApplication.clipboard().setText(text)
        return text

    def csv_text(self) -> str:
        stream = StringIO()
        writer = csv.writer(stream)
        writer.writerows(self.model.raw_rows())
        return stream.getvalue()

    def export_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(self.csv_text())
        return path

    def _current_row_changed(self, current: QtCore.QModelIndex, _previous: QtCore.QModelIndex) -> None:
        if not current.isValid():
            return
        source_index = self.proxy.mapToSource(current)
        row = self.model.row_at(source_index.row())
        if row is not None:
            self.row_selected.emit(row)

    def _fit_columns(self) -> None:
        self.table.resizeColumnsToContents()
        for col, width in {0: 42, 1: 38, 2: 46, 3: 72, 4: 96, 13: 90}.items():
            self.table.setColumnWidth(col, max(width, self.table.columnWidth(col)))

    @staticmethod
    def _summary_text(report: FrequencyReport | None) -> str:
        if report is None:
            return "Results: no fit report"
        state = "stale until next fit" if report.stale else "ready"
        return (
            f"Results {state}: Nobs={report.nobs}, terms={report.n_terms}, active={report.n_active_terms}, "
            f"SDEV={fixed_text(report.sdev)}, source={report.fit_source}, updated={report.updated_at}"
        )
