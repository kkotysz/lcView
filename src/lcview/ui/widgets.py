"""Small reusable Qt widgets."""

from __future__ import annotations

from PySide6 import QtWidgets

from lcview.display import sig_text


class SignificantDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    def __init__(self, digits: int = 2, parent=None) -> None:
        super().__init__(parent)
        self.digits = digits
        self.setDecimals(12)

    def textFromValue(self, value: float) -> str:
        return sig_text(value, self.digits)

    def valueFromText(self, text: str) -> float:
        normalized = text.strip().replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return self.value()
