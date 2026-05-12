import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from lcview.core.combinations import classify_peak
from lcview.core.frequency_model import FrequencyModel
from lcview.ui.models import CandidateTableModel, FrequencyTableModel, kind_code, period_text
from lcview.ui.prewhitening_panel import CANDIDATE_COLUMN_WIDTHS, PrewhiteningPanel


def test_kind_codes_and_period_formatting():
    assert kind_code("independent", (1, 0)) == "IND"
    assert kind_code("combination", (2, 0)) == "H"
    assert kind_code("combination", (1, -1)) == "COM"
    assert period_text(2.0) == "0.500"
    assert period_text(0.0) == ""


def test_frequency_table_period_and_tooltip():
    model = FrequencyModel.empty()
    model.add_independent(2.0)
    table = FrequencyTableModel(model)
    assert table.data(table.index(0, 4), QtCore.Qt.DisplayRole) == "2.000"
    assert table.data(table.index(0, 5), QtCore.Qt.DisplayRole) == "0.500"
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
    assert table.setData(table.index(0, 1), QtCore.Qt.CheckState.Checked.value, QtCore.Qt.CheckStateRole)
    assert toggles == [(0, False), (0, True)]
    assert table.data(table.index(0, 1), QtCore.Qt.CheckStateRole) == QtCore.Qt.CheckState.Checked


def test_frequency_table_edits_base_frequency_or_period_only():
    model = FrequencyModel.empty()
    model.add_independent(2.0)
    model.add_combination((2,))
    table = FrequencyTableModel(model)
    edits = []
    table.base_frequency_edited.connect(lambda index, frequency: edits.append((index, frequency)))

    assert table.flags(table.index(0, 4)) & QtCore.Qt.ItemFlag.ItemIsEditable
    assert table.flags(table.index(0, 5)) & QtCore.Qt.ItemFlag.ItemIsEditable
    assert not table.flags(table.index(1, 4)) & QtCore.Qt.ItemFlag.ItemIsEditable

    assert table.setData(table.index(0, 4), "1,25", QtCore.Qt.EditRole)
    assert table.setData(table.index(0, 5), "4.0", QtCore.Qt.EditRole)
    assert not table.setData(table.index(1, 4), "3.0", QtCore.Qt.EditRole)

    assert edits == [(0, 1.25), (0, 0.25)]


def test_candidate_table_short_kind_and_low_status():
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    candidate = classify_peak(0.2, 1.0, model, baseline=100.0)
    table = CandidateTableModel([candidate])
    assert table.data(table.index(0, 1), QtCore.Qt.DisplayRole) == "IND"
    assert table.data(table.index(0, 4), QtCore.Qt.DisplayRole) == "5.000"
    assert table.data(table.index(0, 5), QtCore.Qt.DisplayRole) == "1.000"
    assert "LOW" in table.data(table.index(0, 8), QtCore.Qt.DisplayRole)


def test_prewhitening_panel_defaults_candidates_to_amplitude_sort():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    model = FrequencyModel.empty()
    candidates = [
        classify_peak(1.0, 0.2, model, baseline=100.0),
        classify_peak(2.0, 1.5, model, baseline=100.0),
        classify_peak(3.0, 0.7, model, baseline=100.0),
    ]
    panel = PrewhiteningPanel()

    panel.set_candidates(candidates)

    table_model = panel.candidate_table.model()
    assert table_model.data(table_model.index(0, 5), QtCore.Qt.DisplayRole) == "1.500"
    assert panel.selected_candidate() == candidates[1]
    assert [panel.candidate_table.columnWidth(i) for i in range(len(CANDIDATE_COLUMN_WIDTHS))] == CANDIDATE_COLUMN_WIDTHS
    panel.close()


def test_prewhitening_panel_preserves_requested_candidate_after_sort():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    model = FrequencyModel.empty()
    candidates = [
        classify_peak(1.0, 0.2, model, baseline=100.0),
        classify_peak(2.0, 1.5, model, baseline=100.0),
        classify_peak(3.0, 0.7, model, baseline=100.0),
    ]
    panel = PrewhiteningPanel()

    selected = panel.set_candidates(candidates, selected_candidate=candidates[2])

    assert selected == candidates[2]
    assert panel.selected_candidate() == candidates[2]
    panel.close()


def test_prewhitening_panel_refine_button_emits_signal():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = PrewhiteningPanel()
    calls = []
    panel.refine_requested.connect(lambda: calls.append("refine"))

    panel.refine_button.click()

    assert calls == ["refine"]
    panel.close()
