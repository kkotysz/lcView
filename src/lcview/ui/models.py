"""Qt table models for frequency state and candidates."""

from __future__ import annotations

import math
from PySide6 import QtCore

from lcview.core.combinations import FrequencyCandidate
from lcview.core.frequency_model import FrequencyModel
from lcview.core.results import FrequencyReport, FrequencyReportRow
from lcview.display import fixed_text, frequency_text, period_text_from_frequency, sig_text


COEFFICIENTS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 100
TERM_INDEX_ROLE = QtCore.Qt.ItemDataRole.UserRole + 101


KIND_LABELS = {
    "independent": ("I", "independent frequency"),
    "harmonic": ("H", "harmonic"),
    "combination": ("C", "combination frequency"),
}


def period_text(frequency: float) -> str:
    return period_text_from_frequency(frequency)


def kind_for_coefficients(kind: str, coefficients: tuple[int, ...]) -> str:
    nonzero = [value for value in coefficients if value]
    if len(nonzero) == 1 and abs(nonzero[0]) > 1:
        return "harmonic"
    return kind


def kind_code(kind: str, coefficients: tuple[int, ...] = ()) -> str:
    normalized = kind_for_coefficients(kind, coefficients)
    return KIND_LABELS.get(normalized, (normalized[:3].upper(), normalized))[0]


def kind_tooltip(kind: str, coefficients: tuple[int, ...] = ()) -> str:
    normalized = kind_for_coefficients(kind, coefficients)
    return KIND_LABELS.get(normalized, (normalized, normalized))[1]


def compact_status(status: str) -> str:
    low = "low frequency" in status
    base = status.replace("; low frequency", "")
    if base == "not resolved":
        base = "not resolved"
    suffix = " LOW" if low else ""
    return f"{base}{suffix}"


def _is_checked_state(value) -> bool:
    if value == QtCore.Qt.CheckState.Checked:
        return True
    try:
        return QtCore.Qt.CheckState(value) == QtCore.Qt.CheckState.Checked
    except (TypeError, ValueError):
        pass
    try:
        return int(value) == QtCore.Qt.CheckState.Checked.value
    except (TypeError, ValueError):
        return False


