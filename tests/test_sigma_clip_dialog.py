import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets

from lcview.core.lightcurve import LightCurve
from lcview.core.sigma_clip import SigmaClipResult
from lcview.ui.sigma_clip_dialog import SigmaClipDialog, SigmaRejectedTableModel


def _sample_result() -> tuple[LightCurve, SigmaClipResult]:
    light_curve = LightCurve(
        time=np.array([0.0, 1.0, 2.0, 3.0]),
        flux=np.array([1.0, 10.0, 1.1, -9.0]),
        error=np.full(4, 0.1),
    )
    keep_mask = np.array([True, False, True, False])
    result = SigmaClipResult(
        cleaned=light_curve.masked(keep_mask),
        rejected=light_curve.masked(~keep_mask),
        keep_mask=keep_mask,
        sigma=3.5,
    )
    return light_curve, result


def test_sigma_rejected_table_allows_unchecking_rejected_points():
    light_curve, result = _sample_result()
    model = SigmaRejectedTableModel(light_curve, ~result.keep_mask)

    assert model.rowCount() == 2
    assert model.data(model.index(0, 0), QtCore.Qt.CheckStateRole) == QtCore.Qt.CheckState.Checked

    assert model.setData(model.index(0, 0), QtCore.Qt.CheckState.Unchecked.value, QtCore.Qt.CheckStateRole)

    assert model.selected_reject_mask().tolist() == [False, False, False, True]


def test_sigma_clip_dialog_returns_cleaned_curve_from_selected_rejections():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    light_curve, result = _sample_result()
    dialog = SigmaClipDialog(light_curve, result, y_inverted=True)

    dialog.table_model.setData(dialog.table_model.index(0, 0), QtCore.Qt.CheckState.Unchecked.value, QtCore.Qt.CheckStateRole)
    cleaned = dialog.cleaned_light_curve()

    assert dialog.plot._y_inverted
    assert cleaned.time.tolist() == [0.0, 1.0, 2.0]
    assert dialog.selected_reject_mask().tolist() == [False, False, False, True]
    dialog.close()


def test_sigma_clip_dialog_box_selection_can_reject_and_keep_points():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    light_curve, result = _sample_result()
    dialog = SigmaClipDialog(light_curve, result)

    dialog.table_model.set_all(False)
    changed = dialog.apply_plot_selection(0.5, 1.5, 9.0, 11.0, rejected=True)

    assert changed == 1
    assert dialog.selected_reject_mask().tolist() == [False, True, False, False]

    changed = dialog.apply_plot_selection(0.5, 1.5, 9.0, 11.0, rejected=False)

    assert changed == 1
    assert dialog.selected_reject_mask().tolist() == [False, False, False, False]
    dialog.close()


def test_sigma_clip_dialog_box_selection_can_add_non_proposed_points():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    light_curve, result = _sample_result()
    dialog = SigmaClipDialog(light_curve, result)

    changed = dialog.apply_plot_selection(1.5, 2.5, 0.5, 1.5, rejected=True)

    assert changed == 1
    assert dialog.selected_reject_mask().tolist() == [False, True, True, True]
    assert dialog.table_model.rowCount() == 3
    dialog.close()


def test_sigma_clip_plot_selector_maps_viewport_rect_to_data_bounds():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    light_curve, result = _sample_result()
    dialog = SigmaClipDialog(light_curve, result)
    if dialog.plot._plot is None:
        dialog.close()
        pytest.skip("pyqtgraph is not installed")

    rect = QtCore.QRect(QtCore.QPoint(5, 5), QtCore.QPoint(60, 60))
    bounds = dialog.plot_selector._rect_to_data_bounds(rect)

    assert len(bounds) == 4
    assert all(np.isfinite(value) for value in bounds)
    dialog.close()
