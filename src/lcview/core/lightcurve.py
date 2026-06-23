"""Light-curve loading and simple transformations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
import csv
import re
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LightCurve:
    time: np.ndarray
    flux: np.ndarray
    error: np.ndarray
    path: Path | None = None

    def __post_init__(self) -> None:
        lengths = {len(self.time), len(self.flux), len(self.error)}
        if len(lengths) != 1:
            raise ValueError("time, flux and error arrays must have the same length")

    @property
    def baseline(self) -> float:
        if len(self.time) == 0:
            raise ValueError("empty light curve has no baseline")
        return float(np.nanmax(self.time) - np.nanmin(self.time))

    @property
    def median_time(self) -> float:
        return float(np.nanmedian(self.time))

    @property
    def median_cadence(self) -> float | None:
        if len(self.time) < 2:
            return None
        diffs = np.diff(np.sort(self.time))
        finite = diffs[np.isfinite(diffs) & (diffs > 0)]
        if finite.size == 0:
            return None
        return float(np.median(finite))

    @property
    def nyquist_frequency(self) -> float | None:
        cadence = self.median_cadence
        if cadence is None or cadence <= 0 or not np.isfinite(cadence):
            return None
        return float(0.5 / cadence)

    def sorted(self) -> "LightCurve":
        order = np.argsort(self.time)
        return LightCurve(self.time[order], self.flux[order], self.error[order], self.path)

    def centered_time(self) -> "LightCurve":
        return LightCurve(self.time - self.median_time, self.flux.copy(), self.error.copy(), self.path).sorted()

    def with_flux(self, flux: Iterable[float]) -> "LightCurve":
        return LightCurve(self.time.copy(), np.asarray(list(flux), dtype=float), self.error.copy(), self.path).sorted()

    def masked(self, mask: np.ndarray) -> "LightCurve":
        return LightCurve(self.time[mask], self.flux[mask], self.error[mask], self.path).sorted()

    def to_array(self) -> np.ndarray:
        return np.column_stack([self.time, self.flux, self.error])

    def save(self, path: Path) -> None:
        np.savetxt(path, self.to_array(), fmt="%16.8f %16.8f %12.6f")


@dataclass(frozen=True)
class LightCurveTable:
    path: Path
    data: pd.DataFrame
    column_names: list[str]
    has_header: bool
    delimiter_name: str

    @property
    def column_count(self) -> int:
        return len(self.column_names)

    def numeric_column_indexes(self) -> list[int]:
        indexes = []
        for index in range(self.column_count):
            values = pd.to_numeric(self.data.iloc[:, index], errors="coerce")
            if values.notna().any():
                indexes.append(index)
        return indexes


COMMENT_PREFIXES = ("#", "%")


def _is_number(text: str) -> bool:
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def _clean_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith(COMMENT_PREFIXES):
        return stripped[1:].strip()
    return stripped


def _delimiter_for_line(line: str) -> tuple[str | None, str]:
    if "," in line:
        return ",", "comma"
    if "\t" in line:
        return "\t", "tab"
    if ";" in line:
        return ";", "semicolon"
    return None, "whitespace"


def _split_line(line: str, delimiter: str | None) -> list[str]:
    line = _clean_line(line)
    if not line:
        return []
    if delimiter is None:
        return [part for part in re.split(r"\s+", line) if part]
    return [part.strip() for part in next(csv.reader([line], delimiter=delimiter))]


def _find_table_start(lines: list[str]) -> tuple[int, list[str] | None, str | None, str]:
    pending_header: tuple[int, list[str], str | None, str] | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        delimiter, delimiter_name = _delimiter_for_line(_clean_line(stripped))
        tokens = _split_line(stripped, delimiter)
        if not tokens:
            continue
        all_numeric = all(_is_number(token) for token in tokens)
        if stripped.startswith(COMMENT_PREFIXES):
            if not all_numeric and len(tokens) >= 2:
                pending_header = (index, tokens, delimiter, delimiter_name)
            continue
        if all_numeric:
            if pending_header is not None:
                _, header_tokens, _, _ = pending_header
                return index, header_tokens, delimiter, delimiter_name
            return index, None, delimiter, delimiter_name
        return index + 1, tokens, delimiter, delimiter_name
    raise ValueError("No table data found")


def read_light_curve_table(path: str | Path) -> LightCurveTable:
    path = Path(path)
    lines = path.read_text().splitlines()
    data_start, header_tokens, delimiter, delimiter_name = _find_table_start(lines)
    rows = []
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(COMMENT_PREFIXES):
            continue
        tokens = _split_line(stripped, delimiter)
        if tokens:
            rows.append(tokens)
    if not rows:
        raise ValueError(f"No numeric light-curve rows found in {path}")
    width = max(len(row) for row in rows)
    padded_rows = [row + [""] * (width - len(row)) for row in rows]
    if header_tokens is None:
        column_names = [f"col{index + 1}" for index in range(width)]
    else:
        column_names = [token or f"col{index + 1}" for index, token in enumerate(header_tokens[:width])]
        if len(column_names) < width:
            column_names.extend(f"col{index + 1}" for index in range(len(column_names), width))
    return LightCurveTable(
        path=path,
        data=pd.DataFrame(padded_rows, columns=column_names),
        column_names=column_names,
        has_header=header_tokens is not None,
        delimiter_name=delimiter_name,
    )


def infer_light_curve_columns(table: LightCurveTable) -> tuple[int, int, int]:
    numeric_indexes = table.numeric_column_indexes()
    if len(numeric_indexes) < 3:
        raise ValueError(f"Need at least three numeric columns in {table.path}")
    return tuple(numeric_indexes[:3])


def light_curve_from_table(table: LightCurveTable, columns: Sequence[int]) -> LightCurve:
    if len(columns) != 3:
        raise ValueError("expected exactly three columns: time, flux, error")
    if len(set(int(column) for column in columns)) != 3:
        raise ValueError("time, flux and error columns must be distinct")
    if any(int(column) < 0 or int(column) >= table.column_count for column in columns):
        raise ValueError("selected light-curve column is out of range")
    selected = table.data.iloc[:, [int(column) for column in columns]].apply(pd.to_numeric, errors="coerce")
    df = selected.dropna()
    if df.empty:
        raise ValueError(f"No numeric light-curve rows found in selected columns of {table.path}")
    return LightCurve(
        time=df.iloc[:, 0].to_numpy(dtype=float),
        flux=df.iloc[:, 1].to_numpy(dtype=float),
        error=df.iloc[:, 2].to_numpy(dtype=float),
        path=table.path,
    ).sorted()


def read_light_curve(path: str | Path, columns: Sequence[int] | None = None) -> LightCurve:
    table = read_light_curve_table(path)
    return light_curve_from_table(table, columns or infer_light_curve_columns(table))


def from_array(data: np.ndarray, path: Path | None = None) -> LightCurve:
    data = np.asarray(data, dtype=float)
    if data.ndim != 2 or data.shape[1] < 3:
        raise ValueError("expected a two-dimensional array with at least three columns")
    return LightCurve(data[:, 0], data[:, 1], data[:, 2], path).sorted()
