import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6 import QtWidgets

from lcview.core.lightcurve import read_light_curve_table
from lcview.ui.column_selection_dialog import ColumnSelectionDialog, suggest_light_curve_columns


def test_column_selection_suggests_header_columns(tmp_path: Path):
    path = tmp_path / "lc.csv"
    path.write_text("hjd,airmass,mag,mag_err\n1.0,1.2,10.1,0.01\n")
    table = read_light_curve_table(path)

    assert suggest_light_curve_columns(table) == (0, 2, 3)


def test_column_selection_dialog_returns_selected_columns(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    path = tmp_path / "lc.csv"
    path.write_text("hjd,airmass,mag,mag_err\n1.0,1.2,10.1,0.01\n")
    table = read_light_curve_table(path)
    dialog = ColumnSelectionDialog(table)

    dialog.time_combo.setCurrentIndex(dialog.time_combo.findData(0))
    dialog.flux_combo.setCurrentIndex(dialog.flux_combo.findData(2))
    dialog.error_combo.setCurrentIndex(dialog.error_combo.findData(3))

    assert dialog.selected_columns() == (0, 2, 3)
    dialog.close()