class FrequencyTableModel(QtCore.QAbstractTableModel):
    term_toggled = QtCore.Signal(int, bool)
    base_frequency_edited = QtCore.Signal(int, float)
    headers = ["#", "On", "Kind", "Label", "Frequency", "Period", "Coefficients"]

    def __init__(self, model: FrequencyModel | None = None) -> None:
        super().__init__()
        self.rows = model.rows() if model else []

    def set_frequency_model(self, model: FrequencyModel) -> None:
        self.beginResetModel()
        self.rows = model.rows()
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self.headers)

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = index.column()
        if role == QtCore.Qt.CheckStateRole and col == 1:
            return QtCore.Qt.CheckState.Checked if row["enabled"] else QtCore.Qt.CheckState.Unchecked
        if role == QtCore.Qt.ToolTipRole and col == 2:
            return kind_tooltip(row["kind"], row["coefficients"])
        if role == QtCore.Qt.ToolTipRole and col in (4, 5):
            if self._editable_base_index(row) is not None:
                return "Double-click to edit this base frequency/period."
            return "Derived from base frequencies and coefficients."
        if role not in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return None
        if col == 0:
            return row["index"] + 1
        if col == 1:
            return ""
        if col == 2:
            return kind_code(row["kind"], row["coefficients"])
        if col == 3:
            return row["label"]
        if col == 4:
            if role == QtCore.Qt.EditRole:
                return f"{row['frequency']:.12g}"
            return frequency_text(row["frequency"])
        if col == 5:
            if role == QtCore.Qt.EditRole:
                frequency = row["frequency"]
                return "" if frequency == 0 else f"{1.0 / frequency:.12g}"
            return period_text(row["frequency"])
        if col == 6:
            return " ".join(str(v) for v in row["coefficients"])
        return None

    def flags(self, index: QtCore.QModelIndex):
        flags = super().flags(index)
        if index.isValid():
            row = self.rows[index.row()]
            if index.column() == 1:
                flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
            if index.column() in (4, 5) and self._editable_base_index(row) is not None:
                flags |= QtCore.Qt.ItemFlag.ItemIsEditable | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        return flags

    def setData(self, index: QtCore.QModelIndex, value, role=QtCore.Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        row = self.rows[index.row()]
        if index.column() == 1 and role == QtCore.Qt.CheckStateRole:
            enabled = _is_checked_state(value)
            row["enabled"] = enabled
            self.dataChanged.emit(index, index, [QtCore.Qt.CheckStateRole, QtCore.Qt.DisplayRole])
            self.term_toggled.emit(int(row["index"]), enabled)
            return True
        if index.column() in (4, 5) and role == QtCore.Qt.EditRole:
            base_index = self._editable_base_index(row)
            if base_index is None:
                return False
            number = self._parse_float(value)
            if number is None or number <= 0:
                return False
            frequency = number if index.column() == 4 else 1.0 / number
            self.base_frequency_edited.emit(base_index, float(frequency))
            return True
        return False

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None

    @staticmethod
    def _editable_base_index(row: dict) -> int | None:
        coefficients = row["coefficients"]
        nonzero = [(index, value) for index, value in enumerate(coefficients) if value]
        if len(nonzero) == 1 and nonzero[0][1] == 1:
            return nonzero[0][0]
        return None

    @staticmethod
    def _parse_float(value) -> float | None:
        try:
            return float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            return None


class CandidateTableModel(QtCore.QAbstractTableModel):
    headers = ["#", "Kind", "Label", "Freq", "Period", "Amp", "S/N", "Delta", "Status"]

    def __init__(self, candidates: list[FrequencyCandidate] | None = None) -> None:
        super().__init__()
        self.candidates = candidates or []

    def set_candidates(self, candidates: list[FrequencyCandidate]) -> None:
        self.beginResetModel()
        self.candidates = candidates
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self.candidates)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self.headers)

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        candidate = self.candidates[index.row()]
        col = index.column()
        if role == QtCore.Qt.ToolTipRole and col == 1:
            return kind_tooltip(candidate.kind, candidate.coefficients)
        if role == QtCore.Qt.UserRole:
            if col == 0:
                return index.row() + 1
            if col == 1:
                return kind_code(candidate.kind, candidate.coefficients)
            if col == 2:
                return candidate.label
            if col == 3:
                return candidate.frequency
            if col == 4:
                return math.inf if candidate.frequency == 0 else 1.0 / candidate.frequency
            if col == 5:
                return candidate.amplitude
            if col == 6:
                return -math.inf if candidate.snr is None else candidate.snr
            if col == 7:
                return candidate.delta
            if col == 8:
                return compact_status(candidate.resolved)
            return None
        if role not in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return None
        if col == 0:
            return index.row() + 1
        if col == 1:
            return kind_code(candidate.kind, candidate.coefficients)
        if col == 2:
            return candidate.label
        if col == 3:
            return frequency_text(candidate.frequency)
        if col == 4:
            return period_text(candidate.frequency)
        if col == 5:
            return fixed_text(candidate.amplitude)
        if col == 6:
            return fixed_text(candidate.snr)
        if col == 7:
            return fixed_text(candidate.delta)
        if col == 8:
            return compact_status(candidate.resolved)
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None


