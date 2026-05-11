"""Prewhitening control panel."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from lcview.core.combinations import FrequencyCandidate
from lcview.core.frequency_model import FrequencyModel
from .models import CandidateTableModel, FrequencyTableModel


class PrewhiteningPanel(QtWidgets.QWidget):
    frequency_selected = QtCore.Signal(object)
    candidate_selected = QtCore.Signal(object)
    add_independent_requested = QtCore.Signal(float)
    add_candidate_requested = QtCore.Signal(object)
    remove_term_requested = QtCore.Signal(int)
    clear_frequencies_requested = QtCore.Signal()
    toggle_term_requested = QtCore.Signal(int, bool)
    fit_requested = QtCore.Signal()
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

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.frequency_table = QtWidgets.QTableView()
        self.frequency_table.setModel(self.frequency_model)
        self.frequency_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.frequency_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.frequency_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QtWidgets.QLabel("Accepted frequencies"))
        layout.addWidget(self.frequency_table, 2)

        accepted_buttons = QtWidgets.QHBoxLayout()
        self.remove_button = QtWidgets.QPushButton("Remove")
        self.clear_all_button = QtWidgets.QPushButton("Clear all")
        self.undo_button = QtWidgets.QPushButton("Undo")
        self.redo_button = QtWidgets.QPushButton("Redo")
        for button in [self.remove_button, self.clear_all_button, self.undo_button, self.redo_button]:
            accepted_buttons.addWidget(button)
        layout.addLayout(accepted_buttons)

        self.candidate_table = QtWidgets.QTableView()
        self.candidate_table.setModel(self.candidate_model)
        self.candidate_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.candidate_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.candidate_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QtWidgets.QLabel("Current peak candidates"))
        layout.addWidget(self.candidate_table, 3)

        candidate_buttons = QtWidgets.QHBoxLayout()
        self.add_independent_button = QtWidgets.QPushButton("Add independent")
        self.add_candidate_button = QtWidgets.QPushButton("Add combination")
        self.fit_button = QtWidgets.QPushButton("Fit / refresh")
        for button in [self.add_independent_button, self.add_candidate_button, self.fit_button]:
            candidate_buttons.addWidget(button)
        layout.addLayout(candidate_buttons)

        tool_buttons = QtWidgets.QHBoxLayout()
        self.detrend_button = QtWidgets.QPushButton("Detrend")
        self.sigma_button = QtWidgets.QPushButton("Sigma clip")
        self.tdfd_button = QtWidgets.QPushButton("TDFD")
        self.export_button = QtWidgets.QPushButton("Export")
        for button in [self.detrend_button, self.sigma_button, self.tdfd_button, self.export_button]:
            tool_buttons.addWidget(button)
        layout.addLayout(tool_buttons)

        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_all_button.clicked.connect(self.clear_frequencies_requested)
        self.frequency_model.term_toggled.connect(self.toggle_term_requested)
        self.frequency_table.clicked.connect(self._frequency_clicked)
        self.candidate_table.clicked.connect(self._candidate_clicked)
        self.add_independent_button.clicked.connect(self._add_independent_selected)
        self.add_candidate_button.clicked.connect(self._add_candidate_selected)
        self.candidate_table.doubleClicked.connect(lambda _: self._add_candidate_selected())
        self.fit_button.clicked.connect(self.fit_requested)
        self.undo_button.clicked.connect(self.undo_requested)
        self.redo_button.clicked.connect(self.redo_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.detrend_button.clicked.connect(self.detrend_requested)
        self.sigma_button.clicked.connect(self.sigma_clip_requested)
        self.tdfd_button.clicked.connect(self.tdfd_requested)

    def set_frequency_model(self, model: FrequencyModel) -> None:
        self.frequency_model.set_frequency_model(model)
        self.frequency_table.resizeColumnsToContents()

    def set_candidates(self, candidates: list[FrequencyCandidate]) -> None:
        self.candidate_model.set_candidates(candidates)
        self.candidate_table.resizeColumnsToContents()
        if candidates:
            self.candidate_table.selectRow(0)
            self.candidate_selected.emit(candidates[0])

    def selected_candidate(self) -> FrequencyCandidate | None:
        rows = self.candidate_table.selectionModel().selectedRows()
        if not rows:
            return self.candidate_model.candidates[0] if self.candidate_model.candidates else None
        return self.candidate_model.candidates[rows[0].row()]

    def selected_term_index(self) -> int | None:
        rows = self.frequency_table.selectionModel().selectedRows()
        if not rows:
            return None
        return int(self.frequency_model.rows[rows[0].row()]["index"])

    def _add_independent_selected(self) -> None:
        candidate = self.selected_candidate()
        if candidate is not None:
            self.add_independent_requested.emit(candidate.frequency)

    def _add_candidate_selected(self) -> None:
        candidate = self.selected_candidate()
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

    def _frequency_clicked(self, item: QtCore.QModelIndex) -> None:
        if item.isValid():
            self.frequency_selected.emit(self.frequency_model.rows[item.row()])

    def _candidate_clicked(self, item: QtCore.QModelIndex) -> None:
        if item.isValid():
            self.candidate_selected.emit(self.candidate_model.candidates[item.row()])
