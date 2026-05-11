"""Legacy text parsers kept for compatibility tests and import paths."""

from __future__ import annotations

from pathlib import Path
import numpy as np

from lcview.core.frequency_model import FrequencyModel


def read_freq(path: str | Path) -> FrequencyModel:
    return FrequencyModel.from_freq_file(path)


def write_freq(model: FrequencyModel, path: str | Path) -> None:
    model.write_freq_file(path)


def read_resid_max(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    with Path(path).open() as handle:
        for line in handle:
            if not line.strip() or line.lstrip().startswith("%"):
                continue
            values = np.fromstring(line, sep=" ")
            if values.size >= 5:
                rows.append(
                    {
                        "index": int(values[0]),
                        "frequency": float(values[1]),
                        "period": float(values[2]),
                        "amplitude": float(values[3]),
                        "snr": float(values[4]),
                    }
                )
    return rows


def read_freq_poss(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    with Path(path).open() as handle:
        for line in handle:
            values = np.fromstring(line, sep=" ")
            if values.size >= 6:
                rows.append(
                    {
                        "score": float(values[0]),
                        "kind_id": int(values[1]),
                        "coefficient_norm": int(values[2]),
                        "weighted_norm": int(values[3]),
                        "delta": float(values[4]),
                        "coefficients": tuple(int(v) for v in values[5:]),
                    }
                )
    return rows
