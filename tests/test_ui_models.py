import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from lcview.core.combinations import FrequencyCandidate, classify_peak
from lcview.core.frequency_model import FrequencyModel
from lcview.core.results import FrequencyReport, FrequencyReportRow
from lcview.ui.models import CandidateTableModel, FrequencyReportTableModel, FrequencyTableModel, kind_code, period_text
from lcview.ui.prewhitening_panel import CANDIDATE_COLUMN_WIDTHS, CANDIDATE_LABEL_COLUMN, CombinationBasesDialog, PrewhiteningPanel


def test_kind_codes_and_period_formatting():
    assert kind_code("independent", (1, 0)) == "I"
    assert kind_code("combination", (2, 0)) == "H"
    assert kind_code("combination", (1, -1)) == "C"
    assert period_text(2.0) == "0.500"
    assert period_text(0.0) == ""


def test_frequency_table_period_and_tooltip():
    model = FrequencyModel.empty()
    model.add_independent(2.0)
    table = FrequencyTableModel(model)
    assert table.data(table.index(0, 4), QtCore.Qt.DisplayRole) == "2.000"
    assert table.data(table.index(0, 5), QtCore.Qt.DisplayRole) == "0.500"
    assert table.data(table.index(0, 2), QtCore.Qt.DisplayRole) == "I"
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
    assert table.data(table.index(0, 1), QtCore.Qt.DisplayRole) == "I"
    assert table.data(table.index(0, 4), QtCore.Qt.DisplayRole) == "5.000"
    assert table.data(table.index(0, 5), QtCore.Qt.DisplayRole) == "1.000"
    assert "LOW" in table.data(table.index(0, 8), QtCore.Qt.DisplayRole)


def test_combination_bases_dialog_selects_independent_base_indexes():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.add_independent(2.0)
    model.add_combination((1, 1))
    dialog = CombinationBasesDialog(model.rows(), selected_indexes=(0,))

    assert dialog.selected_indexes() == (0,)

    dialog.deselect_all_button.click()
    assert dialog.selected_indexes() == ()

    dialog.select_all_button.click()
    assert dialog.selected_indexes() == (0, 1)
    dialog.close()


def test_prewhitening_panel_fits_long_candidate_label_column():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    candidate = FrequencyCandidate(
        frequency=1.0,
        amplitude=1.0,
        snr=6.0,
        kind="combination",
        label="f1 + f2 + f3 + f4 + f5 + f6 + f7",
        coefficients=(1, 1, 1, 1, 1, 1, 1),
        delta=0.0,
        score=0.0,
        resolved="resolved",
        rayleigh=0.001,
    )
    panel = PrewhiteningPanel()

    panel.set_candidates([candidate])

    assert panel.candidate_table.columnWidth(CANDIDATE_LABEL_COLUMN) > CANDIDATE_COLUMN_WIDTHS[CANDIDATE_LABEL_COLUMN]
    panel.close()


def test_frequency_report_table_formats_values_and_stale_status():
    report = FrequencyReport(
        rows=(
            FrequencyReportRow(
                index=0,
                enabled=True,
                kind="independent",
                label="f1",
                coefficients=(1,),
                frequency=2.0,
                frequency_error=0.01,
                period=0.5,
                period_error=0.0025,
                amplitude=1.2345,
                amplitude_error=0.02,
                phase_cycles=0.125,
                phase_error_cycles=0.003,
                status="fit",
            ),
        ),
        nobs=10,
        n_terms=1,
        n_active_terms=1,
        sdev=0.1,
        fit_source="test",
        stale=True,
    )
    table = FrequencyReportTableModel(report)

    assert table.data(table.index(0, 2), QtCore.Qt.DisplayRole) == "I"
    assert table.data(table.index(0, 5), QtCore.Qt.DisplayRole) == "2.000"
    assert table.data(table.index(0, 9), QtCore.Qt.DisplayRole) == "1.234"
    assert table.data(table.index(0, 13), QtCore.Qt.DisplayRole) == "stale"
    assert "Frequency" in table.tsv_text()
    assert "Freq err" in table.plain_text()


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
    widths = [panel.candidate_table.columnWidth(i) for i in range(len(CANDIDATE_COLUMN_WIDTHS))]
    for column, width in enumerate(CANDIDATE_COLUMN_WIDTHS):
        if column == CANDIDATE_LABEL_COLUMN:
            assert widths[column] >= width
        else:
            assert widths[column] == width
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


def test_prewhitening_panel_emits_multiple_selected_candidates():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    model = FrequencyModel.empty()
    candidates = [
        classify_peak(1.0, 0.2, model, baseline=100.0),
        classify_peak(2.0, 1.5, model, baseline=100.0),
        classify_peak(3.0, 0.7, model, baseline=100.0),
    ]
    panel = PrewhiteningPanel()
    panel.set_candidates(candidates)
    selection = panel.candidate_table.selectionModel()
    selection.clearSelection()
    for row in (0, 1):
        index = panel.candidate_table.model().index(row, 0)
        selection.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
    calls = []
    panel.add_candidates_requested.connect(lambda selected: calls.append(selected))

    panel.add_candidate_button.click()

    assert panel.selected_candidates() == [candidates[1], candidates[2]]
    assert calls == [[candidates[1], candidates[2]]]
    panel.close()


def test_prewhitening_panel_refine_button_emits_signal():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = PrewhiteningPanel()
    calls = []
    panel.refine_requested.connect(lambda: calls.append("refine"))

    panel.refine_button.click()

    assert calls == ["refine"]
    panel.close()
