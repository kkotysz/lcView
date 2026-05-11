"""Qt table models for frequency state and candidates."""

from __future__ import annotations

from PySide6 import QtCore

from lcview.core.combinations import FrequencyCandidate
from lcview.core.frequency_model import FrequencyModel
from lcview.display import frequency_text, period_text_from_frequency, sig_text


KIND_LABELS = {
    "independent": ("IND", "independent frequency"),
    "harmonic": ("H", "harmonic"),
    "combination": ("COM", "combination frequency"),
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


class FrequencyTableModel(QtCore.QAbstractTableModel):
    term_toggled = QtCore.Signal(int, bool)
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
            return frequency_text(row["frequency"])
        if col == 5:
            return period_text(row["frequency"])
        if col == 6:
            return " ".join(str(v) for v in row["coefficients"])
        return None

    def flags(self, index: QtCore.QModelIndex):
        flags = super().flags(index)
        if index.isValid() and index.column() == 1:
            flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        return flags

    def setData(self, index: QtCore.QModelIndex, value, role=QtCore.Qt.EditRole) -> bool:
        if not index.isValid() or index.column() != 1 or role != QtCore.Qt.CheckStateRole:
            return False
        enabled = value == QtCore.Qt.CheckState.Checked
        row = self.rows[index.row()]
        row["enabled"] = enabled
        self.dataChanged.emit(index, index, [QtCore.Qt.CheckStateRole, QtCore.Qt.DisplayRole])
        self.term_toggled.emit(int(row["index"]), enabled)
        return True

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None


class CandidateTableModel(QtCore.QAbstractTableModel):
    headers = ["#", "Kind", "Label", "Frequency", "Period", "Amplitude", "S/N", "Delta", "Status"]

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
            return f"{candidate.amplitude:.5f}"
        if col == 6:
            return "" if candidate.snr is None else f"{candidate.snr:.2f}"
        if col == 7:
            return sig_text(candidate.delta)
        if col == 8:
            return compact_status(candidate.resolved)
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None