class FrequencyReportTableModel(QtCore.QAbstractTableModel):
    headers = [
        "#",
        "On",
        "Kind",
        "Label",
        "Coefficients",
        "Frequency",
        "Freq err",
        "Period",
        "Period err",
        "Amp",
        "Amp err",
        "Phase",
        "Phase err",
        "Status",
    ]

    def __init__(self, report: FrequencyReport | None = None) -> None:
        super().__init__()
        self.report = report
        self.rows = list(report.rows) if report else []

    def set_report(self, report: FrequencyReport | None) -> None:
        self.beginResetModel()
        self.report = report
        self.rows = list(report.rows) if report else []
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self.headers)

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = index.column()
        if role == QtCore.Qt.CheckStateRole and col == 1:
            return QtCore.Qt.CheckState.Checked if row.enabled else QtCore.Qt.CheckState.Unchecked
        if role == COEFFICIENTS_ROLE:
            return row.coefficients
        if role == TERM_INDEX_ROLE:
            return row.index
        if role == QtCore.Qt.ToolTipRole and col == 2:
            return kind_tooltip(row.kind, row.coefficients)
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return self._sort_value(row, col)
        if role not in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return None
        return self._display_value(row, col)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None

    def row_at(self, row: int) -> FrequencyReportRow | None:
        if row < 0 or row >= len(self.rows):
            return None
        return self.rows[row]

    def tsv_text(self) -> str:
        lines = ["\t".join(self.headers)]
        for row in self.rows:
            lines.append("\t".join(self._display_value(row, col) for col in range(len(self.headers))))
        return "\n".join(lines)

    def plain_text(self) -> str:
        rows = [self.headers]
        for row in self.rows:
            rows.append([self._display_value(row, col) for col in range(len(self.headers))])
        widths = [max(len(str(row[col])) for row in rows) for col in range(len(self.headers))]
        return "\n".join("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)) for row in rows)

    def raw_rows(self) -> list[list[str]]:
        result = [self.headers]
        for row in self.rows:
            result.append([self._raw_value(row, col) for col in range(len(self.headers))])
        return result

    def _display_value(self, row: FrequencyReportRow, col: int) -> str:
        if col == 0:
            return str(row.index + 1)
        if col == 1:
            return ""
        if col == 2:
            return kind_code(row.kind, row.coefficients)
        if col == 3:
            return row.label
        if col == 4:
            return " ".join(str(value) for value in row.coefficients)
        if col == 5:
            return frequency_text(row.frequency)
        if col == 6:
            return sig_text(row.frequency_error, digits=6)
        if col == 7:
            return fixed_text(row.period)
        if col == 8:
            return sig_text(row.period_error, digits=6)
        if col == 9:
            return fixed_text(row.amplitude)
        if col == 10:
            return sig_text(row.amplitude_error, digits=6)
        if col == 11:
            return fixed_text(row.phase_cycles)
        if col == 12:
            return sig_text(row.phase_error_cycles, digits=6)
        if col == 13:
            if self.report is not None and self.report.stale and row.enabled:
                return "stale"
            return row.status
        return ""

    def _raw_value(self, row: FrequencyReportRow, col: int) -> str:
        if col == 0:
            return str(row.index + 1)
        if col == 1:
            return "1" if row.enabled else "0"
        if col == 2:
            return kind_code(row.kind, row.coefficients)
        if col == 3:
            return row.label
        if col == 4:
            return " ".join(str(value) for value in row.coefficients)
        value = {
            5: row.frequency,
            6: row.frequency_error,
            7: row.period,
            8: row.period_error,
            9: row.amplitude,
            10: row.amplitude_error,
            11: row.phase_cycles,
            12: row.phase_error_cycles,
        }.get(col)
        if value is not None:
            return f"{float(value):.12g}"
        if col == 13:
            return self._display_value(row, col)
        return ""

    def _sort_value(self, row: FrequencyReportRow, col: int):
        if col == 0:
            return row.index + 1
        if col == 1:
            return 1 if row.enabled else 0
        if col == 2:
            return kind_code(row.kind, row.coefficients)
        if col == 3:
            return row.label
        if col == 4:
            return " ".join(str(value) for value in row.coefficients)
        numeric = {
            5: row.frequency,
            6: row.frequency_error,
            7: row.period,
            8: row.period_error,
            9: row.amplitude,
            10: row.amplitude_error,
            11: row.phase_cycles,
            12: row.phase_error_cycles,
        }.get(col)
        if numeric is None:
            return self._display_value(row, col)
        return -math.inf if numeric is None else float(numeric)
