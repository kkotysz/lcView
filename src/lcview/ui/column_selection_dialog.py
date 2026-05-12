"""Dialog for selecting light-curve columns from a generic table."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from lcview.core.lightcurve import LightCurveTable, infer_light_curve_columns


class TablePreviewModel(QtCore.QAbstractTableModel):
    def __init__(self, table: LightCurveTable, max_rows: int = 100) -> None:
        super().__init__()
        self.table = table
        self.max_rows = max_rows

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return min(len(self.table.data), self.max_rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return self.table.column_count

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or role not in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return None
        return str(self.table.data.iat[index.row(), index.column()])

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            return f"{section + 1}: {self.table.column_names[section]}"
        return section + 1


def _column_label(table: LightCurveTable, index: int) -> str:
    return f"{index + 1}: {table.column_names[index]}"


def _find_named_column(table: LightCurveTable, keywords: tuple[str, ...], used: set[int]) -> int | None:
    for index, name in enumerate(table.column_names):
        normalized = name.strip().lower()
        if index not in used and any(keyword in normalized for keyword in keywords):
            return index
    return None


def suggest_light_curve_columns(table: LightCurveTable) -> tuple[int, int, int]:
    try:
        fallback = infer_light_curve_columns(table)
    except ValueError:
        fallback = tuple(range(min(3, table.column_count)))
    used: set[int] = set()
    time_col = _find_named_column(table, ("time", "hjd", "bjd", "jd", "mjd", "date"), used)
    if time_col is None:
        time_col = fallback[0]
    used.add(time_col)
    flux_col = _find_named_column(table, ("flux", "mag", "magnitude", "brightness", "value"), used)
    if flux_col is None:
        flux_col = fallback[1]
    used.add(flux_col)
    error_col = _find_named_column(table, ("err", "error", "sigma", "unc", "e_"), used)
    if error_col is None:
        error_col = fallback[2]
    return int(time_col), int(flux_col), int(error_col)


class ColumnSelectionDialog(QtWidgets.QDialog):
    def __init__(
        self,
        table: LightCurveTable,
        parent: QtWidgets.QWidget | None = None,
        initial_columns: tuple[int, int, int] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select light-curve columns")
        self.table_data = table

        layout = QtWidgets.QVBoxLayout(self)
        header_text = "header detected" if table.has_header else "no header detected"
        layout.addWidget(
            QtWidgets.QLabel(
                f"{table.path.name}: {table.column_count} columns, {table.delimiter_name} separated, {header_text}."
            )
        )

        form = QtWidgets.QFormLayout()
        self.time_combo = QtWidgets.QComboBox()
        self.flux_combo = QtWidgets.QComboBox()
        self.error_combo = QtWidgets.QComboBox()
        for combo in (self.time_combo, self.flux_combo, self.error_combo):
            for index in range(table.column_count):
                combo.addItem(_column_label(table, index), index)
        defaults = initial_columns or suggest_light_curve_columns(table)
        for combo, index in zip((self.time_combo, self.flux_combo, self.error_combo), defaults):
            combo.setCurrentIndex(max(0, combo.findData(index)))
        form.addRow("Time", self.time_combo)
        form.addRow("Flux / magnitude", self.flux_combo)
        form.addRow("Error", self.error_combo)
        layout.addLayout(form)

        self.preview = QtWidgets.QTableView()
        self.preview.setModel(TablePreviewModel(table))
        self.preview.resizeColumnsToContents()
        layout.addWidget(self.preview, 1)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.resize(720, 520)

    def selected_columns(self) -> tuple[int, int, int]:
        return (
            int(self.time_combo.currentData()),
            int(self.flux_combo.currentData()),
            int(self.error_combo.currentData()),
        )

    def accept(self) -> None:
        columns = self.selected_columns()
        if len(set(columns)) != 3:
            QtWidgets.QMessageBox.warning(self, "Invalid columns", "Time, flux and error columns must be distinct.")
            return
        super().accept()
