"""Prewhitening control panel."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from lcview.core.combinations import FrequencyCandidate
from lcview.core.frequency_model import FrequencyModel
from .models import CandidateTableModel, FrequencyTableModel


CANDIDATE_AMPLITUDE_COLUMN = 5
CANDIDATE_COLUMN_WIDTHS = [24, 34, 64, 48, 48, 48, 42, 48, 72]


class PrewhiteningPanel(QtWidgets.QWidget):
    frequency_selected = QtCore.Signal(object)
    candidate_selected = QtCore.Signal(object)
    add_independent_requested = QtCore.Signal(float)
    add_independents_requested = QtCore.Signal(object)
    add_candidate_requested = QtCore.Signal(object)
    add_candidates_requested = QtCore.Signal(object)
    base_frequency_edited = QtCore.Signal(int, float)
    remove_term_requested = QtCore.Signal(int)
    clear_frequencies_requested = QtCore.Signal()
    toggle_term_requested = QtCore.Signal(int, bool)
    fit_requested = QtCore.Signal()
    refine_requested = QtCore.Signal()
    undo_requested = QtCore.Signal()
    redo_requested = QtCore.Signal()
    export_requested = QtCore.Signal()
    detrend_requested = QtCore.Signal()
    sigma_clip_requested = QtCore.Signal()
    tdfd_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.frequency_model = FrequencyTableModel()
        self.candidate_model = CandidateTableModel()
        self.candidate_proxy = QtCore.QSortFilterProxyModel(self)
        self.candidate_proxy.setSourceModel(self.candidate_model)
        self.candidate_proxy.setSortRole(QtCore.Qt.ItemDataRole.UserRole)
        self.candidate_proxy.setDynamicSortFilter(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self.frequency_table = QtWidgets.QTableView()
        self.frequency_table.setModel(self.frequency_model)
        self.frequency_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.frequency_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.frequency_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
            | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.frequency_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QtWidgets.QLabel("Accepted frequencies"))
        layout.addWidget(self.frequency_table, 2)

        accepted_buttons = QtWidgets.QHBoxLayout()
        self.edit_button = QtWidgets.QPushButton("Edit")
        self.remove_button = QtWidgets.QPushButton("Remove")
        self.clear_all_button = QtWidgets.QPushButton("Clear all")
        self.undo_button = QtWidgets.QPushButton("Undo")
        self.redo_button = QtWidgets.QPushButton("Redo")
        self.edit_button.setToolTip("Edit the selected base frequency. You can also double-click Frequency or Period.")
        for button in [self.edit_button, self.remove_button, self.clear_all_button, self.undo_button, self.redo_button]:
            accepted_buttons.addWidget(button)
        layout.addLayout(accepted_buttons)

        self.candidate_table = QtWidgets.QTableView()
        self.candidate_table.setModel(self.candidate_proxy)
        self.candidate_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.candidate_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.candidate_table.setSortingEnabled(True)
        self.candidate_table.sortByColumn(CANDIDATE_AMPLITUDE_COLUMN, QtCore.Qt.SortOrder.DescendingOrder)
        self._configure_candidate_table()

        candidate_buttons = QtWidgets.QGridLayout()
        candidate_buttons.setContentsMargins(0, 0, 0, 0)
        candidate_buttons.setHorizontalSpacing(5)
        candidate_buttons.setVerticalSpacing(4)
        self.add_independent_button = QtWidgets.QPushButton("Add independent")
        self.add_candidate_button = QtWidgets.QPushButton("Add selected")
        self.fit_button = QtWidgets.QPushButton("Fit model")
        self.refine_button = QtWidgets.QPushButton("Refine frequencies")
        self.add_independent_button.setToolTip("Add selected peak candidate(s) as new independent frequencies.")
        self.add_candidate_button.setToolTip("Add selected candidate(s), preserving combination/harmonic classification when available.")
        self.fit_button.setToolTip("Fast linear fit at the accepted frequencies. Use Calculate DFT to refresh peaks.")
        self.refine_button.setToolTip("Slow nonlinear refinement of accepted frequencies.")
        candidate_buttons.addWidget(self.add_independent_button, 0, 0)
        candidate_buttons.addWidget(self.add_candidate_button, 0, 1)
        candidate_buttons.addWidget(self.fit_button, 1, 0)
        candidate_buttons.addWidget(self.refine_button, 1, 1)
        layout.addWidget(QtWidgets.QLabel("Current peak candidates"))
        layout.addLayout(candidate_buttons)
        layout.addWidget(self.candidate_table, 3)

        tool_buttons = QtWidgets.QHBoxLayout()
        self.detrend_button = QtWidgets.QPushButton("Detrend")
        self.sigma_button = QtWidgets.QPushButton("Sigma clip")
        self.tdfd_button = QtWidgets.QPushButton("TDFD")
        self.export_button = QtWidgets.QPushButton("Export")
        for button in [self.detrend_button, self.sigma_button, self.tdfd_button, self.export_button]:
            tool_buttons.addWidget(button)
        layout.addLayout(tool_buttons)

        self.edit_button.clicked.connect(self._edit_selected)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_all_button.clicked.connect(self.clear_frequencies_requested)
        self.frequency_model.term_toggled.connect(self.toggle_term_requested)
        self.frequency_model.base_frequency_edited.connect(lambda index, frequency: self.base_frequency_edited.emit(index, frequency))
        self.frequency_table.clicked.connect(self._frequency_clicked)
        self.frequency_table.selectionModel().currentRowChanged.connect(self._frequency_current_changed)
        self.candidate_table.clicked.connect(self._candidate_clicked)
        self.add_independent_button.clicked.connect(self._add_independent_selected)
        self.add_candidate_button.clicked.connect(self._add_candidate_selected)
        self.candidate_table.doubleClicked.connect(lambda _: self._add_candidate_selected())
        self.fit_button.clicked.connect(self.fit_requested)
        self.refine_button.clicked.connect(self.refine_requested)
        self.undo_button.clicked.connect(self.undo_requested)
        self.redo_button.clicked.connect(self.redo_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.detrend_button.clicked.connect(self.detrend_requested)
        self.sigma_button.clicked.connect(self.sigma_clip_requested)
        self.tdfd_button.clicked.connect(self.tdfd_requested)

    def set_frequency_model(self, model: FrequencyModel) -> None:
        self.frequency_model.set_frequency_model(model)
        self.frequency_table.resizeColumnsToContents()

    def select_term(self, *, term_index: int | None = None, coefficients: tuple[int, ...] | None = None) -> bool:
        target_row = None
        coefficients = None if coefficients is None else tuple(coefficients)
        for row_number, row in enumerate(self.frequency_model.rows):
            if term_index is not None and int(row["index"]) == int(term_index):
                target_row = row_number
                break
            if coefficients is not None and tuple(row["coefficients"]) == coefficients:
                target_row = row_number
                break

        selection_model = self.frequency_table.selectionModel()
        if selection_model is None:
            return False
        blocker = QtCore.QSignalBlocker(selection_model)
        try:
            if target_row is None:
                selection_model.clearSelection()
                self.frequency_table.setCurrentIndex(QtCore.QModelIndex())
                return False
            index = self.frequency_model.index(target_row, 0)
            self.frequency_table.selectRow(target_row)
            self.frequency_table.setCurrentIndex(index)
            self.frequency_table.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
            return True
        finally:
            del blocker

    def set_candidates(
        self,
        candidates: list[FrequencyCandidate],
        selected_candidate: FrequencyCandidate | None = None,
    ) -> FrequencyCandidate | None:
        self.candidate_model.set_candidates(candidates)
        self.candidate_proxy.sort(CANDIDATE_AMPLITUDE_COLUMN, QtCore.Qt.SortOrder.DescendingOrder)
        self._fit_candidate_columns()
        if not candidates:
            self.candidate_table.clearSelection()
            return None

        proxy_index = self._candidate_proxy_index(selected_candidate) if selected_candidate is not None else QtCore.QModelIndex()
        row = proxy_index.row() if proxy_index.isValid() else 0
        self.candidate_table.selectRow(row)
        selected = self.selected_candidate()
        if selected is not None:
            self.candidate_selected.emit(selected)
        return selected

    def selected_candidate(self) -> FrequencyCandidate | None:
        candidates = self.selected_candidates()
        return candidates[0] if candidates else None

    def selected_candidates(self) -> list[FrequencyCandidate]:
        rows = self.candidate_table.selectionModel().selectedRows()
        if not rows:
            if self.candidate_proxy.rowCount() == 0:
                return []
            rows = [self.candidate_proxy.index(0, 0)]
        candidates: list[FrequencyCandidate] = []
        seen: set[int] = set()
        for row in sorted(rows, key=lambda item: item.row()):
            source_index = self.candidate_proxy.mapToSource(row)
            if not source_index.isValid() or source_index.row() in seen:
                continue
            seen.add(source_index.row())
            candidates.append(self.candidate_model.candidates[source_index.row()])
        return candidates

    def selected_term_index(self) -> int | None:
        rows = self.frequency_table.selectionModel().selectedRows()
        if not rows:
            return None
        return int(self.frequency_model.rows[rows[0].row()]["index"])

    def _add_independent_selected(self) -> None:
        candidates = self.selected_candidates()
        if len(candidates) > 1:
            self.add_independents_requested.emit(candidates)
            return
        candidate = candidates[0] if candidates else None
        if candidate is not None:
            self.add_independent_requested.emit(candidate.frequency)

    def _add_candidate_selected(self) -> None:
        candidates = self.selected_candidates()
        if len(candidates) > 1:
            self.add_candidates_requested.emit(candidates)
            return
        candidate = candidates[0] if candidates else None
        if candidate is None:
            return
        if candidate.kind == "independent" or not any(candidate.coefficients):
            self.add_independent_requested.emit(candidate.frequency)
        else:
            self.add_candidate_requested.emit(candidate)

    def _remove_selected(self) -> None:
        index = self.selected_term_index()
        if index is not None:
            self.remove_term_requested.emit(index)

    def _edit_selected(self) -> None:
        rows = self.frequency_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        index = self.frequency_model.index(row, 4)
        if self.frequency_model.flags(index) & QtCore.Qt.ItemFlag.ItemIsEditable:
            self.frequency_table.edit(index)

    def _frequency_clicked(self, item: QtCore.QModelIndex) -> None:
        self._emit_frequency_selected(item)

    def _frequency_current_changed(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex) -> None:
        self._emit_frequency_selected(current)

    def _emit_frequency_selected(self, item: QtCore.QModelIndex) -> None:
        if item.isValid() and 0 <= item.row() < len(self.frequency_model.rows):
            self.frequency_selected.emit(self.frequency_model.rows[item.row()])

    def _candidate_clicked(self, item: QtCore.QModelIndex) -> None:
        if item.isValid():
            source_index = self.candidate_proxy.mapToSource(item)
            if source_index.isValid():
                self.candidate_selected.emit(self.candidate_model.candidates[source_index.row()])

    def _candidate_proxy_index(self, candidate: FrequencyCandidate) -> QtCore.QModelIndex:
        for row, existing in enumerate(self.candidate_model.candidates):
            if existing is candidate:
                return self.candidate_proxy.mapFromSource(self.candidate_model.index(row, 0))
        for row, existing in enumerate(self.candidate_model.candidates):
            if existing == candidate:
                return self.candidate_proxy.mapFromSource(self.candidate_model.index(row, 0))
        return QtCore.QModelIndex()

    def _configure_candidate_table(self) -> None:
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        if font.pointSize() > 0:
            font.setPointSize(max(8, font.pointSize() - 2))
        else:
            font.setPixelSize(11)
        self.candidate_table.setFont(font)
        self.candidate_table.horizontalHeader().setFont(font)
        self.candidate_table.verticalHeader().hide()
        self.candidate_table.verticalHeader().setDefaultSectionSize(QtGui.QFontMetrics(font).height() + 6)
        self.candidate_table.setWordWrap(False)
        self.candidate_table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.candidate_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.candidate_table.horizontalHeader().setStretchLastSection(False)
        self.candidate_table.horizontalHeader().setMinimumSectionSize(18)
        self._fit_candidate_columns()

    def _fit_candidate_columns(self) -> None:
        self.candidate_table.resizeColumnsToContents()
        for column, width in enumerate(CANDIDATE_COLUMN_WIDTHS):
            self.candidate_table.setColumnWidth(column, width)
