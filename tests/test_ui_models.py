import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore

from lcview.core.combinations import classify_peak
from lcview.core.frequency_model import FrequencyModel
from lcview.ui.models import CandidateTableModel, FrequencyTableModel, kind_code, period_text


def test_kind_codes_and_period_formatting():
    assert kind_code("independent", (1, 0)) == "IND"
    assert kind_code("combination", (2, 0)) == "H"
    assert kind_code("combination", (1, -1)) == "COM"
    assert period_text(2.0) == "0.5"
    assert period_text(0.0) == ""


def test_frequency_table_period_and_tooltip():
    model = FrequencyModel.empty()
    model.add_independent(2.0)
    table = FrequencyTableModel(model)
    assert table.data(table.index(0, 4), QtCore.Qt.DisplayRole) == "2"
    assert table.data(table.index(0, 5), QtCore.Qt.DisplayRole) == "0.5"
    assert table.data(table.index(0, 2), QtCore.Qt.DisplayRole) == "IND"
    assert "independent" in table.data(table.index(0, 2), QtCore.Qt.ToolTipRole)
    assert table.data(table.index(0, 1), QtCore.Qt.CheckStateRole) == QtCore.Qt.CheckState.Checked


def test_frequency_table_checkbox_emits_toggle():
    model = FrequencyModel.empty()
    model.add_independent(2.0)
    table = FrequencyTableModel(model)
    toggles = []
    table.term_toggled.connect(lambda index, enabled: toggles.append((index, enabled)))
    assert table.setData(table.index(0, 1), QtCore.Qt.CheckState.Unchecked, QtCore.Qt.CheckStateRole)
    assert toggles == [(0, False)]


def test_candidate_table_short_kind_and_low_status():
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    candidate = classify_peak(0.2, 1.0, model, baseline=100.0)
    table = CandidateTableModel([candidate])
    assert table.data(table.index(0, 1), QtCore.Qt.DisplayRole) == "IND"
    assert table.data(table.index(0, 4), QtCore.Qt.DisplayRole) == "5"
    assert "LOW" in table.data(table.index(0, 8), QtCore.Qt.DisplayRole)
